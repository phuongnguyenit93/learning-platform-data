# Ánh xạ enum theo tên và theo giá trị nghiệp vụ

Enum trong Java thường biểu diễn một tập trạng thái hoặc lựa chọn có giới hạn, chẳng hạn trạng thái đơn hàng, phương thức thanh toán hay vai trò người dùng. Khi trao đổi dữ liệu JSON, Jackson cần chuyển một giá trị JSON thành đúng hằng enum và ghi hằng enum thành một giá trị JSON tương ứng.

Có hai cách biểu diễn thường gặp:

- **Theo tên enum**: JSON dùng chính tên hằng trong source code, ví dụ "PENDING", "PAID".
- **Theo giá trị nghiệp vụ**: JSON dùng một mã ổn định theo hợp đồng, ví dụ "WAITING_PAYMENT", "SETTLED", "VOID".

Ánh xạ theo tên đơn giản và phù hợp khi tên enum Java cũng chính là hợp đồng JSON. Ánh xạ theo mã nghiệp vụ hữu ích khi API cần giữ ổn định dù tên hằng Java thay đổi, hoặc mã trao đổi khác với cách đặt tên trong code.

## 1. Enum là gì và vì sao cần ánh xạ?

Enum là kiểu Java định nghĩa một tập hằng số cố định:

~~~java
public enum OrderStatus {
    PENDING,
    CONFIRMED,
    SHIPPED,
    CANCELLED
}
~~~

Một field có thể sử dụng enum:

~~~java
public class Order {
    private String orderId;
    private OrderStatus status;

    public Order() {
    }

    public String getOrderId() {
        return orderId;
    }

    public void setOrderId(String orderId) {
        this.orderId = orderId;
    }

    public OrderStatus getStatus() {
        return status;
    }

    public void setStatus(OrderStatus status) {
        this.status = status;
    }
}
~~~

JSON tương ứng có thể là:

~~~json
{
  "orderId": "ORD-1001",
  "status": "PENDING"
}
~~~

Khi serialize, Jackson chuyển hằng enum thành giá trị JSON. Khi deserialize, Jackson tìm hằng enum tương ứng với giá trị nhận được.

Việc ánh xạ cần một quy tắc rõ ràng. Nếu quy tắc chỉ dựa vào tên hằng Java, đổi tên hằng có thể ảnh hưởng hợp đồng JSON. Nếu dùng mã nghiệp vụ riêng, source code có thể thay đổi tên nội bộ mà vẫn giữ mã trao đổi ổn định.

## 2. Ánh xạ enum theo tên mặc định

### 2.1. Serialization theo tên hằng

Với enum đơn giản:

~~~java
public enum OrderStatus {
    PENDING,
    PAID,
    CANCELLED
}
~~~

Jackson Databind 2.x thường serialize enum thành tên hằng:

~~~java
ObjectMapper mapper = new ObjectMapper();

String json = mapper.writeValueAsString(OrderStatus.PAID);
System.out.println(json);
~~~

Kết quả:

~~~json
"PAID"
~~~

Nếu enum là property của object:

~~~java
Order order = new Order();
order.setOrderId("ORD-1001");
order.setStatus(OrderStatus.PAID);

String json = mapper.writeValueAsString(order);
~~~

JSON có dạng:

~~~json
{
  "orderId": "ORD-1001",
  "status": "PAID"
}
~~~

Tên hằng Java trở thành giá trị string trong JSON.

### 2.2. Deserialization theo tên hằng

Jackson có thể đọc lại giá trị string tương ứng:

~~~java
OrderStatus status = mapper.readValue(
        "\"PAID\"",
        OrderStatus.class
);

System.out.println(status);
~~~

Kết quả là hằng OrderStatus.PAID.

Mặc định thông thường, việc khớp tên enum phân biệt chữ hoa và chữ thường. Ví dụ "PAID" khớp với PAID, còn "paid" có thể không khớp nếu chưa bật cấu hình cho phép case-insensitive.

### 2.3. Ưu điểm và giới hạn

Ánh xạ theo tên phù hợp khi:

- Tên hằng Java đã được xem là một phần của hợp đồng JSON.
- Client và server cùng thống nhất cách viết.
- Tập enum ít thay đổi và không cần mã trao đổi riêng.
- Tên hằng đủ rõ để các hệ thống khác hiểu.

Giới hạn của cách này là tên hằng source code bị gắn trực tiếp với dữ liệu trao đổi. Ví dụ, đổi PAID thành PAYMENT_COMPLETED sẽ làm JSON mặc định đổi từ "PAID" thành "PAYMENT_COMPLETED". Client cũ có thể không còn đọc được dữ liệu mới.

Nếu API công khai hoặc nhiều hệ thống cùng tiêu thụ JSON, nên cân nhắc một giá trị nghiệp vụ ổn định thay vì phụ thuộc hoàn toàn vào tên hằng.

## 3. Không nên nhầm tên enum với ordinal

Mỗi enum constant có ordinal là vị trí khai báo, bắt đầu từ 0:

~~~java
public enum OrderStatus {
    PENDING,    // ordinal 0
    PAID,       // ordinal 1
    CANCELLED   // ordinal 2
}
~~~

Jackson mặc định thường ghi enum theo tên. Tuy nhiên, có thể cấu hình Jackson dùng index bằng SerializationFeature.WRITE_ENUMS_USING_INDEX.

~~~java
ObjectMapper mapper = new ObjectMapper();
mapper.enable(SerializationFeature.WRITE_ENUMS_USING_INDEX);

String json = mapper.writeValueAsString(OrderStatus.PAID);
~~~

Giá trị có thể được ghi thành:

~~~json
1
~~~

Không nên dùng ordinal làm mã nghiệp vụ trong API hoặc dữ liệu lưu trữ lâu dài. Nếu chèn một hằng mới vào giữa enum, ordinal của các hằng phía sau thay đổi. Dữ liệu cũ khi đọc lại có thể bị hiểu thành trạng thái khác.

Ví dụ, thay đổi:

~~~java
public enum OrderStatus {
    PENDING,
    PAID,
    CANCELLED
}
~~~

thành:

~~~java
public enum OrderStatus {
    PENDING,
    CONFIRMED,
    PAID,
    CANCELLED
}
~~~

PAID chuyển từ ordinal 1 sang ordinal 2. Một JSON lưu số 1 trước đây có thể mang ý nghĩa khác sau khi cập nhật code.

Tên hằng hoặc business code ổn định thường an toàn hơn ordinal. Nếu đã có API dùng index, cần xem đó là hợp đồng có phiên bản và quản lý thay đổi cẩn thận.

## 4. Ánh xạ enum theo giá trị nghiệp vụ

Một enum có thể chứa mã trao đổi riêng bên cạnh tên hằng Java:

~~~java
public enum PaymentStatus {

    PENDING("WAITING_PAYMENT"),
    PAID("SETTLED"),
    CANCELLED("VOID");

    private final String code;

    PaymentStatus(String code) {
        this.code = code;
    }

    public String getCode() {
        return code;
    }
}
~~~

Ở đây:

| Tên hằng Java | Giá trị nghiệp vụ |
|---|---|
| PENDING | WAITING_PAYMENT |
| PAID | SETTLED |
| CANCELLED | VOID |

Tên hằng mô tả cách code tổ chức trạng thái. Business code là giá trị được thống nhất với hệ thống bên ngoài.

Có thể ánh xạ code bằng @JsonValue.

### 4.1. Dùng @JsonValue để ghi mã nghiệp vụ

~~~java
public enum PaymentStatus {

    PENDING("WAITING_PAYMENT"),
    PAID("SETTLED"),
    CANCELLED("VOID");

    private final String code;

    PaymentStatus(String code) {
        this.code = code;
    }

    @JsonValue
    public String getCode() {
        return code;
    }
}
~~~

Khi serialize:

~~~java
String json = mapper.writeValueAsString(PaymentStatus.PAID);
~~~

Kết quả:

~~~json
"SETTLED"
~~~

Thay vì ghi tên hằng PAID, Jackson ghi giá trị trả về từ method có @JsonValue.

Đối với enum, Jackson 2.x còn có thể dùng giá trị @JsonValue để tìm lại enum khi deserialize, miễn các giá trị đó xác định duy nhất một hằng.

~~~java
PaymentStatus status = mapper.readValue(
        "\"SETTLED\"",
        PaymentStatus.class
);
~~~

Kết quả là PaymentStatus.PAID.

Lựa chọn này gọn khi một enum có một mã JSON duy nhất và mã đó được dùng cả hai chiều. Không nên để nhiều enum constant trả về cùng một @JsonValue, vì việc tìm ngược từ JSON về enum sẽ trở nên mơ hồ.

### 4.2. Dùng @JsonCreator để kiểm soát chiều đọc

Khi cần hỗ trợ alias, chuẩn hóa chữ hoa/thường hoặc trả lỗi có chủ đích cho mã không biết, có thể dùng factory method được đánh dấu @JsonCreator.

~~~java
public enum PaymentStatus {

    PENDING("WAITING_PAYMENT"),
    PAID("SETTLED"),
    CANCELLED("VOID");

    private final String code;

    PaymentStatus(String code) {
        this.code = code;
    }

    @JsonValue
    public String getCode() {
        return code;
    }

    @JsonCreator(mode = JsonCreator.Mode.DELEGATING)
    public static PaymentStatus fromCode(String value) {
        if (value == null) {
            return null;
        }

        return switch (value) {
            case "WAITING_PAYMENT", "PENDING" -> PENDING;
            case "SETTLED", "PAID" -> PAID;
            case "VOID", "CANCELLED" -> CANCELLED;
            default -> throw new IllegalArgumentException(
                    "Unknown payment status: " + value
            );
        };
    }
}
~~~

Factory method nhận một giá trị JSON scalar, tra cứu và trả về hằng enum tương ứng. Ví dụ trên chấp nhận cả business code hiện hành và tên cũ như alias.

Việc dùng @JsonCreator giúp chiều đọc có thể linh hoạt hơn chiều ghi. Serialization vẫn dùng @JsonValue để chỉ phát ra business code chuẩn. Nhờ đó, API có thể tiếp tục đọc alias cũ trong giai đoạn chuyển đổi nhưng luôn ghi một giá trị thống nhất.

Khi factory method ném IllegalArgumentException, Jackson thường bọc lỗi trong exception ánh xạ JSON. Ứng dụng có thể chuyển lỗi đó thành response đầu vào không hợp lệ.

### 4.3. Dùng @JsonProperty trên enum constant

Một cách khác là gắn trực tiếp JSON name lên từng enum constant:

~~~java
public enum PaymentStatus {

    @JsonProperty("waiting_payment")
    PENDING,

    @JsonProperty("settled")
    PAID,

    @JsonProperty("void")
    CANCELLED
}
~~~

Với Jackson 2.6 trở lên, @JsonProperty trên enum constant có thể chỉ định giá trị dùng trong JSON. Cách này phù hợp khi mỗi constant có một tên JSON cố định và không cần logic tra cứu phức tạp.

So sánh các cách:

| Cách | Điểm mạnh | Khi nên dùng |
|---|---|---|
| Mặc định theo enum name | Đơn giản, không cần annotation | Tên hằng chính là hợp đồng JSON |
| @JsonProperty trên constant | Khai báo mã cạnh hằng enum | Mỗi hằng có một JSON name cố định |
| @JsonValue | Ghi giá trị trả về từ method; enum có thể đọc ngược theo giá trị đó | Có field code hoặc cách tính mã |
| @JsonCreator | Chủ động kiểm soát tra cứu, alias và lỗi | Quy tắc đọc phức tạp hơn quy tắc ghi |

Không nên khai báo nhiều cơ chế ánh xạ chồng chéo cho cùng enum nếu không hiểu rõ thứ tự ưu tiên và cách Jackson kết hợp metadata. Chọn một chiến lược chính để code dễ đọc và dễ kiểm thử.

## 5. Giá trị hiển thị và mã nghiệp vụ là hai khái niệm khác nhau

Không nên dùng một chuỗi hiển thị cho cả API và giao diện người dùng nếu chuỗi đó có thể thay đổi theo ngôn ngữ hoặc cách diễn đạt.

Ví dụ:

~~~java
public enum PaymentStatus {

    PENDING("WAITING_PAYMENT", "Đang chờ thanh toán"),
    PAID("SETTLED", "Đã thanh toán"),
    CANCELLED("VOID", "Đã hủy");

    private final String code;
    private final String label;

    PaymentStatus(String code, String label) {
        this.code = code;
        this.label = label;
    }

    public String getCode() {
        return code;
    }

    public String getLabel() {
        return label;
    }
}
~~~

Ba thành phần có vai trò khác nhau:

- Tên hằng PENDING là định danh trong source code.
- Mã WAITING_PAYMENT là giá trị trao đổi ổn định với hệ thống khác.
- Nhãn Đang chờ thanh toán là nội dung hiển thị cho người dùng.

Nhãn có thể cần dịch sang tiếng Anh hoặc thay đổi câu chữ mà không làm thay đổi API. Mã nghiệp vụ nên ổn định qua các lần đổi tên class hoặc refactor.

Nếu dùng @JsonValue trên getLabel(), JSON có thể thay đổi theo ngôn ngữ hoặc câu chữ giao diện. Vì vậy, hãy chọn getCode() làm giá trị JSON nếu hợp đồng yêu cầu mã ổn định.

## 6. Xử lý chữ hoa/thường và alias

### 6.1. Chấp nhận enum name không phân biệt hoa thường

Với ánh xạ mặc định theo tên, Jackson 2.x cung cấp MapperFeature.ACCEPT_CASE_INSENSITIVE_ENUMS ở các phiên bản hỗ trợ:

~~~java
ObjectMapper mapper = JsonMapper.builder()
        .enable(MapperFeature.ACCEPT_CASE_INSENSITIVE_ENUMS)
        .build();
~~~

Khi đó, các giá trị như "PAID" và "paid" có thể cùng ánh xạ vào OrderStatus.PAID.

Đây là cấu hình cho phép đọc linh hoạt hơn. Nó không thay đổi tên enum mà Jackson ghi ra khi serialization theo name. Hãy xác nhận hành vi trên đúng phiên bản Jackson đang dùng.

### 6.2. Chấp nhận alias bằng @JsonCreator

Nếu API cần đọc cả mã mới và giá trị cũ, factory method có thể ánh xạ nhiều đầu vào về cùng một enum constant:

~~~java
@JsonCreator(mode = JsonCreator.Mode.DELEGATING)
public static PaymentStatus fromCode(String value) {
    if (value == null) {
        return null;
    }

    return switch (value.toUpperCase(Locale.ROOT)) {
        case "WAITING_PAYMENT", "PENDING" -> PENDING;
        case "SETTLED", "PAID" -> PAID;
        case "VOID", "CANCELLED" -> CANCELLED;
        default -> throw new IllegalArgumentException(
                "Unsupported payment status: " + value
        );
    };
}
~~~

Dùng Locale.ROOT khi chuẩn hóa chuỗi kỹ thuật để tránh phụ thuộc locale mặc định của máy chạy. Không nên dùng cách chuẩn hóa này nếu mã nghiệp vụ có phân biệt chữ hoa/thường theo hợp đồng.

Alias giúp duy trì tương thích khi đổi mã, nhưng cần có kế hoạch loại bỏ giá trị cũ nếu nó chỉ được hỗ trợ tạm thời. Serialization nên phát ra một mã canonical duy nhất.

## 7. Xử lý giá trị enum không biết

Khi client gửi một giá trị không có trong enum, Jackson cần một chính sách rõ ràng.

### 7.1. Mặc định: báo lỗi

Với enum theo tên:

~~~java
public enum OrderStatus {
    PENDING,
    PAID,
    CANCELLED
}
~~~

JSON:

~~~json
{
  "status": "REFUNDED"
}
~~~

Nếu REFUNDED không phải hằng enum và không có cấu hình fallback, Jackson thường ném lỗi ánh xạ enum. Đây là lựa chọn an toàn khi giá trị lạ cần được phát hiện.

### 7.2. Ánh xạ giá trị lạ thành null

Jackson có DeserializationFeature.READ_UNKNOWN_ENUM_VALUES_AS_NULL ở các phiên bản hỗ trợ:

~~~java
ObjectMapper mapper = JsonMapper.builder()
        .enable(DeserializationFeature.READ_UNKNOWN_ENUM_VALUES_AS_NULL)
        .build();
~~~

Khi gặp enum value không biết, Jackson có thể trả về null.

Cách này giúp đọc dữ liệu có giá trị mới mà client hiện tại chưa hiểu, nhưng có thể che giấu lỗi chính tả hoặc dữ liệu không hợp lệ. Với property bắt buộc, null còn có thể khiến lỗi chỉ xuất hiện ở bước validation sau đó.

### 7.3. Dùng hằng mặc định với @JsonEnumDefaultValue

Có thể định nghĩa một hằng đại diện cho giá trị không biết:

~~~java
public enum OrderStatus {

    PENDING,
    PAID,
    CANCELLED,

    @JsonEnumDefaultValue
    UNKNOWN
}
~~~

Sau đó bật feature:

~~~java
ObjectMapper mapper = JsonMapper.builder()
        .enable(
                DeserializationFeature.READ_UNKNOWN_ENUM_VALUES_USING_DEFAULT_VALUE
        )
        .build();
~~~

Khi gặp giá trị enum lạ, Jackson có thể ánh xạ thành UNKNOWN.

Chỉ nên dùng fallback khi nghiệp vụ có cách xử lý UNKNOWN rõ ràng. Không nên coi UNKNOWN là PAID hoặc một trạng thái có quyền thực hiện hành động quan trọng.

Nếu bật đồng thời nhiều feature xử lý unknown enum, hãy đọc quy tắc ưu tiên của phiên bản Jackson. Chọn một chính sách chủ đích để tránh kết quả khó đoán.

## 8. Tránh dùng toString() làm business code

Jackson có các feature như WRITE_ENUMS_USING_TO_STRING và READ_ENUMS_USING_TO_STRING để dùng toString() trong quá trình ghi/đọc enum. Tuy nhiên, toString() thường được override cho mục đích debug hoặc hiển thị.

Ví dụ:

~~~java
public enum OrderStatus {
    PENDING,
    PAID;

    @Override
    public String toString() {
        return name().toLowerCase(Locale.ROOT);
    }
}
~~~

Nếu bật WRITE_ENUMS_USING_TO_STRING, JSON có thể trở thành "paid" thay vì "PAID". Sau này thay đổi toString() để hiển thị nhãn thân thiện có thể vô tình thay đổi hợp đồng JSON.

Nếu cần mã nghiệp vụ, nên dùng field code với @JsonValue hoặc @JsonProperty. Nếu cần chuỗi hiển thị, dùng method riêng như getLabel().

## 9. Ví dụ hoàn chỉnh với business code

~~~java
import com.fasterxml.jackson.annotation.JsonCreator;
import com.fasterxml.jackson.annotation.JsonValue;
import com.fasterxml.jackson.databind.ObjectMapper;

public enum PaymentStatus {

    PENDING("WAITING_PAYMENT"),
    PAID("SETTLED"),
    CANCELLED("VOID");

    private final String code;

    PaymentStatus(String code) {
        this.code = code;
    }

    @JsonValue
    public String getCode() {
        return code;
    }

    @JsonCreator(mode = JsonCreator.Mode.DELEGATING)
    public static PaymentStatus fromCode(String value) {
        if (value == null) {
            return null;
        }

        return switch (value) {
            case "WAITING_PAYMENT" -> PENDING;
            case "SETTLED" -> PAID;
            case "VOID" -> CANCELLED;
            default -> throw new IllegalArgumentException(
                    "Unknown payment status: " + value
            );
        };
    }
}
~~~

Sử dụng:

~~~java
public class Payment {
    private String paymentId;
    private PaymentStatus status;

    public Payment() {
    }

    public String getPaymentId() {
        return paymentId;
    }

    public void setPaymentId(String paymentId) {
        this.paymentId = paymentId;
    }

    public PaymentStatus getStatus() {
        return status;
    }

    public void setStatus(PaymentStatus status) {
        this.status = status;
    }
}
~~~

~~~java
ObjectMapper mapper = new ObjectMapper();

Payment payment = new Payment();
payment.setPaymentId("PAY-100");
payment.setStatus(PaymentStatus.PAID);

String json = mapper.writeValueAsString(payment);
System.out.println(json);

Payment restored = mapper.readValue(json, Payment.class);
System.out.println(restored.getStatus());
System.out.println(restored.getStatus().getCode());
~~~

JSON có dạng:

~~~json
{
  "paymentId": "PAY-100",
  "status": "SETTLED"
}
~~~

Khi đọc lại, Jackson gọi creator để ánh xạ SETTLED thành PaymentStatus.PAID. Khi ghi, Jackson dùng @JsonValue để phát ra SETTLED.

## 10. Kiểm thử ánh xạ enum

Enum là một phần của hợp đồng JSON, vì vậy nên kiểm thử cả hai chiều.

### 10.1. Kiểm thử serialization

~~~java
@Test
void writesBusinessCodeInsteadOfEnumName() throws Exception {
    String json = mapper.writeValueAsString(PaymentStatus.PAID);

    assertEquals("\"SETTLED\"", json);
}
~~~

Test xác nhận API phát business code thay vì tên hằng Java.

### 10.2. Kiểm thử deserialization

~~~java
@Test
void readsBusinessCodeIntoEnum() throws Exception {
    PaymentStatus status = mapper.readValue(
            "\"SETTLED\"",
            PaymentStatus.class
    );

    assertEquals(PaymentStatus.PAID, status);
}
~~~

### 10.3. Kiểm thử alias nếu có

~~~java
@Test
void readsLegacyAlias() throws Exception {
    PaymentStatus status = mapper.readValue(
            "\"PAID\"",
            PaymentStatus.class
    );

    assertEquals(PaymentStatus.PAID, status);
}
~~~

Test alias chỉ phù hợp khi factory method chủ động hỗ trợ giá trị cũ.

### 10.4. Kiểm thử giá trị không biết

~~~java
@Test
void rejectsUnknownBusinessCode() {
    assertThrows(
            JsonProcessingException.class,
            () -> mapper.readValue(
                    "\"CHARGEBACK_PENDING\"",
                    PaymentStatus.class
            )
    );
}
~~~

Nếu ứng dụng chọn fallback UNKNOWN hoặc null, hãy viết test theo chính sách đó. Không nên để hành vi của enum phụ thuộc một cách ngẫu nhiên vào default chưa được kiểm thử.

## 11. Lựa chọn chiến lược theo loại hợp đồng

| Tình huống | Chiến lược nên cân nhắc |
|---|---|
| Enum nội bộ, tên hằng ổn định và chính là JSON contract | Mặc định theo enum name |
| API công khai, tên code cần ổn định qua refactor | Business code với @JsonValue |
| Mỗi enum constant có JSON name tĩnh, không cần logic | @JsonProperty trên constant |
| Cần alias hoặc chuẩn hóa đầu vào | @JsonCreator factory method |
| Cần chấp nhận khác biệt chữ hoa/thường | ACCEPT_CASE_INSENSITIVE_ENUMS hoặc chuẩn hóa trong creator |
| Client cần chịu được enum value mới | UNKNOWN fallback hoặc null theo hợp đồng |
| Cần biểu diễn nhãn giao diện đa ngôn ngữ | Method label riêng, không dùng làm business code |
| Cần lưu dữ liệu bền vững | Mã nghiệp vụ ổn định, tránh ordinal |

Không có một cách ánh xạ phù hợp cho mọi enum. Hãy chọn theo phạm vi sử dụng và mức độ ổn định cần có của hợp đồng.

## 12. Những nguyên tắc nên giữ

1. Dùng enum name khi tên hằng Java thực sự là tên JSON mà hệ thống muốn công bố.
2. Dùng business code ổn định khi dữ liệu được trao đổi giữa nhiều hệ thống hoặc lưu trữ lâu dài.
3. Không dùng ordinal làm mã trạng thái nếu thứ tự khai báo có thể thay đổi.
4. Không dùng toString() làm hợp đồng JSON nếu method đó phục vụ hiển thị/debug.
5. Đảm bảo mỗi business code ánh xạ duy nhất về một enum constant.
6. Nếu hỗ trợ alias, ghi ra một giá trị canonical duy nhất.
7. Quy định rõ cách xử lý giá trị enum không biết: báo lỗi, null hay UNKNOWN.
8. Kiểm thử serialization và deserialization cùng các trường hợp alias/unknown.
9. Khi nâng Jackson, kiểm tra lại annotation và feature đang dùng theo đúng phiên bản.

Ánh xạ enum theo tên phù hợp với mô hình đơn giản, còn ánh xạ theo giá trị nghiệp vụ giúp tách định danh nội bộ khỏi hợp đồng dữ liệu. Jackson hỗ trợ cả hai chiều; ứng dụng cần chọn một quy tắc rõ ràng, ổn định và kiểm thử được để dữ liệu JSON không bị thay đổi ngoài ý muốn khi source code phát triển.
