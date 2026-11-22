# Tránh gọi lại chính deserializer gây đệ quy vô hạn

Jackson Databind chọn một deserializer dựa trên kiểu Java đích. Nếu custom deserializer của kiểu Account lại gọi readValue hoặc treeToValue để deserialize chính kiểu Account, Jackson thường chọn lại custom deserializer đó. Deserializer tự gọi lại chính nó trên cùng dữ liệu, rồi lặp đi lặp lại cho đến khi stack bị tràn.

Đây là lỗi đệ quy do **tái nhập cùng bộ xử lý**, không phải lỗi do JSON có object lồng nhau. Một cấu trúc cây có các node con cùng kiểu vẫn có thể được đọc đệ quy an toàn, miễn là mỗi lần gọi xử lý một token/subtree con riêng và parser tiến về phía trước.

Bài học này giải thích cách vòng chọn deserializer hoạt động, các mẫu code dễ gây đệ quy, cách đọc dữ liệu an toàn bằng tree hoặc DTO trung gian, cách bọc deserializer mặc định bằng delegate, và cách phân biệt đệ quy hợp lệ với vòng lặp vô hạn.

## 1. Jackson chọn deserializer theo kiểu đích

Khi gọi:

```java
Account account = mapper.readValue(json, Account.class);
```

Jackson thực hiện các bước khái quát:

```text
JSON text
   │
   ▼
JsonParser tạo token
   │
   ▼
Jackson xác định kiểu đích Account
   │
   ▼
Tìm deserializer đã đăng ký cho Account
   │
   ▼
Gọi deserialize(parser, context)
   │
   ▼
Tạo Account
```

Deserializer có thể được chọn từ nhiều nguồn cấu hình, ví dụ:

- Annotation **@JsonDeserialize(using = ...)** trên class hoặc property.
- Module đăng ký bằng **SimpleModule.addDeserializer(...)**.
- Module/framework tích hợp.
- Deserializer mặc định do Jackson tạo cho bean, record, collection hoặc kiểu scalar.

Điểm quan trọng: khi đang ở trong một deserializer, nếu code yêu cầu Jackson deserialize lại cùng kiểu đích, Jackson không tự hiểu rằng lần gọi sau phải dùng một cách xử lý khác. Nó tra cứu theo cấu hình hiện tại và có thể chọn đúng deserializer đang chạy.

## 2. Mẫu lỗi phổ biến: gọi readValue cho chính kiểu đang xử lý

Giả sử có model:

```java
public record Account(
    String id,
    String displayName,
    boolean active
) {}
```

Custom deserializer:

```java
public final class AccountDeserializer
        extends StdDeserializer<Account> {

    public AccountDeserializer() {
        super(Account.class);
    }

    @Override
    public Account deserialize(
            JsonParser parser,
            DeserializationContext context
    ) throws IOException {
        return parser.getCodec().readValue(parser, Account.class);
    }
}
```

Và đăng ký deserializer cho Account:

```java
SimpleModule module = new SimpleModule();
module.addDeserializer(Account.class, new AccountDeserializer());

ObjectMapper mapper = new ObjectMapper()
    .registerModule(module);
```

Đây là vòng lặp:

1. Jackson bắt đầu deserialize Account.
2. Jackson gọi AccountDeserializer.deserialize.
3. Method gọi readValue(parser, Account.class).
4. Jackson lại tìm deserializer cho Account.
5. Module vẫn chỉ tới AccountDeserializer.
6. Jackson gọi lại chính method đó.
7. Method tiếp tục gọi readValue với cùng kiểu đích.

Kết quả thường là StackOverflowError với stack trace lặp lại giữa custom deserializer và các method đọc dữ liệu của Jackson.

Không nên kỳ vọng readValue sẽ bỏ qua custom deserializer hiện tại và tự tìm bean deserializer mặc định. Nó không có ý nghĩa “gọi cách deserialize mặc định”; nó có nghĩa “deserialize giá trị tiếp theo thành kiểu này theo cấu hình hiện tại”.

Cùng vấn đề xảy ra nếu dùng annotation:

```java
@JsonDeserialize(using = AccountDeserializer.class)
public class Account {
    // properties
}
```

Dù custom deserializer được đăng ký qua annotation hay module, việc gọi lại cùng kiểu đích vẫn có thể chọn lại chính nó.

## 3. Gọi treeToValue cùng kiểu cũng có thể đệ quy

Một biến thể khác có vẻ an toàn hơn là đọc JSON thành tree rồi chuyển tree thành object:

```java
@Override
public Account deserialize(
        JsonParser parser,
        DeserializationContext context
) throws IOException {
    JsonNode root = parser.getCodec().readTree(parser);

    return parser.getCodec().treeToValue(root, Account.class);
}
```

Nhưng cách này vẫn có thể đệ quy:

- readTree đọc JSON thành JsonNode.
- treeToValue(root, Account.class) tạo quá trình deserialize từ tree.
- Kiểu đích vẫn là Account.
- Custom deserializer gắn với Account được chọn lại.
- Deserializer lại đọc tree và gọi treeToValue cùng kiểu.

Việc đã đọc hết parser ban đầu không loại bỏ vấn đề. Lần chuyển đổi từ tree tạo một luồng đọc mới nhưng vẫn chọn cùng custom deserializer cho cùng kiểu đích.

Tương tự, các cách sau có thể gây cùng lỗi nếu được gọi từ custom deserializer đang xử lý Account:

```java
mapper.readValue(parser, Account.class);
mapper.readerFor(Account.class).readValue(parser);
parser.getCodec().readValue(parser, Account.class);
parser.getCodec().treeToValue(root, Account.class);
context.readValue(parser, Account.class);
```

Đổi từ API này sang API khác không giải quyết được vòng lặp nếu kiểu đích và cấu hình deserializer vẫn giống nhau.

## 4. Dấu hiệu nhận biết đệ quy vô hạn

Các dấu hiệu thường gặp:

- Ứng dụng ném StackOverflowError trong khi JSON không sâu bất thường.
- Stack trace lặp nhiều lần cùng một custom deserializer.
- Các frame readValue, treeToValue hoặc deserialize xuất hiện lặp lại.
- Breakpoint trong custom deserializer bị gọi lại liên tục.
- Mỗi lần vào method, parser có thể vẫn ở cùng token bắt đầu object hoặc cùng vị trí dữ liệu.

Ví dụ một chuỗi stack trace rút gọn có thể trông như:

```text
AccountDeserializer.deserialize(...)
ObjectMapper.readValue(...)
AccountDeserializer.deserialize(...)
ObjectMapper.readValue(...)
AccountDeserializer.deserialize(...)
...
```

Đừng xử lý bằng cách bắt StackOverflowError rồi trả về null hoặc object mặc định. Đây là lỗi cấu trúc trong cách deserialize; bắt lỗi chỉ che giấu nguyên nhân và có thể làm dữ liệu sai đi tiếp.

## 5. Cách an toàn thứ nhất: đọc tree rồi tự tạo object

Nếu custom deserializer cần biến đổi dữ liệu, đổi tên field, áp dụng giá trị mặc định hoặc kiểm tra nhiều field cùng lúc, có thể đọc thành JsonNode rồi tự tạo object đích.

Ví dụ payload:

```json
{
  "account_id": "A-100",
  "display_name": "  Nguyen An  ",
  "active": true
}
```

Model Java:

```java
public record Account(
    String id,
    String displayName,
    boolean active
) {}
```

Deserializer:

```java
public final class AccountDeserializer
        extends StdDeserializer<Account> {

    public AccountDeserializer() {
        super(Account.class);
    }

    @Override
    public Account deserialize(
            JsonParser parser,
            DeserializationContext context
    ) throws IOException {
        JsonNode root = parser.getCodec().readTree(parser);

        if (!root.isObject()) {
            throw JsonMappingException.from(
                parser,
                "Account must be a JSON object"
            );
        }

        JsonNode idNode = root.get("account_id");
        JsonNode nameNode = root.get("display_name");
        JsonNode activeNode = root.get("active");

        if (idNode == null || !idNode.isTextual()) {
            throw JsonMappingException.from(
                parser,
                "account_id must be a string"
            );
        }

        if (nameNode == null || !nameNode.isTextual()) {
            throw JsonMappingException.from(
                parser,
                "display_name must be a string"
            );
        }

        if (activeNode == null || !activeNode.isBoolean()) {
            throw JsonMappingException.from(
                parser,
                "active must be a boolean"
            );
        }

        String id = idNode.textValue();
        String displayName = nameNode.textValue().trim();
        boolean active = activeNode.booleanValue();

        return new Account(id, displayName, active);
    }
}
```

Deserializer không yêu cầu Jackson deserialize lại Account. Nó đọc các node, kiểm tra kiểu và gọi constructor để tạo object.

Cách này phù hợp khi:

- JSON có hình dạng khác model Java.
- Cần gộp hoặc tách field.
- Cần tính giá trị từ nhiều property.
- Cần áp dụng quy tắc validation/normalization trong lúc tạo object.
- Cấu trúc payload nhỏ hoặc vừa và việc tạo tree không gây áp lực bộ nhớ đáng kể.

Với payload lớn hoặc cần xử lý tuần tự, có thể đọc token trực tiếp bằng JsonParser thay vì dựng toàn bộ tree.

### 5.1. Không gọi treeToValue về lại kiểu đích

Sau khi đọc JsonNode, tránh:

```java
return parser.getCodec().treeToValue(root, Account.class);
```

Thay vào đó, tự tạo Account như ví dụ trên hoặc chuyển tree sang một kiểu trung gian khác không gắn custom deserializer của Account.

Tree model chỉ là cách truy cập dữ liệu; nó không tự vô hiệu hóa annotation hoặc module của kiểu đích.

## 6. Cách an toàn thứ hai: dùng DTO trung gian khác kiểu đích

Nếu JSON gần giống một DTO thông thường và custom logic chỉ cần đổi một vài giá trị, có thể tạo một kiểu wire/payload riêng. Kiểu này mô tả hình dạng JSON đầu vào, còn kiểu domain là kết quả cuối cùng.

Ví dụ:

```java
public record AccountPayload(
    @JsonProperty("account_id") String id,
    @JsonProperty("display_name") String displayName,
    boolean active
) {}

public record Account(
    String id,
    String displayName,
    boolean active
) {}
```

Deserializer:

```java
public final class AccountDeserializer
        extends StdDeserializer<Account> {

    public AccountDeserializer() {
        super(Account.class);
    }

    @Override
    public Account deserialize(
            JsonParser parser,
            DeserializationContext context
    ) throws IOException {
        AccountPayload payload =
            context.readValue(parser, AccountPayload.class);

        return new Account(
            payload.id(),
            payload.displayName().trim(),
            payload.active()
        );
    }
}
```

Ở đây, context.readValue được dùng cho AccountPayload, không phải Account. Jackson tìm deserializer cho kiểu wire riêng; kiểu đó không được gắn AccountDeserializer nên không quay lại cùng method.

Cách này phù hợp khi:

- Payload có schema rõ ràng.
- Phần lớn mapping là thông thường.
- Custom logic chỉ cần chuyển đổi sau khi đọc.
- Muốn tận dụng annotation, module và validation cho DTO trung gian.

Đảm bảo DTO trung gian thực sự là kiểu khác và không vô tình được cấu hình dùng lại custom deserializer của kiểu đích.

### 6.1. Tên property có thể khác tên Java

Có thể dùng JsonProperty trên DTO trung gian để ánh xạ tên JSON:

```java
public record AccountPayload(
    @JsonProperty("account_id") String id,
    @JsonProperty("display_name") String displayName,
    boolean active
) {}
```

Không cần viết parser thủ công chỉ vì tên field JSON khác tên field Java. DTO trung gian giúp Jackson xử lý phần mapping thông thường; custom deserializer chỉ đảm nhiệm chuyển đổi nghiệp vụ.

## 7. Cách an toàn thứ ba: bọc deserializer mặc định bằng delegate

Một số yêu cầu không cần tự viết toàn bộ logic đọc JSON. Ví dụ:

- Để Jackson bind bean như bình thường.
- Sau đó trim một chuỗi.
- Chuẩn hóa mã.
- Tính một field dẫn xuất.
- Kiểm tra invariant sau khi object đã được tạo.

Trong trường hợp đó, có thể **bọc deserializer mặc định** và gọi delegate. Điểm cốt lõi là phải lấy delegate từ quá trình tạo bean mặc định, không tra cứu lại cùng kiểu đích bên trong custom deserializer.

Jackson cung cấp BeanDeserializerModifier để can thiệp deserializer bean sau khi Jackson tạo nó. Có thể bọc deserializer đó bằng DelegatingDeserializer.

### 7.1. Viết wrapper delegate

```java
public final class AccountPostProcessingDeserializer
        extends DelegatingDeserializer {

    public AccountPostProcessingDeserializer(
            JsonDeserializer<?> delegate
    ) {
        super(delegate);
    }

    @Override
    public Object deserialize(
            JsonParser parser,
            DeserializationContext context
    ) throws IOException {
        Account account = (Account) super.deserialize(parser, context);

        return new Account(
            account.id(),
            account.displayName() == null
                ? null
                : account.displayName().trim(),
            account.active()
        );
    }

    @Override
    protected DelegatingDeserializer newDelegatingInstance(
            JsonDeserializer<?> newDelegate
    ) {
        return new AccountPostProcessingDeserializer(newDelegate);
    }
}
```

super.deserialize gọi delegate đã được truyền vào constructor. Delegate là deserializer bean mặc định mà Jackson đã tạo trước khi modifier bọc nó. Nó không thực hiện một lần tra cứu mới cho cùng kiểu đích.

Method newDelegatingInstance tạo wrapper mới khi Jackson contextualize delegate. Việc hỗ trợ lifecycle này quan trọng khi deserializer phụ thuộc property, generic type hoặc context của lần mapping.

### 7.2. Đăng ký BeanDeserializerModifier

```java
SimpleModule module = new SimpleModule();

module.setDeserializerModifier(new BeanDeserializerModifier() {
    @Override
    public JsonDeserializer<?> modifyDeserializer(
            DeserializationConfig config,
            BeanDescription beanDescription,
            JsonDeserializer<?> deserializer
    ) {
        if (beanDescription.getBeanClass() == Account.class) {
            return new AccountPostProcessingDeserializer(deserializer);
        }

        return deserializer;
    }
});

ObjectMapper mapper = JsonMapper.builder()
    .addModule(module)
    .build();
```

Modifier nhận deserializer mà Jackson đã xây dựng cho bean. Với kiểu Account, nó trả về wrapper; với kiểu khác, nó giữ nguyên deserializer ban đầu.

Trong mẫu này, không đồng thời gắn @JsonDeserialize(using = AccountDeserializer.class) lên Account để thay thế deserializer. Mục tiêu là để Jackson tạo bean deserializer mặc định rồi modifier bọc nó. Nếu một custom deserializer khác đã thay thế deserializer mặc định, delegate có thể không còn là bean deserializer mà bạn định bọc.

### 7.3. Vì sao delegate tránh được đệ quy?

Luồng xử lý:

```text
Jackson tạo bean deserializer mặc định cho Account
                 │
                 ▼
BeanDeserializerModifier nhận deserializer đó
                 │
                 ▼
Tạo AccountPostProcessingDeserializer(delegate)
                 │
                 ▼
deserialize(parser)
                 │
                 ▼
super.deserialize(parser, context)
                 │
                 ▼
Delegate đọc JSON thành Account
                 │
                 ▼
Wrapper hậu xử lý Account
                 │
                 ▼
Trả kết quả
```

Wrapper không gọi lại registry để tìm AccountDeserializer. Nó giữ tham chiếu trực tiếp đến delegate đã được tạo.

DelegatingDeserializer còn hỗ trợ các hook contextualization/resolution của Jackson để chuyển tiếp cấu hình đến delegate. Nếu tự viết wrapper bằng cách chỉ giữ một field JsonDeserializer<?> và gọi nó, cần hiểu thêm lifecycle ResolvableDeserializer và ContextualDeserializer; nếu bỏ qua, các serializer/deserializer lồng nhau hoặc generic property có thể hoạt động sai.

## 8. Không dùng findContextualValueDeserializer để “né” chính mình

Một cách thử thường gặp là tìm deserializer cho cùng kiểu ngay trong custom deserializer:

```java
JsonDeserializer<Object> delegate =
    context.findContextualValueDeserializer(
        context.constructType(Account.class),
        null
    );

return (Account) delegate.deserialize(parser, context);
```

Cách này không đảm bảo lấy được bean deserializer mặc định. Nếu Account được cấu hình dùng custom deserializer hiện tại, quá trình tra cứu có thể trả lại chính deserializer đó hoặc tạo vòng tham chiếu tương đương.

Tương tự, findRootValueDeserializer và findContextualValueDeserializer là API tra cứu deserializer theo kiểu, không phải API “bỏ qua custom deserializer đang áp dụng”.

Nếu muốn delegate cho cùng kiểu bean, hãy lấy deserializer mặc định ở giai đoạn xây dựng bằng BeanDeserializerModifier, rồi bọc đối tượng được truyền vào. Nếu muốn đọc sang kiểu khác, dùng DTO trung gian. Nếu muốn tự xử lý dữ liệu, đọc tree hoặc token rồi tạo object.

## 9. Đệ quy hợp lệ với object lồng nhau cùng kiểu

Không phải mọi lần gọi lại cùng deserializer đều là lỗi. Một cấu trúc cây có thể chứa node con cùng kiểu:

```json
{
  "value": "root",
  "children": [
    {
      "value": "child-a",
      "children": []
    },
    {
      "value": "child-b",
      "children": [
        {
          "value": "grandchild",
          "children": []
        }
      ]
    }
  ]
}
```

Model:

```java
public record Node(
    String value,
    List<Node> children
) {}
```

Deserializer tùy biến cho Node có thể cần deserialize từng child thành Node:

```java
public final class NodeDeserializer extends StdDeserializer<Node> {

    public NodeDeserializer() {
        super(Node.class);
    }

    @Override
    public Node deserialize(
            JsonParser parser,
            DeserializationContext context
    ) throws IOException {
        if (parser.currentToken() != JsonToken.START_OBJECT) {
            throw JsonMappingException.from(
                parser,
                "Node must be a JSON object"
            );
        }

        String value = null;
        List<Node> children = new ArrayList<>();

        while (parser.nextToken() != JsonToken.END_OBJECT) {
            if (parser.currentToken() != JsonToken.FIELD_NAME) {
                throw JsonMappingException.from(
                    parser,
                    "Expected a field name in Node"
                );
            }

            String fieldName = parser.currentName();
            JsonToken valueToken = parser.nextToken();

            switch (fieldName) {
                case "value" -> {
                    if (valueToken != JsonToken.VALUE_STRING) {
                        throw JsonMappingException.from(
                            parser,
                            "Node value must be a string"
                        );
                    }
                    value = parser.getText();
                }
                case "children" -> {
                    if (valueToken != JsonToken.START_ARRAY) {
                        throw JsonMappingException.from(
                            parser,
                            "Node children must be an array"
                        );
                    }

                    while (parser.nextToken() != JsonToken.END_ARRAY) {
                        if (parser.currentToken() != JsonToken.START_OBJECT) {
                            throw JsonMappingException.from(
                                parser,
                                "Each child must be an object"
                            );
                        }

                        Node child = context.readValue(parser, Node.class);
                        children.add(child);
                    }
                }
                default -> parser.skipChildren();
            }
        }

        return new Node(value, children);
    }
}
```

Trong đoạn này, context.readValue(parser, Node.class) gọi cùng kiểu deserializer nhưng parser đang đứng ở START_OBJECT của một child khác. Lần gọi con xử lý subtree đó và trả về khi đã đọc xong object con. Parser của lần gọi cha tiếp tục từ vị trí sau child.

Đây là đệ quy có tiến triển:

- Mỗi lần gọi xử lý một object con nằm sâu hơn trong cây.
- Parser đi qua token của subtree con.
- Mỗi lần gọi trả về sau khi hoàn thành object được giao.
- Số lần gọi bị giới hạn bởi số node và độ sâu thực tế của JSON.

Ngược lại, gọi context.readValue(parser, Node.class) ngay tại đầu method mà không chuyển parser sang token của một child khác sẽ xử lý lại cùng object và gây đệ quy vô hạn.

### 9.1. Hợp đồng vị trí parser

Khi tự viết deserializer cho cấu trúc lồng nhau, hãy quy định rõ:

- Khi method được gọi, parser đang ở token nào.
- Method phải đọc hết cấu trúc nào.
- Khi method trả về, parser đang ở token kết thúc nào.
- Caller sẽ gọi nextToken() tiếp theo ở đâu.

Ví dụ NodeDeserializer nhận parser tại START_OBJECT và trả về khi parser đang ở END_OBJECT của node đó. Caller đọc array có thể gọi nextToken() để tới child tiếp theo hoặc END_ARRAY.

Hợp đồng này giúp tránh bỏ sót token, đọc lặp token hoặc vô tình gọi lại deserializer trên cùng dữ liệu.

## 10. Chọn giải pháp theo mục tiêu

| Mục tiêu | Cách phù hợp | Vì sao |
| --- | --- | --- |
| Đổi tên, trim hoặc chuẩn hóa vài field | DTO trung gian | Jackson bind phần thông thường, code chỉ chuyển đổi sau |
| Kiểm tra nhiều field và tự tạo object | Đọc JsonNode rồi tạo object | Không gọi lại deserializer cùng kiểu |
| Giữ bean binding mặc định rồi hậu xử lý | BeanDeserializerModifier + delegate wrapper | Delegate là deserializer mặc định đã được tạo |
| Đọc JSON lớn hoặc cần kiểm soát token | Dùng JsonParser trực tiếp | Tránh tạo toàn bộ tree |
| Đọc cấu trúc cây có child cùng kiểu | Đệ quy theo child token | Mỗi lần gọi xử lý subtree khác |
| Đọc cùng kiểu ở đúng parser position hiện tại | Không gọi lại | Sẽ tái nhập cùng deserializer |

Đừng viết custom deserializer nếu annotation, naming strategy, mix-in hoặc DTO trung gian đã giải quyết được vấn đề. Custom deserializer phù hợp khi mapping thực sự cần logic riêng.

## 11. Các lỗi tinh vi liên quan đến delegate

### 11.1. Delegate chưa được contextualize

Một số deserializer cần biết property hiện tại, kiểu generic hoặc annotation trên property. Nếu wrapper giữ delegate nhưng không chuyển tiếp contextualization, mapping có thể mất cấu hình của property.

Dùng DelegatingDeserializer thường thuận tiện vì nó hỗ trợ các interface lifecycle của Jackson. Nếu tự implement wrapper, cần xem xét:

- ResolvableDeserializer.resolve(...)
- ContextualDeserializer.createContextual(...)
- deserialize(...)
- deserialize(..., intoValue) nếu hỗ trợ update existing object
- Các method xử lý null, empty hoặc object-id nếu wrapper thay đổi hành vi liên quan

Không nên sao chép một wrapper đơn giản rồi giả định nó tương thích với mọi kiểu bean.

### 11.2. Delegate bị bọc nhiều lần

Nếu cùng một module hoặc modifier được đăng ký nhiều lần, bean deserializer có thể bị bọc nhiều lớp. Điều này không nhất thiết gây đệ quy nhưng có thể làm hậu xử lý chạy nhiều lần hoặc khiến stack trace khó đọc.

Đăng ký module một lần và tránh tạo nhiều mapper có cấu hình chồng chéo. Nếu modifier cần nhận diện wrapper đã có, hãy thiết kế điều kiện đăng ký rõ ràng.

### 11.3. Custom deserializer của property con

Một bean có thể có custom deserializer ở một property:

```java
public record Order(
    String id,
    @JsonDeserialize(using = MoneyDeserializer.class)
    Money total
) {}
```

Deserializer cho Order không nên tự deserialize lại Order chỉ để xử lý total. Jackson đã biết cách xử lý property total theo annotation riêng khi dùng bean deserializer mặc định hoặc DTO trung gian.

Nếu custom logic nằm ở Money, hãy giới hạn deserializer ở Money và không can thiệp vào kiểu cha khi không cần thiết.

### 11.4. Dùng một ObjectMapper thứ hai trong deserializer

Tạo mapper mới bên trong custom deserializer thường là dấu hiệu cấu trúc chưa rõ:

```java
ObjectMapper anotherMapper = new ObjectMapper();
return anotherMapper.readValue(parser, Account.class);
```

Mapper mới có thể không có cùng module, naming strategy, date/time module, mix-in, coercion policy hoặc visibility configuration. Nếu mapper mới cũng được cấu hình custom deserializer tương tự, lỗi đệ quy vẫn có thể xảy ra.

Hãy dùng DeserializationContext và cấu hình mapper đã được ứng dụng quản lý. Khi cần mapping sang kiểu khác, dùng DTO trung gian hoặc tree model.

## 12. Xử lý lỗi và validation đúng tầng

Custom deserializer nên báo lỗi mapping có ngữ cảnh khi JSON không đúng hình dạng mong đợi:

```java
throw JsonMappingException.from(
    parser,
    "account_id must be a non-empty string"
);
```

Không nên:

- Bắt StackOverflowError để trả về object rỗng.
- Trả về null khi gặp kiểu dữ liệu không hợp lệ mà không có hợp đồng cho phép.
- Gọi lại cùng kiểu đích để “thử cách mặc định”.
- Bỏ qua lỗi parse rồi tiếp tục tạo object thiếu field bắt buộc.

Nếu dữ liệu parse được nhưng vi phạm nghiệp vụ, có thể dùng constructor/factory hoặc validation layer để báo lỗi tương ứng. Parser/deserializer chịu trách nhiệm chuyển JSON thành Java; validation nghiệp vụ quyết định object có hợp lệ để sử dụng hay không.

## 13. Kiểm thử để phát hiện tái nhập và xác nhận delegate

Không nhất thiết phải viết một test cố tình gây StackOverflowError. Thay vào đó, kiểm tra các hành vi mong muốn của từng pattern.

### 13.1. Test custom deserializer đọc tree

```java
@Test
void readsAccountWithCustomFieldNames() throws Exception {
    String json = """
        {
          "account_id": "A-100",
          "display_name": "  Nguyen An  ",
          "active": true
        }
        """;

    Account account = mapper.readValue(json, Account.class);

    assertEquals("A-100", account.id());
    assertEquals("Nguyen An", account.displayName());
    assertTrue(account.active());
}
```

### 13.2. Test DTO trung gian

```java
@Test
void mapsWirePayloadToDomainAccount() throws Exception {
    String json = """
        {
          "account_id": "A-200",
          "display_name": "  Tran Binh  ",
          "active": false
        }
        """;

    Account account = mapper.readValue(json, Account.class);

    assertEquals("A-200", account.id());
    assertEquals("Tran Binh", account.displayName());
    assertFalse(account.active());
}
```

### 13.3. Test wrapper delegate giữ bean mapping

Nếu dùng BeanDeserializerModifier, kiểm tra:

- Các property thông thường vẫn được bind.
- Naming strategy và annotation của DTO vẫn hoạt động.
- Hậu xử lý chỉ chạy một lần.
- Property null được xử lý đúng.
- Nested bean và collection vẫn deserialize.
- Generic property và contextual serializer/deserializer vẫn được giữ.

Ví dụ test hậu xử lý:

```java
@Test
void delegatesDefaultBindingThenNormalizesName() throws Exception {
    String json = """
        {
          "id": "A-300",
          "displayName": "  Le Chi  ",
          "active": true
        }
        """;

    Account account = mapper.readValue(json, Account.class);

    assertEquals("A-300", account.id());
    assertEquals("Le Chi", account.displayName());
    assertTrue(account.active());
}
```

### 13.4. Test cây lồng nhau

Với NodeDeserializer, test root có nhiều child và grandchild. Kiểm tra số node, thứ tự child và giá trị ở từng cấp. Điều này chứng minh recursive call đang xử lý các subtree khác nhau và parser được tiêu thụ đúng.

### 13.5. Test dữ liệu sai

Test các trường hợp:

- Root là scalar thay vì object.
- Field bắt buộc bị thiếu.
- Field có sai token type.
- Child trong array không phải object.
- Array con không kết thúc đúng do JSON lỗi.
- Payload có nesting quá sâu theo giới hạn ứng dụng.

Với dữ liệu lồng nhau từ nguồn không đáng tin cậy, cần có giới hạn độ sâu và kích thước ở tầng parser/server phù hợp. Đệ quy hợp lệ vẫn có thể làm stack tăng theo độ sâu của cây; tránh để input không giới hạn gây cạn tài nguyên.

## 14. Quy trình chẩn đoán và sửa lỗi

Khi gặp stack overflow trong custom deserializer:

1. Tìm frame đầu tiên thuộc code ứng dụng trong stack trace.
2. Xác định target type mà method đang deserialize.
3. Tìm các lệnh readValue, treeToValue, readerFor hoặc context.readValue.
4. Kiểm tra target type của lệnh đó có chính là kiểu custom deserializer đang xử lý không.
5. Kiểm tra parser đang ở token nào khi gọi lại.
6. Nếu cần mapping thông thường, đổi sang DTO trung gian.
7. Nếu cần tự kiểm tra cấu trúc, đọc tree hoặc token rồi tự tạo object.
8. Nếu chỉ hậu xử lý bean mặc định, dùng BeanDeserializerModifier và delegate.
9. Nếu là cấu trúc recursive thật, bảo đảm mỗi lần gọi xử lý một child subtree khác và parser tiến đúng.
10. Viết test cho payload bình thường, nested payload và dữ liệu sai.

Khi sửa xong, chạy test trên mapper thực tế của ứng dụng. Một unit test dùng mapper mới có thể không tái hiện module, mix-in hoặc custom deserializer mà Spring Boot hay framework đã đăng ký.

## 15. Bài thực hành tổng hợp

Tạo model:

```java
public record Account(
    String id,
    String displayName,
    boolean active
) {}
```

Payload sử dụng tên field khác:

```json
{
  "account_id": "A-100",
  "display_name": "  Nguyen An  ",
  "active": true
}
```

Thực hiện:

1. Viết custom deserializer cho Account.
2. Thử gọi readValue(parser, Account.class) từ bên trong deserializer và quan sát cơ chế chọn lại cùng deserializer; không dùng cách này trong ứng dụng.
3. Thử đọc JsonNode, tự kiểm tra ba field và tạo Account.
4. Tạo AccountPayload riêng với JsonProperty.
5. Dùng context.readValue(parser, AccountPayload.class) rồi chuyển thành Account.
6. Tạo BeanDeserializerModifier để bọc bean deserializer mặc định.
7. Hậu xử lý displayName bằng DelegatingDeserializer.
8. So sánh code và phạm vi trách nhiệm của ba cách.
9. Tạo model Node có danh sách child cùng kiểu.
10. Viết deserializer đọc child bằng context.readValue(parser, Node.class) khi parser đang ở token bắt đầu object con.
11. Kiểm tra root, child và grandchild để phân biệt recursive traversal hợp lệ với gọi lại cùng token.
12. Viết test cho field thiếu, sai kiểu, object rỗng và nesting sâu.

Bài thực hành hoàn thành khi có thể giải thích vì sao cùng một kiểu deserializer được gọi cho child node là hợp lệ, còn gọi lại nó trên cùng giá trị hiện tại là đệ quy vô hạn.

## 16. Nguyên tắc ghi nhớ

- Jackson chọn deserializer theo kiểu Java đích và cấu hình annotation/module hiện tại.
- Trong custom deserializer, gọi readValue cùng kiểu đích thường chọn lại chính custom deserializer.
- treeToValue(root, SameType.class) cũng có thể gọi lại deserializer đó dù dữ liệu đã được đọc thành tree.
- Đổi sang ObjectReader, ObjectMapper hoặc DeserializationContext không tự động bỏ qua custom deserializer.
- Nếu tự xử lý, đọc JsonNode hoặc token rồi tạo object đích trực tiếp.
- Nếu cần bind phần lớn field theo cách mặc định, dùng DTO trung gian có kiểu khác.
- Nếu chỉ cần hậu xử lý bean mặc định, bọc delegate lấy từ BeanDeserializerModifier.
- DelegatingDeserializer giúp chuyển tiếp lifecycle contextualization/resolution cho delegate.
- Đệ quy cùng kiểu là hợp lệ khi mỗi lần xử lý một subtree con riêng và parser tiến về phía trước.
- Hợp đồng vị trí parser đầu vào/đầu ra của mỗi helper phải rõ ràng.
- Không bắt StackOverflowError để che lỗi cấu trúc; sửa vòng gọi deserializer.
- Kiểm thử mapper thực tế, nested data, dữ liệu sai và giới hạn độ sâu.

Khi viết custom deserializer, hãy xác định rõ ai chịu trách nhiệm đọc JSON thành kiểu đích. Đừng yêu cầu Jackson đọc lại cùng kiểu từ bên trong chính deserializer đó. Hãy tự tạo object, chuyển qua DTO trung gian hoặc bọc bean deserializer mặc định bằng delegate; chỉ dùng lời gọi đệ quy cùng kiểu khi parser đã tiến tới một subtree con khác.
