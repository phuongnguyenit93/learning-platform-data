# Phân biệt ReadingConverter và WritingConverter

## 1. Vai trò của converter trong Spring Data Elasticsearch

Spring Data Elasticsearch phải chuyển đổi qua lại giữa hai dạng dữ liệu:

- **Domain object:** các lớp Java mà ứng dụng sử dụng, chẳng hạn `Customer`, `Address`, `ProductCode`.
- **Elasticsearch document:** dữ liệu JSON được lưu trong index và trả về trong `_source`.

`MappingElasticsearchConverter` đảm nhiệm việc ánh xạ object Java thành document khi ghi và đọc document thành object Java khi lấy dữ liệu. Trong quá trình đó, ứng dụng có thể đăng ký converter tùy chỉnh để xử lý những kiểu dữ liệu riêng của nghiệp vụ.

Hai annotation thường dùng là:

- `@WritingConverter`: đánh dấu converter được sử dụng khi ghi dữ liệu từ kiểu Java của ứng dụng sang kiểu dữ liệu mà Elasticsearch có thể lưu.
- `@ReadingConverter`: đánh dấu converter được sử dụng khi đọc dữ liệu từ biểu diễn của Elasticsearch trở lại kiểu Java của ứng dụng.

Tên gọi được xác định theo góc nhìn của thao tác lưu trữ. Writing là chiều ứng dụng ghi vào Elasticsearch; Reading là chiều ứng dụng đọc từ Elasticsearch.

## 2. Phân biệt chiều chuyển đổi

Hãy xét một thuộc tính `address` trong entity `Customer`. Trong Java, ứng dụng sử dụng một kiểu `Address` riêng. Khi lưu, ta muốn chuyển `Address` thành một `Map` để Elasticsearch lưu thành JSON object. Khi đọc, ta muốn chuyển `Map` nhận được từ document trở lại `Address`.

~~~text
                 GHI DOCUMENT
Java domain object                         Elasticsearch document
Address  ------------------------------->  Map / JSON object
                 @WritingConverter


                 ĐỌC DOCUMENT
Java domain object                         Elasticsearch document
Address  <-------------------------------  Map / JSON object
                 @ReadingConverter
~~~

| Annotation | Chiều chuyển đổi | Ví dụ kiểu nguồn và đích |
|---|---|---|
| `@WritingConverter` | Java domain type → kiểu lưu trữ | `Address` → `Map<String, Object>` |
| `@ReadingConverter` | Kiểu lưu trữ → Java domain type | `Map<String, Object>` → `Address` |

Hai converter thường tạo thành một cặp để dữ liệu có thể đi theo cả hai chiều. Tuy nhiên, không bắt buộc phải có đủ cả hai. Nếu ứng dụng chỉ ghi một kiểu dữ liệu mà không cần đọc nó thành domain object, có thể chỉ cần writing converter. Nếu ứng dụng chỉ cần chuyển dữ liệu trả về thành một kiểu Java riêng, reading converter có thể là đủ.

## 3. Ví dụ domain object cần chuyển đổi

Giả sử ứng dụng quản lý khách hàng. Một địa chỉ có hai thuộc tính là đường phố và thành phố:

~~~java
public record Address(String street, String city) {
}
~~~

Entity lưu khách hàng:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

@Document(indexName = "customers")
public class Customer {

    @Id
    private String id;

    private String name;

    @Field(type = FieldType.Object)
    private Address address;

    // Constructors, getters và setters
}
~~~

Ở tầng nghiệp vụ, code có thể tạo object:

~~~java
Address address = new Address(
    "2800 East Observatory Road",
    "Los Angeles"
);

Customer customer = new Customer();
customer.setId("c-100");
customer.setName("Alex");
customer.setAddress(address);
~~~

Ứng dụng muốn document trong Elasticsearch có cấu trúc JSON dễ đọc và truy vấn:

~~~json
{
  "id": "c-100",
  "name": "Alex",
  "address": {
    "street": "2800 East Observatory Road",
    "city": "Los Angeles"
  }
}
~~~

Để ánh xạ `Address` thành object JSON và đọc ngược lại, ta viết hai converter theo hai chiều.

## 4. WritingConverter: chuyển domain object sang dữ liệu lưu trữ

Writing converter nhận object Java và trả về kiểu mà tầng lưu trữ hiểu được. Trong ví dụ này, `Address` được chuyển thành `Map<String, Object>`.

~~~java
import java.util.LinkedHashMap;
import java.util.Map;

import org.springframework.core.convert.converter.Converter;
import org.springframework.data.convert.WritingConverter;

@WritingConverter
public class AddressToMapConverter
        implements Converter<Address, Map<String, Object>> {

    @Override
    public Map<String, Object> convert(Address source) {
        Map<String, Object> target = new LinkedHashMap<>();

        target.put("street", source.street());
        target.put("city", source.city());

        return target;
    }
}
~~~

Các điểm cần chú ý:

- `@WritingConverter` cho Spring Data biết converter này dành cho chiều ghi.
- Kiểu nguồn là `Address`, tức kiểu domain object của ứng dụng.
- Kiểu đích là `Map<String, Object>`, một biểu diễn có thể được chuyển thành JSON object.
- `LinkedHashMap` giúp thứ tự các phần tử trong map ổn định khi quan sát dữ liệu, dù thứ tự field JSON không nên được dùng làm quy tắc nghiệp vụ.
- Converter không tự gửi request đến Elasticsearch. Nó chỉ tạo ra giá trị đích để `MappingElasticsearchConverter` tiếp tục ghi vào document.

Khi ghi `Customer`, converter được áp dụng cho thuộc tính `address`. Giá trị `Address` trở thành map có hai key `street` và `city`, sau đó được biểu diễn thành object trong `_source`.

Luồng xử lý:

~~~text
Customer
   |
   v
MappingElasticsearchConverter
   |
   v
AddressToMapConverter
   |
   v
Map<String, Object>
   |
   v
JSON object trong Elasticsearch document
~~~

Nếu converter trả về một chuỗi thay vì map, Elasticsearch sẽ nhận một giá trị scalar. Vì vậy, kiểu đích của converter phải phù hợp với mapping và cấu trúc dữ liệu mà ứng dụng mong muốn.

## 5. ReadingConverter: chuyển dữ liệu lưu trữ về domain object

Reading converter thực hiện chiều ngược lại. Nó nhận giá trị mà Elasticsearch document cung cấp và tạo ra object Java mà ứng dụng sử dụng.

~~~java
import java.util.Map;

import org.springframework.core.convert.converter.Converter;
import org.springframework.data.convert.ReadingConverter;

@ReadingConverter
public class MapToAddressConverter
        implements Converter<Map<String, Object>, Address> {

    @Override
    public Address convert(Map<String, Object> source) {
        String street = (String) source.get("street");
        String city = (String) source.get("city");

        return new Address(street, city);
    }
}
~~~

Các điểm cần chú ý:

- `@ReadingConverter` đánh dấu chiều đọc.
- Kiểu nguồn là `Map<String, Object>`, biểu diễn object được đọc từ document.
- Kiểu đích là `Address`, kiểu domain object mà ứng dụng cần.
- Converter lấy các trường trong map và tạo một instance `Address`.

Luồng xử lý:

~~~text
Elasticsearch document
   |
   v
Map<String, Object>
   |
   v
MapToAddressConverter
   |
   v
MappingElasticsearchConverter
   |
   v
Customer có thuộc tính Address
~~~

Trong ví dụ tối giản, converter giả định `street` và `city` có mặt và có kiểu `String`. Với dữ liệu thực tế, cần quyết định cách xử lý khi field bị thiếu, giá trị null hoặc kiểu dữ liệu không đúng. Có thể kiểm tra đầu vào và ném exception có thông tin rõ ràng nếu document không hợp lệ.

Không nên âm thầm gán giá trị mặc định cho dữ liệu sai định dạng nếu điều đó làm thay đổi ý nghĩa nghiệp vụ.

## 6. Đăng ký converter bằng ElasticsearchCustomConversions

Viết các lớp converter là chưa đủ. Spring Data cần biết những converter nào được phép dùng trong quá trình ánh xạ. `ElasticsearchCustomConversions` là nơi đăng ký các quy tắc chuyển đổi tùy chỉnh.

Một cấu hình Java dựa trên `ElasticsearchConfiguration`:

~~~java
import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.elasticsearch.client.ClientConfiguration;
import org.springframework.data.elasticsearch.client.elc.ElasticsearchConfiguration;
import org.springframework.data.elasticsearch.core.convert.ElasticsearchCustomConversions;

@Configuration
public class ElasticsearchConfig extends ElasticsearchConfiguration {

    @Override
    public ClientConfiguration clientConfiguration() {
        return ClientConfiguration.builder()
            .connectedTo("localhost:9200")
            .build();
    }

    @Bean
    @Override
    public ElasticsearchCustomConversions elasticsearchCustomConversions() {
        return new ElasticsearchCustomConversions(
            List.of(
                new AddressToMapConverter(),
                new MapToAddressConverter()
            )
        );
    }
}
~~~

Trong cấu hình trên:

1. `ElasticsearchConfiguration` cung cấp cơ chế cấu hình client và các thành phần ánh xạ của Spring Data Elasticsearch.
2. `elasticsearchCustomConversions()` trả về danh sách converter tùy chỉnh.
3. `AddressToMapConverter` được đăng ký cho chiều ghi.
4. `MapToAddressConverter` được đăng ký cho chiều đọc.
5. `MappingElasticsearchConverter` sử dụng các converter đã đăng ký khi chuyển đổi entity và document.

Nếu dự án dùng Spring Boot auto-configuration, có thể khai báo bean `ElasticsearchCustomConversions` trong một lớp `@Configuration` riêng theo cách cấu hình của phiên bản đang dùng. Không cần tạo thêm một client chỉ để đăng ký converter.

Các converter được đăng ký dưới dạng instance. Spring Data không tự động quét toàn bộ classpath để lấy mọi lớp có triển khai `Converter`, vì tự động đăng ký có thể tạo ra những chuyển đổi ngoài ý muốn trong conversion service. Vì vậy, hãy đưa converter vào `ElasticsearchCustomConversions` hoặc cơ chế đăng ký tương ứng của dự án.

`CustomConversions` cũng có các converter mặc định cho một số kiểu dữ liệu phổ biến, chẳng hạn nhóm kiểu thời gian Java. Khi bổ sung converter riêng, hãy dùng `ElasticsearchCustomConversions` đúng cách để giữ hành vi mặc định mà Spring Data cung cấp.

## 7. Vì sao cần phân biệt chiều bằng annotation?

Spring Data có thể suy luận chiều chuyển đổi từ kiểu nguồn và kiểu đích. Nếu một converter chuyển từ domain type sang kiểu mà Elasticsearch xử lý được, hệ thống có thể nhận ra đó là converter ghi. Tương tự, converter từ kiểu lưu trữ sang domain type thường được nhận diện là converter đọc.

Tuy nhiên, có trường hợp cả hai đầu đều là kiểu dữ liệu đơn giản mà hệ thống có thể xử lý trực tiếp. Khi đó, chỉ nhìn vào source và target không đủ để biết converter dành cho chiều nào.

Ví dụ:

~~~java
Converter<String, Long>
~~~

`String` và `Long` đều là kiểu dữ liệu đơn giản. Nếu đăng ký converter này cho cả hai chiều, Spring Data có thể áp dụng chuyển đổi trong tình huống không mong muốn. Việc chuyển mọi chuỗi thành số khi ghi không nhất thiết là ý định của ứng dụng.

Có thể chỉ rõ chiều bằng annotation:

~~~java
import org.springframework.core.convert.converter.Converter;
import org.springframework.data.convert.ReadingConverter;

@ReadingConverter
public class StringToLongReadingConverter
        implements Converter<String, Long> {

    @Override
    public Long convert(String source) {
        return Long.valueOf(source);
    }
}
~~~

Converter này chỉ dành cho chiều đọc. Nếu cần chiều ghi ngược lại, hãy định nghĩa converter riêng và đánh dấu `@WritingConverter`:

~~~java
import org.springframework.core.convert.converter.Converter;
import org.springframework.data.convert.WritingConverter;

@WritingConverter
public class LongToStringWritingConverter
        implements Converter<Long, String> {

    @Override
    public String convert(Long source) {
        return source.toString();
    }
}
~~~

Cặp converter tách biệt giúp ý định rõ ràng và tránh việc một converter bị sử dụng nhầm trong cả hai chiều.

Với kiểu domain riêng như `Address`, hướng chuyển đổi thường dễ nhận biết hơn vì một đầu là domain type, đầu kia là kiểu lưu trữ. Dù vậy, gắn annotation `@ReadingConverter` hoặc `@WritingConverter` vẫn là cách thể hiện rõ ràng mục đích của converter.

## 8. So sánh với converter hai chiều và các annotation khác

Không nên nhầm `@ReadingConverter` và `@WritingConverter` với các annotation kiểm soát việc đọc/ghi thuộc tính trong entity.

| Thành phần | Ý nghĩa |
|---|---|
| `@ReadingConverter` | Đánh dấu một `Converter` dùng khi đọc dữ liệu từ Elasticsearch thành domain type |
| `@WritingConverter` | Đánh dấu một `Converter` dùng khi ghi domain type thành dạng lưu trữ |
| `@Transient` | Bỏ qua thuộc tính khi ghi và không khôi phục giá trị đó khi đọc entity |
| `@ReadOnlyProperty` | Không ghi giá trị thuộc tính, nhưng vẫn đọc giá trị từ document |
| `@WriteOnlyProperty` | Ghi thuộc tính vào Elasticsearch, nhưng không gán giá trị khi đọc entity |
| `@ValueConverter` | Chọn converter ở phạm vi một thuộc tính cụ thể thay vì đăng ký chuyển đổi chung cho mọi thuộc tính cùng kiểu |

`ReadingConverter` và `WritingConverter` điều khiển hướng của một quy tắc chuyển đổi kiểu. Chúng không quyết định một thuộc tính có được phép xuất hiện trong document hay không. Các annotation như `@Transient`, `@ReadOnlyProperty` và `@WriteOnlyProperty` mới kiểm soát việc đưa thuộc tính vào quá trình đọc/ghi entity.

Ngoài ra, một converter thông thường có thể được đăng ký dùng chung cho mọi thuộc tính cùng kiểu. Nếu chỉ một thuộc tính cần cách chuyển đổi đặc biệt, có thể cân nhắc cơ chế property-level converter như `@ValueConverter` được hỗ trợ trong phiên bản Spring Data Elasticsearch tương ứng.

## 9. Những trường hợp nên dùng converter tùy chỉnh

Converter hữu ích khi mô hình domain của ứng dụng khác với biểu diễn JSON mong muốn trong Elasticsearch.

| Trường hợp | Writing converter | Reading converter |
|---|---|---|
| Value object `Address` thành JSON object | `Address` → `Map<String, Object>` | `Map<String, Object>` → `Address` |
| Mã sản phẩm dạng class riêng | `ProductCode` → `String` | `String` → `ProductCode` |
| Kiểu tiền tệ tùy chỉnh | `Money` → `Map` chứa amount và currency | `Map` → `Money` |
| Kiểu trạng thái nội bộ | Chuyển enum/domain state thành chuỗi chuẩn | Chuỗi lưu trữ thành enum/domain state |

Ví dụ với `ProductCode`:

~~~java
public record ProductCode(String value) {
}
~~~

Writing converter:

~~~java
import org.springframework.core.convert.converter.Converter;
import org.springframework.data.convert.WritingConverter;

@WritingConverter
public class ProductCodeToStringConverter
        implements Converter<ProductCode, String> {

    @Override
    public String convert(ProductCode source) {
        return source.value();
    }
}
~~~

Reading converter:

~~~java
import org.springframework.core.convert.converter.Converter;
import org.springframework.data.convert.ReadingConverter;

@ReadingConverter
public class StringToProductCodeConverter
        implements Converter<String, ProductCode> {

    @Override
    public ProductCode convert(String source) {
        return new ProductCode(source);
    }
}
~~~

Document lưu `ProductCode` dưới dạng chuỗi:

~~~json
{
  "productCode": "SKU-2026-001"
}
~~~

Cách này giúp domain model giữ kiểu `ProductCode` để tránh truyền chuỗi tùy ý trong nghiệp vụ, trong khi Elasticsearch vẫn lưu một giá trị keyword đơn giản.

Với dữ liệu cần tìm kiếm hoặc thống kê theo nhiều thuộc tính, hãy cân nhắc chuyển thành `Map`/object thay vì gom toàn bộ thành một chuỗi. Ví dụ, nếu cần lọc theo amount và currency riêng biệt, lưu hai field riêng sẽ phù hợp hơn một chuỗi `"USD 12.50"`.

## 10. Các lưu ý khi triển khai converter

**Đăng ký đủ chiều cần dùng.** Writing converter không tự động tạo ra reading converter ngược lại. Nếu ứng dụng ghi rồi đọc entity, hãy đăng ký cả hai chiều khi cần.

**Kiểu đích phải phù hợp với mapping.** Nếu converter trả về `Map`, field trong Elasticsearch phải có mapping object phù hợp. Nếu converter trả về `String`, hãy chọn kiểu field tương ứng, ví dụ `keyword` hoặc `text` tùy nhu cầu truy vấn.

**Xử lý dữ liệu thiếu và null.** Document cũ có thể không chứa field mới hoặc có cấu trúc khác. Reading converter cần xác định cách xử lý dữ liệu thiếu, null và sai kiểu.

**Tránh chuyển đổi mất thông tin.** Nếu writing converter bỏ đi một thuộc tính, reading converter không thể khôi phục giá trị đó từ document. Hãy quyết định rõ dữ liệu nào được lưu và dữ liệu nào chỉ tồn tại trong domain object.

**Tránh converter quá tổng quát.** Converter giữa hai kiểu đơn giản có thể ảnh hưởng nhiều thuộc tính trong hệ thống. Dùng kiểu value object riêng và annotation định hướng để giới hạn phạm vi và tránh chuyển đổi ngoài ý muốn.

**Không đăng ký converter trùng lặp hoặc mâu thuẫn.** Nhiều converter cùng source/target nhưng có quy tắc khác nhau có thể làm việc lựa chọn converter khó đoán. Mỗi cặp kiểu nên có một ý nghĩa chuyển đổi rõ ràng.

**Giữ converter tập trung vào chuyển đổi.** Converter nên chuyển dữ liệu và kiểm tra định dạng cần thiết. Không đặt truy vấn database, gọi REST API hoặc logic nghiệp vụ phụ thuộc trạng thái bên ngoài vào converter, vì việc ánh xạ có thể diễn ra trong nhiều luồng đọc/ghi.

**Chú ý dữ liệu đã tồn tại.** Khi thay đổi cấu trúc JSON mà converter tạo ra, document cũ có thể không còn tương thích với reading converter mới. Có thể cần hỗ trợ cả định dạng cũ trong giai đoạn chuyển đổi hoặc reindex dữ liệu.

## 11. Luồng ghi và đọc hoàn chỉnh

Khi ứng dụng lưu khách hàng:

~~~text
Customer
  |
  | address: Address
  v
MappingElasticsearchConverter
  |
  v
@WritingConverter: AddressToMapConverter
  |
  v
Map<String, Object>
  |
  v
JSON document
  |
  v
Elasticsearch index
~~~

Khi ứng dụng lấy khách hàng:

~~~text
Elasticsearch index
  |
  v
JSON document / _source
  |
  v
Map<String, Object>
  |
  v
@ReadingConverter: MapToAddressConverter
  |
  v
Address
  |
  v
Customer
~~~

Cả hai chiều cùng được quản lý bởi cơ chế mapping của Spring Data Elasticsearch. Service và repository làm việc với entity Java; ứng dụng không cần tự gọi converter ở mỗi thao tác lưu hoặc tìm kiếm.

## 12. Quy trình xây dựng và đăng ký converter

Có thể triển khai theo trình tự sau:

1. Xác định kiểu domain nào cần biểu diễn khác đi trong Elasticsearch.
2. Chọn kiểu dữ liệu lưu trữ phù hợp: `String`, `Map`, số hoặc kiểu khác.
3. Viết converter chiều ghi từ domain type sang kiểu lưu trữ và gắn `@WritingConverter`.
4. Viết converter chiều đọc từ kiểu lưu trữ về domain type và gắn `@ReadingConverter` nếu ứng dụng cần khôi phục entity.
5. Đăng ký các instance trong `ElasticsearchCustomConversions`.
6. Đảm bảo bean custom conversions được dùng bởi cấu hình `MappingElasticsearchConverter` của ứng dụng.
7. Kiểm tra document JSON được ghi ra có đúng cấu trúc và mapping hay không.
8. Kiểm tra dữ liệu đọc vào tạo được domain object hợp lệ, kể cả khi field thiếu hoặc null theo những trường hợp mà nghiệp vụ cho phép.

## Kết luận

`@WritingConverter` và `@ReadingConverter` phân biệt hai hướng chuyển đổi trong quá trình ánh xạ entity Java với Elasticsearch document. Writing converter biến kiểu domain thành biểu diễn có thể lưu trữ; reading converter khôi phục biểu diễn lưu trữ thành kiểu domain.

Các converter được đăng ký tập trung thông qua `ElasticsearchCustomConversions` để `MappingElasticsearchConverter` sử dụng tự động. Xác định đúng source, target, chiều chuyển đổi và mapping của field giúp dữ liệu được ghi ra nhất quán, đọc lại đúng kiểu và giữ domain model độc lập với cấu trúc JSON lưu trong Elasticsearch.

## Tài liệu tham khảo

- [Spring Data Elasticsearch — Object Mapping và Custom Conversions](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/object-mapping.html)
- [Spring Data Commons — Custom Conversions](https://docs.spring.io/spring-data/elasticsearch/reference/data-commons/custom-conversions.html)
