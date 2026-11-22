# Phân biệt bỏ qua một thuộc tính và bỏ qua mọi thuộc tính không nhận diện

Khi Jackson đọc JSON để tạo object Java, có hai tình huống dễ bị nhầm lẫn:

- JSON chứa một thuộc tính mà mô hình Java có nhận diện, nhưng ứng dụng chủ động muốn bỏ qua thuộc tính đó.
- JSON chứa một thuộc tính mà mô hình Java không nhận diện được, chẳng hạn trường mới do hệ thống gửi bổ sung hoặc một tên trường bị viết sai.

Jackson cung cấp các cơ chế riêng cho hai tình huống này. `@JsonIgnore` dùng để bỏ qua một property được chỉ định. `DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES` quyết định cách xử lý các property đầu vào không được nhận diện. Ngoài ra, `@JsonIgnoreProperties(ignoreUnknown = true)` cho phép một kiểu Java chấp nhận các trường lạ mà không cần thay đổi chính sách của toàn bộ mapper.

Phân biệt đúng các cơ chế này giúp ứng dụng vừa kiểm soát được dữ liệu cần loại bỏ, vừa tránh vô tình bỏ qua lỗi sai tên trường hoặc dữ liệu không khớp hợp đồng API.

## 1. Thế nào là thuộc tính được nhận diện và thuộc tính không nhận diện?

Giả sử ứng dụng có kiểu Java:

```java
public class Customer {
    private String name;
    private String email;
    private String internalNote;

    public Customer() {}

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }

    public String getEmail() {
        return email;
    }

    public void setEmail(String email) {
        this.email = email;
    }

    public String getInternalNote() {
        return internalNote;
    }

    public void setInternalNote(String internalNote) {
        this.internalNote = internalNote;
    }
}
```

Jackson Databind thực hiện introspection để tìm property thông qua field, getter, setter, creator và annotation theo visibility/cấu hình của mapper. Với cấu hình thông thường, `name`, `email` và `internalNote` đều có thể được nhận diện.

JSON sau chứa cả ba property đã biết:

```json
{
  "name": "An",
  "email": "an@example.com",
  "internalNote": "Imported from legacy system"
}
```

Nếu JSON có thêm `loyaltyLevel` nhưng `Customer` không có property tương ứng, không có accessor hay cơ chế nhận dữ liệu bổ sung nào xử lý nó, thì `loyaltyLevel` là thuộc tính không nhận diện đối với kiểu đích.

```json
{
  "name": "An",
  "email": "an@example.com",
  "loyaltyLevel": "GOLD"
}
```

Một tên trường cũng có thể trở thành không nhận diện dù class có field gần giống. Ví dụ, JSON gửi `eamil` trong khi Java có `email`. Tương tự, một field private có thể tồn tại trong class nhưng không được Jackson phát hiện do visibility hoặc cấu hình property. Vì vậy, “không nhận diện” phụ thuộc vào mô hình property mà Jackson xây dựng, không chỉ phụ thuộc vào việc có nhìn thấy tên field trong mã nguồn hay không.

## 2. Bỏ qua một property cụ thể bằng @JsonIgnore

`@JsonIgnore` đánh dấu một property cần được bỏ qua trong quá trình ánh xạ JSON. Cơ chế này phù hợp khi ứng dụng đã biết chính xác thuộc tính nào không nên tham gia trao đổi dữ liệu.

Ví dụ, `internalNote` là thông tin nội bộ, không thuộc hợp đồng JSON của `Customer`:

```java
import com.fasterxml.jackson.annotation.JsonIgnore;

public class Customer {
    private String name;
    private String email;

    @JsonIgnore
    private String internalNote;

    public Customer() {}

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }

    public String getEmail() {
        return email;
    }

    public void setEmail(String email) {
        this.email = email;
    }

    public String getInternalNote() {
        return internalNote;
    }

    public void setInternalNote(String internalNote) {
        this.internalNote = internalNote;
    }
}
```

Với property đã được Jackson hợp nhất từ field và accessor, annotation trên field được xem xét trong quá trình introspection. Khi serialize, `internalNote` không được ghi ra JSON. Khi deserialize, giá trị JSON có tên `internalNote` cũng bị bỏ qua theo quy tắc ignore.

Ví dụ input:

```json
{
  "name": "An",
  "email": "an@example.com",
  "internalNote": "Do not expose this field"
}
```

Jackson vẫn đọc `name` và `email`; `internalNote` là property đã được đánh dấu bỏ qua nên giá trị này không được gán vào property. Đây là một trường hợp khác với một tên trường hoàn toàn không được nhận diện.

### 2.1. @JsonIgnore có tác động ở hai chiều

Mặc định, `@JsonIgnore` có ý nghĩa bỏ qua property trong quá trình serialize và deserialize. Nếu chỉ muốn property được nhận vào nhưng không xuất ra JSON, hãy xem xét:

```java
@JsonProperty(access = JsonProperty.Access.WRITE_ONLY)
private String password;
```

Nếu chỉ muốn property xuất ra response mà không nhận giá trị từ JSON, có thể dùng `READ_ONLY`. Hai lựa chọn này khác với `@JsonIgnore`, vốn loại property khỏi quá trình ánh xạ theo quy tắc ignore.

`@JsonIgnore` không xóa field khỏi object Java và không tự xóa dữ liệu khỏi database. Nó chỉ điều khiển cách Jackson xử lý property khi chuyển đổi JSON. Nếu dữ liệu nhạy cảm đã được nạp vào object, ứng dụng vẫn phải bảo vệ nó trong bộ nhớ, log, lưu trữ và các luồng xử lý khác.

## 3. Bỏ qua mọi property không nhận diện bằng FAIL_ON_UNKNOWN_PROPERTIES

`DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES` điều khiển cách Jackson phản ứng khi JSON đầu vào có property không thể ánh xạ vào kiểu đích.

Trong Jackson Databind độc lập, feature này mặc định được bật. Khi feature bật và không có cơ chế xử lý unknown property khác, Jackson ném `UnrecognizedPropertyException` khi gặp trường không nhận diện.

Ví dụ, `Customer` không có property `loyaltyLevel`:

```json
{
  "name": "An",
  "email": "an@example.com",
  "loyaltyLevel": "GOLD"
}
```

Nếu dùng mapper strict:

```java
import com.fasterxml.jackson.databind.DeserializationFeature;
import com.fasterxml.jackson.databind.ObjectMapper;

ObjectMapper mapper = new ObjectMapper();
mapper.enable(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES);

Customer customer = mapper.readValue(json, Customer.class);
```

Jackson sẽ báo lỗi vì `loyaltyLevel` không được nhận diện. Cách này hữu ích khi dữ liệu đầu vào phải tuân thủ chính xác hợp đồng, hoặc khi muốn phát hiện sớm lỗi đánh máy ở tên trường.

### 3.1. Tắt feature để bỏ qua unknown property trên mapper

Nếu ứng dụng cần tương thích với các hệ thống thường bổ sung trường mới, có thể tắt feature:

```java
ObjectMapper mapper = new ObjectMapper();
mapper.disable(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES);

Customer customer = mapper.readValue(json, Customer.class);
```

Khi đó, các property không nhận diện trong quá trình deserialize sẽ được bỏ qua thay vì làm thao tác đọc thất bại. Các property được nhận diện như `name` và `email` vẫn được ánh xạ bình thường.

Thiết lập này có phạm vi mapper: các thao tác deserialize sử dụng mapper theo cấu hình đó sẽ chịu ảnh hưởng. Vì vậy, hãy cân nhắc trước khi tắt feature toàn cục. Nếu chỉ một kiểu hoặc một luồng tích hợp cần chấp nhận trường lạ, cấu hình phạm vi hẹp hơn thường dễ kiểm soát hơn.

Lưu ý: framework như Spring Boot có thể cấu hình `ObjectMapper` khác với mapper được tạo bằng `new ObjectMapper()`. Không nên suy ra hành vi của ứng dụng từ mặc định của thư viện mà chưa kiểm tra mapper thực tế.

## 4. Bỏ qua unknown property riêng cho một kiểu bằng @JsonIgnoreProperties

Nếu chỉ một DTO cần chấp nhận trường không nhận diện, có thể dùng `@JsonIgnoreProperties(ignoreUnknown = true)`:

```java
import com.fasterxml.jackson.annotation.JsonIgnoreProperties;

@JsonIgnoreProperties(ignoreUnknown = true)
public class PartnerCustomer {
    private String name;
    private String email;

    public PartnerCustomer() {}

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }

    public String getEmail() {
        return email;
    }

    public void setEmail(String email) {
        this.email = email;
    }
}
```

Annotation này yêu cầu Jackson bỏ qua các property không nhận diện khi deserialize `PartnerCustomer`. Các kiểu Java khác vẫn tuân theo chính sách unknown-property của mapper nếu chúng không có cấu hình riêng.

Ví dụ, một đối tác có thể bổ sung trường `loyaltyLevel`, `segment` hoặc `sourceSystem` theo thời gian. DTO tích hợp được đánh dấu `ignoreUnknown = true` có thể tiếp tục đọc những trường mà ứng dụng chưa sử dụng.

`ignoreUnknown = true` không có nghĩa mọi property của class đều bị bỏ qua. Những property đã được nhận diện như `name` và `email` vẫn được ánh xạ bình thường. Annotation cũng không làm thay đổi việc serialize object thành JSON; mục tiêu của cờ này là xử lý property không nhận diện ở chiều deserialize.

### 4.1. Bỏ qua tên property cụ thể bằng JsonIgnoreProperties

`@JsonIgnoreProperties` còn có dạng chỉ định danh sách tên property:

```java
@JsonIgnoreProperties({"internalNote", "legacyCode"})
public class CustomerView {
    private String name;
    private String internalNote;
    private String legacyCode;
}
```

Danh sách này chỉ định những tên property cụ thể cần bỏ qua theo annotation. Nó khác với `ignoreUnknown = true`, vốn chấp nhận mọi tên đầu vào mà kiểu đích không nhận diện.

Một số cấu hình của annotation như `allowGetters` hoặc `allowSetters` có thể điều chỉnh chiều xử lý đối với các property được liệt kê. Nếu dùng các tùy chọn đó, hãy xác định rõ mục tiêu là chỉ bỏ khi đọc hay chỉ bỏ khi ghi. Không nên nhầm danh sách tên property được ignore với chính sách bỏ qua tất cả trường lạ.

## 5. So sánh ba cơ chế thường gặp

| Cơ chế | Đối tượng bị tác động | Chiều xử lý chính | Phạm vi |
| --- | --- | --- | --- |
| `@JsonIgnore` | Một property được chỉ định | Serialize và deserialize đều bỏ qua theo quy tắc ignore | Property trong mô hình |
| `FAIL_ON_UNKNOWN_PROPERTIES` | Property đầu vào không được nhận diện | Chỉ deserialize; bật thì báo lỗi, tắt thì bỏ qua | Mapper hoặc reader sử dụng feature |
| `@JsonIgnoreProperties(ignoreUnknown = true)` | Mọi property đầu vào không nhận diện của kiểu được đánh dấu | Chỉ deserialize đối với unknown property | Kiểu Java được annotation |
| `@JsonIgnoreProperties({"a", "b"})` | Các property có tên được liệt kê | Theo quy tắc ignore; có thể tinh chỉnh bằng `allowGetters`/`allowSetters` | Kiểu Java được annotation |

Ví dụ với JSON:

```json
{
  "name": "An",
  "internalNote": "private",
  "loyaltyLevel": "GOLD"
}
```

Giả sử `Customer` có property `name`, có property `internalNote` được đánh dấu `@JsonIgnore`, nhưng không có property `loyaltyLevel`:

- `name` được nhận diện và ánh xạ bình thường.
- `internalNote` được nhận diện nhưng bị ignore theo annotation.
- `loyaltyLevel` không được nhận diện. Cách xử lý nó phụ thuộc feature `FAIL_ON_UNKNOWN_PROPERTIES`, annotation `ignoreUnknown`, any-setter hoặc handler liên quan.

Như vậy, `@JsonIgnore` không phải cách tổng quát để chấp nhận mọi trường mới từ client; còn tắt `FAIL_ON_UNKNOWN_PROPERTIES` không phải cách chỉ định một property nội bộ cần loại khỏi JSON.

## 6. Khi nào nên strict, khi nào nên lenient?

### 6.1. Nên giữ strict khi hợp đồng đầu vào cần được kiểm soát

Chế độ strict phù hợp khi:

- API nội bộ yêu cầu client gửi đúng schema đã thống nhất.
- Payload là lệnh nghiệp vụ quan trọng, một trường sai tên có thể khiến dữ liệu bị hiểu sai.
- Muốn phát hiện sớm client gửi sai field hoặc dùng phiên bản hợp đồng không tương thích.
- Dữ liệu được nhập vào hệ thống tài chính, đơn hàng hoặc quy trình cần kiểm tra chặt chẽ.

Ví dụ, client gửi `amout` thay vì `amount`. Nếu unknown property bị bỏ qua, giá trị tiền có thể không được gán như dự kiến và lỗi chỉ xuất hiện ở bước nghiệp vụ sau đó. Chế độ strict giúp lỗi tên trường được phát hiện ngay ở ranh giới nhận dữ liệu.

### 6.2. Có thể lenient khi cần tương thích tiến về phía trước

Chế độ bỏ qua trường lạ có thể phù hợp khi:

- Ứng dụng chỉ sử dụng một phần dữ liệu từ đối tác.
- Hệ thống nguồn thường bổ sung trường mà consumer cũ không cần biết.
- DTO được thiết kế rõ ràng để chỉ đọc các trường ứng dụng quan tâm.
- Hợp đồng tích hợp quy định consumer phải bỏ qua các trường chưa hỗ trợ.

Tuy nhiên, lenient có rủi ro che giấu lỗi đánh máy hoặc thay đổi schema ngoài dự kiến. Nếu bỏ qua unknown property, hãy có logging, metrics hoặc kiểm tra hợp đồng ở tầng phù hợp để phát hiện thay đổi quan trọng.

## 7. Không muốn bỏ dữ liệu lạ? Hãy thu thập nó

Đôi khi ứng dụng không muốn báo lỗi nhưng cũng không muốn vứt bỏ trường chưa biết. Khi đó, `@JsonAnySetter` có thể thu thập các property còn lại vào một map.

```java
import com.fasterxml.jackson.annotation.JsonAnySetter;
import com.fasterxml.jackson.databind.JsonNode;

import java.util.LinkedHashMap;
import java.util.Map;

public class ExtensibleCustomer {
    private String name;
    private final Map<String, JsonNode> additionalProperties = new LinkedHashMap<>();

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }

    @JsonAnySetter
    public void addAdditionalProperty(String key, JsonNode value) {
        additionalProperties.put(key, value);
    }

    public Map<String, JsonNode> getAdditionalProperties() {
        return additionalProperties;
    }
}
```

Với JSON có thêm `loyaltyLevel`, Jackson ánh xạ `name` vào property đã biết và chuyển trường chưa biết vào `additionalProperties`. Ứng dụng có thể lưu, ghi log hoặc xử lý những trường mở rộng đó sau.

`@JsonAnySetter` là một cơ chế xử lý unknown property cụ thể. Khi có any-setter phù hợp, các trường được nó tiếp nhận không còn bị xem là trường không xử lý để ném lỗi theo `FAIL_ON_UNKNOWN_PROPERTIES`. Vì vậy, đây là lựa chọn hữu ích khi hợp đồng cho phép mở rộng và consumer cần giữ lại dữ liệu bổ sung.

## 8. Cấu hình theo phạm vi mapper hoặc reader

Nếu chỉ một luồng nhập dữ liệu cần bỏ qua trường lạ, không nhất thiết phải tắt feature trên mapper dùng chung:

```java
import com.fasterxml.jackson.databind.DeserializationFeature;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.ObjectReader;

ObjectMapper mapper = new ObjectMapper();

// Reader mặc định vẫn strict theo cấu hình mapper.
ObjectReader strictReader = mapper.readerFor(Customer.class)
        .with(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES);

// Chỉ reader này bỏ qua property không nhận diện.
ObjectReader tolerantReader = mapper.readerFor(PartnerCustomer.class)
        .without(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES);
```

`ObjectReader` là cấu hình bất biến cho chiều deserialize. `with(...)` và `without(...)` tạo reader mới, không bật/tắt feature trên mapper gốc. Cách này hữu ích khi một ứng dụng có nhiều hợp đồng đầu vào với mức nghiêm ngặt khác nhau.

Nếu `PartnerCustomer` đã được đánh dấu `@JsonIgnoreProperties(ignoreUnknown = true)`, annotation cũng thể hiện chính sách ngay trên kiểu DTO. Nên chọn cách cấu hình theo kiến trúc của ứng dụng: annotation khi chính sách thuộc về kiểu đó; reader khi chính sách phụ thuộc vào luồng xử lý; mapper khi đó là mặc định chung.

## 9. Lưu ý khi dùng với Spring Boot

Spring Boot thường cấu hình `ObjectMapper` và tích hợp nó với HTTP message converter. Hành vi xử lý unknown property trong API vì vậy phụ thuộc vào mapper thực tế của ứng dụng, các thuộc tính cấu hình Spring Boot và những customizer/module đã đăng ký.

Khi endpoint có hành vi khác với đoạn thử nghiệm độc lập, hãy kiểm tra:

1. Controller đang sử dụng converter nào để đọc `Content-Type` của request.
2. Converter đang dùng mapper nào.
3. Mapper có bật hay tắt `FAIL_ON_UNKNOWN_PROPERTIES` không.
4. DTO có `@JsonIgnoreProperties(ignoreUnknown = true)` hoặc `@JsonAnySetter` không.
5. Có naming strategy hoặc annotation khiến một trường tưởng như đã biết nhưng thực tế không được nhận diện không.

Không nên chỉ thêm `@JsonIgnore` để sửa lỗi một trường JSON lạ. Trước tiên hãy xác định trường đó là property đã biết cần loại bỏ, hay là dữ liệu ngoài mô hình cần được báo lỗi, bỏ qua hoặc thu thập.

## 10. Ghi nhớ

- `@JsonIgnore` bỏ qua một property cụ thể đã được nhận diện; mặc định ảnh hưởng cả chiều serialize và deserialize.
- `FAIL_ON_UNKNOWN_PROPERTIES` quyết định cách xử lý property đầu vào mà Jackson không nhận diện: bật thì báo lỗi, tắt thì bỏ qua.
- `@JsonIgnoreProperties(ignoreUnknown = true)` cho phép một kiểu DTO bỏ qua các trường lạ khi deserialize mà không cần nới lỏng toàn bộ mapper.
- `@JsonIgnoreProperties({"fieldA", "fieldB"})` liệt kê tên property cụ thể cần ignore; không đồng nghĩa với bỏ qua mọi tên không nhận diện.
- `@JsonAnySetter` cho phép thu thập property chưa biết thay vì bỏ đi.
- Strict giúp phát hiện lỗi hợp đồng và typo; lenient hỗ trợ tương thích với dữ liệu mở rộng nhưng có thể che giấu lỗi đầu vào.

Khi thiết kế DTO, hãy phân loại từng trường hợp: property đã biết nhưng không muốn trao đổi, property không nằm trong mô hình, hay property mở rộng cần được giữ lại. Chọn đúng cơ chế cho từng trường hợp sẽ giúp API có hành vi rõ ràng và dễ bảo trì.
