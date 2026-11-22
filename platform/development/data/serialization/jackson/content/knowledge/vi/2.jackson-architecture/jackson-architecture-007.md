# Phân biệt cấu hình đọc, cấu hình ghi và cấu hình ánh xạ

Trong Jackson, đọc JSON, ghi JSON và ánh xạ giữa JSON với thuộc tính Java là ba nhóm trách nhiệm có liên quan nhưng không đồng nhất. Phân biệt được chúng giúp đặt mỗi tùy chọn đúng nơi, tránh cấu hình toàn cục quá rộng và dễ giải thích vì sao cùng một ObjectMapper có thể đọc dữ liệu theo một quy tắc nhưng ghi dữ liệu theo quy tắc khác.

Ví dụ, khi nhận JSON từ một API, ứng dụng có thể muốn bỏ qua trường lạ để tương thích với phiên bản API mới hơn. Khi gửi JSON đi, ứng dụng lại muốn định dạng dễ đọc hoặc bỏ các thuộc tính có giá trị null. Trong khi đó, quy tắc đổi tên fullName thành full_name cần được dùng nhất quán khi cả đọc lẫn ghi. Ba nhu cầu này thuộc ba nhóm cấu hình khác nhau.

## 1. Nhìn tổng thể ba nhóm cấu hình

| Nhóm | Chiều xử lý chính | Câu hỏi mà cấu hình trả lời | API thường gặp |
|---|---|---|---|
| Cấu hình đọc (deserialization) | JSON → đối tượng Java | Jackson xử lý dữ liệu đầu vào và tạo đối tượng như thế nào? | DeserializationFeature, ObjectReader, DeserializationConfig |
| Cấu hình ghi (serialization) | Đối tượng Java → JSON | Jackson biểu diễn đối tượng đầu ra thành JSON như thế nào? | SerializationFeature, ObjectWriter, SerializationConfig |
| Cấu hình ánh xạ (mapping) | Quy tắc liên kết JSON và Java | Thuộc tính nào tương ứng với thuộc tính nào, được phát hiện và diễn giải ra sao? | MapperFeature, annotation, naming strategy, visibility, module |

Có thể hình dung luồng xử lý như sau:

~~~text
                         CẤU HÌNH ÁNH XẠ
              tên thuộc tính, annotation, visibility,
              kiểu dữ liệu, constructor, serializer...
                              │
                              ▼
JSON đầu vào ──► Parser ──► Deserializer ──► Đối tượng Java
                  ▲              ▲
                  │              │
          Cấu hình cú pháp   Cấu hình đọc
          đầu vào JSON      (DeserializationFeature)

Đối tượng Java ──► Serializer ──► Generator ──► JSON đầu ra
                       ▲              ▲
                       │              │
                 Cấu hình ghi   Cấu hình cú pháp
                 (SerializationFeature) đầu ra JSON
~~~

Sơ đồ cho thấy cấu hình ánh xạ tham gia vào quá trình Jackson xác định cách liên kết dữ liệu với mô hình Java. Cấu hình đọc và ghi điều khiển hành vi của từng chiều xử lý. Parser và generator còn có các tùy chọn cấp thấp để kiểm soát cú pháp JSON.

## 2. Cấu hình đọc: JSON thành đối tượng Java

Cấu hình đọc quyết định Jackson phản ứng thế nào khi chuyển JSON thành đối tượng Java. Nhóm tùy chọn thường dùng nằm trong DeserializationFeature.

Một số ví dụ:

| Tùy chọn | Tác dụng |
|---|---|
| FAIL_ON_UNKNOWN_PROPERTIES | Báo lỗi khi JSON có thuộc tính không tìm thấy trong lớp Java. |
| FAIL_ON_NULL_FOR_PRIMITIVES | Báo lỗi khi JSON truyền null cho kiểu nguyên thủy như int hoặc boolean. |
| ACCEPT_SINGLE_VALUE_AS_ARRAY | Cho phép một giá trị đơn được đọc thành mảng hoặc collection có một phần tử. |
| UNWRAP_SINGLE_VALUE_ARRAYS | Cho phép đọc mảng một phần tử thành một giá trị đơn trong các trường hợp phù hợp. |
| READ_ENUMS_USING_TO_STRING | Dùng toString() của enum khi chuyển giá trị JSON thành enum. |

Ví dụ, lớp Java có hai thuộc tính name và age, nhưng JSON nhận được có thêm trường source:

~~~java
public class Customer {
    private String name;
    private int age;

    public Customer() {
    }

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }

    public int getAge() {
        return age;
    }

    public void setAge(int age) {
        this.age = age;
    }
}
~~~

~~~json
{
  "name": "Lan",
  "age": 25,
  "source": "mobile-app"
}
~~~

Theo mặc định, FAIL_ON_UNKNOWN_PROPERTIES được bật. Vì Customer không có thuộc tính source, thao tác đọc có thể ném UnrecognizedPropertyException. Nếu ứng dụng muốn chấp nhận trường bổ sung từ API, có thể tắt tùy chọn này:

~~~java
ObjectMapper mapper = new ObjectMapper();
mapper.disable(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES);

Customer customer = mapper.readValue(json, Customer.class);
~~~

Đây là cấu hình đọc vì nó chỉ thay đổi cách Jackson xử lý dữ liệu đầu vào. Nó không quyết định JSON đầu ra có thụt lề hay không, cũng không đổi tên thuộc tính Java.

### Dùng ObjectReader cho một lần đọc cụ thể

Nếu chỉ một luồng nhập dữ liệu cần bỏ qua thuộc tính lạ, còn các luồng khác phải nghiêm ngặt, không nên thay đổi cấu hình chung của mapper cho từng yêu cầu. Có thể tạo ObjectReader với cấu hình riêng:

~~~java
ObjectMapper mapper = new ObjectMapper();

ObjectReader strictReader = mapper.readerFor(Customer.class)
    .with(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES);

ObjectReader tolerantReader = mapper.readerFor(Customer.class)
    .without(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES);

Customer strictCustomer = strictReader.readValue(json);
Customer tolerantCustomer = tolerantReader.readValue(json);
~~~

ObjectReader là đối tượng đọc bất biến. Cấu hình được gắn vào reader áp dụng cho những lần đọc qua reader đó, không làm thay đổi cấu hình gốc của ObjectMapper. Đây là cách phù hợp khi nhiều API hoặc nhiều nguồn dữ liệu có yêu cầu đầu vào khác nhau.

## 3. Cấu hình ghi: đối tượng Java thành JSON

Cấu hình ghi quyết định cách Jackson chuyển đối tượng Java thành JSON. Nhóm tùy chọn thường dùng nằm trong SerializationFeature.

Một số ví dụ:

| Tùy chọn | Tác dụng |
|---|---|
| INDENT_OUTPUT | Thêm khoảng trắng và xuống dòng để JSON dễ đọc. |
| FAIL_ON_EMPTY_BEANS | Báo lỗi khi Jackson không tìm thấy thuộc tính có thể ghi trên một bean. |
| WRAP_ROOT_VALUE | Bọc giá trị gốc trong một thuộc tính mang tên root khi cấu hình tên root phù hợp. |
| WRITE_ENUMS_USING_TO_STRING | Dùng toString() của enum khi ghi enum thành JSON. |
| WRITE_DATES_AS_TIMESTAMPS | Điều khiển việc ghi kiểu ngày giờ dưới dạng timestamp trong các trường hợp serializer tương ứng hỗ trợ. |

Ví dụ bật định dạng đẹp:

~~~java
ObjectMapper mapper = new ObjectMapper();
mapper.enable(SerializationFeature.INDENT_OUTPUT);

String json = mapper.writeValueAsString(customer);
~~~

Kết quả có thể được trình bày thành nhiều dòng và có thụt lề. Nếu tắt INDENT_OUTPUT, Jackson vẫn ghi cùng dữ liệu nhưng dùng dạng JSON gọn hơn. Nội dung thuộc tính không tự thay đổi chỉ vì bật hoặc tắt thụt lề.

Một ví dụ khác là bỏ các thuộc tính null khi ghi:

~~~java
import com.fasterxml.jackson.annotation.JsonInclude;

ObjectMapper mapper = new ObjectMapper();
mapper.setSerializationInclusion(JsonInclude.Include.NON_NULL);
~~~

Thiết lập này ảnh hưởng đến JSON đầu ra: thuộc tính có giá trị null được bỏ qua. Nó không có nghĩa Jackson sẽ bỏ qua trường null khi đọc JSON. Muốn kiểm soát hành vi lúc đọc, cần chọn tùy chọn đọc hoặc quy tắc ánh xạ phù hợp.

### Dùng ObjectWriter cho một lần ghi cụ thể

Có thể tạo writer riêng cho từng định dạng đầu ra:

~~~java
ObjectMapper mapper = new ObjectMapper();

ObjectWriter prettyWriter = mapper.writerFor(Customer.class)
    .with(SerializationFeature.INDENT_OUTPUT);

ObjectWriter compactWriter = mapper.writerFor(Customer.class)
    .without(SerializationFeature.INDENT_OUTPUT);

String prettyJson = prettyWriter.writeValueAsString(customer);
String compactJson = compactWriter.writeValueAsString(customer);
~~~

ObjectWriter cũng bất biến và có thể tái sử dụng. Ví dụ, log nội bộ có thể dùng writer dễ đọc, trong khi phản hồi API dùng writer gọn. Cả hai vẫn dựa trên cùng mô hình Java và quy tắc ánh xạ của mapper.

## 4. Cấu hình ánh xạ: liên kết thuộc tính JSON với mô hình Java

Cấu hình ánh xạ quyết định Jackson nhận diện thuộc tính Java như thế nào và liên kết chúng với tên, kiểu và cấu trúc dữ liệu trong JSON ra sao. Đây là lớp quy tắc nằm bên dưới cả quá trình đọc và ghi.

Các nội dung thường thuộc nhóm này gồm:

- **Phát hiện thuộc tính:** Jackson có nhận diện field, getter, setter hoặc constructor hay không.
- **Tên thuộc tính:** tên JSON tương ứng với tên thuộc tính Java, có dùng quy tắc đổi tên chung hay không.
- **Annotation:** cách diễn giải @JsonProperty, @JsonAlias, @JsonIgnore, @JsonCreator, @JsonFormat và các annotation Jackson khác.
- **Visibility:** field hoặc accessor nào được phép tham gia quá trình ánh xạ.
- **Kiểu dữ liệu và bộ chuyển đổi:** serializer, deserializer, module hoặc quy tắc chuyển đổi tùy chỉnh.
- **Mix-in:** bổ sung metadata Jackson cho một lớp mà không phải sửa mã nguồn của lớp đó.

MapperFeature chứa nhiều tùy chọn ảnh hưởng đến cách Jackson khám phá và diễn giải mô hình. Ví dụ:

| Tùy chọn | Ý nghĩa |
|---|---|
| USE_ANNOTATIONS | Cho phép Jackson sử dụng annotation để xác định quy tắc ánh xạ. |
| AUTO_DETECT_FIELDS | Điều khiển việc tự động phát hiện field. |
| AUTO_DETECT_GETTERS | Điều khiển việc tự động phát hiện getter. |
| AUTO_DETECT_SETTERS | Điều khiển việc tự động phát hiện setter. |
| ACCEPT_CASE_INSENSITIVE_PROPERTIES | Cho phép đối chiếu tên thuộc tính không phân biệt chữ hoa, chữ thường khi đọc thuộc tính. |

### Ví dụ đổi tên thuộc tính

Java thường dùng camelCase, trong khi một API có thể dùng snake_case. Có thể khai báo naming strategy để Jackson áp dụng quy tắc tên chung:

~~~java
ObjectMapper mapper = JsonMapper.builder()
    .propertyNamingStrategy(PropertyNamingStrategies.SNAKE_CASE)
    .build();
~~~

Với lớp:

~~~java
public class User {
    private String fullName;

    public String getFullName() {
        return fullName;
    }

    public void setFullName(String fullName) {
        this.fullName = fullName;
    }
}
~~~

Jackson có thể ánh xạ thuộc tính fullName của Java với tên full_name trong JSON:

~~~json
{
  "full_name": "Nguyen Van An"
}
~~~

Quy tắc tên này có ý nghĩa ở cả hai chiều: khi đọc, Jackson tìm full_name để gán cho fullName; khi ghi, Jackson dùng full_name làm tên thuộc tính JSON. Vì vậy naming strategy là quy tắc ánh xạ, không đơn thuần là cấu hình đọc hoặc cấu hình ghi.

### Dùng annotation để mô tả ánh xạ

Khi một thuộc tính cần tên cụ thể, có thể dùng @JsonProperty:

~~~java
public class Account {
    @JsonProperty("account_id")
    private Long id;

    // getter và setter
}
~~~

Annotation này khai báo tên JSON rõ ràng cho thuộc tính. Nó được Jackson sử dụng khi đọc và ghi, trừ khi cấu hình quyền truy cập hoặc annotation khác giới hạn một chiều.

Một số annotation có phạm vi riêng:

- @JsonAlias khai báo các tên thay thế được chấp nhận khi đọc. Khi ghi, Jackson vẫn dùng tên thuộc tính chính.
- @JsonIgnore thường loại thuộc tính khỏi quá trình đọc và ghi theo quy tắc annotation.
- @JsonProperty(access = JsonProperty.Access.WRITE_ONLY) cho phép nhận giá trị khi đọc nhưng không xuất thuộc tính đó khi ghi.
- @JsonFormat mô tả định dạng cho một số kiểu dữ liệu, chẳng hạn ngày giờ hoặc enum; tác động cụ thể phụ thuộc vào serializer hoặc deserializer của kiểu đó.

Như vậy, annotation có thể tham gia cả hai chiều hoặc chỉ một chiều. Việc annotation được đặt trên lớp không tự động biến mọi hành vi của nó thành cấu hình ghi hay cấu hình đọc; cần xem ý nghĩa cụ thể của annotation.

### Module và serializer/deserializer tùy chỉnh

Một module có thể đăng ký serializer, deserializer, hỗ trợ kiểu dữ liệu hoặc bổ sung quy tắc introspection. Ví dụ, JavaTimeModule bổ sung cách xử lý các kiểu ngày giờ của Java Time API:

~~~java
ObjectMapper mapper = JsonMapper.builder()
    .addModule(new JavaTimeModule())
    .build();
~~~

Nếu kiểu dữ liệu của ứng dụng có định dạng riêng, có thể đăng ký serializer và deserializer tùy chỉnh. Serializer được gọi ở chiều ghi; deserializer được gọi ở chiều đọc. Tuy nhiên, việc đăng ký chúng là một phần của cấu hình mapper và cơ chế ánh xạ kiểu dữ liệu, vì Jackson cần biết bộ chuyển đổi nào tương ứng với kiểu Java đó.

## 5. Phân biệt cấu hình databind với cấu hình parser và generator

Ngoài ba nhóm trên, Jackson còn có cấu hình ở tầng xử lý cú pháp JSON:

- Parser đọc luồng ký tự hoặc byte và tạo token. Các tùy chọn như JsonReadFeature.ALLOW_JAVA_COMMENTS hoặc JsonReadFeature.ALLOW_TRAILING_COMMA điều khiển cú pháp đầu vào được chấp nhận.
- Generator tạo cú pháp JSON đầu ra. Các tùy chọn thuộc JsonWriteFeature điều khiển cách ghi token và định dạng ở tầng generator.

Không nên nhầm JsonReadFeature với DeserializationFeature. Ví dụ, cho phép dấu phẩy cuối trong JSON là quyết định của parser; bỏ qua một thuộc tính JSON không tồn tại trong lớp Java là quyết định của quá trình databind.

Tương tự, JsonWriteFeature không đồng nghĩa với SerializationFeature. Generator quyết định cách ghi cú pháp JSON; serializer quyết định cách biểu diễn đối tượng và thuộc tính Java thành các giá trị JSON.

Có thể phân biệt theo câu hỏi:

| Câu hỏi | Tầng cấu hình phù hợp |
|---|---|
| JSON có được phép chứa comment hoặc dấu phẩy cuối không? | Parser, JsonReadFeature |
| Trường JSON không có trong lớp Java có làm phát sinh lỗi không? | Đọc, DeserializationFeature |
| fullName của Java tương ứng với full_name trong JSON không? | Ánh xạ, naming strategy hoặc annotation |
| JSON đầu ra có thụt lề không? | Ghi, SerializationFeature.INDENT_OUTPUT |
| Generator có ghi tên field theo quy tắc cú pháp nào không? | Generator, JsonWriteFeature |

## 6. Kết hợp ba nhóm trong một ObjectMapper

Trong ứng dụng, một ObjectMapper thường giữ cấu hình chung cho một miền dữ liệu hoặc một tích hợp. Có thể dùng builder để thiết lập các quy tắc trước khi sử dụng:

~~~java
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.DeserializationFeature;
import com.fasterxml.jackson.databind.MapperFeature;
import com.fasterxml.jackson.databind.SerializationFeature;
import com.fasterxml.jackson.databind.PropertyNamingStrategies;
import com.fasterxml.jackson.databind.json.JsonMapper;
import com.fasterxml.jackson.datatype.jsr310.JavaTimeModule;

ObjectMapper mapper = JsonMapper.builder()
    // Quy tắc ánh xạ
    .propertyNamingStrategy(PropertyNamingStrategies.SNAKE_CASE)
    .enable(MapperFeature.ACCEPT_CASE_INSENSITIVE_PROPERTIES)

    // Quy tắc đọc
    .disable(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES)

    // Quy tắc ghi
    .enable(SerializationFeature.INDENT_OUTPUT)

    // Hỗ trợ kiểu dữ liệu
    .addModule(new JavaTimeModule())
    .build();
~~~

Trong ví dụ này:

1. Naming strategy và MapperFeature điều khiển cách Jackson nhận diện tên thuộc tính.
2. FAIL_ON_UNKNOWN_PROPERTIES điều khiển cách Jackson xử lý thuộc tính lạ khi đọc.
3. INDENT_OUTPUT điều khiển cách Jackson trình bày JSON khi ghi.
4. JavaTimeModule cung cấp hỗ trợ chuyển đổi cho các kiểu ngày giờ Java Time.

Tên import và một số API builder có thể khác ở phiên bản Jackson cũ. Ví dụ trên dùng API của Jackson Databind 2.x hiện đại; JsonMapper.builder() có từ dòng 2.10 và PropertyNamingStrategies có trong các phiên bản mới hơn của dòng 2.x.

Sau khi tạo mapper, có thể tách các cấu hình theo từng thao tác:

~~~java
ObjectReader customerReader = mapper.readerFor(Customer.class)
    .with(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES);

ObjectWriter customerApiWriter = mapper.writerFor(Customer.class)
    .without(SerializationFeature.INDENT_OUTPUT);

Customer customer = customerReader.readValue(inputJson);
String outputJson = customerApiWriter.writeValueAsString(customer);
~~~

Mapper vẫn cung cấp naming strategy và module chung. Reader bổ sung yêu cầu đọc nghiêm ngặt cho thao tác đó; writer yêu cầu JSON gọn cho thao tác ghi đó.

## 7. Chọn đúng nơi đặt cấu hình

Khi cần thêm một tùy chọn, hãy xác định nó tác động đến phần nào của luồng:

1. **Tác động đến dữ liệu JSON đầu vào sau khi parser đã tạo token?** Xem DeserializationFeature hoặc ObjectReader.
2. **Tác động đến JSON được tạo từ đối tượng Java?** Xem SerializationFeature hoặc ObjectWriter.
3. **Tác động đến cách tìm thuộc tính, tên thuộc tính, annotation, visibility hoặc bộ chuyển đổi kiểu?** Xem MapperFeature, annotation, naming strategy, module hoặc serializer/deserializer tùy chỉnh.
4. **Tác động đến cú pháp JSON thô?** Xem cấu hình parser hoặc generator như JsonReadFeature và JsonWriteFeature.

Một số tình huống dễ nhầm:

| Yêu cầu | Nơi cấu hình nên xem |
|---|---|
| Bỏ qua trường mới được API bổ sung khi nhận JSON | DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES |
| Không cho phép null gán vào int khi đọc | DeserializationFeature.FAIL_ON_NULL_FOR_PRIMITIVES |
| Trả JSON có xuống dòng và thụt lề | SerializationFeature.INDENT_OUTPUT |
| Không xuất thuộc tính có giá trị null | JsonInclude hoặc cấu hình inclusion khi ghi |
| Đổi tên thuộc tính Java theo snake_case | PropertyNamingStrategies.SNAKE_CASE |
| Một thuộc tính chỉ được nhận vào, không được xuất ra | @JsonProperty(access = WRITE_ONLY) |
| Chấp nhận comment trong văn bản JSON | JsonReadFeature ở tầng parser |
| Định nghĩa cách đọc một kiểu dữ liệu nghiệp vụ đặc biệt | Custom deserializer hoặc module |

Lưu ý rằng một annotation hoặc module có thể cung cấp quy tắc cho nhiều chiều. Cần phân loại theo hành vi cụ thể thay vì chỉ nhìn vị trí khai báo. Chẳng hạn, @JsonAlias là metadata ánh xạ tên nhưng chỉ có tác dụng khi đọc; còn naming strategy thường được dùng ở cả đọc và ghi.

## 8. Phạm vi cấu hình và khả năng tái sử dụng

Jackson cung cấp nhiều mức để tránh phải thay đổi cấu hình toàn cục:

- **Cấp mapper:** thiết lập mặc định dùng chung, thường tạo một lần bằng JsonMapper.builder() hoặc ObjectMapper rồi cấu hình trước khi sử dụng.
- **Cấp thao tác:** tạo ObjectReader hoặc ObjectWriter để áp dụng quy tắc riêng cho một kiểu hoặc một luồng xử lý.
- **Cấp lớp hoặc thuộc tính:** dùng annotation để mô tả quy tắc gắn với mô hình dữ liệu.
- **Cấp parser/generator:** cấu hình JsonFactory khi cần thay đổi cú pháp JSON ở tầng luồng.

ObjectReader và ObjectWriter là các đối tượng bất biến, nhẹ và có thể tái sử dụng. Chúng phù hợp để chia sẻ các chính sách đọc/ghi khác nhau mà không phải liên tục bật tắt feature trên mapper dùng chung.

ObjectMapper có thể được dùng an toàn giữa nhiều luồng khi toàn bộ cấu hình đã hoàn tất trước khi các luồng bắt đầu đọc hoặc ghi. Vì vậy, nên tạo và cấu hình mapper ở giai đoạn khởi tạo ứng dụng, sau đó tái sử dụng. Tránh thay đổi cấu hình của mapper dùng chung trong lúc xử lý request; hãy tạo reader hoặc writer riêng cho nhu cầu cụ thể.

Một nguyên tắc thực hành hữu ích là đặt quy tắc ổn định của mô hình ở cấp mapper hoặc annotation, còn chính sách phụ thuộc từng API ở cấp ObjectReader và ObjectWriter. Cách tổ chức này làm rõ trách nhiệm, hạn chế tác động ngoài ý muốn và giúp kiểm soát đầu vào cũng như đầu ra độc lập.
