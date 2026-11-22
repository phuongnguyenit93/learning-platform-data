# Đăng ký Jackson Module, serializer và deserializer tùy chỉnh trong Spring Data REST

## Mục tiêu

Sau bài này, bạn có thể:

- Giải thích Jackson Module dùng để làm gì và khi nào nên tạo module riêng.
- Viết serializer để chuyển một kiểu Java thành JSON theo contract của API.
- Viết deserializer để chuyển JSON request thành kiểu Java tương ứng.
- Đăng ký cả hai thông qua ObjectMapper mà Spring Data REST sử dụng.
- Kiểm tra kết quả trên endpoint repository, đồng thời tránh làm mất cấu hình Jackson và HAL có sẵn.

## 1. Jackson tham gia vào Spring Data REST như thế nào?

Spring Data REST xuất bản repository thành HTTP resources. Khi client gửi request hoặc nhận response, framework cần chuyển đổi giữa Java object và JSON:

- **Serialization:** Java object → JSON response. Jackson gọi serializer để ghi giá trị ra JSON.
- **Deserialization:** JSON request → Java object. Jackson gọi deserializer để đọc dữ liệu và tạo giá trị Java.

Ví dụ một entity có thuộc tính kiểu Money. Contract mặc định có thể biểu diễn Money bằng object gồm amount và currency. Nếu API cần một định dạng riêng, chẳng hạn luôn ghi amount dưới dạng số và currency dưới dạng mã tiền tệ, ta có thể định nghĩa serializer/deserializer cho Money.

Jackson Module là một đơn vị đăng ký các thành phần mở rộng cho Jackson, chẳng hạn serializer, deserializer, key serializer, mix-in annotation hoặc các cấu hình kiểu dữ liệu. SimpleModule là lựa chọn thuận tiện khi cần đăng ký một vài serializer và deserializer theo Java type.

Luồng xử lý tổng quát:

1. Client gửi JSON đến endpoint Spring Data REST.
2. Spring Data REST sử dụng ObjectMapper được cấu hình cho REST để deserialize request body.
3. Jackson tìm deserializer phù hợp với kiểu thuộc tính và chuyển JSON thành Java value.
4. Repository xử lý entity theo nghiệp vụ.
5. Khi tạo response, Jackson tìm serializer phù hợp và ghi Java value thành JSON.
6. Spring Data REST bổ sung cấu trúc resource và liên kết HAL theo cấu hình của ứng dụng.

Serializer/deserializer tùy chỉnh chỉ quyết định cách biểu diễn kiểu dữ liệu mà chúng được đăng ký. Chúng không thay thế repository, không tự lưu entity và không thay đổi quy tắc HTTP của Spring Data REST.

## 2. Chọn phạm vi tùy chỉnh phù hợp

Có hai cách phổ biến để gắn serializer/deserializer:

| Cách | Phạm vi | Khi nên dùng |
|---|---|---|
| Jackson Module đăng ký theo Java type | Mọi thuộc tính có kiểu được đăng ký trong ObjectMapper tương ứng | Một kiểu dữ liệu cần có cùng JSON contract ở nhiều entity hoặc endpoint |
| @JsonSerialize và @JsonDeserialize | Một class hoặc property cụ thể có annotation | Chỉ một thuộc tính cần cách biểu diễn đặc biệt |

Ví dụ, nếu mọi thuộc tính Money trong REST API đều cần cùng định dạng thì đăng ký qua module giúp tập trung cấu hình. Nếu chỉ một trường cần định dạng khác, annotation tại property thường thể hiện ý định rõ hơn.

Hãy chú ý phạm vi của ObjectMapper. Module đăng ký vào mapper của Spring Data REST sẽ tác động đến các endpoint dùng mapper đó. Nếu ứng dụng có nhiều ObjectMapper cho các mục đích khác nhau, đừng giả định module đã tự động xuất hiện trong tất cả mapper.

## 3. Xây dựng kiểu dữ liệu ví dụ

Giả sử API quản lý Person và entity có thuộc tính salary kiểu Money. Ta muốn JSON của Money có dạng:

    {
      "amount": 1250.50,
      "currency": "USD"
    }

Kiểu Java minh họa:

    import java.math.BigDecimal;

    public class Money {
        private final BigDecimal amount;
        private final String currency;

        public Money(BigDecimal amount, String currency) {
            if (amount == null) {
                throw new IllegalArgumentException("amount is required");
            }
            if (currency == null || currency.isBlank()) {
                throw new IllegalArgumentException("currency is required");
            }
            this.amount = amount;
            this.currency = currency;
        }

        public BigDecimal getAmount() {
            return amount;
        }

        public String getCurrency() {
            return currency;
        }
    }

Ví dụ này giữ amount dưới dạng BigDecimal để tránh sai số nhị phân thường gặp khi dùng double cho giá trị tiền. Trong ứng dụng thực tế, có thể thay currency bằng java.util.Currency hoặc một enum được kiểm tra theo quy tắc nghiệp vụ.

## 4. Viết serializer

Serializer kế thừa StdSerializer và cài đặt phương thức serialize. Phương thức nhận Java value, JsonGenerator và SerializerProvider.

    import java.io.IOException;

    import com.fasterxml.jackson.core.JsonGenerator;
    import com.fasterxml.jackson.databind.SerializerProvider;
    import com.fasterxml.jackson.databind.ser.std.StdSerializer;

    public final class MoneySerializer extends StdSerializer<Money> {

        public MoneySerializer() {
            super(Money.class);
        }

        @Override
        public void serialize(
                Money value,
                JsonGenerator generator,
                SerializerProvider provider) throws IOException {

            generator.writeStartObject();
            generator.writeNumberField("amount", value.getAmount());
            generator.writeStringField("currency", value.getCurrency());
            generator.writeEndObject();
        }
    }

Các lệnh quan trọng:

- writeStartObject() bắt đầu một JSON object.
- writeNumberField() ghi trường số.
- writeStringField() ghi trường chuỗi.
- writeEndObject() kết thúc object.

Với Money có amount là 1250.50 và currency là USD, serializer tạo ra JSON object gồm hai trường tương ứng. Thứ tự trường trong JSON không nên được dùng làm điều kiện nghiệp vụ ở phía client; contract nằm ở tên và kiểu dữ liệu của trường.

Serializer cần xử lý đúng giá trị null theo contract. Thông thường Jackson có cơ chế null serializer riêng; không nên tự ghi chuỗi "null" nếu API cần JSON null thực sự.

## 5. Viết deserializer

Deserializer kế thừa StdDeserializer và cài đặt phương thức deserialize. Phương thức đọc token JSON, kiểm tra cấu trúc rồi tạo đối tượng Java.

    import java.io.IOException;

    import com.fasterxml.jackson.core.JsonParser;
    import com.fasterxml.jackson.databind.DeserializationContext;
    import com.fasterxml.jackson.databind.JsonMappingException;
    import com.fasterxml.jackson.databind.JsonNode;
    import com.fasterxml.jackson.databind.deser.std.StdDeserializer;

    public final class MoneyDeserializer extends StdDeserializer<Money> {

        public MoneyDeserializer() {
            super(Money.class);
        }

        @Override
        public Money deserialize(
                JsonParser parser,
                DeserializationContext context) throws IOException {

            JsonNode node = parser.getCodec().readTree(parser);

            if (node == null || !node.isObject()) {
                throw JsonMappingException.from(
                    parser, "Money must be a JSON object");
            }

            JsonNode amount = node.get("amount");
            JsonNode currency = node.get("currency");

            if (amount == null || !amount.isNumber()
                    || currency == null || !currency.isTextual()) {
                throw JsonMappingException.from(
                    parser,
                    "Money requires numeric amount and string currency");
            }

            try {
                return new Money(
                    amount.decimalValue(),
                    currency.asText());
            } catch (IllegalArgumentException ex) {
                throw JsonMappingException.from(
                    parser, "Invalid Money value", ex);
            }
        }
    }

Cách xử lý trên có các bước:

1. Dùng parser.getCodec().readTree(parser) để đọc JSON thành cây JsonNode.
2. Xác nhận node là object.
3. Lấy amount và currency bằng tên trường.
4. Kiểm tra amount là số và currency là chuỗi.
5. Tạo Money từ BigDecimal và currency.
6. Báo lỗi mapping nếu JSON sai contract hoặc giá trị không hợp lệ.

Không nên âm thầm thay dữ liệu sai bằng amount bằng 0 hoặc currency mặc định. Điều đó biến request không hợp lệ thành dữ liệu có vẻ hợp lệ và có thể gây lỗi nghiệp vụ khó truy vết. Hãy trả lỗi deserialization rõ ràng để client sửa request.

Nếu contract cần cho phép trường tùy chọn, hãy định nghĩa rõ hành vi khi trường vắng mặt, khi giá trị là null và khi giá trị có kiểu sai. Không coi ba trường hợp này là một.

## 6. Đóng gói serializer và deserializer trong SimpleModule

SimpleModule giúp đăng ký cả hai thành phần theo cùng Java type:

    import com.fasterxml.jackson.databind.module.SimpleModule;

    public final class MoneyModule extends SimpleModule {

        public MoneyModule() {
            super("money-module");
            addSerializer(Money.class, new MoneySerializer());
            addDeserializer(Money.class, new MoneyDeserializer());
        }
    }

Sau khi tạo module, ta cần đăng ký nó vào ObjectMapper mà Spring Data REST sử dụng.

## 7. Đăng ký module với Spring Data REST

Cách rõ ràng để tùy chỉnh ObjectMapper của Spring Data REST là triển khai RepositoryRestConfigurer và override configureJacksonObjectMapper.

    import com.fasterxml.jackson.databind.ObjectMapper;
    import org.springframework.context.annotation.Configuration;
    import org.springframework.data.rest.webmvc.config.RepositoryRestConfigurer;

    @Configuration
    public class RepositoryRestJacksonConfiguration
            implements RepositoryRestConfigurer {

        @Override
        public void configureJacksonObjectMapper(
                ObjectMapper objectMapper) {

            objectMapper.registerModule(new MoneyModule());
        }
    }

Spring Data REST gọi callback này khi cấu hình mapper phục vụ REST resources. Ta đăng ký module trên mapper được truyền vào, nhờ đó custom serializer/deserializer tham gia vào quá trình chuyển đổi request và response của Spring Data REST.

Các nguyên tắc cần giữ:

- Đăng ký module trên ObjectMapper được framework cung cấp.
- Không tạo một ObjectMapper mới bằng new ObjectMapper() rồi kỳ vọng Spring Data REST tự dùng mapper đó.
- Không thay thế mapper đang có nếu chỉ cần bổ sung một kiểu dữ liệu.
- Không xóa các module hoặc cấu hình Jackson đã được Spring Boot và Spring Data REST đăng ký.
- Đặt module trong configuration được Spring quản lý để callback được phát hiện.
- Nếu có nhiều RepositoryRestConfigurer, hãy tổ chức cấu hình rõ ràng và kiểm tra thứ tự khi một cấu hình phụ thuộc vào cấu hình khác.

Việc dùng một SimpleModule riêng giúp nhóm serializer/deserializer liên quan, dễ đọc và dễ kiểm thử. Khi có nhiều kiểu dữ liệu, có thể thêm nhiều cặp addSerializer/addDeserializer vào module hoặc tách module theo miền nghiệp vụ.

## 8. Khi nào dùng annotation thay cho module?

Nếu chỉ một property cần định dạng đặc biệt, có thể gắn annotation trực tiếp:

    import com.fasterxml.jackson.databind.annotation.JsonDeserialize;
    import com.fasterxml.jackson.databind.annotation.JsonSerialize;

    public class Person {

        @JsonSerialize(using = MoneySerializer.class)
        @JsonDeserialize(using = MoneyDeserializer.class)
        private Money salary;

        public Money getSalary() {
            return salary;
        }

        public void setSalary(Money salary) {
            this.salary = salary;
        }
    }

Cách này thể hiện trực tiếp serializer/deserializer được dùng cho property salary. Hãy chọn một cách đăng ký phù hợp với contract để tránh cấu hình lặp lại khó hiểu. Nếu vừa đăng ký module vừa đặt annotation cho cùng property, hãy kiểm tra mapper thực tế và kết quả test thay vì giả định cấu hình nào sẽ được áp dụng.

## 9. Kiểm tra serializer và deserializer

Nên kiểm tra hai lớp riêng biệt trước, sau đó kiểm tra tích hợp với endpoint Spring Data REST.

### Kiểm tra serialization

Tạo một Money có amount 1250.50 và currency USD, serialize rồi xác nhận JSON có:
- amount là JSON number.
- currency là JSON string.
- Tên trường đúng contract.
- Không có trường nội bộ không được công bố.

### Kiểm tra deserialization

Đưa JSON object có amount và currency vào mapper, sau đó xác nhận:
- Kết quả là một Money.
- BigDecimal giữ đúng giá trị và scale cần thiết.
- Currency giữ đúng mã.
- JSON thiếu trường hoặc sai kiểu bị từ chối.
- Giá trị không hợp lệ tạo mapping error dễ hiểu.

### Kiểm tra endpoint Spring Data REST

Dùng integration test hoặc MockMvc để kiểm tra endpoint repository thực tế:

- GET một item hoặc collection có thuộc tính Money: response dùng serializer tùy chỉnh.
- POST một item có Money: request body được deserializer tùy chỉnh xử lý.
- PUT/PATCH item: kiểm tra deserializer trên các trường được gửi.
- Kiểm tra các liên kết _links và metadata HAL vẫn xuất hiện bình thường.
- Kiểm tra status code và response body theo contract của endpoint.

Ví dụ request tạo item:

    POST /people
    Content-Type: application/json
    Accept: application/hal+json

    {
      "firstName": "An",
      "salary": {
        "amount": 1250.50,
        "currency": "USD"
      }
    }

Response minh họa có thể chứa:

    {
      "firstName": "An",
      "salary": {
        "amount": 1250.50,
        "currency": "USD"
      },
      "_links": {
        "self": {
          "href": "http://localhost:8080/people/42"
        }
      }
    }

Đây là cấu trúc minh họa; tên collection, thuộc tính, ID và các link thực tế phụ thuộc repository và cấu hình của ứng dụng.

## 10. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Serializer không được gọi | Module chưa đăng ký vào mapper mà endpoint đang dùng; Java type không khớp | Kiểm tra callback RepositoryRestConfigurer và kiểu thuộc tính thực tế |
| Deserializer không được gọi | Request không chứa property đó, endpoint dùng kiểu khác hoặc annotation/configuration khác được áp dụng | Kiểm tra request body, entity mapping và mapper |
| GET đúng nhưng POST lỗi | Serializer hoạt động nhưng deserializer chưa xử lý đúng JSON đầu vào | Kiểm tra riêng hai chiều chuyển đổi |
| JSON sai kiểu vẫn được chấp nhận | Deserializer thiếu kiểm tra node hoặc tự dùng giá trị mặc định | Validate object, trường, kiểu và quy tắc miền |
| Các API khác bị thay đổi định dạng | Module được đăng ký vào ObjectMapper dùng chung cho nhiều API | Xác định mapper và phạm vi đăng ký; giới hạn custom type |
| HAL links hoặc metadata biến mất | Thay mapper hoặc ghi đè cấu hình REST hiện có | Bổ sung module vào mapper được truyền vào; không thay mapper toàn bộ |
| Một property có kết quả khác module mong đợi | Property có annotation tùy chỉnh hoặc có cấu hình Jackson khác | Kiểm tra annotation và mapper hiệu lực qua integration test |

## 11. Checklist trước khi hoàn tất

- [ ] Xác định đúng Java type cần tùy chỉnh.
- [ ] Định nghĩa JSON contract với tên trường và kiểu dữ liệu rõ ràng.
- [ ] Serializer ghi đúng kiểu JSON, không biến số thành chuỗi ngoài ý muốn.
- [ ] Deserializer kiểm tra cấu trúc và kiểu trường trước khi tạo object.
- [ ] Lỗi dữ liệu không hợp lệ được báo rõ, không tự thay bằng giá trị mặc định.
- [ ] Đăng ký SimpleModule vào ObjectMapper của Spring Data REST qua RepositoryRestConfigurer.
- [ ] Không tạo mapper mới hoặc xóa module HAL có sẵn.
- [ ] Kiểm tra serialization, deserialization và endpoint thực tế.
- [ ] Xác nhận các link HAL và những thuộc tính khác vẫn hoạt động.
- [ ] Kiểm tra các client hiện tại nếu JSON contract đã thay đổi.

## Kết luận

Jackson Module gom các thành phần mở rộng của Jackson thành một đơn vị có thể đăng ký. Serializer định nghĩa cách Java value được ghi thành JSON; deserializer định nghĩa cách JSON được chuyển thành Java value. Với Spring Data REST, hãy đăng ký module trên ObjectMapper được truyền vào callback configureJacksonObjectMapper của RepositoryRestConfigurer. Cách này giữ nguyên mapper và cấu hình REST hiện có, đồng thời cho phép kiểm soát JSON contract của các kiểu dữ liệu tùy chỉnh.

## Tài liệu tham khảo

- Spring Data REST — Customizing Spring Data REST: https://docs.spring.io/spring-data/rest/reference/customizing-sdr.html
- Spring Data REST — Repository configuration: https://docs.spring.io/spring-data/rest/reference/
- Jackson Databind — SimpleModule API: https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-databind/latest/com/fasterxml/jackson/databind/module/SimpleModule.html
- Jackson Databind — StdSerializer API: https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-databind/latest/com/fasterxml/jackson/databind/ser/std/StdSerializer.html
- Jackson Databind — StdDeserializer API: https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-databind/latest/com/fasterxml/jackson/databind/deser/std/StdDeserializer.html
