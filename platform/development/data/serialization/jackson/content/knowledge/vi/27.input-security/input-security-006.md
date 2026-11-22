# Đánh giá default typing và giới hạn kiểu bằng PolymorphicTypeValidator

Jackson thường deserialize một JSON object theo kiểu Java mà ứng dụng chỉ định. Khi kiểu đích là một interface, abstract class hoặc Object, một JSON object có thể tương ứng với nhiều class triển khai khác nhau. Để biết phải tạo subtype nào, Jackson cần type metadata. Cơ chế polymorphic typing cho phép JSON mang thông tin loại dữ liệu, còn default typing có thể tự thêm metadata cho nhiều kiểu Java mà không cần gắn annotation lên từng class.

Sự tiện lợi này đi kèm rủi ro bảo mật. Nếu ứng dụng chấp nhận type id chứa tên class từ dữ liệu không tin cậy, input có thể yêu cầu Jackson khởi tạo những class không mong muốn có mặt trên classpath. Vì vậy, Jackson cung cấp PolymorphicTypeValidator để giới hạn base type và subtype được phép trong quá trình xử lý polymorphic type id.

Bài này giải thích default typing hoạt động ở đâu, các chế độ áp dụng, cách validator kiểm tra type, cách xây allowlist hẹp với BasicPolymorphicTypeValidator và những giới hạn còn lại. Với JSON từ HTTP client, webhook hoặc message broker bên ngoài, cần xem default typing là một quyết định bảo mật ở ranh giới dữ liệu, không chỉ là một tùy chọn tiện lợi để giữ kiểu Java.

## 1. Vì sao Jackson cần polymorphic type metadata?

Giả sử model có một base type:

~~~java
public abstract class Payment {
    private BigDecimal amount;

    public BigDecimal getAmount() {
        return amount;
    }

    public void setAmount(BigDecimal amount) {
        this.amount = amount;
    }
}
~~~

Hai subtype có field riêng:

~~~java
public class CardPayment extends Payment {
    private String lastFourDigits;

    public String getLastFourDigits() {
        return lastFourDigits;
    }

    public void setLastFourDigits(String lastFourDigits) {
        this.lastFourDigits = lastFourDigits;
    }
}

public class BankTransferPayment extends Payment {
    private String bankCode;

    public String getBankCode() {
        return bankCode;
    }

    public void setBankCode(String bankCode) {
        this.bankCode = bankCode;
    }
}
~~~

Một property khai báo kiểu Payment có thể chứa một trong hai subtype:

~~~java
public class PaymentRequest {
    private Payment payment;

    public Payment getPayment() {
        return payment;
    }

    public void setPayment(Payment payment) {
        this.payment = payment;
    }
}
~~~

Nếu JSON chỉ có dữ liệu:

~~~json
{
  "payment": {
    "amount": 125000,
    "bankCode": "VCB"
  }
}
~~~

Jackson cần biết object bên trong phải trở thành CardPayment hay BankTransferPayment. Chỉ nhìn field hiện có không phải cách chọn subtype đáng tin cậy: field có thể bị thiếu, mở rộng hoặc trùng tên giữa các subtype.

Một discriminator rõ ràng giải quyết vấn đề:

~~~json
{
  "payment": {
    "type": "bank_transfer",
    "amount": 125000,
    "bankCode": "VCB"
  }
}
~~~

Với cách khai báo tường minh, ứng dụng có thể dùng JsonTypeInfo.Id.NAME và ánh xạ bank_transfer tới BankTransferPayment. Đây thường là cách dễ kiểm soát nhất cho hợp đồng JSON công khai.

Default typing là một cách khác: Jackson tự đưa type metadata vào các property thuộc những nhóm kiểu được chọn, thường sử dụng tên class Java làm type id. Không cần thêm JsonTypeInfo vào từng model, nhưng wire format gắn chặt hơn với implementation Java và cần validator phù hợp khi deserialize.

## 2. Default typing làm gì?

Default typing là cơ chế Jackson tự áp dụng polymorphic type information cho các property thỏa một chính sách kiểu mặc định. Khi serialize, type id được ghi cùng dữ liệu; khi deserialize, Jackson đọc type id để xác định subtype cụ thể.

Trong Jackson 2.x, API chính là:

~~~java
mapper.activateDefaultTyping(
        polymorphicTypeValidator,
        ObjectMapper.DefaultTyping.NON_FINAL,
        JsonTypeInfo.As.WRAPPER_ARRAY
);
~~~

Đối số gồm:

- PolymorphicTypeValidator: chính sách quyết định base type và subtype nào được phép.
- DefaultTyping: phạm vi kiểu Java sẽ nhận type metadata.
- JsonTypeInfo.As: hình thức đặt type metadata trong JSON.

Default typing khác với annotation JsonTypeInfo được gắn vào một class hoặc property. Annotation thường giới hạn polymorphism vào những vị trí được khai báo. Default typing có thể tác động rộng đến nhiều property trong mapper theo chế độ được chọn.

### 2.1. Ví dụ hình dạng JSON

Với inclusion WRAPPER_ARRAY, type id thường xuất hiện trong một array bao quanh giá trị:

~~~json
[
  "com.example.api.BankTransferPayment",
  {
    "amount": 125000,
    "bankCode": "VCB"
  }
]
~~~

Đây là minh họa về hình dạng type metadata. Tên class thực tế phụ thuộc ứng dụng. Với default typing, type id thường gắn với class Java, nên đổi package hoặc tên class có thể làm payload cũ không còn tương thích.

Nếu chọn As.PROPERTY cho object, metadata có thể xuất hiện như một property:

~~~json
{
  "@class": "com.example.api.BankTransferPayment",
  "amount": 125000,
  "bankCode": "VCB"
}
~~~

WRAPPER_ARRAY thường phù hợp hơn khi cần một cách bao ngoài có thể thể hiện type metadata cho nhiều loại giá trị JSON. As.PROPERTY có giới hạn đối với một số hình dạng scalar/container; hãy chọn inclusion phù hợp với kiểu dữ liệu và kiểm tra wire output thực tế.

### 2.2. Default typing không phải một yêu cầu cho mọi JSON

Nếu model có schema rõ và chỉ cần một vài polymorphic property, dùng JsonTypeInfo với logical type name thường dễ đọc và ổn định hơn. Default typing thường được cân nhắc trong hệ thống nội bộ cần round-trip object graph tổng quát hoặc tương thích một format Java-centric đã tồn tại.

Không nên bật default typing chỉ để tránh khai báo subtype ở một vài DTO. Phạm vi ảnh hưởng của nó có thể lớn hơn dự kiến.

## 3. Các chế độ DefaultTyping

ObjectMapper.DefaultTyping xác định nhóm declared type nào sẽ được gắn type metadata. Tên chế độ khá dễ gây hiểu nhầm; điều quan trọng là hiểu phạm vi khai báo kiểu, không chỉ nhìn runtime class.

| Chế độ | Ý nghĩa khái quát |
|---|---|
| JAVA_LANG_OBJECT | Tập trung vào property khai báo kiểu Object |
| OBJECT_AND_NON_CONCRETE | Bao gồm Object và các kiểu khai báo không concrete như interface/abstract class |
| NON_CONCRETE_AND_ARRAYS | Bao gồm kiểu không concrete và các array tương ứng theo quy tắc của Jackson |
| NON_FINAL | Phạm vi rộng hơn, áp dụng cho nhiều declared type không final |
| EVERYTHING | Phạm vi rộng nhất trong các lựa chọn default typing, ngoại trừ những kiểu tự nhiên/primitive được Jackson xử lý đặc biệt |

Chi tiết điều kiện áp dụng có thể có ngoại lệ theo phiên bản Jackson và loại kiểu. Hãy kiểm tra Javadoc của đúng version thay vì coi bảng này là thay thế cho hợp đồng API.

### 3.1. JAVA_LANG_OBJECT

Chế độ này hữu ích khi model có các property khai báo kiểu Object và cần giữ runtime type của giá trị. Ví dụ:

~~~java
public class AuditEntry {
    private Object details;

    public Object getDetails() {
        return details;
    }

    public void setDetails(Object details) {
        this.details = details;
    }
}
~~~

Khi đọc lại property details, Jackson cần type metadata để biết object thực tế là class nào. Tuy nhiên, Object là base type rất rộng. Nếu dữ liệu đầu vào không tin cậy, cho phép tùy ý subtype của Object là rủi ro lớn.

### 3.2. OBJECT_AND_NON_CONCRETE

Chế độ này nhắm tới các declared type mà bản thân không xác định được implementation cụ thể, chẳng hạn interface hoặc abstract class, cùng Object theo quy tắc của Jackson.

Ví dụ property khai báo Payment hoặc List interface. Khi deserialize, type metadata có thể giúp xác định implementation cụ thể.

Không nên nhầm điều này với việc Jackson cần type metadata cho mọi property. Các property có kiểu concrete rõ ràng thường không cần subtype id để biết class đích.

### 3.3. NON_CONCRETE_AND_ARRAYS

Chế độ này mở rộng xử lý cho array của những kiểu không concrete theo chính sách tương ứng. Nếu ứng dụng có cấu trúc collection/array phức tạp, hãy kiểm tra output và behavior của đúng version Jackson thay vì suy ra chỉ từ tên chế độ.

### 3.4. NON_FINAL

NON_FINAL có phạm vi rộng và dễ làm nhiều model nhận type metadata mà người viết ứng dụng không nhận ra. Đây không phải lựa chọn an toàn mặc định cho mọi API.

Một class không final có thể được mở rộng bởi subtype khác. Nếu type id từ JSON được dùng để chọn class, validator cần giới hạn chặt những subtype có thể được chấp nhận.

### 3.5. EVERYTHING

EVERYTHING là chế độ rộng nhất và thường không cần thiết cho ứng dụng API thông thường. Việc áp dụng metadata quá rộng làm payload phụ thuộc mạnh vào Java class model, tăng độ phức tạp khi tương thích và mở rộng diện tích cần kiểm soát.

Hãy chọn phạm vi hẹp nhất đáp ứng mục đích. Đừng dùng chế độ rộng để bù cho model thiếu rõ ràng.

## 4. Rủi ro bảo mật của polymorphic deserialization

Polymorphic deserialization có thể tạo instance của subtype được chỉ định bởi type id. Nếu ứng dụng cho phép dữ liệu bên ngoài chọn tên class tùy ý trên classpath, Jackson có thể bị yêu cầu khởi tạo những class không được thiết kế để làm DTO đầu vào.

Một số thư viện có class có hành vi đặc biệt trong constructor, setter, getter hoặc callback. Khi kết hợp với cấu hình polymorphic quá rộng, những kiểu này có thể trở thành gadget trong chuỗi khai thác deserialization. Hậu quả tùy classpath và cấu hình, có thể gồm đọc/ghi tài nguyên, truy cập mạng, thực thi hành vi ngoài ý muốn hoặc gây cạn tài nguyên.

Rủi ro không chỉ đến từ tên class hiển thị trong JSON. Điều quan trọng là input có thể điều khiển lựa chọn kiểu được tạo trong tiến trình server.

### 4.1. Vì sao class name trong input là vấn đề?

Ví dụ một payload mang type id:

~~~json
[
  "com.some.library.SomeRuntimeType",
  {
    "property": "value"
  }
]
~~~

Nếu validator và chính sách polymorphic cho phép, Jackson có thể resolve class đó rồi deserialize dữ liệu vào nó. Ứng dụng không nên cho client quyết định class Java bất kỳ chỉ vì class nằm trên classpath.

Tên class cũng là chi tiết triển khai. Refactor package, đổi module hoặc nâng dependency có thể thay đổi các class có thể được resolve. Điều này làm contract JSON kém ổn định hơn logical type id.

### 4.2. Không dùng LaissezFaireSubTypeValidator cho dữ liệu không tin cậy

LaissezFaireSubTypeValidator là validator có tính permissive, về cơ bản không tạo allowlist chặt cho subtype. Nó có thể xuất hiện trong ví dụ cũ hoặc cấu hình legacy, nhưng không nên xem là biện pháp bảo vệ cho default typing trên input bên ngoài.

Tương tự, API enableDefaultTyping cũ đã bị deprecated trong Jackson 2.x để hướng ứng dụng sang activateDefaultTyping với validator rõ ràng. Việc chỉ thay API cũ bằng API mới mà truyền validator permissive không tự làm cấu hình trở nên an toàn.

### 4.3. PolymorphicTypeValidator giảm rủi ro nào?

Validator kiểm soát những kiểu được phép tham gia quá trình polymorphic type resolution. Nó giúp từ chối type id hoặc subtype ngoài chính sách trước khi dữ liệu được binding vào class đó.

Validator không thay thế mọi biện pháp bảo vệ JSON:

- Không giới hạn kích thước request hoặc độ sâu JSON.
- Không xác thực mọi field nghiệp vụ.
- Không kiểm tra quyền truy cập người dùng vào object.
- Không ngăn lỗi logic trong một subtype đã được allowlist.
- Không thay thế kiểm soát parser constraints, timeout hoặc giới hạn collection.
- Không biến class-name type id thành wire contract ổn định.

## 5. PolymorphicTypeValidator kiểm tra ở những giai đoạn nào?

PolymorphicTypeValidator định nghĩa ba bước kiểm tra chính. Mỗi bước có thể trả về một trong ba trạng thái:

| Trạng thái | Ý nghĩa |
|---|---|
| ALLOWED | Kiểu hoặc quyết định hiện tại được cho phép; có thể không cần kiểm tra sâu hơn |
| DENIED | Từ chối type resolution |
| INDETERMINATE | Chưa đủ thông tin; Jackson cần bước kiểm tra tiếp theo |

Các method cốt lõi:

- validateBaseType(...): kiểm tra declared base type mà polymorphic handling đang áp dụng.
- validateSubClassName(...): kiểm tra tên subtype từ type id trước khi resolve class.
- validateSubType(...): kiểm tra class subtype sau khi tên đã được resolve thành Java type.

### 5.1. Kiểm tra base type

Base type là kiểu mà property hoặc vị trí dữ liệu được khai báo. Ví dụ field khai báo Object, Payment hoặc một interface.

Nếu validator trả ALLOWED cho base type, điều đó có thể có nghĩa mọi subtype trong phạm vi base type này được chấp nhận và không cần kiểm tra thêm. Vì vậy, không nên cho phép một base type rộng như Object nếu mục đích là giới hạn subtype.

Một quy tắc allow base type quá rộng có thể vô hiệu hóa ý nghĩa allowlist subtype mà người viết nghĩ rằng mình đã thiết lập.

### 5.2. Kiểm tra tên subtype trước khi nạp class

Khi base type chưa được cho phép hoàn toàn, Jackson có thể đưa chuỗi type id cho validateSubClassName(...). Đây là cơ hội từ chối một class name không thuộc quy ước trước khi resolve class.

Ví dụ, ứng dụng chỉ dự định nhận các payload type trong một nhóm class nội bộ. Validator có thể kiểm tra prefix package hoặc một quy tắc tên class.

Kiểm tra tên giúp từ chối sớm, nhưng prefix string không phải allowlist hoàn hảo nếu package chứa class không an toàn hoặc có package name gần giống.

### 5.3. Kiểm tra subtype sau khi resolve

Nếu bước kiểm tra tên trả INDETERMINATE, Jackson có thể resolve class rồi gọi validateSubType(...). Đây là bước kiểm tra dựa trên class thực tế, cho phép kiểm tra quan hệ kế thừa hoặc kiểu cụ thể.

Một allowlist dựa trên base class an toàn thường hữu ích ở bước này: chỉ chấp nhận những subtype thực sự kế thừa một lớp marker được ứng dụng kiểm soát.

### 5.4. Vì sao có ba trạng thái?

Ba trạng thái giúp validator không phải quyết định chỉ bằng một chuỗi tên. Có thể:

1. Từ chối ngay base type không hợp lệ.
2. Cho phép một base type đã được chứng minh an toàn.
3. Kiểm tra type id string trước khi load class.
4. Nếu chưa kết luận, kiểm tra class subtype sau khi resolve.

DENIED là quyết định từ chối. INDETERMINATE không có nghĩa là cho phép; nó yêu cầu validator tiếp tục đánh giá ở giai đoạn sau.

## 6. Dùng BasicPolymorphicTypeValidator để tạo allowlist

BasicPolymorphicTypeValidator là implementation có sẵn, cho phép xây quy tắc theo base class, subtype class, package prefix hoặc pattern. Với Jackson 2.x, builder có thể dùng để tạo validator:

~~~java
BasicPolymorphicTypeValidator validator =
        BasicPolymorphicTypeValidator.builder()
                .allowIfSubType(TrustedPayload.class)
                .build();
~~~

Trong ví dụ, TrustedPayload là base class marker do ứng dụng sở hữu. Chỉ các class subtype phù hợp với loại payload được chọn mới được allow theo quy tắc này.

Kích hoạt default typing:

~~~java
ObjectMapper mapper = new ObjectMapper();

mapper.activateDefaultTyping(
        validator,
        ObjectMapper.DefaultTyping.NON_FINAL,
        JsonTypeInfo.As.WRAPPER_ARRAY
);
~~~

Đây là ví dụ kỹ thuật để minh họa cách validator giới hạn class-based type id. Với API nhận JSON công khai, vẫn nên cân nhắc tránh default typing và dùng explicit logical type id thay thế.

### 6.1. Tạo marker base class dành riêng cho payload

~~~java
public abstract class TrustedPayload {
    private String requestId;

    public String getRequestId() {
        return requestId;
    }

    public void setRequestId(String requestId) {
        this.requestId = requestId;
    }
}

public class UserPayload extends TrustedPayload {
    private String userId;

    public String getUserId() {
        return userId;
    }

    public void setUserId(String userId) {
        this.userId = userId;
    }
}

public class InvoicePayload extends TrustedPayload {
    private String invoiceId;

    public String getInvoiceId() {
        return invoiceId;
    }

    public void setInvoiceId(String invoiceId) {
        this.invoiceId = invoiceId;
    }
}
~~~

Các subtype cần được ứng dụng chủ động kiểm soát. Không nên đặt class tùy ý vào marker hierarchy chỉ để tránh validator từ chối.

### 6.2. Cho phép subtype cụ thể

Nếu chỉ có một số ít kiểu, có thể xây quy tắc theo class cụ thể:

~~~java
BasicPolymorphicTypeValidator validator =
        BasicPolymorphicTypeValidator.builder()
                .allowIfSubType(UserPayload.class)
                .allowIfSubType(InvoicePayload.class)
                .build();
~~~

Tùy API overload của Jackson version, allowIfSubType(Class<?>) có thể được dùng để cho phép class cụ thể hoặc các subtype của class đó. Hãy xác nhận ngữ nghĩa trong Javadoc của version dự án và ưu tiên một hierarchy marker hẹp nếu có nhiều subtype cùng nhóm.

Không dùng allowIfBaseType(Object.class) như một shortcut. Object là base type quá rộng; nếu được đánh dấu ALLOWED, validator có thể không cần kiểm tra subtype theo cách bạn dự định.

### 6.3. Allow theo package prefix

Có thể giới hạn class name theo package prefix:

~~~java
BasicPolymorphicTypeValidator validator =
        BasicPolymorphicTypeValidator.builder()
                .allowIfSubType("com.example.api.payload.")
                .build();
~~~

Dấu chấm cuối prefix có ý nghĩa: nó giúp tránh khớp nhầm package có tên bắt đầu giống nhưng không nằm trong namespace mong muốn.

Package allowlist rộng hơn class allowlist. Nếu package chứa tiện ích, helper hoặc class có hành vi ngoài DTO, mọi class phù hợp prefix có thể được mở rộng diện chấp nhận. Chỉ dùng cách này khi package được quản trị như một vùng tin cậy và không chứa kiểu nguy hiểm.

## 7. Allowlist và denylist: nên chọn cách nào?

Với polymorphic deserialization, allowlist thường dễ đánh giá hơn denylist.

**Allowlist** nêu rõ những loại dữ liệu ứng dụng chấp nhận. Khi thêm subtype mới, thay đổi cần được review và đăng ký rõ.

**Denylist** nêu các loại đã biết là nguy hiểm. Danh sách này có thể bỏ sót class mới từ dependency được thêm vào sau này.

Một chính sách tốt thường có:

- Base type marker do ứng dụng sở hữu.
- Subtype được đăng ký có chủ đích.
- Validator mặc định không cho phép các class ngoài allowlist.
- Test xác nhận class hợp lệ được đọc và class ngoài danh sách bị từ chối.
- Quy trình review khi thêm dependency hoặc subtype.

Không nên nghĩ rằng package prefix tự động là allowlist an toàn. Nó chỉ an toàn nếu nội dung package và quyền thêm class vào package được kiểm soát.

## 8. Tránh allow base type quá rộng

BasicPolymorphicTypeValidator có các quy tắc cho base type và subtype. Hai loại quy tắc có ý nghĩa khác nhau:

- allowIfBaseType(...) có thể cho phép polymorphic handling khi declared base type khớp quy tắc.
- allowIfSubType(...) giới hạn class subtype thực tế hoặc tên subtype theo quy tắc được cấu hình.

Ví dụ không nên dùng:

~~~java
BasicPolymorphicTypeValidator validator =
        BasicPolymorphicTypeValidator.builder()
                .allowIfBaseType(Object.class)
                .build();
~~~

Vì nhiều property động được khai báo Object, quy tắc này quá rộng và có thể khiến mọi subtype của Object nằm trong phạm vi được chấp nhận mà không còn bước giới hạn mong muốn.

Hãy để base type rộng ở trạng thái cần kiểm tra tiếp, rồi chỉ cho phép các subtype thuộc hierarchy an toàn hoặc danh sách class đã xác định.

## 9. Default typing và explicit @JsonTypeInfo khác nhau thế nào?

Hai cách đều có thể bật polymorphism, nhưng phạm vi và hợp đồng khác nhau.

| Tiêu chí | Default typing | Explicit JsonTypeInfo |
|---|---|---|
| Nơi cấu hình | Mapper-wide theo DefaultTyping | Class hoặc property cụ thể |
| Type id | Thường class name với default typing | Có thể logical name, class name hoặc custom id |
| Phạm vi | Có thể ảnh hưởng nhiều property | Chỉ vị trí được khai báo và kế thừa theo quy tắc annotation |
| Độ ổn định wire format | Gắn chặt với Java class/package nếu dùng class id | Logical id có thể ổn định qua refactor |
| Kiểm soát subtype | PolymorphicTypeValidator và typing config | Subtype registry/validator tùy Id strategy |
| Phù hợp | Một số graph nội bộ Java-centric | API/event contract có schema rõ |

Ví dụ explicit logical type:

~~~java
@JsonTypeInfo(
        use = JsonTypeInfo.Id.NAME,
        include = JsonTypeInfo.As.PROPERTY,
        property = "type"
)
@JsonSubTypes({
        @JsonSubTypes.Type(value = UserPayload.class, name = "user"),
        @JsonSubTypes.Type(value = InvoicePayload.class, name = "invoice")
})
public abstract class ApiPayload {
}
~~~

JSON:

~~~json
{
  "type": "invoice",
  "invoiceId": "INV-100"
}
~~~

Consumer không cần biết package hoặc class name. Đây thường là thiết kế tốt hơn cho API giữa các hệ thống hoặc payload do người dùng gửi.

## 10. PolymorphicTypeValidator không thay thế subtype registry nghiệp vụ

Validator trả lời câu hỏi: “Class này có được phép tham gia polymorphic deserialization không?”

Nó không trả lời đầy đủ câu hỏi: “Giá trị này có phải một loại nghiệp vụ hợp lệ trong API này không?”

Ví dụ, một class có thể thuộc package được allow nhưng không nên được phép trong một endpoint cụ thể. Ngược lại, một class được phép trong một integration nội bộ không có nghĩa nó được phép trong public API.

Nên tách các lớp kiểm soát:

1. Parser constraints giới hạn kích thước và cấu trúc JSON.
2. PolymorphicTypeValidator giới hạn class/type resolution.
3. DTO/schema validation kiểm tra field và miền giá trị.
4. Authorization kiểm tra caller có được phép thực hiện nghiệp vụ hay truy cập entity.
5. Service/domain layer kiểm tra invariant nghiệp vụ.

Một validator không phải firewall tổng quát cho toàn bộ dữ liệu.

## 11. Đặt validator cho class-based type id

PolymorphicTypeValidator đặc biệt quan trọng khi type id có thể resolve thành Java class, chẳng hạn default typing hoặc JsonTypeInfo.Id.CLASS / MINIMAL_CLASS.

Với logical type id JsonTypeInfo.Id.NAME, ứng dụng ánh xạ chuỗi như user hoặc invoice tới subtype đã đăng ký. Cách này không yêu cầu JSON cung cấp tên class đầy đủ. Nó giúp tránh phụ thuộc trực tiếp vào package name và làm allowlist subtype dễ đọc hơn.

Nếu phải duy trì class-based type id trong hệ thống cũ, hãy:

- Dùng validator hẹp.
- Không dùng LaissezFaireSubTypeValidator cho dữ liệu ngoài.
- Tránh base type Object được allow toàn phần.
- Giới hạn classpath và dependency có mặt trong runtime.
- Kiểm tra các class được phép thực sự là data model thụ động.
- Viết test từ chối class ngoài danh sách.
- Xem xét migration sang logical type id nếu contract cho phép.

## 12. Cấu hình mapper an toàn theo một boundary cụ thể

Không nên bật default typing trên một mapper global nếu ứng dụng dùng mapper đó cho nhiều luồng: public API, internal event, persistence cache và file import có thể có mức tin cậy khác nhau.

Nếu một integration nội bộ thực sự cần default typing, tạo mapper riêng và chỉ dùng tại boundary đó:

~~~java
BasicPolymorphicTypeValidator validator =
        BasicPolymorphicTypeValidator.builder()
                .allowIfSubType(TrustedPayload.class)
                .build();

ObjectMapper internalPayloadMapper = new ObjectMapper();

internalPayloadMapper.activateDefaultTyping(
        validator,
        ObjectMapper.DefaultTyping.NON_FINAL,
        JsonTypeInfo.As.WRAPPER_ARRAY
);
~~~

Mapper này cần được cấu hình xong trước khi chia sẻ cho nhiều thread. Không bật/tắt default typing theo từng request trên một mapper đang được dùng đồng thời.

Mapper public API nên có cấu hình riêng, thường không bật default typing:

~~~java
ObjectMapper publicApiMapper = JsonMapper.builder()
        .addModule(new JavaTimeModule())
        .build();
~~~

Với public API, dùng DTO cụ thể và explicit logical discriminator khi thật sự cần polymorphism.

## 13. Default typing có ảnh hưởng đến serialize không?

Có. Default typing điều khiển cả cách ghi type metadata và cách đọc type metadata. Khi serialize, Jackson có thể phát type id để round-trip được runtime subtype. Khi deserialize, validator quyết định type id có được chấp nhận hay không.

PolymorphicTypeValidator chủ yếu là một cơ chế kiểm tra ở quá trình type resolution khi đọc. Nó không phải bộ lọc field hoặc bộ kiểm tra nội dung output.

Một payload được serialize từ object hợp lệ trong ứng dụng vẫn có thể bị consumer khác từ chối nếu validator của consumer không cho phép subtype đó. Producer và consumer phải thống nhất chính sách type metadata và tập subtype.

### 13.1. Thay đổi chế độ default typing làm thay đổi wire format

Nếu đổi từ NON_FINAL sang JAVA_LANG_OBJECT, một số property có thể không còn type metadata hoặc được áp dụng khác. Nếu đổi inclusion từ WRAPPER_ARRAY sang PROPERTY, JSON shape cũng thay đổi.

Đây là thay đổi contract. Hãy kiểm tra fixture JSON, compatibility test và consumer trước khi triển khai.

### 13.2. deactivation

Jackson 2.x có API deactivateDefaultTyping() để tắt chính sách default typing đã cấu hình trên mapper. Việc này không xóa explicit JsonTypeInfo annotation khỏi model; annotation vẫn có thể yêu cầu polymorphic handling tại vị trí được khai báo.

Không dùng deactivateDefaultTyping() như một thao tác tạm thời trên mapper đang chia sẻ nhiều thread. Hãy tạo mapper đã cấu hình đúng cho từng boundary.

## 14. Xử lý type id không hợp lệ hoặc không được phép

Khi type id không được validator chấp nhận, Jackson sẽ từ chối polymorphic type resolution và thường phát sinh exception thuộc nhóm InvalidTypeIdException/JsonMappingException.

Các trường hợp cần phân biệt:

- Không có type id trong vị trí bắt buộc.
- Type id có cú pháp nhưng class không resolve được.
- Class resolve được nhưng validator từ chối.
- Class được allow nhưng không tương thích với base type.
- Class hợp lệ nhưng JSON field bên trong không phù hợp.

Các lỗi này có nguyên nhân khác nhau. Log nên giữ exception subtype, type id nếu an toàn, base type, property path và location. Không trả stack trace hoặc classpath nội bộ cho client.

Nếu muốn xử lý subtype chưa biết, hãy thiết kế explicit fallback model hoặc đọc payload thành JsonNode rồi xử lý unknown type có chủ đích. Không nên tắt validator hoặc cho phép mọi class để “sửa” lỗi unknown subtype.

## 15. Ví dụ test: cho phép hierarchy tin cậy, từ chối class ngoài

Giả sử ứng dụng có base class marker:

~~~java
public abstract class TrustedPayload {
    private String requestId;

    public String getRequestId() {
        return requestId;
    }

    public void setRequestId(String requestId) {
        this.requestId = requestId;
    }
}

public class UserPayload extends TrustedPayload {
    private String userId;

    public String getUserId() {
        return userId;
    }

    public void setUserId(String userId) {
        this.userId = userId;
    }
}

public class UnrelatedPayload {
    private String command;

    public String getCommand() {
        return command;
    }

    public void setCommand(String command) {
        this.command = command;
    }
}
~~~

Tạo validator và mapper:

~~~java
static ObjectMapper createMapper() {
    BasicPolymorphicTypeValidator validator =
            BasicPolymorphicTypeValidator.builder()
                    .allowIfSubType(TrustedPayload.class)
                    .build();

    ObjectMapper mapper = new ObjectMapper();
    mapper.activateDefaultTyping(
            validator,
            ObjectMapper.DefaultTyping.NON_FINAL,
            JsonTypeInfo.As.WRAPPER_ARRAY
    );

    return mapper;
}
~~~

Test round-trip cho subtype hợp lệ:

~~~java
@Test
void shouldRoundTripTrustedSubtype() throws Exception {
    ObjectMapper mapper = createMapper();

    UserPayload payload = new UserPayload();
    payload.setRequestId("REQ-1");
    payload.setUserId("U-100");

    String json = mapper.writerFor(Object.class)
            .writeValueAsString(payload);

    Object restored = mapper.readValue(json, Object.class);

    assertInstanceOf(UserPayload.class, restored);
}
~~~

Test từ chối subtype không nằm trong hierarchy allowlist cần dùng type id của class ngoài danh sách và xác nhận mapping thất bại. Khi viết test cho project thực tế, dùng đúng package name của class test và Jackson version đang chạy; đừng phụ thuộc một message string cụ thể.

~~~java
@Test
void shouldRejectSubtypeOutsideAllowlist() {
    ObjectMapper mapper = createMapper();

    String json = """
            [
              "com.example.other.UnrelatedPayload",
              {"command":"run"}
            ]
            """;

    assertThrows(
            JsonMappingException.class,
            () -> mapper.readValue(json, Object.class)
    );
}
~~~

Test cần bảo đảm type id trong fixture trỏ đến class có mặt trên test classpath. Mục tiêu là kiểm tra validator từ chối subtype, không phải kiểm tra lỗi class-not-found.

## 16. Những lỗi cấu hình thường gặp

**Bật default typing mà không truyền validator phù hợp.** Cấu hình cũ hoặc validator permissive không tạo allowlist có ý nghĩa.

**Dùng LaissezFaireSubTypeValidator với dữ liệu bên ngoài.** Validator permissive không giới hạn class-name type id theo chính sách an toàn.

**Allow base type Object.** Object quá rộng; có thể làm mất bước kiểm tra subtype mà ứng dụng trông đợi.

**Dùng NON_FINAL hoặc EVERYTHING mà không đánh giá phạm vi.** Chế độ rộng làm nhiều property nhận type metadata và tăng diện tích polymorphic deserialization.

**Allow toàn bộ package chỉ vì đó là package DTO.** Package có thể chứa class ngoài ý muốn hoặc thay đổi theo dependency/refactor. Hãy giới hạn bằng marker hierarchy hoặc class allowlist khi có thể.

**Cho rằng validator kiểm tra field nghiệp vụ.** Validator kiểm tra type resolution, không thay thế schema validation, Bean Validation hoặc authorization.

**Cho rằng explicit logical type id cần class-name validator giống default typing.** Id.NAME ánh xạ logical name tới subtype đã đăng ký; nó không yêu cầu input chỉ định package/class name.

**Chia sẻ một mapper rồi thay đổi default typing theo request.** Mapper cần được cấu hình trước khi sử dụng đồng thời; dùng mapper riêng theo trust boundary.

**Chỉ test payload hợp lệ.** Cần test class ngoài allowlist, type id sai, thiếu type id và subtype không tương thích base type.

**Dùng default typing như giải pháp polymorphism cho public API.** Explicit logical discriminator thường ổn định và dễ kiểm soát hơn.

## 17. Hướng tiếp cận cho API nhận dữ liệu không tin cậy

Với JSON do client, webhook hoặc đối tác gửi, một quy trình an toàn thường là:

1. Xác định DTO đầu vào cụ thể thay vì deserialize vào Object chung.
2. Dùng explicit discriminator với logical type name nếu cần subtype.
3. Đăng ký subtype được phép bằng annotation hoặc module rõ ràng.
4. Không bật default typing toàn mapper.
5. Nếu legacy bắt buộc default typing, dùng PolymorphicTypeValidator allowlist hẹp và mapper riêng.
6. Giới hạn request size, nesting depth, token length và collection size.
7. Validate field và invariant sau khi binding.
8. Kiểm tra authorization ở service layer.
9. Log type id/path một cách an toàn, tránh raw payload nhạy cảm.
10. Duy trì test từ chối subtype không mong muốn qua mỗi lần nâng Jackson hoặc dependency.

Đối với event nội bộ, vẫn cần xác định trust boundary. “Nội bộ” không có nghĩa mọi message đều đáng tin: queue có thể nhận dữ liệu từ nhiều producer, replay file có thể đã bị chỉnh sửa và credential của producer có thể bị lộ.

## 18. Khi nào default typing có thể chấp nhận được?

Default typing có thể có chỗ đứng trong hệ thống kiểm soát chặt, chẳng hạn cache nội bộ hoặc format lưu trữ Java-centric, khi:

- Producer và consumer cùng thuộc một trust boundary.
- Payload không thể bị người dùng bên ngoài tùy ý sửa.
- Tập subtype được kiểm soát và validator có allowlist rõ.
- Classpath runtime được quản trị.
- Format có versioning và migration.
- Có kiểm thử từ chối type id ngoài danh sách.
- Có parser constraints và giới hạn tài nguyên.

Ngay cả trong trường hợp đó, hãy cân nhắc lưu DTO/event schema có version hoặc explicit logical discriminator thay vì tên class. Điều này giảm coupling giữa dữ liệu lưu trữ với package Java.

## 19. Checklist đánh giá cấu hình

Trước khi bật default typing, hãy trả lời:

- Có thật sự cần giữ runtime subtype khi serialize/deserialize không?
- Có thể dùng explicit JsonTypeInfo.Id.NAME không?
- Mapper có nhận JSON từ người dùng hoặc hệ thống ngoài không?
- DefaultTyping mode nào là phạm vi hẹp nhất đáp ứng nhu cầu?
- Validator có allow base type rộng như Object không?
- Allowlist dựa trên class/hierarchy hay package prefix?
- Package được allow có chứa class có side effect hoặc class từ dependency không?
- Type id có thể làm thay đổi khi refactor package không?
- Mapper có được tách theo trust boundary không?
- Có test xác nhận subtype hợp lệ và subtype bị từ chối không?
- Parser constraints và validation nghiệp vụ đã được cấu hình chưa?
- Có kế hoạch nâng cấp và tương thích dữ liệu cũ không?

Nếu chưa trả lời được các câu hỏi này, chưa nên bật default typing trên dữ liệu không tin cậy.

## 20. Kết luận

Default typing giúp Jackson tự thêm polymorphic type metadata cho những declared type thuộc phạm vi được chọn. Cơ chế này tiện cho một số object graph nội bộ nhưng có thể làm JSON phụ thuộc vào tên class và mở rộng khả năng khởi tạo subtype từ input. Với dữ liệu không tin cậy, default typing rộng hoặc validator permissive có thể tạo rủi ro deserialization nghiêm trọng.

PolymorphicTypeValidator cung cấp các bước kiểm tra base type, tên subtype và class subtype thực tế, với kết quả ALLOWED, DENIED hoặc INDETERMINATE. BasicPolymorphicTypeValidator có thể xây allowlist theo class hierarchy hoặc package prefix; hãy ưu tiên marker base class hẹp, tránh allow base type Object và kiểm thử các type id bị từ chối. Validator chỉ kiểm soát type resolution, không thay thế parser constraints, validation hay authorization.

Với public API và event contract giữa nhiều hệ thống, explicit logical type id như user hoặc invoice thường ổn định và dễ review hơn class-name default typing. Chỉ dùng default typing khi có lý do kỹ thuật rõ, trust boundary được xác định, mapper được cô lập và allowlist được duy trì như một phần của chính sách bảo mật.

## Tài liệu tham khảo

- [Jackson Databind — ObjectMapper API](https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-databind/latest/com/fasterxml/jackson/databind/ObjectMapper.html)
- [Jackson Databind — PolymorphicTypeValidator API](https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-databind/latest/com/fasterxml/jackson/databind/jsontype/PolymorphicTypeValidator.html)
- [Jackson Databind — BasicPolymorphicTypeValidator API](https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-databind/latest/com/fasterxml/jackson/databind/jsontype/BasicPolymorphicTypeValidator.html)
- [Jackson Databind — DefaultTyping API](https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-databind/latest/com/fasterxml/jackson/databind/ObjectMapper.DefaultTyping.html)
- [Jackson Annotations — JsonTypeInfo API](https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-annotations/latest/com/fasterxml/jackson/annotation/JsonTypeInfo.html)
- [Jackson Databind — Polymorphic Deserialization documentation](https://github.com/FasterXML/jackson-docs/wiki/JacksonPolymorphicDeserialization)

