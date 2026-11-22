# Phân biệt tên kiểu ổn định trong hợp đồng và tên lớp triển khai

## 1. Vì sao tên kiểu đa hình là một phần của hợp đồng JSON?

Một API có thể trả về nhiều biến thể của cùng một khái niệm. Ví dụ, một giao dịch thanh toán có thể dùng thẻ ngân hàng hoặc ví điện tử. Trong Java, các biến thể thường được mô hình hóa bằng một lớp cha hoặc interface và nhiều lớp triển khai:

    PaymentMethod
       ├── CardPayment
       └── WalletPayment

Khi Jackson serialize một đối tượng thông qua kiểu cha, consumer cần biết JSON đó đại diện cho biến thể nào để tạo đúng kiểu Java khi deserialize. Thông tin này được gọi là **type id** hoặc **type discriminator**.

Ví dụ JSON có thể mang một trường phân biệt:

    {
      "kind": "card",
      "lastFourDigits": "4242"
    }

Giá trị card là tên kiểu trong hợp đồng dữ liệu. Nó mô tả biến thể nghiệp vụ mà producer muốn gửi. Consumer có thể ánh xạ tên đó sang một lớp Java cụ thể, nhưng tên lớp không nhất thiết phải xuất hiện trong JSON.

Điểm quan trọng là phân biệt:

- **Tên kiểu ổn định (logical type name):** định danh do hợp đồng JSON quy định, ví dụ card hoặc wallet.
- **Tên lớp triển khai (implementation class name):** tên Java như com.example.payment.CardPayment.

Tên lớp là chi tiết triển khai của một phiên bản phần mềm. Tên kiểu logic là một phần của giao thức giữa producer và consumer. Nếu đưa tên lớp trực tiếp vào payload, việc đổi package hoặc đổi tên lớp có thể làm hỏng khả năng đọc dữ liệu đã lưu và tương thích giữa các phiên bản.

## 2. Jackson hỗ trợ nhiều chiến lược type id

Jackson dùng annotation JsonTypeInfo để xác định cách đưa thông tin kiểu vào JSON và cách dùng thông tin đó khi đọc JSON. Thuộc tính use chọn chiến lược type id.

| Chiến lược | Nội dung type id | Đặc điểm |
|---|---|---|
| Id.NAME | Tên logic được ánh xạ tới subtype | Tách hợp đồng JSON khỏi tên lớp Java |
| Id.CLASS | Tên lớp Java đầy đủ, gồm package | Gắn chặt payload với tên lớp và package |
| Id.MINIMAL_CLASS | Tên lớp rút gọn tương đối với package cơ sở | Vẫn phụ thuộc cấu trúc package |
| Id.CUSTOM | Giá trị do TypeIdResolver tùy biến | Có thể thực hiện quy ước riêng, nhưng cần tự quản lý mapping |
| Id.DEDUCTION | Suy luận subtype từ tập thuộc tính JSON | Không gửi type id tường minh; phụ thuộc cấu trúc field phân biệt được subtype |

Nếu mục tiêu là một hợp đồng JSON có thể tồn tại qua nhiều lần refactor Java, Id.NAME thường là lựa chọn phù hợp. Producer gửi một định danh có ý nghĩa nghiệp vụ; mỗi phiên bản ứng dụng ánh xạ định danh đó sang lớp triển khai hiện tại của mình.

## 3. Dùng Id.NAME với tên subtype tường minh

Ví dụ dưới đây khai báo một kiểu cơ sở PaymentMethod và hai subtype. JsonTypeInfo đặt trên kiểu cơ sở để Jackson biết cần dùng type id khi xử lý đối tượng thông qua PaymentMethod.

~~~java
import com.fasterxml.jackson.annotation.JsonSubTypes;
import com.fasterxml.jackson.annotation.JsonTypeInfo;

@JsonTypeInfo(
        use = JsonTypeInfo.Id.NAME,
        include = JsonTypeInfo.As.PROPERTY,
        property = "kind"
)
@JsonSubTypes({
        @JsonSubTypes.Type(
                value = CardPayment.class,
                name = "card"
        ),
        @JsonSubTypes.Type(
                value = WalletPayment.class,
                name = "wallet"
        )
})
public abstract class PaymentMethod {
}
~~~

Các lớp triển khai:

~~~java
public class CardPayment extends PaymentMethod {
    private String lastFourDigits;

    public CardPayment() {
    }

    public CardPayment(String lastFourDigits) {
        this.lastFourDigits = lastFourDigits;
    }

    public String getLastFourDigits() {
        return lastFourDigits;
    }

    public void setLastFourDigits(String lastFourDigits) {
        this.lastFourDigits = lastFourDigits;
    }
}
~~~

~~~java
public class WalletPayment extends PaymentMethod {
    private String provider;

    public WalletPayment() {
    }

    public WalletPayment(String provider) {
        this.provider = provider;
    }

    public String getProvider() {
        return provider;
    }

    public void setProvider(String provider) {
        this.provider = provider;
    }
}
~~~

Khi serialize một biến có kiểu tham chiếu PaymentMethod, Jackson ghi type id theo tên logic đã khai báo:

~~~java
ObjectMapper mapper = new ObjectMapper();

PaymentMethod payment = new CardPayment("4242");
String json = mapper.writerFor(PaymentMethod.class)
        .writeValueAsString(payment);

System.out.println(json);
~~~

JSON có dạng:

~~~json
{
  "kind": "card",
  "lastFourDigits": "4242"
}
~~~

Khi đọc lại thông qua kiểu cơ sở:

~~~java
PaymentMethod restored = mapper.readValue(json, PaymentMethod.class);

if (restored instanceof CardPayment card) {
    System.out.println(card.getLastFourDigits());
}
~~~

Jackson đọc kind, tìm subtype đã đăng ký với tên card rồi tạo CardPayment. Payload không cần biết package hoặc tên lớp Java.

Trong ví dụ, writerFor(PaymentMethod.class) làm rõ rằng serialization đang diễn ra theo kiểu cơ sở có khai báo thông tin đa hình. Nếu serialize trực tiếp một biến với kiểu tĩnh là lớp triển khai, việc áp dụng type metadata còn phụ thuộc cấu hình và annotation ở hệ phân cấp; khi hợp đồng yêu cầu discriminator, nên kiểm thử bằng đúng kiểu khai báo mà API thực sự sử dụng.

## 4. Tên logic phải được chọn tường minh

Không nên để tên logic vô tình phụ thuộc vào tên lớp hoặc cách đặt tên Java. Hãy chọn các giá trị có ý nghĩa trong miền nghiệp vụ:

| Tên logic trong JSON | Lớp triển khai hiện tại |
|---|---|
| card | CardPayment |
| wallet | WalletPayment |
| bank-transfer | BankTransferPayment |

Các tên card, wallet và bank-transfer là định danh giao thức. Chúng có thể giữ nguyên khi lớp Java được đổi tên hoặc chuyển package.

Một số nguyên tắc đặt tên:

- Chọn tên ngắn, rõ nghĩa và không phụ thuộc ngôn ngữ lập trình.
- Dùng một quy ước nhất quán, chẳng hạn lowercase với dấu gạch ngang.
- Tránh dùng tên package, tên module hoặc tên lớp làm giá trị type id.
- Không tái sử dụng một type id cũ cho một ý nghĩa nghiệp vụ khác.
- Xem type id như giá trị schema cần được quản lý, kiểm thử và duy trì tương thích.

Type id không nên là tên tùy ý do client tự chọn để yêu cầu máy chủ khởi tạo một lớp bất kỳ. Nó phải thuộc tập biến thể mà hợp đồng cho phép.

## 5. Đổi tên lớp mà không đổi hợp đồng JSON

Giả sử phiên bản đầu dùng lớp CardPayment:

    package com.example.payment;

    public class CardPayment extends PaymentMethod {
        // ...
    }

Payload được lưu:

    {
      "kind": "card",
      "lastFourDigits": "4242"
    }

Trong phiên bản sau, nhóm phát triển có thể đổi tên lớp thành BankCardMethod hoặc chuyển nó sang package khác:

    package com.example.billing.method;

    public class BankCardMethod extends PaymentMethod {
        // ...
    }

Nếu subtype mapping vẫn khai báo tên logic card cho lớp mới, JSON đã lưu tiếp tục được đọc:

~~~java
@JsonSubTypes({
        @JsonSubTypes.Type(
                value = BankCardMethod.class,
                name = "card"
        ),
        @JsonSubTypes.Type(
                value = WalletPayment.class,
                name = "wallet"
        )
})
~~~

Định danh card trong hợp đồng không đổi. Producer mới và consumer cũ có thể tiếp tục trao đổi payload theo cùng một schema nếu các field nghiệp vụ còn tương thích.

Đây là lợi ích chính của việc tách type id khỏi class name: refactor nội bộ không nhất thiết kéo theo thay đổi giao thức hoặc dữ liệu lưu trữ.

## 6. Điều gì xảy ra khi dùng Id.CLASS?

Nếu dùng Id.CLASS, Jackson đưa tên lớp đầy đủ vào JSON. Ví dụ:

~~~java
@JsonTypeInfo(
        use = JsonTypeInfo.Id.CLASS,
        include = JsonTypeInfo.As.PROPERTY,
        property = "@class"
)
public abstract class PaymentMethod {
}
~~~

Payload có thể chứa:

~~~json
{
  "@class": "com.example.payment.CardPayment",
  "lastFourDigits": "4242"
}
~~~

Consumer cần tìm lớp theo tên được gửi. Điều này tạo ra sự phụ thuộc trực tiếp giữa JSON và cấu trúc mã nguồn Java:

- Đổi package làm tên lớp trong payload cũ không còn trỏ đến lớp hiện tại.
- Đổi tên lớp có thể làm dữ liệu đã lưu không đọc được nếu không có cơ chế tương thích.
- Consumer cần có lớp với đúng tên và classpath tương ứng.
- Payload bộc lộ cấu trúc nội bộ của ứng dụng.

Id.MINIMAL_CLASS giảm độ dài tên bằng cách dùng tên tương đối với package cơ sở của kiểu khai báo. Nó vẫn gắn type id với cấu trúc package và tên lớp, vì vậy không giải quyết được vấn đề hợp đồng độc lập với implementation.

Id.CLASS có thể hữu ích trong một số hệ thống Java nội bộ, có kiểm soát chặt cả producer lẫn consumer và có lý do cụ thể để dùng tên lớp. Tuy nhiên, với JSON được lưu lâu dài, gửi qua API công khai hoặc trao đổi giữa các dịch vụ có vòng đời phát hành độc lập, type name logic thường bền vững hơn.

## 7. Đăng ký subtype bằng mã thay vì annotation

Ngoài JsonSubTypes, có thể đăng ký tên logic với ObjectMapper thông qua NamedType:

~~~java
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.jsontype.NamedType;

ObjectMapper mapper = new ObjectMapper();
mapper.registerSubtypes(
        new NamedType(CardPayment.class, "card"),
        new NamedType(WalletPayment.class, "wallet")
);
~~~

Kiểu cơ sở vẫn cần khai báo JsonTypeInfo với Id.NAME để Jackson biết cần dùng cơ chế type id theo tên:

~~~java
@JsonTypeInfo(
        use = JsonTypeInfo.Id.NAME,
        include = JsonTypeInfo.As.PROPERTY,
        property = "kind"
)
public abstract class PaymentMethod {
}
~~~

Đăng ký bằng mã hữu ích khi:

- Muốn tập trung cấu hình polymorphism tại một module cấu hình.
- Không thể sửa lớp domain hoặc lớp thư viện bên ngoài.
- Cần dùng Jackson Mix-in hoặc cấu hình theo ứng dụng.
- Muốn kiểm soát tập subtype được phép ở từng ObjectMapper.

Hãy bảo đảm mapper dùng để serialize và mapper dùng để deserialize có cùng quy ước type id. Nếu producer phát kind = card nhưng consumer không đăng ký subtype đó, consumer không thể tạo đúng biến thể.

## 8. Dùng JsonTypeName khi muốn đặt tên ngay trên subtype

JsonTypeName cho phép gắn tên logic với lớp subtype:

~~~java
import com.fasterxml.jackson.annotation.JsonTypeName;

@JsonTypeName("card")
public class CardPayment extends PaymentMethod {
    // ...
}
~~~

Tên này là metadata của Jackson, không phải tên lớp Java. Khi subtype được nhận diện bởi cơ chế resolver và được đăng ký phù hợp, Jackson có thể dùng tên đã khai báo thay vì tên lớp.

Có thể chọn một trong các cách quản lý:

- Khai báo mapping tập trung trên kiểu cơ sở bằng JsonSubTypes.
- Đặt JsonTypeName trên từng subtype và đăng ký subtype với mapper.
- Đăng ký NamedType trong cấu hình mapper.

Tránh duy trì nhiều nguồn mapping mâu thuẫn. Nếu cùng một subtype được gắn nhiều tên, cần xác định tên nào là canonical cho chiều serialization và cách nhận tên cũ trong chiều deserialization.

## 9. Hình thức đưa type id vào JSON

JsonTypeInfo còn có thuộc tính include để chọn vị trí type id. Một số hình thức thường gặp:

| Include mode | Cách thể hiện | Ví dụ khái niệm |
|---|---|---|
| As.PROPERTY | Một property trong object | {"kind":"card","lastFourDigits":"4242"} |
| As.EXISTING_PROPERTY | Dùng property discriminator đã có trong mô hình | Object có field kind được serialize như property thông thường |
| As.WRAPPER_OBJECT | Type id làm tên key bọc payload | {"card":{"lastFourDigits":"4242"}} |
| As.WRAPPER_ARRAY | Type id là phần tử đầu trong array wrapper | ["card",{"lastFourDigits":"4242"}] |
| As.EXTERNAL_PROPERTY | Type id nằm cạnh property chứa giá trị đa hình | {"paymentKind":"card","payment":{...}} |

As.PROPERTY thường dễ đọc và phổ biến với API JSON. As.WRAPPER_OBJECT hoặc As.WRAPPER_ARRAY có thể phù hợp khi schema muốn thể hiện biến thể bằng cấu trúc wrapper. As.EXTERNAL_PROPERTY hữu ích trong một số mô hình chứa nhiều field liên quan.

Hãy chọn hình thức theo hợp đồng API và kiểm thử payload thực tế. Đổi include mode có thể thay đổi cấu trúc JSON, nên đây là thay đổi schema chứ không chỉ là refactor cấu hình.

### Thuộc tính visible

Với As.PROPERTY, type id mặc định được Jackson sử dụng để chọn subtype và không nhất thiết được gán vào một field Java cùng tên. Thuộc tính visible của JsonTypeInfo điều khiển việc type id có tiếp tục được chuyển cho quá trình deserialization như một property thông thường hay không.

Nếu đặt visible = true, lớp triển khai có thể nhận giá trị discriminator vào một thuộc tính phù hợp. Chỉ bật khi mô hình thực sự cần lưu type id như dữ liệu thường; nếu không, mặc định thường đơn giản hơn.

## 10. Xử lý type id không được biết

Với Id.NAME, consumer cần biết type id được gửi. Nếu payload chứa:

    {
      "kind": "crypto-wallet",
      "address": "..."
    }

nhưng mapper không có subtype được đăng ký với tên crypto-wallet, Jackson thường ném InvalidTypeIdException trong quá trình deserialization.

Đây là tình huống khác với unknown property:

| Tình huống | Ví dụ | Lỗi/cơ chế |
|---|---|---|
| Unknown property | Có field loyaltyLevel mà lớp không khai báo | FAIL_ON_UNKNOWN_PROPERTIES |
| Unknown type id | kind = crypto-wallet nhưng chưa đăng ký subtype | InvalidTypeIdException / type id resolution |
| Known type, unknown property | kind = card nhưng payload có field mới | Chính sách unknown property của subtype |
| Known type, invalid value | kind = card nhưng lastFourDigits có kiểu object không hợp lệ | Lỗi mapping/coercion theo property |

Không nên tự động biến mọi type id lạ thành một subtype mặc định nếu ý nghĩa nghiệp vụ không tương đương. Chẳng hạn, không thể an toàn coi một phương thức thanh toán chưa biết là CardPayment chỉ để quá trình đọc không lỗi.

Nếu cần hỗ trợ type id cũ, hãy thêm mapping tương thích có chủ đích và giữ một tên canonical cho chiều ghi. Nếu cần giữ nguyên biến thể chưa biết để chuyển tiếp, có thể đọc envelope hoặc payload thành JsonNode và xử lý discriminator như dữ liệu mở, thay vì ép nó vào một subtype không phù hợp.

## 11. Tên logic hỗ trợ phiên bản producer và consumer độc lập

Giả sử hệ thống có các phiên bản:

| Phiên bản | Type id được phát | Lớp Java |
|---|---|---|
| Producer v1 | card | CardPayment |
| Producer v2 | card | BankCardMethod |
| Consumer v1 | card | CardPayment |
| Consumer v2 | card | BankCardMethod |

Các phiên bản có thể dùng những lớp Java khác nhau nhưng cùng hiểu tên card. Điều kiện là cấu trúc field và semantics của subtype vẫn tương thích.

Nếu phiên bản mới cần thêm một biến thể, ví dụ bank-transfer, có thể bổ sung type id mới mà không thay đổi card hoặc wallet. Consumer cũ cần có chính sách rõ ràng cho type id chưa biết: từ chối, chuyển tiếp dưới dạng cây JSON, hoặc xử lý bằng một fallback được định nghĩa đúng nghiệp vụ.

Không nên thay type id card thành bank-card chỉ vì lớp Java được đổi tên. Nếu muốn đổi tên định danh giao thức, cần một kế hoạch migration:

1. Xác định tên mới và thời điểm bắt đầu phát.
2. Cập nhật consumer để nhận cả tên cũ và tên mới trong giai đoạn chuyển tiếp.
3. Chỉ chuyển producer sang phát tên mới khi consumer cần thiết đã được triển khai.
4. Theo dõi lượng payload còn dùng tên cũ.
5. Loại bỏ tên cũ sau khi hết thời hạn tương thích và dữ liệu cũ đã được xử lý.

Nếu cần nhận nhiều alias cho cùng một subtype, có thể dùng TypeIdResolver tùy biến hoặc lớp chuyển đổi ở ranh giới dữ liệu. Cần bảo đảm serializer luôn phát một tên canonical để payload mới không dao động giữa nhiều tên.

## 12. Bảo mật khi xử lý type metadata

Type id từ JSON có thể ảnh hưởng đến lớp mà Jackson tạo ra. Vì vậy, không nên để dữ liệu không đáng tin cậy tùy ý quyết định implementation class được khởi tạo.

Một số nguyên tắc:

- Ưu tiên Id.NAME với tập subtype được đăng ký rõ ràng cho các hợp đồng JSON bên ngoài.
- Chỉ đăng ký những subtype ứng dụng thực sự cho phép.
- Kiểm tra quyền và dữ liệu sau khi deserialize; biết type id hợp lệ không có nghĩa request hợp lệ về nghiệp vụ.
- Tránh bật default typing rộng trên payload không đáng tin cậy.
- Nếu hệ thống cần default typing, dùng PolymorphicTypeValidator với allowlist hẹp và đánh giá cấu hình theo đúng phiên bản Jackson.
- Không dùng tên lớp gửi từ client như một cơ chế chọn class tùy ý.

Id.CLASS và default typing có thể tạo rủi ro khi dữ liệu đầu vào có thể chỉ định các kiểu nằm trên classpath. Jackson đã bổ sung các cơ chế kiểm soát polymorphic typing qua validator, nhưng ứng dụng vẫn phải cấu hình allowlist đúng cách. Dùng Id.NAME với mapping tường minh giúp giới hạn tập biến thể có thể được tạo.

Ngay cả khi dùng Id.NAME, vẫn cần kiểm soát type id. Một logical name không phải bí mật hay cơ chế phân quyền; nó chỉ chọn subtype trong tập đã được cấu hình. Mọi field và hành động của subtype vẫn cần validation và authorization thông thường.

## 13. Kiểm thử hợp đồng type id

Không chỉ kiểm tra rằng một đối tượng có thể serialize và deserialize trong cùng một phiên bản. Hãy kiểm thử JSON như một hợp đồng độc lập với implementation.

Các ca kiểm thử nên có:

| Ca | Mục tiêu | Kết quả cần xác nhận |
|---|---|---|
| T01 | Serialize CardPayment qua PaymentMethod | JSON chứa kind = card |
| T02 | Deserialize JSON kind = card | Tạo đúng subtype hiện tại |
| T03 | Refactor/đổi tên lớp nhưng giữ mapping | Payload cũ vẫn đọc được |
| T04 | JSON có type id chưa đăng ký | Bị từ chối hoặc đi qua fallback đã định nghĩa |
| T05 | JSON có field mới trên subtype đã biết | Theo chính sách unknown-property của subtype |
| T06 | Đọc rồi ghi lại payload cũ | Type id canonical vẫn ổn định |
| T07 | Consumer cũ nhận type id mới | Chính sách tương thích được thực hiện rõ ràng |

Ví dụ test JUnit cho tên logic:

~~~java
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

class PaymentTypeIdTest {
    private final ObjectMapper mapper = new ObjectMapper();

    @Test
    void writesStableLogicalTypeName() throws Exception {
        PaymentMethod payment = new CardPayment("4242");

        String json = mapper.writerFor(PaymentMethod.class)
                .writeValueAsString(payment);

        assertTrue(json.contains("\"kind\":\"card\""));
        assertFalse(json.contains("CardPayment"));
    }

    @Test
    void readsLogicalTypeNameIntoRegisteredSubtype() throws Exception {
        String json = """
                {
                  "kind": "card",
                  "lastFourDigits": "4242"
                }
                """;

        PaymentMethod payment = mapper.readValue(
                json,
                PaymentMethod.class
        );

        assertInstanceOf(CardPayment.class, payment);
        assertEquals("4242", ((CardPayment) payment).getLastFourDigits());
    }
}
~~~

Test đầu xác nhận payload chứa tên logic và không rò rỉ tên lớp. Test thứ hai xác nhận cùng type id được ánh xạ về subtype mà phiên bản hiện tại đăng ký.

Trong hệ thống nhiều service, nên lưu một số JSON fixture đại diện cho từng phiên bản hợp đồng. Mỗi phiên bản consumer chạy test đọc fixture cũ và fixture mới theo chính sách đã công bố. Điều này phát hiện lỗi do đổi tên lớp, package hoặc type id trước khi phát hành.

## 14. Chọn Id.NAME, Id.CLASS hay chiến lược khác?

| Nhu cầu | Lựa chọn thường phù hợp | Lý do |
|---|---|---|
| API công khai hoặc message lưu lâu dài | Id.NAME | Type id là tên hợp đồng ổn định |
| Các service Java phát hành độc lập | Id.NAME | Không buộc mọi service có cùng package/class name |
| Refactor package hoặc đổi tên lớp thường xuyên | Id.NAME | Mapping nội bộ có thể thay đổi mà payload không đổi |
| Dữ liệu Java nội bộ, classpath và phiên bản được kiểm soát chặt | Có thể cân nhắc Id.CLASS | Chỉ khi phụ thuộc tên lớp là chủ ý của thiết kế |
| Quy tắc type id đặc biệt hoặc alias phức tạp | Id.CUSTOM | Cho phép tự quản lý cách phân giải tên |
| Subtype phân biệt rõ bằng tập field, không cần discriminator | Có thể cân nhắc Id.DEDUCTION | Không có type id tường minh, nhưng phụ thuộc schema không mơ hồ |

Nếu đang thiết kế một hợp đồng mới và không có lý do mạnh để phụ thuộc tên lớp, hãy bắt đầu với Id.NAME và các tên subtype được khai báo tường minh.

## 15. Kết luận

Trong ánh xạ đa hình của Jackson, type id cho biết một JSON object thuộc biến thể nào của kiểu cơ sở. Id.NAME dùng tên logic do hợp đồng định nghĩa, chẳng hạn card hoặc wallet, rồi ánh xạ tên đó sang lớp Java hiện tại. Id.CLASS và Id.MINIMAL_CLASS đưa tên lớp hoặc tên lớp rút gọn vào payload, khiến dữ liệu phụ thuộc package và cách đặt tên implementation. Khi cần JSON bền vững qua refactor và các phiên bản producer/consumer độc lập, hãy dùng tên logic, đăng ký subtype tường minh, kiểm thử cả serialize lẫn deserialize và quản lý migration của type id như một thay đổi schema. Đồng thời giới hạn tập subtype được phép để tránh biến metadata từ JSON thành cơ chế khởi tạo lớp tùy ý.
