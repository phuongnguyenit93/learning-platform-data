# Giới hạn kiểu được phép khi dùng thông tin kiểu từ dữ liệu ngoài

Jackson hỗ trợ polymorphic deserialization: JSON có thể mang một type identifier để cho biết cần tạo subtype Java nào. Tính năng này hữu ích khi một thuộc tính được khai báo bằng interface, abstract class hoặc kiểu cha nhưng payload có thể chứa nhiều biến thể.

Khi type identifier đến từ request, message broker, file hoặc hệ thống bên ngoài, nó là dữ liệu không đáng tin cậy. Nếu để payload tự chọn tên class Java một cách rộng rãi, ứng dụng có thể vô tình cho phép tạo những lớp không nằm trong mô hình nghiệp vụ dự kiến. Vì vậy, cần giới hạn subtype bằng một allowlist rõ ràng, ưu tiên tên kiểu logic thay cho tên class và tránh bật default typing toàn cục nếu không thật sự cần.

## 1. Polymorphic deserialization là gì?

Giả sử hệ thống có nhiều phương thức thanh toán. Các phương thức có chung một kiểu cha nhưng chứa các trường khác nhau:

- Thanh toán bằng thẻ có cardToken.
- Chuyển khoản có bankCode và accountNumber.

Một DTO có thể khai báo:

~~~java
public class PaymentRequest {
    private PaymentMethod method;

    public PaymentMethod getMethod() {
        return method;
    }

    public void setMethod(PaymentMethod method) {
        this.method = method;
    }
}
~~~

Nếu chỉ biết kiểu khai báo là PaymentMethod, Jackson không thể tự suy ra nên tạo CardPayment hay BankTransfer nếu payload không có quy tắc phân biệt.

Polymorphic deserialization bổ sung type information để xác định subtype:

~~~json
{
  "method": {
    "kind": "card",
    "cardToken": "tok_123"
  }
}
~~~

Giá trị kind là một type identifier. Jackson dùng nó để chọn lớp Java đã được đăng ký tương ứng, rồi ánh xạ các property còn lại.

Luồng xử lý:

~~~text
JSON từ bên ngoài
       |
       v
Đọc type identifier: "card"
       |
       v
Tra cứu subtype được phép
       |
       +----> Không nằm trong allowlist: từ chối
       |
       v
Tạo CardPayment
       |
       v
Ánh xạ các field và trả object
~~~

Type identifier chỉ nên chọn một kiểu đã được ứng dụng cho phép. Nó không nên trở thành chỉ dẫn để tải hoặc khởi tạo tùy ý bất kỳ class nào có mặt trên classpath.

## 2. Ưu tiên logical type name với Id.NAME

Cách an toàn và dễ kiểm soát thường là dùng tên logic như card hoặc bank-transfer thay vì tên class đầy đủ.

Khai báo trên kiểu cha:

~~~java
import com.fasterxml.jackson.annotation.JsonSubTypes;
import com.fasterxml.jackson.annotation.JsonTypeInfo;

@JsonTypeInfo(
    use = JsonTypeInfo.Id.NAME,
    include = JsonTypeInfo.As.PROPERTY,
    property = "kind"
)
@JsonSubTypes({
    @JsonSubTypes.Type(value = CardPayment.class, name = "card"),
    @JsonSubTypes.Type(value = BankTransfer.class, name = "bank-transfer")
})
public interface PaymentMethod {
}
~~~

Các subtype:

~~~java
public final class CardPayment implements PaymentMethod {
    private String cardToken;

    public CardPayment() {
    }

    public String getCardToken() {
        return cardToken;
    }

    public void setCardToken(String cardToken) {
        this.cardToken = cardToken;
    }
}

public final class BankTransfer implements PaymentMethod {
    private String bankCode;
    private String accountNumber;

    public BankTransfer() {
    }

    public String getBankCode() {
        return bankCode;
    }

    public void setBankCode(String bankCode) {
        this.bankCode = bankCode;
    }

    public String getAccountNumber() {
        return accountNumber;
    }

    public void setAccountNumber(String accountNumber) {
        this.accountNumber = accountNumber;
    }
}
~~~

JSON hợp lệ:

~~~json
{
  "method": {
    "kind": "card",
    "cardToken": "tok_123"
  }
}
~~~

Hoặc:

~~~json
{
  "method": {
    "kind": "bank-transfer",
    "bankCode": "VCB",
    "accountNumber": "001234"
  }
}
~~~

Danh sách trong JsonSubTypes là allowlist tường minh cho kiểu PaymentMethod. Payload chỉ chọn được các logical name đã được khai báo.

### 2.1. Đăng ký subtype bằng ObjectMapper

Thay vì annotation JsonSubTypes, có thể đăng ký subtype bằng mapper:

~~~java
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.jsontype.NamedType;

ObjectMapper mapper = new ObjectMapper();

mapper.registerSubtypes(
    new NamedType(CardPayment.class, "card"),
    new NamedType(BankTransfer.class, "bank-transfer")
);
~~~

Kiểu cha vẫn cần khai báo metadata polymorphic tương ứng, ví dụ JsonTypeInfo với Id.NAME. Cách đăng ký bằng code hữu ích khi danh sách subtype được cấu hình tập trung hoặc do module quản lý.

Không nên vừa đăng ký nhiều nơi vừa dùng các tên logic mâu thuẫn. Hãy duy trì một nguồn allowlist rõ ràng để reviewer có thể biết chính xác kiểu nào được tạo từ dữ liệu ngoài.

### 2.2. Dùng JsonTypeName để đặt tên cho subtype

Có thể đặt logical name ngay trên subtype:

~~~java
import com.fasterxml.jackson.annotation.JsonTypeName;

@JsonTypeName("card")
public final class CardPayment implements PaymentMethod {
    // ...
}
~~~

JsonTypeName đặt tên logic cho kiểu, còn Jackson vẫn cần biết subtype đó thuộc hierarchy được phép, chẳng hạn thông qua JsonSubTypes hoặc registerSubtypes. Chỉ đặt JsonTypeName không nên được xem là cơ chế tự động quét và cho phép mọi lớp trong ứng dụng.

## 3. Giới hạn polymorphism ở đúng thuộc tính

Không phải mọi property của một DTO đều cần polymorphic typing. Nếu chỉ trường method có nhiều biến thể, có thể đặt JsonTypeInfo trên property thay vì toàn bộ kiểu cha:

~~~java
public class PaymentRequest {
    @JsonTypeInfo(
        use = JsonTypeInfo.Id.NAME,
        include = JsonTypeInfo.As.PROPERTY,
        property = "kind"
    )
    @JsonSubTypes({
        @JsonSubTypes.Type(value = CardPayment.class, name = "card"),
        @JsonSubTypes.Type(value = BankTransfer.class, name = "bank-transfer")
    })
    private PaymentMethod method;

    public PaymentMethod getMethod() {
        return method;
    }

    public void setMethod(PaymentMethod method) {
        this.method = method;
    }
}
~~~

Cách này giới hạn type metadata vào một vị trí cụ thể. Nó hữu ích khi cùng một interface được sử dụng ở nhiều nơi nhưng chỉ một số property được phép nhận subtype động.

Nếu quy tắc áp dụng nhất quán cho mọi nơi dùng PaymentMethod, khai báo trên kiểu cha có thể rõ ràng hơn. Dù chọn vị trí nào, danh sách subtype phải được giới hạn và quản lý như một phần của hợp đồng dữ liệu.

## 4. Điều gì xảy ra khi payload gửi type identifier không hợp lệ?

Giả sử allowlist chỉ có card và bank-transfer nhưng payload gửi:

~~~json
{
  "method": {
    "kind": "admin-command",
    "command": "..."
  }
}
~~~

Jackson không tìm được subtype có tên admin-command. Với cấu hình thông thường, nó từ chối deserialize và thường phát sinh InvalidTypeIdException (thuộc nhóm JsonMappingException).

Có thể kiểm tra bằng test:

~~~java
import static org.junit.jupiter.api.Assertions.assertThrows;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.exc.InvalidTypeIdException;
import org.junit.jupiter.api.Test;

class PaymentPolymorphismTest {
    private final ObjectMapper mapper = new ObjectMapper();

    @Test
    void rejectsUnknownTypeId() {
        String json = """
            {
              "method": {
                "kind": "admin-command"
              }
            }
            """;

        assertThrows(
            InvalidTypeIdException.class,
            () -> mapper.readValue(json, PaymentRequest.class)
        );
    }
}
~~~

Đừng biến type identifier không biết thành một subtype mặc định nếu việc đó khiến payload sai hợp đồng vẫn được chấp nhận âm thầm. Chỉ dùng defaultImpl khi fallback có ý nghĩa nghiệp vụ cụ thể, giới hạn rõ ràng và được kiểm thử.

Cũng không nên tắt FAIL_ON_INVALID_SUBTYPE chỉ để tránh exception. Khi subtype không hợp lệ, ứng dụng cần một kết quả có chủ đích: từ chối request, chuyển thành lỗi validation hoặc xử lý theo một fallback đã được thiết kế.

## 5. Tránh Id.CLASS và Id.MINIMAL_CLASS với dữ liệu ngoài

Jackson có các chiến lược type identifier khác nhau:

| Id strategy | Nội dung type identifier | Nhận xét |
|---|---|---|
| Id.NAME | Tên logic như card | Dễ giới hạn bằng danh sách subtype được đăng ký |
| Id.CLASS | Tên class Java đầy đủ | Để dữ liệu ngoài chỉ định tên lớp trên classpath |
| Id.MINIMAL_CLASS | Tên class rút gọn tương đối với package | Vẫn dựa vào class name, không phải allowlist logic |
| Id.DEDUCTION | Suy luận subtype từ tập property | Không nhận class name, nhưng có thể mơ hồ nếu các subtype có cấu trúc giống nhau |
| Id.CUSTOM | Giá trị do TypeIdResolver định nghĩa | Có thể an toàn nếu resolver dùng registry allowlist và từ chối mọi tên khác |

Ví dụ không nên dùng cho dữ liệu không đáng tin cậy:

~~~java
@JsonTypeInfo(
    use = JsonTypeInfo.Id.CLASS,
    include = JsonTypeInfo.As.PROPERTY,
    property = "@class"
)
private Object payload;
~~~

Với Id.CLASS, type identifier có thể chứa tên class Java. Nếu cấu hình cho phép, dữ liệu đầu vào có thể yêu cầu Jackson tạo một lớp khác với kiểu cụ thể mà ứng dụng dự định nhận.

Rủi ro không chỉ nằm ở lớp hiện tại. Classpath của ứng dụng có thể chứa thư viện với các lớp có hành vi phụ khi được khởi tạo hoặc khi property được bind. Một số chuỗi gadget trong thư viện có thể dẫn đến tác động không mong muốn. Khả năng khai thác cụ thể phụ thuộc lớp có mặt, phiên bản thư viện, base type, validator và cấu hình; không nên coi việc chỉ dùng Jackson là bằng chứng rằng mọi class name đều an toàn.

Với hợp đồng JSON do bên ngoài kiểm soát, ưu tiên Id.NAME và allowlist subtype. Tránh Id.CLASS/Id.MINIMAL_CLASS, đặc biệt khi base type là Object hoặc một kiểu rất rộng.

## 6. Default typing là cấu hình có phạm vi toàn mapper

Jackson có cơ chế default typing để tự thêm type metadata cho các kiểu được chọn, kể cả khi model không khai báo JsonTypeInfo trên từng property.

Ví dụ API:

~~~java
mapper.activateDefaultTyping(
    validator,
    ObjectMapper.DefaultTyping.NON_FINAL,
    JsonTypeInfo.As.PROPERTY
);
~~~

Cấu hình này ảnh hưởng đến một tập kiểu rộng theo chính sách DefaultTyping. Nếu bật cho mapper xử lý request bên ngoài, type metadata có thể được áp dụng ở nhiều vị trí hơn dự kiến, bao gồm những property không được thiết kế như polymorphic contract.

Một số lựa chọn DefaultTyping thường gặp:

| Lựa chọn | Phạm vi khái quát |
|---|---|
| JAVA_LANG_OBJECT | Các property có kiểu khai báo Object |
| OBJECT_AND_NON_CONCRETE | Object và các kiểu khai báo abstract/interface |
| NON_CONCRETE_AND_ARRAYS | Kiểu không concrete và array tương ứng |
| NON_FINAL | Phần lớn kiểu không final |
| EVERYTHING | Phạm vi rất rộng, bao gồm cả những kiểu khác |

Tên và phạm vi chi tiết cần đối chiếu với phiên bản Jackson đang dùng. Điểm cần nhớ là các lựa chọn như NON_FINAL hoặc EVERYTHING có thể làm thay đổi định dạng JSON trên diện rộng và tăng số vị trí mà type id từ payload tham gia vào quá trình tạo object.

Với API mới, thường dễ kiểm soát hơn nếu đánh dấu polymorphism trên đúng interface hoặc property cần nhiều subtype, thay vì bật default typing toàn cục.

## 7. PolymorphicTypeValidator khi thật sự cần default typing

Từ Jackson 2.10, default typing sử dụng PolymorphicTypeValidator để quyết định subtype nào được phép. Với Jackson 2.x, BasicPolymorphicTypeValidator cung cấp cách xây dựng chính sách theo base type hoặc subtype.

Ví dụ minh họa một allowlist hẹp cho hai lớp subtype final:

~~~java
import com.fasterxml.jackson.annotation.JsonTypeInfo;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.jsontype.BasicPolymorphicTypeValidator;
import com.fasterxml.jackson.databind.json.JsonMapper;

BasicPolymorphicTypeValidator validator =
    BasicPolymorphicTypeValidator.builder()
        .allowIfSubType(CardPayment.class)
        .allowIfSubType(BankTransfer.class)
        .build();

ObjectMapper mapper = JsonMapper.builder()
    .activateDefaultTyping(
        validator,
        ObjectMapper.DefaultTyping.OBJECT_AND_NON_CONCRETE,
        JsonTypeInfo.As.PROPERTY
    )
    .build();
~~~

Các lớp trong ví dụ là final để không mở rộng allowlist qua các subclass tùy ý. Validator cần được thiết kế theo toàn bộ kiểu polymorphic mà mapper thực sự phải xử lý; nếu ứng dụng có nhiều hierarchy khác nhau, một allowlist chỉ gồm hai lớp trên sẽ khiến các kiểu còn lại bị từ chối.

BasicPolymorphicTypeValidator có các cách match theo class, base type hoặc tên package/prefix. Cho phép cả package rộng có nghĩa là mọi lớp phù hợp với điều kiện đó có thể được chấp nhận; chỉ nên dùng package prefix nếu package được dành riêng cho các subtype tin cậy và được kiểm soát chặt.

Ví dụ trên minh họa cách đặt validator, không phải khuyến nghị bật default typing toàn cục cho mọi request. Nếu chỉ cần hai biến thể PaymentMethod, Id.NAME cùng danh sách subtype tường minh thường đơn giản và dễ audit hơn.

### 7.1. Đừng dùng LaissezFaireSubTypeValidator cho input không tin cậy

Một số ví dụ cũ dùng LaissezFaireSubTypeValidator để cho phép subtype mà không có allowlist hữu ích. Đây không phải lựa chọn phù hợp cho dữ liệu bên ngoài.

Validator phải trả lời câu hỏi: "Subtype cụ thể này có nằm trong tập lớp mà ứng dụng chủ động cho phép không?" Nếu câu trả lời chỉ là "lớp đó tồn tại và có thể gán vào base type", chính sách đang quá rộng cho một ranh giới tin cậy.

### 7.2. Allowlist theo package có giới hạn

Một package prefix như com.example.dto.safe có thể tiện khi có nhiều subtype. Tuy nhiên, nếu developer thêm một class mới vào package đó, class mới có thể tự động lọt vào allowlist mà không có thay đổi tại nơi cấu hình bảo mật.

Vì vậy:

- Ưu tiên đăng ký từng subtype khi số lượng nhỏ và hợp đồng ổn định.
- Nếu dùng package allowlist, dành package riêng chỉ chứa kiểu dữ liệu an toàn.
- Review mọi class mới được thêm vào package được tin cậy.
- Không cho phép package chung như java., org. hoặc com. chỉ vì chúng chứa các DTO cần dùng.
- Kiểm thử rằng class ngoài allowlist bị từ chối.

## 8. Dùng TypeIdResolver với registry đóng

Khi cần quy tắc ánh xạ type name tùy chỉnh, có thể dùng TypeIdResolver. Resolver nên tra cứu trong một registry tĩnh hoặc registry do ứng dụng kiểm soát.

Ví dụ ý tưởng registry:

~~~java
private static final Map<String, Class<? extends PaymentMethod>> ALLOWED_TYPES =
    Map.of(
        "card", CardPayment.class,
        "bank-transfer", BankTransfer.class
    );
~~~

Resolver chỉ được trả về kiểu khi id nằm trong map. Với id không tồn tại, phải báo lỗi thay vì nối chuỗi để tạo tên class, gọi Class.forName hoặc tìm class tùy ý.

Các nguyên tắc cho resolver:

1. Dùng tên logic ổn định.
2. Duy trì map id -> subtype tường minh.
3. Từ chối id null, rỗng hoặc không biết.
4. Không suy ra class name từ input.
5. Không dùng reflection để tải lớp tùy ý.
6. Kiểm tra subtype thuộc đúng base type và được phép trong registry.

TypeIdResolver hữu ích khi type ID có quy tắc tương thích phức tạp, nhưng nó không tự an toàn. Toàn bộ bảo mật phụ thuộc cách resolver tra cứu và từ chối đầu vào.

## 9. Id.DEDUCTION không phải cơ chế cho phép class tùy ý

Một lựa chọn khác là để Jackson suy luận subtype từ các property có trong JSON:

~~~java
@JsonTypeInfo(use = JsonTypeInfo.Id.DEDUCTION)
@JsonSubTypes({
    @JsonSubTypes.Type(CardPayment.class),
    @JsonSubTypes.Type(BankTransfer.class)
})
public interface PaymentMethod {
}
~~~

Payload không cần trường kind:

~~~json
{
  "cardToken": "tok_123"
}
~~~

Jackson xem tập property để xác định subtype phù hợp trong tập đã biết. Cách này không yêu cầu payload gửi tên class, nhưng vẫn cần danh sách subtype được đăng ký.

Hạn chế:

- Nếu các subtype có property trùng nhau hoặc payload thiếu trường phân biệt, Jackson có thể không suy luận được.
- Thêm field vào subtype có thể ảnh hưởng khả năng phân biệt.
- Schema trở nên khó đọc hơn vì không có discriminator tường minh.
- Nó không thay thế validation dữ liệu sau khi chọn subtype.

Dùng deduction khi cấu trúc các biến thể thực sự phân biệt rõ và hợp đồng không cần discriminator. Với API public, một logical discriminator như kind thường dễ tài liệu hóa và ổn định hơn.

## 10. Type metadata không phải validation nghiệp vụ

Allowlist chỉ giới hạn class nào được tạo. Nó không chứng minh dữ liệu của subtype đó hợp lệ.

Ví dụ kind = card được phép, nhưng cardToken có thể rỗng, sai định dạng hoặc thuộc một tài khoản không được phép sử dụng.

Sau khi deserialize, vẫn cần xác thực:

~~~java
public void validate(PaymentMethod method) {
    if (method instanceof CardPayment card) {
        if (card.getCardToken() == null
                || card.getCardToken().isBlank()) {
            throw new IllegalArgumentException("cardToken is required");
        }
    } else if (method instanceof BankTransfer transfer) {
        if (transfer.getBankCode() == null
                || transfer.getBankCode().isBlank()) {
            throw new IllegalArgumentException("bankCode is required");
        }

        if (transfer.getAccountNumber() == null
                || transfer.getAccountNumber().isBlank()) {
            throw new IllegalArgumentException("accountNumber is required");
        }
    }
}
~~~

Trong ứng dụng thực tế, có thể dùng Bean Validation hoặc validator ở tầng service/domain. Cần phân biệt:

- **Subtype allowlist:** kiểu Java nào được phép tạo?
- **Deserialization validation:** property có đúng kiểu và cấu trúc không?
- **Business validation:** giá trị có hợp lệ theo nghiệp vụ không?
- **Authorization:** người gửi có quyền thực hiện hành động tương ứng không?

Không thay thế một lớp kiểm tra bằng lớp khác. Một payload có subtype hợp lệ vẫn có thể chứa dữ liệu nguy hiểm hoặc không được phép theo nghiệp vụ.

## 11. Giới hạn dữ liệu polymorphic trong các kiểu rộng

Đặc biệt cẩn thận với các property khai báo kiểu Object:

~~~java
public class Message {
    private Object payload;

    public Object getPayload() {
        return payload;
    }

    public void setPayload(Object payload) {
        this.payload = payload;
    }
}
~~~

Object cho phép rất nhiều kiểu Java. Nếu bật default typing hoặc chấp nhận class name từ input ở đây, phạm vi lựa chọn kiểu có thể quá rộng.

Nếu schema đã biết, thay Object bằng kiểu cụ thể hoặc interface có subtype allowlist:

~~~java
public class Message {
    private PaymentMethod payload;

    public PaymentMethod getPayload() {
        return payload;
    }

    public void setPayload(PaymentMethod payload) {
        this.payload = payload;
    }
}
~~~

Cách khai báo này thu hẹp hierarchy và giúp Jackson áp dụng metadata chỉ cho các kiểu đã được thiết kế.

Nếu thật sự cần một trường JSON động, dùng JsonNode hoặc Map<String, JsonNode> thường giữ dữ liệu dưới dạng JSON tree mà không yêu cầu Jackson tạo class tùy ý.

## 12. Xử lý unknown type id có chủ đích

Có ba tình huống cần phân biệt:

| Tình huống | Hành vi nên cân nhắc |
|---|---|
| Type id nằm trong allowlist | Deserialize subtype tương ứng |
| Type id không biết hoặc bị giả mạo | Từ chối với lỗi mapping rõ ràng |
| Hệ thống cần forward subtype tương lai mà chưa hiểu | Giữ raw JSON/JsonNode hoặc envelope trung gian |

Nếu muốn forward dữ liệu chưa biết, không nhất thiết phải tạo một Java subtype giả. Có thể giữ phần JSON chưa biết dưới dạng JsonNode hoặc raw payload trong một lớp envelope, sau đó chuyển tiếp theo chính sách rõ ràng.

Không nên dùng defaultImpl chung cho mọi type id lạ nếu nó làm mất thông tin discriminator hoặc khiến một payload sai cấu trúc được xem như subtype hợp lệ. Nếu có UnknownPayment riêng, nó cần được thiết kế như một kiểu dữ liệu an toàn, không thực thi hành vi nhạy cảm, và phải giữ lại đủ dữ liệu cần thiết nếu mục tiêu là forward.

## 13. Kiểm thử allowlist

Một bộ test nên bao gồm cả subtype được phép và subtype bị từ chối.

~~~java
import static org.junit.jupiter.api.Assertions.assertInstanceOf;
import static org.junit.jupiter.api.Assertions.assertThrows;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.exc.InvalidTypeIdException;
import org.junit.jupiter.api.Test;

class PaymentTypeAllowlistTest {
    private final ObjectMapper mapper = new ObjectMapper();

    @Test
    void acceptsRegisteredSubtype() throws Exception {
        PaymentRequest request = mapper.readValue(
            """
            {
              "method": {
                "kind": "card",
                "cardToken": "tok_123"
              }
            }
            """,
            PaymentRequest.class
        );

        assertInstanceOf(CardPayment.class, request.getMethod());
    }

    @Test
    void rejectsUnregisteredSubtype() {
        String json = """
            {
              "method": {
                "kind": "admin-command"
              }
            }
            """;

        assertThrows(
            InvalidTypeIdException.class,
            () -> mapper.readValue(json, PaymentRequest.class)
        );
    }
}
~~~

Ngoài hai test cơ bản, nên có:

- Test serialize subtype thành logical type ID dự kiến.
- Test type id sai chữ hoa/chữ thường nếu hợp đồng phân biệt.
- Test thiếu discriminator.
- Test type id null hoặc rỗng.
- Test payload có field không hợp lệ bên trong subtype hợp lệ.
- Test class không nằm trong package/allowlist.
- Test khi thêm subtype mới để bảo đảm thay đổi registry có chủ đích.

Test bảo mật nên xác nhận các kiểu không được phép bị từ chối trước khi logic nghiệp vụ chạy.

## 14. Các nguyên tắc triển khai an toàn

Khi dữ liệu ngoài chứa type information, áp dụng các nguyên tắc sau:

1. Ưu tiên JsonTypeInfo.Id.NAME với discriminator có ý nghĩa nghiệp vụ.
2. Khai báo subtype bằng JsonSubTypes hoặc registerSubtypes; giữ registry nhỏ và tường minh.
3. Tránh Id.CLASS và Id.MINIMAL_CLASS cho payload không tin cậy.
4. Không bật default typing toàn cục nếu chỉ một vài property cần polymorphism.
5. Nếu bắt buộc dùng default typing, cung cấp PolymorphicTypeValidator với allowlist hẹp.
6. Tránh LaissezFaireSubTypeValidator hoặc validator cho phép mọi subtype.
7. Không cho input điều khiển Class.forName, tên package hoặc classloader.
8. Không dùng Object cho payload nếu có thể khai báo base interface cụ thể.
9. Từ chối unknown type id trừ khi có một fallback an toàn được thiết kế rõ.
10. Xác thực field, kích thước, độ sâu và quyền nghiệp vụ sau khi chọn subtype.
11. Dùng phiên bản Jackson được cập nhật bảo mật và giữ các module cùng major/version tương thích.
12. Kiểm thử cả kiểu hợp lệ, kiểu ngoài allowlist và các biến thể payload lỗi.

## 15. Ghi nhớ

- Polymorphic deserialization dùng type identifier để chọn subtype của interface hoặc abstract class.
- Dữ liệu type id từ bên ngoài là input không đáng tin cậy; nó phải được kiểm tra trước khi tạo subtype.
- Ưu tiên Id.NAME và logical discriminator như card hoặc bank-transfer.
- JsonSubTypes hoặc registerSubtypes xác định tập subtype mà ứng dụng chủ động hỗ trợ.
- Tránh Id.CLASS/Id.MINIMAL_CLASS khi payload bên ngoài có thể điều khiển tên class.
- Default typing có phạm vi rộng; nếu bắt buộc dùng, giới hạn bằng PolymorphicTypeValidator allowlist hẹp.
- Không coi package prefix rộng hoặc LaissezFaireSubTypeValidator là allowlist an toàn.
- Unknown type id nên bị từ chối hoặc được giữ dưới dạng JSON thô theo một chính sách forward rõ ràng.
- Allowlist chỉ kiểm soát class được tạo; vẫn cần validation dữ liệu và authorization nghiệp vụ.

