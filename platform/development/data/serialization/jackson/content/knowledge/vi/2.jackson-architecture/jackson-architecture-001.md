# Vai trò của lớp xử lý luồng, lớp annotation và lớp ánh xạ

Jackson được tổ chức thành nhiều thành phần phối hợp với nhau. Khi làm việc với JSON, bạn thường thấy ba nhóm chính: **lớp xử lý luồng** trong `jackson-core`, **lớp annotation** trong `jackson-annotations` và **lớp ánh xạ dữ liệu** trong `jackson-databind`.

Ba nhóm này giải quyết ba câu hỏi khác nhau:

- Dữ liệu JSON được đọc và ghi như thế nào ở mức cấu trúc và token?
- Có thể khai báo quy tắc ánh xạ giữa JSON và Java ở đâu?
- Làm thế nào để biến các token JSON thành object Java và ngược lại?

Hiểu được ranh giới trách nhiệm của từng lớp giúp bạn chọn đúng API, biết nơi cần cấu hình khi kết quả JSON không như mong đợi và tránh nhầm lẫn giữa việc phân tích cú pháp với việc ánh xạ object.

## 1. Bức tranh kiến trúc tổng thể

Trong Jackson, ba thành phần thường gặp có quan hệ bổ trợ:

```text
                 Ứng dụng Java
                       │
                       ▼
              jackson-databind
           ObjectMapper / ObjectReader
           ObjectWriter / JsonNode
                       │
          sử dụng parser và generator
                       ▼
                jackson-core
          JsonFactory / JsonParser
                JsonGenerator
                       │
             đọc hoặc ghi JSON
                       ▼
                 JSON input/output

  jackson-annotations cung cấp metadata
  để databind hiểu quy tắc ánh xạ
```

Có thể hình dung `jackson-core` là nền tảng xử lý JSON ở mức luồng, `jackson-annotations` là nơi khai báo metadata cho mô hình Java, còn `jackson-databind` là lớp kết nối dữ liệu JSON với kiểu Java. Trong cách sử dụng thông thường, ứng dụng gọi API của databind; databind dựa vào core để đọc hoặc ghi JSON và sử dụng annotation khi xác định cách ánh xạ.

Đây là cách phân chia trách nhiệm, không phải ba bước bắt buộc mà lập trình viên phải tự gọi lần lượt trong mọi chương trình. Nếu dùng `ObjectMapper`, phần lớn công việc phối hợp giữa các thành phần đã được thư viện thực hiện.

## 2. Lớp xử lý luồng: jackson-core

`jackson-core` cung cấp nền tảng đọc và ghi JSON. Nó tập trung vào cú pháp và cấu trúc JSON, không cần biết dữ liệu đó đại diện cho `Order`, `Customer` hay một kiểu nghiệp vụ cụ thể nào.

### 2.1. Đọc JSON thành các token

Khi đọc JSON, parser phân tích nội dung đầu vào và cung cấp một chuỗi token. Ví dụ, với JSON:

```json
{
  "id": "DH-1001",
  "paid": true,
  "items": ["book", "pen"]
}
```

Parser có thể lần lượt phát ra các token tương ứng như:

```text
START_OBJECT
FIELD_NAME       "id"
VALUE_STRING     "DH-1001"
FIELD_NAME       "paid"
VALUE_TRUE
FIELD_NAME       "items"
START_ARRAY
VALUE_STRING     "book"
VALUE_STRING     "pen"
END_ARRAY
END_OBJECT
```

Các token mô tả cấu trúc JSON: bắt đầu/kết thúc object hoặc array, tên trường và giá trị string, number, boolean hay null. `JsonParser` là API đọc theo kiểu streaming: chương trình có thể xử lý từng token khi đọc đến nó.

### 2.2. Ghi JSON bằng generator

Ở chiều ghi, `JsonGenerator` cung cấp các thao tác phát ra cấu trúc JSON. Chương trình chủ động ghi bắt đầu object, tên trường, giá trị và kết thúc object. Generator đảm nhiệm việc tạo cú pháp JSON hợp lệ theo chuỗi thao tác được gọi.

Ví dụ minh họa cách ghi một object JSON:

```java
import com.fasterxml.jackson.core.JsonFactory;
import com.fasterxml.jackson.core.JsonGenerator;

import java.io.StringWriter;

public class CoreWriteExample {
    public static void main(String[] args) throws Exception {
        StringWriter output = new StringWriter();
        JsonFactory factory = new JsonFactory();

        try (JsonGenerator generator = factory.createGenerator(output)) {
            generator.writeStartObject();
            generator.writeStringField("id", "DH-1001");
            generator.writeBooleanField("paid", true);
            generator.writeEndObject();
        }

        System.out.println(output);
    }
}
```

Kết quả là một object JSON có hai trường `id` và `paid`. Ví dụ này làm việc trực tiếp với cú pháp JSON; không có class `Order` nào được Jackson tự động tạo hoặc đọc.

### 2.3. Khi nào dùng streaming API?

Streaming API phù hợp khi:

- Tệp hoặc payload JSON rất lớn và không muốn giữ toàn bộ cấu trúc trong bộ nhớ.
- Chỉ cần đọc một vài trường trong một luồng dữ liệu.
- Cần kiểm soát thứ tự đọc/ghi và cách xử lý từng phần tử.
- Đang xây dựng một thành phần xử lý dữ liệu ở mức thấp hoặc định dạng tùy biến.

Vì chương trình tự điều khiển việc đi qua token, streaming có thể tiết kiệm bộ nhớ và cho phép xử lý sớm từng phần dữ liệu. Đổi lại, code phải tự quản lý trạng thái parser/generator và cấu trúc lồng nhau. Với payload nghiệp vụ thông thường, cách làm này có thể dài dòng hơn cần thiết.

## 3. Lớp annotation: jackson-annotations

`jackson-annotations` cung cấp các annotation để mô tả cách một thuộc tính hoặc kiểu Java liên hệ với JSON. Annotation là metadata gắn với class, constructor, method hoặc field. Bản thân annotation không đọc JSON, không tạo object và cũng không tự ghi JSON.

Thành phần thực hiện việc diễn giải metadata trong luồng ánh xạ thông thường là databind. Nói cách khác, annotation khai báo quy tắc; `ObjectMapper` và các cơ chế introspection của Jackson sử dụng quy tắc đó khi serialize hoặc deserialize.

### 3.1. Điều khiển tên thuộc tính với JsonProperty

Tên thuộc tính Java và tên trường trong hợp đồng JSON không nhất thiết phải giống nhau. `@JsonProperty` cho phép chỉ định tên JSON cần dùng.

```java
import com.fasterxml.jackson.annotation.JsonProperty;

public record Customer(
        @JsonProperty("customer_id") String id,
        String name
) {}
```

Với quy tắc trên, thuộc tính `id` được biểu diễn bằng tên `customer_id` trong JSON. Khi đọc JSON, Jackson databind cũng dựa vào metadata này để ánh xạ trường `customer_id` về thành phần `id` của record.

### 3.2. Bỏ qua thuộc tính với JsonIgnore

`@JsonIgnore` đánh dấu một thuộc tính cần được bỏ qua theo quy tắc xử lý của Jackson. Ví dụ:

```java
import com.fasterxml.jackson.annotation.JsonIgnore;

public class Account {
    private String username;

    @JsonIgnore
    private String internalNote;

    // Constructor, getter và setter được lược bỏ để tập trung vào annotation.
}
```

Trong mô hình phù hợp với cách introspection đang dùng, `internalNote` sẽ không được đưa vào biểu diễn JSON và cũng không được bind theo thuộc tính bị bỏ qua. Khi áp dụng cho class thật, cần xem xét vị trí annotation trên field, getter, setter hoặc constructor parameter và cách Jackson gộp các property đó.

### 3.3. Một số annotation thường gặp

| Annotation | Mục đích thường dùng |
| --- | --- |
| `@JsonProperty` | Chỉ định tên thuộc tính JSON hoặc khai báo property có tên cụ thể. |
| `@JsonIgnore` | Bỏ qua một thuộc tính trong quá trình xử lý JSON. |
| `@JsonAlias` | Khai báo thêm các tên có thể nhận khi deserialize. |
| `@JsonCreator` | Chỉ định constructor hoặc factory method dùng để tạo object khi deserialize. |
| `@JsonFormat` | Tùy chỉnh cách biểu diễn/đọc một số kiểu dữ liệu, chẳng hạn định dạng ngày giờ. |
| `@JsonInclude` | Quy định điều kiện đưa thuộc tính vào JSON khi serialize. |
| `@JsonPropertyOrder` | Gợi ý thứ tự thuộc tính khi ghi JSON. |
| `@JsonTypeInfo` | Mô tả cách đưa thông tin kiểu vào JSON cho một số mô hình đa hình. |

Không phải annotation nào cũng có cùng tác động ở hai chiều. Có annotation chủ yếu ảnh hưởng đến serialization, có annotation chủ yếu ảnh hưởng đến deserialization, và có annotation liên quan đến cả hai. Cần đọc đúng mục đích của từng annotation thay vì giả định mọi annotation đều chỉ đổi tên field.

Annotation giúp quy tắc ánh xạ nằm gần mô hình Java, dễ đọc và thuận tiện khi quy tắc thuộc về chính kiểu dữ liệu đó. Nếu một kiểu cần nhiều cách biểu diễn JSON khác nhau tùy API hoặc ngữ cảnh, cấu hình qua `ObjectMapper`, mix-in hoặc serializer/deserializer riêng có thể phù hợp hơn việc gắn một quy tắc cố định vào class.

## 4. Lớp ánh xạ: jackson-databind

`jackson-databind` cung cấp cơ chế ánh xạ giữa cấu trúc JSON và kiểu Java. Đây là lớp mà phần lớn ứng dụng sử dụng trực tiếp khi muốn làm việc với object thay vì tự thao tác từng token.

API quen thuộc nhất là `ObjectMapper`. Nó phối hợp việc đọc JSON, xác định kiểu đích, tạo object, đọc thuộc tính và chuyển object thành JSON. Trong quá trình đó, databind sử dụng parser/generator từ core và metadata từ annotations khi có.

### 4.1. ObjectMapper: ánh xạ hai chiều

Ví dụ, ứng dụng có DTO:

```java
import com.fasterxml.jackson.annotation.JsonProperty;

import java.math.BigDecimal;

public record Order(
        @JsonProperty("order_id") String id,
        BigDecimal amount,
        boolean paid
) {}
```

Ứng dụng có thể chuyển đổi object và JSON như sau:

```java
import com.fasterxml.jackson.databind.ObjectMapper;

public class DatabindExample {
    public static void main(String[] args) throws Exception {
        ObjectMapper mapper = new ObjectMapper();

        Order order = new Order("DH-1001", new BigDecimal("129.50"), true);

        // Object Java -> JSON
        String json = mapper.writeValueAsString(order);

        // JSON -> object Java
        Order restored = mapper.readValue(json, Order.class);

        System.out.println(json);
        System.out.println(restored.id());
    }
}
```

Khi `writeValueAsString` được gọi, databind tìm các property cần ghi, áp dụng metadata liên quan rồi yêu cầu cơ chế ghi JSON tạo kết quả. Khi `readValue` được gọi, databind đọc cấu trúc JSON, tìm cách tạo `Order`, ánh xạ `order_id` vào `id` và chuyển các giá trị sang kiểu Java tương ứng.

Đây là lý do bạn không cần tự viết chuỗi JSON hay duyệt từng token trong tình huống thông thường. Databind cung cấp lớp trừu tượng làm việc ở mức object.

### 4.2. Object tree với JsonNode

Không phải lúc nào cấu trúc JSON cũng cố định hoặc đã có class Java tương ứng. Databind còn cung cấp tree model, cho phép đọc JSON thành cây node:

```java
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;

public class TreeExample {
    public static void main(String[] args) throws Exception {
        String json = """
                {
                  "id": "DH-1001",
                  "amount": 129.50,
                  "paid": true
                }
                """;

        ObjectMapper mapper = new ObjectMapper();
        JsonNode root = mapper.readTree(json);

        String id = root.path("id").asText();
        boolean paid = root.path("paid").asBoolean();

        System.out.println(id + ": " + paid);
    }
}
```

`JsonNode` hữu ích khi cần kiểm tra trường tồn tại hay không, duyệt cấu trúc động hoặc chỉ lấy một phần dữ liệu mà chưa muốn định nghĩa DTO. Tree model thuận tiện hơn streaming khi cần truy cập nhiều lần hoặc đi lại trong cấu trúc, nhưng thường phải giữ cây dữ liệu trong bộ nhớ.

### 4.3. Kiểu generic và JavaType

Khi đọc một kiểu cụ thể, `Order.class` đủ để chỉ định kiểu đích. Với collection có generic như `List<Order>`, chỉ truyền `List.class` sẽ không giữ được đầy đủ thông tin kiểu phần tử do type erasure của Java.

Databind cung cấp `TypeReference` hoặc `JavaType` để mô tả kiểu generic:

```java
import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;

import java.util.List;

ObjectMapper mapper = new ObjectMapper();

List<Order> orders = mapper.readValue(
        json,
        new TypeReference<List<Order>>() {}
);
```

Nhờ thông tin kiểu đầy đủ, databind có thể ánh xạ mỗi phần tử trong JSON array thành một `Order` thay vì chỉ tạo các map hoặc object không xác định kiểu.

## 5. Ba lớp phối hợp trong một lần deserialize

Giả sử ứng dụng nhận JSON và muốn tạo `Customer` có annotation `@JsonProperty("customer_id")`.

```text
JSON input
   │
   ▼
jackson-core
JsonParser đọc cấu trúc và phát token
   │
   ▼
jackson-databind
Xác định kiểu Customer và quy tắc tạo object
   │
   ├── đọc metadata từ jackson-annotations
   │      @JsonProperty("customer_id")
   │
   ├── ánh xạ token vào property tương ứng
   │
   ▼
Customer object
```

Ở chiều serialize, luồng trách nhiệm đi theo hướng ngược lại:

```text
Customer object
   │
   ▼
jackson-databind
Xác định property cần ghi và áp dụng annotation
   │
   ▼
jackson-core
JsonGenerator ghi cấu trúc JSON
   │
   ▼
JSON output
```

Điểm quan trọng là annotation không thay parser, generator hoặc databind. Annotation chỉ mô tả metadata. Core xử lý cấu trúc JSON. Databind kết nối cấu trúc đó với object Java.

## 6. Chọn lớp nào cho từng nhu cầu?

| Nhu cầu | Thành phần phù hợp | Lý do |
| --- | --- | --- |
| Đọc JSON lớn theo từng phần tử | `jackson-core` | Streaming parser cho phép xử lý token tuần tự. |
| Ghi JSON thủ công theo từng trường | `jackson-core` | Generator cho phép kiểm soát trực tiếp cấu trúc được ghi. |
| Đổi tên trường JSON của DTO | `jackson-annotations` kết hợp databind | Annotation khai báo tên; databind diễn giải khi ánh xạ. |
| Chuyển JSON thành DTO | `jackson-databind` | Databind thực hiện object mapping. |
| Chuyển DTO thành JSON | `jackson-databind` | Databind chọn property và ghi qua core. |
| Đọc JSON chưa có mô hình cố định | Tree model của databind hoặc streaming core | Chọn tree nếu cần truy cập cấu trúc; chọn streaming nếu muốn xử lý tuần tự, tiết kiệm bộ nhớ. |
| Tạo nhiều cách biểu diễn cho cùng một kiểu | Cấu hình databind, mix-in hoặc serializer/deserializer | Quy tắc có thể phụ thuộc ngữ cảnh thay vì cố định trong annotation của class. |

Trong ứng dụng Spring Boot Web thông thường, bạn thường khai báo DTO và để HTTP message converter sử dụng `ObjectMapper` đã được cấu hình. Bạn chỉ cần làm việc trực tiếp với core khi có nhu cầu kiểm soát ở mức token hoặc xử lý luồng lớn; chỉ thêm annotation khi muốn mô tả quy tắc ánh xạ phù hợp với mô hình.

## 7. Phân biệt lỗi theo đúng lớp chịu trách nhiệm

Việc hiểu kiến trúc cũng giúp khoanh vùng lỗi:

- **Lỗi cú pháp JSON:** nội dung đầu vào không phải JSON hợp lệ, chẳng hạn thiếu dấu phẩy hoặc đóng ngoặc sai. Đây là lỗi ở quá trình parse của core.
- **Lỗi ánh xạ kiểu:** JSON hợp lệ nhưng giá trị không thể chuyển sang kiểu Java mong đợi, chẳng hạn một chuỗi không thể chuyển thành số. Lỗi phát sinh trong quá trình databind chuyển đổi giá trị.
- **Sai tên thuộc tính:** JSON dùng tên khác với property mà databind đang nhận diện. Kiểm tra annotation, naming strategy và cấu hình property discovery.
- **Không tạo được object:** kiểu Java không có constructor/factory phù hợp hoặc metadata tạo object chưa đúng. Kiểm tra constructor, record, `@JsonCreator` và cấu hình liên quan.
- **JSON đầu ra thiếu hoặc thừa trường:** kiểm tra annotation như `@JsonIgnore`, `@JsonInclude`, getter/field được nhận diện và cấu hình serialization.

Không nên mặc định mọi lỗi liên quan đến JSON đều là lỗi của annotation hoặc `ObjectMapper`. Hãy xác định lỗi xảy ra khi parser đọc cú pháp, khi databind chuyển đổi kiểu hay khi metadata khiến property được diễn giải khác mong đợi.

## 8. Những điều cần nhớ khi sử dụng ba lớp

1. `jackson-core` xử lý JSON ở mức luồng: parser đọc token, generator ghi token.
2. `jackson-annotations` cung cấp metadata để mô tả quy tắc ánh xạ trên kiểu Java.
3. `jackson-databind` ánh xạ giữa JSON và object Java; `ObjectMapper` là API cấp cao phổ biến.
4. Databind sử dụng core để đọc/ghi JSON và có thể diễn giải annotation trong quá trình ánh xạ.
5. Streaming cho phép kiểm soát và xử lý tuần tự; tree model cho phép truy cập cấu trúc JSON linh hoạt; object binding phù hợp với DTO có kiểu rõ ràng.
6. Chọn đúng lớp theo nhu cầu giúp code dễ hiểu và giúp xác định đúng nơi cần điều tra khi có lỗi.

Khi nhìn thấy một đoạn code dùng `ObjectMapper`, hãy hiểu rằng ứng dụng đang sử dụng lớp ánh xạ cấp cao. Khi thấy `JsonParser` hoặc `JsonGenerator`, đó là thao tác trực tiếp ở lớp xử lý luồng. Khi thấy `@JsonProperty` hay `@JsonIgnore`, đó là metadata khai báo cách databind nên diễn giải mô hình Java trong quá trình trao đổi dữ liệu.
