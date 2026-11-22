# Tránh cho dữ liệu ngoài tự do lựa chọn lớp Java để khởi tạo

Khi Jackson đọc JSON vào một kiểu Java cụ thể, ứng dụng thường biết trước class đích. Nhưng trong mô hình đa hình, property có thể khai báo là interface hoặc lớp cha, trong khi JSON chứa dữ liệu của nhiều lớp con. Jackson cần một cách xác định subtype để tạo đúng object. Nếu type information cho phép dữ liệu đầu vào cung cấp tên lớp Java tùy ý, một nguồn JSON không đáng tin cậy có thể tác động đến lớp được khởi tạo trong ứng dụng.

Đây là một ranh giới bảo mật quan trọng. **Dữ liệu ngoài chỉ nên chọn trong tập subtype mà ứng dụng đã cho phép rõ ràng; dữ liệu không được quyền yêu cầu Jackson nạp và khởi tạo một lớp bất kỳ trên classpath.** Trong Jackson, cách thiết kế an toàn thường là dùng type ID logic như user-created hoặc order-paid, ánh xạ chúng tới một danh sách subtype được đăng ký trước. Tránh dùng tên class do client cung cấp, tránh bật default typing rộng cho JSON không tin cậy và từ chối type ID không nằm trong allowlist.

Bài học này tập trung vào bảo mật đầu vào trong Data Serialization Jackson: cách polymorphic deserialization hoạt động, vì sao việc để JSON lựa chọn class tùy ý nguy hiểm, cách giới hạn subtype, vai trò của PolymorphicTypeValidator khi không thể loại bỏ default typing và cách kiểm thử ranh giới tin cậy.

## 1. Vì sao Jackson cần thông tin subtype?

Giả sử một hệ thống nhận nhiều loại command:

~~~java
public interface IncomingCommand {
}
~~~

Các command cụ thể:

~~~java
public final class CreateAccount implements IncomingCommand {
    private String username;

    public CreateAccount() {
    }

    public String getUsername() {
        return username;
    }

    public void setUsername(String username) {
        this.username = username;
    }
}

public final class DisableAccount implements IncomingCommand {
    private String accountId;

    public DisableAccount() {
    }

    public String getAccountId() {
        return accountId;
    }

    public void setAccountId(String accountId) {
        this.accountId = accountId;
    }
}
~~~

Property hoặc API có thể khai báo kiểu cha:

~~~java
IncomingCommand command = mapper.readValue(json, IncomingCommand.class);
~~~

Chỉ nhìn vào IncomingCommand, Jackson không biết phải tạo CreateAccount hay DisableAccount. Một cơ chế đa hình cần cung cấp discriminator hoặc một quy tắc khác để xác định subtype.

JSON có thể mang một type ID logic:

~~~json
{
  "kind": "create-account",
  "username": "an"
}
~~~

Hoặc:

~~~json
{
  "kind": "disable-account",
  "accountId": "acct-42"
}
~~~

Ứng dụng có thể ánh xạ create-account sang CreateAccount và disable-account sang DisableAccount. Điều quan trọng là mapping này do code ứng dụng định nghĩa trước. JSON chỉ chọn một tên trong tập lựa chọn đã được cho phép.

## 2. Rủi ro khi JSON điều khiển tên class Java

Jackson hỗ trợ nhiều kiểu type ID. Một số cơ chế có thể đưa tên lớp Java vào JSON, chẳng hạn:

- JsonTypeInfo.Id.CLASS: type ID là tên class đầy đủ.
- JsonTypeInfo.Id.MINIMAL_CLASS: type ID là tên class rút gọn tương đối với package của kiểu cơ sở.
- Default typing: mapper tự thêm/đọc type metadata cho nhiều kiểu dựa trên cấu hình toàn cục.

Nếu ứng dụng đọc một class name từ JSON rồi cho phép nó quyết định lớp cần khởi tạo, dữ liệu ngoài đã tác động trực tiếp tới quá trình tạo object. Classpath của ứng dụng thường chứa nhiều lớp từ framework và dependency. Một số lớp có constructor, setter, factory hoặc callback có tác dụng phụ khi được tạo hay gán property. Trong các điều kiện phù hợp, kẻ tấn công có thể khai thác một chuỗi lớp và hành vi có sẵn để tạo gadget chain.

Một gadget chain là tổ hợp các lớp có sẵn trong runtime mà quá trình deserialize có thể kích hoạt theo cách dẫn tới hành vi nguy hiểm. Rủi ro phụ thuộc vào phiên bản Jackson, classpath, cấu hình, kiểu base và đường đi thực tế của object. Không phải mọi lần dùng polymorphism đều là lỗ hổng, nhưng để input không tin cậy tự do chọn class làm bề mặt tấn công tăng mạnh.

Ví dụ về dạng thiết kế không an toàn:

~~~java
// Không dùng kiểu thiết kế này cho JSON đến từ client hoặc nguồn ngoài.
@JsonTypeInfo(
        use = JsonTypeInfo.Id.CLASS,
        include = JsonTypeInfo.As.PROPERTY,
        property = "@class"
)
public abstract class Message {
}
~~~

Khi type ID chứa tên class, JSON có thể cố yêu cầu mapper phân giải một implementation theo tên lớp. Nếu validator hoặc cấu hình không giới hạn đúng cách, input có thể chọn kiểu mà nhà phát triển không định công bố.

Không giải quyết vấn đề bằng cách kiểm tra một vài chuỗi nguy hiểm sau khi deserialize. Lúc đó Jackson có thể đã khởi tạo object và kích hoạt hành vi của nó. Hãy giới hạn lớp được phép trước khi quá trình tạo object diễn ra.

## 3. Dùng type ID logic với allowlist subtype

Với API hoặc message contract, ưu tiên JsonTypeInfo.Id.NAME. Type ID là một tên nghiệp vụ ổn định, không phải tên package hay class Java.

~~~java
import com.fasterxml.jackson.annotation.JsonSubTypes;
import com.fasterxml.jackson.annotation.JsonTypeInfo;

@JsonTypeInfo(
        use = JsonTypeInfo.Id.NAME,
        include = JsonTypeInfo.As.PROPERTY,
        property = "kind"
)
@JsonSubTypes({
        @JsonSubTypes.Type(value = CreateAccount.class, name = "create-account"),
        @JsonSubTypes.Type(value = DisableAccount.class, name = "disable-account")
})
public interface IncomingCommand {
}
~~~

Hai lớp con có thể là các DTO dữ liệu cụ thể:

~~~java
public record CreateAccount(String username) implements IncomingCommand {
}

public record DisableAccount(String accountId) implements IncomingCommand {
}
~~~

Khi đọc JSON:

~~~java
ObjectMapper mapper = new ObjectMapper();

IncomingCommand command = mapper.readValue(
        """
        {
          "kind": "create-account",
          "username": "an"
        }
        """,
        IncomingCommand.class
);
~~~

Jackson đọc kind, tìm tên trong danh sách subtype được khai báo và tạo đúng implementation. JSON không thể thay create-account bằng một class name tùy ý rồi yêu cầu mapper tải class đó.

@JsonSubTypes đóng vai trò allowlist cho kiểu cơ sở được đánh dấu. Khi thêm subtype, nhà phát triển phải thay đổi code hoặc cấu hình đăng ký. Đây là một quyết định có thể review, kiểm thử và quản lý qua phiên bản.

### 3.1. Type ID là hợp đồng JSON

Các tên create-account và disable-account nên được xem là một phần của hợp đồng công khai. Chúng có thể tồn tại ổn định dù package hoặc tên lớp Java thay đổi.

Có thể đặt tên trên lớp con bằng JsonTypeName:

~~~java
import com.fasterxml.jackson.annotation.JsonTypeName;

@JsonTypeName("create-account")
public record CreateAccount(String username) implements IncomingCommand {
}
~~~

Danh sách subtype vẫn phải được giới hạn rõ ràng bằng JsonSubTypes, registerSubtypes() hoặc một type resolver có allowlist. JsonTypeName đặt tên logic; nó không tự biến mọi class trong classpath thành subtype được chấp nhận.

### 3.2. Đăng ký subtype bằng mapper

Nếu không thể sửa interface hoặc muốn tập trung cấu hình ở composition root, có thể đăng ký tên logic:

~~~java
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.jsontype.NamedType;

ObjectMapper mapper = new ObjectMapper();

mapper.registerSubtypes(
        new NamedType(CreateAccount.class, "create-account"),
        new NamedType(DisableAccount.class, "disable-account")
);
~~~

Kiểu cơ sở vẫn cần khai báo cơ chế type information, ví dụ JsonTypeInfo với Id.NAME và property kind, hoặc cấu hình type resolver phù hợp. registerSubtypes() cung cấp danh sách subtype và tên; nó không tự thêm discriminator nếu base type chưa có quy tắc đa hình.

Đăng ký rõ ràng cũng giúp từng mapper có thể chấp nhận một tập message khác nhau. Không nên tự động quét toàn bộ package rồi đăng ký mọi lớp tìm thấy, vì việc đó làm allowlist khó kiểm soát.

## 4. Unknown type ID phải bị từ chối

Giả sử ứng dụng chỉ đăng ký hai loại command, nhưng input gửi:

~~~json
{
  "kind": "com.example.internal.AdminCommand",
  "payload": "..."
}
~~~

Hoặc:

~~~json
{
  "kind": "unknown-command",
  "username": "an"
}
~~~

Jackson không tìm thấy tên logic tương ứng trong subtype registry và thường ném InvalidTypeIdException, một loại JsonMappingException. Đây là hành vi fail closed: dữ liệu không xác định không được tự động chuyển thành một class tùy ý.

Không nên dùng fallback rộng kiểu “nếu không biết thì thử Class.forName(typeName)”. Cũng không nên biến type ID lạ thành một lớp có quyền thực thi hành động. Nếu hợp đồng cần tương thích với loại message mới, có thể thiết kế một DTO UnknownMessage an toàn chỉ để lưu dữ liệu thô đã giới hạn, nhưng phải quyết định rõ field nào được giữ và tuyệt đối không dùng nó để nạp class.

defaultImpl trong JsonTypeInfo có thể chỉ định kiểu fallback khi thiếu hoặc không phân giải được type ID tùy cấu hình. Chỉ dùng khi có yêu cầu tương thích rõ ràng và fallback là một DTO dữ liệu inert, không có hành vi nhạy cảm. Với command hoặc event mà subtype quyết định hành động, từ chối type ID lạ thường an toàn và dễ vận hành hơn.

## 5. Không bật default typing rộng cho dữ liệu không tin cậy

Default typing là cơ chế Jackson tự thêm type metadata dựa trên loại khai báo, ví dụ property kiểu Object, interface, abstract class hoặc nhiều kiểu non-final tùy DefaultTyping được chọn.

Một cấu hình default typing toàn cục có thể ảnh hưởng tới nhiều property mà người viết API không nhận ra. Khi JSON đến từ bên ngoài, điều này có thể khiến nhiều vị trí dữ liệu có quyền tác động đến kiểu Java được tạo.

Tránh các mẫu cấu hình permissive như dùng LaissezFaireSubTypeValidator.instance để chấp nhận rộng các subtype, đặc biệt khi bật activateDefaultTyping() trên mapper đọc request, webhook, message broker hoặc file do người dùng tải lên.

~~~java
// Không bật default typing permissive cho input không tin cậy.
mapper.activateDefaultTyping(
        LaissezFaireSubTypeValidator.instance,
        ObjectMapper.DefaultTyping.NON_FINAL
);
~~~

Đoạn code trên minh họa một cấu hình cần tránh. Default typing không phải cách thuận tiện để tự động khôi phục mọi class graph Java từ JSON công khai.

Nếu một hệ thống legacy cần default typing để đọc dữ liệu nội bộ đã phát hành trước đó, hãy đánh giá liệu có thể thay bằng DTO có schema rõ ràng và Id.NAME hay không. Tách mapper đọc dữ liệu tin cậy khỏi mapper đọc input công khai; đừng dùng một mapper có cấu hình permissive cho mọi boundary.

## 6. Vai trò của PolymorphicTypeValidator

Jackson cung cấp PolymorphicTypeValidator để kiểm tra việc một subtype có được phép sử dụng trong quá trình polymorphic deserialization hay không. Validator đặc biệt quan trọng khi cấu hình default typing hoặc khi hệ thống vẫn phải xử lý type ID dựa trên class name.

Validator có thể kiểm tra base type, tên subtype và lớp subtype đã được phân giải. Một BasicPolymorphicTypeValidator có thể được xây dựng với các điều kiện allow/deny cụ thể.

Tuy nhiên, validator không phải lý do để bật default typing rộng một cách tùy tiện. Nó cần được cấu hình theo allowlist hẹp, được kiểm thử với cả lớp hợp lệ và lớp bị từ chối, và phải phù hợp với mọi base type mà mapper xử lý.

Các nguyên tắc khi cấu hình validator:

- Chỉ cho phép các subtype phục vụ một hợp đồng đã xác định.
- Ưu tiên danh sách lớp contract cụ thể hoặc một họ lớp dữ liệu rất hẹp.
- Tránh cho phép toàn bộ package rộng chứa cả DTO lẫn service, framework hoặc tiện ích nội bộ.
- Không dùng denylist một vài class nguy hiểm làm lớp bảo vệ duy nhất.
- Kiểm tra cả base type và subtype; một subtype an toàn trong một ngữ cảnh chưa chắc an toàn trong ngữ cảnh khác.
- Từ chối class không xác định thay vì fallback sang class tùy ý.

Nếu phải dùng activateDefaultTyping(), hãy cấu hình PolymorphicTypeValidator hẹp nhất có thể và kiểm tra hành vi của phiên bản Jackson đang chạy. Cấu hình đó vẫn nên được coi là giải pháp tương thích có phạm vi hạn chế. Với API công khai, allowlist type ID logic theo từng base type thường dễ hiểu và ít rủi ro hơn.

## 7. Tránh Id.CLASS và Id.MINIMAL_CLASS trong hợp đồng ngoài

Hai loại type ID sau cần được cân nhắc đặc biệt:

| Type ID | Nội dung thường được ghi vào JSON | Rủi ro thiết kế |
|---|---|---|
| Id.CLASS | Tên class đầy đủ, thường gồm package | JSON phụ thuộc implementation Java; input có thể yêu cầu phân giải class name. |
| Id.MINIMAL_CLASS | Tên class rút gọn tương đối với package | Vẫn phụ thuộc tên lớp/package và có thể gây khó hiểu khi refactor. |
| Id.NAME | Tên logic được đăng ký | Có thể giới hạn rõ bằng subtype allowlist. |
| Id.DEDUCTION | Không ghi discriminator; suy luận từ field | Chỉ chọn trong tập subtype đã biết; có thể mơ hồ khi schema giao nhau. |
| Id.CUSTOM | Giá trị do resolver tự định nghĩa | An toàn tùy implementation; resolver phải dùng allowlist, không phản chiếu tùy ý. |

Id.CLASS có thể hữu ích trong một số định dạng nội bộ được kiểm soát chặt, nhưng không nên là lựa chọn mặc định cho API, event hoặc file mà nguồn gửi không hoàn toàn tin cậy. Id.MINIMAL_CLASS không loại bỏ vấn đề; nó chỉ rút gọn biểu diễn tên class.

Id.NAME tách hợp đồng JSON khỏi package Java. Nếu đổi com.example.commands.CreateAccount thành một package khác, type ID create-account vẫn có thể giữ nguyên.

## 8. Giới hạn polymorphism ở đúng property cần thiết

Không phải mọi field đều cần đa hình. Nếu một DTO chứa property kiểu Object, map có value Object hoặc một base interface rộng, phạm vi mà input có thể ảnh hưởng tới kiểu dữ liệu sẽ lớn hơn.

Ưu tiên kiểu cụ thể:

~~~java
public record CreateOrderRequest(
        String customerId,
        List<OrderLineRequest> lines
) {
}

public record OrderLineRequest(
        String productCode,
        int quantity
) {
}
~~~

Nếu thật sự cần nhiều dạng phần tử, đặt polymorphic metadata trên base type hoặc property cụ thể đó:

~~~java
public record WorkflowRequest(
        List<IncomingCommand> commands
) {
}
~~~

Không bật type metadata toàn cục chỉ để hỗ trợ một property đa hình. Giới hạn phạm vi bằng annotation trên interface/base type hoặc property cần thiết. Những field còn lại nên giữ kiểu cụ thể.

### 8.1. Không dùng Object như một cách né schema

Ví dụ sau làm hợp đồng khó kiểm soát:

~~~java
public class GenericMessage {
    private String type;
    private Object payload;
}
~~~

Nếu mapper có default typing, payload có thể trở thành vị trí nhận type metadata cho nhiều class. Nếu mapper không có default typing, payload thường trở thành cấu trúc untyped như Map/List/scalar và ứng dụng phải tự xác thực.

Nếu các message type đã biết, dùng base interface với subtype allowlist:

~~~java
public class GenericMessage {
    private String messageId;
    private IncomingCommand payload;
}
~~~

Nếu payload thực sự là dữ liệu động, dùng JsonNode rồi kiểm tra schema, kích thước, kiểu và các key được phép trước khi xử lý. Không chuyển một field động thành lệnh khởi tạo class.

## 9. Type ID không phải authorization

Allowlist trả lời câu hỏi: “Ứng dụng có chấp nhận kiểu dữ liệu này hay không?” Nó không trả lời câu hỏi: “Người gửi có quyền thực hiện hành động tương ứng hay không?”

Ví dụ, CreateAccount có thể là subtype hợp lệ, nhưng một người dùng không có quyền tạo tài khoản vẫn không được phép gửi command đó. Sau deserialization, tầng ứng dụng vẫn phải xác thực danh tính, kiểm tra quyền, kiểm tra tenant và xác thực dữ liệu nghiệp vụ.

Không dùng tên type như admin, trusted hoặc internal làm bằng chứng về quyền. Client có thể tự gửi mọi chuỗi mà họ biết. Quyền phải được lấy từ authentication context đáng tin cậy và policy của server.

Tương tự, không để constructor của DTO thực hiện hành động như tạo user, ghi file, gọi network hoặc thay đổi trạng thái hệ thống. Deserialization nên tạo dữ liệu; service đã được authorize mới thực hiện nghiệp vụ.

## 10. Giữ subtype là DTO dữ liệu đơn giản

Các lớp được phép deserialize nên có trách nhiệm rõ ràng và ít side effect:

- Chứa field dữ liệu cần thiết.
- Constructor không thực hiện I/O hoặc gọi service.
- Setter không thực hiện hành động nhạy cảm.
- Không chứa logic thực thi lệnh trong quá trình binding.
- Không mở rộng một base class đặc quyền chỉ để tái sử dụng code.
- Validation nghiệp vụ thực hiện sau binding tại tầng ứng dụng.

Ví dụ, một event DTO:

~~~java
public sealed interface DomainEvent
        permits UserCreatedEvent, OrderPaidEvent {
}

public record UserCreatedEvent(
        String eventId,
        String userId
) implements DomainEvent {
}

public record OrderPaidEvent(
        String eventId,
        String orderId,
        long amountInCents
) implements DomainEvent {
}
~~~

Các record chỉ giữ dữ liệu. Handler riêng được gọi sau khi message được xác thực và kiểm tra quyền. Cách tách này giúp việc tạo object không tự kích hoạt nghiệp vụ.

Sealed interface của Java giới hạn lớp con ở compile time. Nó là một lớp bảo vệ hữu ích cho thiết kế code, nhưng vẫn cần cấu hình Jackson để chỉ chấp nhận các subtype mong muốn và cần kiểm tra hành vi ở runtime. Với Java phiên bản chưa hỗ trợ sealed type, có thể dùng interface/class thường cùng danh sách subtype đăng ký rõ ràng.

## 11. Chọn một discriminator rõ ràng và ổn định

Một discriminator nên có các đặc điểm:

- Tên field rõ nghĩa như kind, eventType hoặc commandType.
- Giá trị là tên logic ngắn, ổn định và không chứa tên package/class.
- Danh sách giá trị được tài liệu hóa.
- Không dùng discriminator làm cơ chế phân quyền.
- Type ID không xác định bị từ chối hoặc xử lý bằng một fallback an toàn đã định nghĩa.
- Không cho client tự cung cấp tên class đầy đủ.

Ví dụ hợp đồng:

~~~json
{
  "eventType": "user-created",
  "eventId": "evt-100",
  "userId": "usr-42"
}
~~~

Tên user-created mô tả loại event, không tiết lộ class Java. Nếu sau này implementation đổi từ class sang record, hoặc chuyển package, contract không phải thay đổi.

Không nên dùng một field tên class, @class hoặc javaType để khuyến khích client gửi tên implementation. Đặt tên discriminator theo ngôn ngữ nghiệp vụ.

## 12. Xử lý type ID không biết và tương thích phiên bản

Khi thêm subtype mới, consumer cũ có thể chưa biết type ID đó. Có ba chính sách thường gặp:

| Chính sách | Hành vi | Khi phù hợp |
|---|---|---|
| Fail closed | Ném lỗi mapping khi type ID không biết | Command hoặc event cần xử lý đúng semantics. |
| Safe unknown envelope | Đưa dữ liệu vào DTO unknown có schema giới hạn | Gateway cần lưu/chuyển tiếp message chưa hiểu. |
| Explicit fallback | Dùng một default implementation inert đã định nghĩa | Hợp đồng legacy có quy tắc fallback rõ ràng. |

Với command có thể làm thay đổi trạng thái, fail closed thường là lựa chọn dễ bảo vệ nhất. Với gateway cần chuyển tiếp message, có thể dùng JsonNode hoặc raw payload giới hạn kích thước để lưu/chuyển tiếp mà không khởi tạo class không biết.

Không nên coi defaultImpl là cách bỏ qua validation. Fallback phải là kiểu cụ thể, không có side effect, có giới hạn dữ liệu và không tự diễn giải field tùy ý thành hành động.

Versioning cũng cần được quản lý rõ. Thêm type ID mới là thay đổi hợp đồng; consumer cũ cần biết sẽ từ chối, bỏ qua hay chuyển tiếp. Không thay đổi ý nghĩa của type ID hiện có trong khi vẫn giữ tên cũ.

## 13. Custom TypeIdResolver phải ánh xạ qua allowlist

Jackson cho phép dùng JsonTypeInfo.Id.CUSTOM với TypeIdResolver tùy biến. Cơ chế này hữu ích nếu type ID có quy tắc riêng, nhưng implementation có thể trở thành lỗ hổng nếu chuyển input thành tên class rồi gọi reflection.

Không làm kiểu sau:

~~~java
// Mẫu nguy hiểm: không chuyển type ID ngoài thành class name tùy ý.
Class<?> type = Class.forName(typeId);
~~~

Resolver nên dùng map tĩnh hoặc registry được xây dựng từ các kiểu cho phép:

~~~java
private static final Map<String, Class<? extends DomainEvent>> ALLOWED_TYPES =
        Map.of(
                "user-created", UserCreatedEvent.class,
                "order-paid", OrderPaidEvent.class
        );

public static Class<? extends DomainEvent> resolve(String typeId) {
    Class<? extends DomainEvent> type = ALLOWED_TYPES.get(typeId);
    if (type == null) {
        throw new IllegalArgumentException("Unsupported event type: " + typeId);
    }
    return type;
}
~~~

Đây là ý tưởng registry, không phải một TypeIdResolver hoàn chỉnh. Khi tích hợp vào Jackson, resolver phải tuân thủ SPI của phiên bản đang dùng và báo lỗi mapping phù hợp nếu type ID không có trong registry. Không dùng Class.forName() với dữ liệu ngoài và không tự quét classpath theo tên do client gửi.

## 14. Cẩn trọng với Id.DEDUCTION

JsonTypeInfo.Id.DEDUCTION cho phép Jackson suy luận subtype dựa trên tập property có trong JSON thay vì đọc discriminator tường minh. Cách này tránh việc client gửi class name và chỉ hoạt động với tập subtype mà mapper biết.

Tuy vậy, deduction không tự làm schema an toàn nếu subtype chứa field giao nhau hoặc dữ liệu có thể tạo ra nhiều cách diễn giải. Nếu các subtype không thể phân biệt rõ, Jackson có thể báo lỗi mơ hồ. Khi hợp đồng cần dễ đọc, dễ version và dễ kiểm thử, discriminator Id.NAME tường minh thường dễ vận hành hơn.

Dù dùng deduction, hãy đăng ký tập subtype cụ thể và không mở rộng sang class tùy ý. Việc không có discriminator không có nghĩa mapper không cần allowlist.

## 15. Tách mapper theo ranh giới tin cậy

Một ứng dụng có thể đọc nhiều nguồn dữ liệu:

- JSON công khai từ REST client.
- Webhook từ đối tác.
- Message từ broker nội bộ.
- Snapshot hoặc cache do chính ứng dụng tạo.
- File import do người dùng tải lên.

Các nguồn này không có cùng mức độ tin cậy. Không nên dùng một ObjectMapper với default typing permissive cho tất cả.

Một thiết kế rõ ràng có thể có:

~~~java
ObjectMapper publicApiMapper = JsonMapper.builder()
        .addModule(new JavaTimeModule())
        .build();

ObjectMapper internalMapper = JsonMapper.builder()
        .addModule(new JavaTimeModule())
        // Chỉ thêm cấu hình tương thích nội bộ đã được giới hạn và kiểm thử.
        .build();
~~~

Ví dụ trên không bật default typing. Nếu một định dạng nội bộ legacy thật sự cần polymorphic metadata, cấu hình nó trong mapper chuyên biệt và giới hạn subtype. Mapper đọc request công khai nên có DTO và type registry rõ ràng, không kế thừa một cấu hình permissive chỉ vì mapper nội bộ cần nó.

Tập trung tạo mapper tại composition root. Không tạo mapper mới trong từng request, và không sửa cấu hình mapper singleton sau khi đã bắt đầu sử dụng đồng thời.

## 16. Những kiểm soát bổ sung ngoài subtype allowlist

Allowlist subtype giải quyết việc lựa chọn class, nhưng JSON vẫn có thể gây tiêu tốn tài nguyên hoặc làm dữ liệu nghiệp vụ sai. Tại boundary cần thêm các kiểm soát phù hợp:

- Giới hạn kích thước HTTP body/message.
- Giới hạn độ sâu lồng nhau và số phần tử collection.
- Kiểm tra độ dài chuỗi, số và phạm vi giá trị.
- Từ chối property không biết nếu contract yêu cầu schema chặt.
- Validate object sau binding trước khi gọi service.
- Đặt timeout và giới hạn tài nguyên cho việc parse dữ liệu lớn.
- Không ghi raw payload chứa secret vào log.
- Cập nhật Jackson và các dependency có liên quan theo bản vá bảo mật được hỗ trợ.

Không dùng kiểm tra kích thước thay cho allowlist, và không dùng allowlist thay cho validation nghiệp vụ. Mỗi lớp kiểm soát xử lý một loại rủi ro riêng.

## 17. Kiểm thử allowlist và hành vi từ chối

Kiểm thử bảo mật phải chứng minh cả hai phía: subtype hợp lệ được đọc đúng; type ID ngoài danh sách bị từ chối.

Ví dụ với IncomingCommand đã khai báo JsonTypeInfo và JsonSubTypes:

~~~java
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.exc.InvalidTypeIdException;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

class IncomingCommandSecurityTest {
    private final ObjectMapper mapper = new ObjectMapper();

    @Test
    void acceptsRegisteredLogicalType() throws Exception {
        IncomingCommand command = mapper.readValue(
                """
                {
                  "kind": "create-account",
                  "username": "an"
                }
                """,
                IncomingCommand.class
        );

        assertInstanceOf(CreateAccount.class, command);
    }

    @Test
    void rejectsUnknownTypeId() {
        assertThrows(InvalidTypeIdException.class, () ->
                mapper.readValue(
                        """
                        {
                          "kind": "unknown-command",
                          "username": "an"
                        }
                        """,
                        IncomingCommand.class
                )
        );
    }

    @Test
    void doesNotAcceptClassNameAsLogicalType() {
        assertThrows(InvalidTypeIdException.class, () ->
                mapper.readValue(
                        """
                        {
                          "kind": "java.lang.Runtime",
                          "username": "an"
                        }
                        """,
                        IncomingCommand.class
                )
        );
    }
}
~~~

Test thứ ba xác nhận class name không được hiểu là type ID hợp lệ. Nó không chứng minh toàn bộ mapper an toàn nếu mapper còn bật default typing ở một vị trí khác. Cần kiểm tra cấu hình mapper thực tế của ứng dụng, không chỉ một test trên base interface.

Các test bổ sung nên bao gồm:

- Mỗi logical type được đăng ký tạo đúng class.
- Type ID thiếu bị xử lý theo chính sách đã công bố.
- Type ID không biết bị từ chối.
- Subtype không thuộc base type bị từ chối.
- Không có custom resolver nào dùng reflection với dữ liệu ngoài.
- Không có default typing permissive trên mapper đọc public input.
- Mapper public không kế thừa module/validator không cần thiết từ mapper nội bộ.
- Constructor và setter của DTO không kích hoạt side effect.
- JSON lồng sâu hoặc quá lớn bị giới hạn theo boundary policy.

## 18. Quy trình thiết kế polymorphic deserialization an toàn

Khi một API cần đọc interface hoặc abstract class từ JSON, hãy thực hiện theo trình tự:

1. **Xác định base type:** chỉ kiểu nào thật sự cần nhiều implementation?
2. **Liệt kê subtype hợp lệ:** ghi rõ từng class dữ liệu mà ứng dụng chấp nhận.
3. **Chọn logical type ID:** dùng tên nghiệp vụ ổn định, không dùng class name.
4. **Đăng ký allowlist:** JsonSubTypes, NamedType hoặc resolver tĩnh.
5. **Giới hạn phạm vi:** đặt metadata trên base type/property cần thiết, không bật toàn cục.
6. **Từ chối type ID lạ:** fail closed hoặc dùng safe unknown envelope đã định nghĩa.
7. **Kiểm tra side effect:** subtype chỉ là DTO dữ liệu, không thực thi nghiệp vụ trong constructor/setter.
8. **Authorize sau binding:** type ID hợp lệ không đồng nghĩa người gửi có quyền.
9. **Kiểm soát tài nguyên:** giới hạn payload, độ sâu và số phần tử.
10. **Kiểm thử mapper thực tế:** xác nhận allowlist và mọi đường cấu hình polymorphic.
11. **Quản lý version:** thêm type ID là thay đổi contract có review và kiểm thử.
12. **Cập nhật dependency:** theo dõi bản vá Jackson và thư viện có mặt trên classpath.

## 19. So sánh các lựa chọn

| Cách làm | Mức kiểm soát | Khuyến nghị cho dữ liệu ngoài |
|---|---|---|
| Id.NAME với subtype allowlist | Rõ tên logic và tập class được phép | Ưu tiên |
| registerSubtypes() với tên logic | Allowlist tập trung trong cấu hình mapper | Phù hợp |
| Id.DEDUCTION với subtype đã đăng ký | Không dùng class name, nhưng suy luận có thể mơ hồ | Chỉ dùng khi schema phân biệt rõ |
| Id.CUSTOM dùng registry tĩnh | Tùy implementation, có thể kiểm soát tốt | Chỉ khi resolver thật sự allowlist |
| Id.CLASS | JSON mang tên class Java | Tránh cho public/untrusted input |
| Id.MINIMAL_CLASS | JSON vẫn phụ thuộc tên class/package | Tránh cho public/untrusted input |
| Default typing permissive | Có thể mở rộng phạm vi class được khởi tạo trên nhiều property | Không dùng với input không tin cậy |
| Default typing có validator hẹp | Có lớp kiểm soát nhưng cấu hình phức tạp và phạm vi toàn cục | Chỉ cân nhắc cho legacy sau đánh giá |
| JsonNode với schema/dispatch tường minh | Ứng dụng tự kiểm tra discriminator và tạo DTO cụ thể | Phù hợp với payload động có kiểm soát |

## 20. Kết luận

Polymorphic deserialization cần biết lớp con nào sẽ được tạo, nhưng dữ liệu ngoài không được tự quyết định tên class Java. Hãy dùng type ID logic với allowlist subtype được đăng ký rõ ràng; Id.NAME cùng JsonSubTypes hoặc NamedType thường là lựa chọn phù hợp cho API và message contract. Từ chối type ID không biết, tránh Id.CLASS, Id.MINIMAL_CLASS và default typing permissive trên mapper đọc dữ liệu không tin cậy. Nếu hệ thống legacy buộc phải dùng default typing, giới hạn bằng PolymorphicTypeValidator hẹp, tách mapper theo ranh giới tin cậy và kiểm thử mọi đường deserialization. Cuối cùng, subtype hợp lệ chỉ có nghĩa dữ liệu được phép bind: authorization, validation nghiệp vụ và giới hạn tài nguyên vẫn phải được thực hiện ở tầng ứng dụng.

