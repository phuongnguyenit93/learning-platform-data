# Enum, UUID, BigDecimal và lựa chọn biểu diễn phù hợp

## Mục tiêu

Sau bài học này, bạn có thể:

- Giải thích vì sao Enum, UUID và BigDecimal cần được cân nhắc khi lưu thành property trong Neo4j.
- Chọn cách biểu diễn ổn định cho enum thay vì phụ thuộc vào thứ tự hằng số.
- Lưu UUID dưới dạng chuỗi và chuyển đổi qua lại với kiểu UUID trong Java.
- Lưu BigDecimal chính xác bằng chuỗi thập phân hoặc số nguyên đã nhân theo scale.
- Đăng ký custom converter trong Spring Data Neo4j và chọn biểu diễn phù hợp với truy vấn, index và yêu cầu nghiệp vụ.

## 1. Neo4j property và kiểu dữ liệu Java

Java có nhiều kiểu dữ liệu phong phú, nhưng Neo4j property model chỉ hỗ trợ một tập kiểu giá trị nhất định. Những kiểu thường gặp gồm chuỗi, boolean, các kiểu số nguyên và số thực, một số kiểu ngày giờ, duration, point và các mảng tương ứng. Một property không thể lưu tùy ý mọi object Java.

Vì vậy, khi domain model sử dụng Enum, UUID hoặc BigDecimal, cần xác định kiểu giá trị thực sự được ghi vào node. Spring Data Neo4j (SDN) sử dụng hệ thống conversion để chuyển đổi giữa kiểu Java và kiểu property mà Neo4j Driver hỗ trợ.

Ví dụ, một hóa đơn có thể chứa:

~~~java
public class Invoice {
    private OrderStatus status;
    private UUID externalId;
    private BigDecimal total;
}
~~~

Các kiểu trên có ý nghĩa tốt trong Java:

- OrderStatus giới hạn trạng thái vào một tập giá trị hợp lệ.
- UUID cung cấp định danh có xác suất trùng lặp cực thấp.
- BigDecimal biểu diễn số thập phân chính xác, phù hợp với tiền và phép tính decimal.

Nhưng chúng không phải ba kiểu property native giống như String, Long hay Boolean. Cần có cách chuyển đổi rõ ràng để dữ liệu được lưu ổn định và đọc lại đúng nghĩa.

## 2. Enum: lưu mã nghiệp vụ ổn định

Enum thường biểu diễn một tập lựa chọn hữu hạn, chẳng hạn trạng thái đơn hàng, loại tài khoản hoặc mức độ ưu tiên.

~~~java
public enum OrderStatus {
    PENDING,
    PAID,
    CANCELLED
}
~~~

Một cách lưu phổ biến là chuyển enum thành chuỗi. Ví dụ:

~~~text
(:Order {
    orderId: "order-100",
    status: "PAID"
})
~~~

Chuỗi dễ đọc khi kiểm tra dữ liệu trực tiếp bằng Cypher. Tuy nhiên, nếu lưu bằng tên hằng số Java, việc đổi tên hằng số có thể ảnh hưởng dữ liệu đã lưu. Nếu lưu bằng ordinal (vị trí 0, 1, 2), việc thêm hoặc sắp xếp lại hằng số có thể làm các bản ghi cũ mang ý nghĩa khác.

### Dùng mã ổn định thay cho ordinal

Có thể gắn mã nghiệp vụ riêng cho mỗi hằng số:

~~~java
public enum OrderStatus {
    PENDING("pending"),
    PAID("paid"),
    CANCELLED("cancelled");

    private final String code;

    OrderStatus(String code) {
        this.code = code;
    }

    public String getCode() {
        return code;
    }

    public static OrderStatus fromCode(String code) {
        for (OrderStatus status : values()) {
            if (status.code.equals(code)) {
                return status;
            }
        }
        throw new IllegalArgumentException("Unknown order status: " + code);
    }
}
~~~

Mã pending, paid và cancelled được xem như một phần của schema dữ liệu. Có thể đổi tên hằng số Java mà vẫn giữ mã đã lưu. Nếu cần đổi mã, hãy xem đó là một thay đổi dữ liệu và có kế hoạch chuyển đổi các node hiện có.

### Đăng ký converter cho Enum

SDN hỗ trợ custom conversion thông qua Neo4jConversions. Có thể viết converter chiều ghi và chiều đọc:

~~~java
@WritingConverter
public class OrderStatusWriteConverter
        implements Converter<OrderStatus, String> {

    @Override
    public String convert(OrderStatus source) {
        return source.getCode();
    }
}
~~~

~~~java
@ReadingConverter
public class OrderStatusReadConverter
        implements Converter<String, OrderStatus> {

    @Override
    public OrderStatus convert(String source) {
        return OrderStatus.fromCode(source);
    }
}
~~~

Converter ghi biến enum thành chuỗi mã. Converter đọc nhận chuỗi từ Neo4j và khôi phục enum tương ứng. Việc tách hai chiều giúp ý nghĩa chuyển đổi rõ ràng, đặc biệt khi có nhiều kiểu Java cùng được chuyển thành chuỗi.

Nếu dữ liệu có thể chứa mã trạng thái mới hơn phiên bản ứng dụng hiện tại, fromCode có thể cần chiến lược tương thích như giá trị UNKNOWN, hoặc ứng dụng phải từ chối đọc để phát hiện dữ liệu chưa được hỗ trợ. Chọn hành vi theo yêu cầu nghiệp vụ; không âm thầm đổi mã không nhận diện thành một trạng thái hợp lệ khác.

## 3. UUID: lưu chuỗi định danh chuẩn

UUID là kiểu định danh 128 bit được Java cung cấp qua java.util.UUID. Neo4j không có property scalar riêng mang kiểu UUID. Cách biểu diễn dễ tương tác nhất là lưu UUID thành chuỗi chuẩn.

Ví dụ:

~~~text
(:Customer {
    customerId: "cust-100",
    externalId: "550e8400-e29b-41d4-a716-446655440000"
})
~~~

Chuỗi do UUID.toString() tạo ra có dạng chuẩn gồm các nhóm ký tự hex phân tách bằng dấu gạch ngang. Khi đọc, UUID.fromString() chuyển chuỗi trở lại kiểu UUID.

Converter chiều ghi:

~~~java
@WritingConverter
public class UuidWriteConverter
        implements Converter<UUID, String> {

    @Override
    public String convert(UUID source) {
        return source.toString();
    }
}
~~~

Converter chiều đọc:

~~~java
@ReadingConverter
public class UuidReadConverter
        implements Converter<String, UUID> {

    @Override
    public UUID convert(String source) {
        return UUID.fromString(source);
    }
}
~~~

Trong domain entity, thuộc tính vẫn có thể dùng UUID:

~~~java
@Node("Customer")
public class Customer {

    @Id
    private String customerId;

    private UUID externalId;

    private String displayName;
}
~~~

Ở đây customerId là định danh node do ứng dụng quản lý, còn externalId là một UUID được lưu dưới dạng chuỗi thông qua converter. Phân biệt hai vai trò này giúp tránh nhầm UUID của hệ thống bên ngoài với định danh kỹ thuật của node.

### Khi nào nên dùng chuỗi UUID?

Chuỗi UUID phù hợp khi:

- Cần truyền ID qua REST API, message hoặc log.
- Cần tìm kiếm bằng phép so sánh bằng.
- Muốn đọc và kiểm tra dữ liệu trực tiếp bằng Cypher.
- Cần chia sẻ định danh giữa nhiều dịch vụ hoặc hệ thống.

Có thể tạo index hoặc uniqueness constraint cho property UUID nếu nghiệp vụ yêu cầu tra cứu nhanh và không cho phép trùng lặp. Hãy bảo đảm dữ liệu được chuẩn hóa cùng một định dạng; không trộn chuỗi UUID chuẩn với chuỗi viết tùy ý.

Không nên dùng chuỗi UUID như một giá trị số để sắp xếp theo thời gian. UUID thông thường không đảm bảo thứ tự thời gian có ý nghĩa nghiệp vụ; nếu cần thời điểm tạo, hãy lưu thêm property thời gian riêng.

## 4. BigDecimal: giữ độ chính xác thập phân

BigDecimal thường được dùng cho tiền, thuế, tỷ lệ và các đại lượng cần kiểm soát độ chính xác thập phân.

~~~java
BigDecimal total = new BigDecimal("1250.75");
~~~

Nên tạo giá trị từ chuỗi thập phân hoặc từ một nguồn decimal chính xác. Tránh khởi tạo từ double khi cần giữ chính xác, vì sai số nhị phân của double có thể đã xuất hiện trước khi giá trị được đưa vào BigDecimal.

Neo4j có kiểu số nguyên và số thực, nhưng không có property native mang ngữ nghĩa decimal với precision và scale tùy ý như BigDecimal. Nếu chuyển sang double, có thể mất độ chính xác ở một số phép tính. Vì vậy cần chọn cách biểu diễn theo yêu cầu của dữ liệu.

### Cách 1: lưu BigDecimal thành chuỗi

Converter ghi:

~~~java
@WritingConverter
public class BigDecimalWriteConverter
        implements Converter<BigDecimal, String> {

    @Override
    public String convert(BigDecimal source) {
        return source.toPlainString();
    }
}
~~~

Converter đọc:

~~~java
@ReadingConverter
public class BigDecimalReadConverter
        implements Converter<String, BigDecimal> {

    @Override
    public BigDecimal convert(String source) {
        return new BigDecimal(source);
    }
}
~~~

Ví dụ node:

~~~text
(:Invoice {
    invoiceId: "inv-001",
    total: "1250.7500"
})
~~~

toPlainString() giữ biểu diễn thập phân mà không dùng ký pháp số mũ. Khi đọc lại bằng constructor BigDecimal(String), giá trị decimal được khôi phục mà không chuyển qua double.

Ưu điểm:

- Giữ chính xác giá trị thập phân và scale thể hiện trong chuỗi.
- Phù hợp với số decimal có precision lớn hoặc scale thay đổi.
- Dễ kiểm tra trực tiếp trong Neo4j.

Hạn chế:

- Property là chuỗi, nên phép so sánh, sắp xếp và lọc khoảng theo giá trị số không có ngữ nghĩa số.
- Không thể cộng hoặc tính tổng trực tiếp như một property số mà không chuyển đổi.
- Cần thống nhất định dạng chuỗi và cách chuẩn hóa dữ liệu.

Nếu truy vấn thường cần lọc theo khoảng giá trị hoặc tính tổng, chuỗi có thể không phải biểu diễn thuận tiện nhất.

### Cách 2: lưu số nguyên đã nhân theo scale

Nếu nghiệp vụ có scale cố định, chẳng hạn tiền luôn dùng hai chữ số thập phân, có thể chuyển giá trị thành số nguyên theo đơn vị nhỏ nhất.

Ví dụ:

~~~java
BigDecimal amount = new BigDecimal("1250.75");

long amountMinor = amount
    .movePointRight(2)
    .longValueExact();
~~~

Kết quả là 125075 đơn vị cent. Có thể lưu node như sau:

~~~text
(:Invoice {
    invoiceId: "inv-001",
    amountMinor: 125075,
    currency: "USD",
    amountScale: 2
})
~~~

Khi đọc lại:

~~~java
BigDecimal amount = BigDecimal.valueOf(amountMinor, 2);
~~~

longValueExact() sẽ báo lỗi nếu giá trị sau khi dịch dấu thập phân không thể biểu diễn chính xác thành số nguyên 64 bit. Điều này giúp phát hiện dữ liệu vượt giới hạn hoặc có nhiều chữ số thập phân hơn scale đã quy định thay vì âm thầm làm tròn.

Cách này có lợi khi cần:

- So sánh số tiền theo thứ tự số học.
- Lọc theo khoảng.
- Sắp xếp hoặc tổng hợp bằng các phép toán số.
- Tạo index trên property số nguyên.

Cần lưu scale và đơn vị tiền tệ theo quy tắc nghiệp vụ. Không mặc định mọi loại tiền đều có hai chữ số thập phân. Với dữ liệu có scale thay đổi, hãy lưu scale cùng giá trị hoặc dùng một mô hình số tiền có quy ước rõ ràng. Cũng cần kiểm tra giới hạn của long; số rất lớn có thể vượt phạm vi 64 bit.

### Cách 3: lưu double khi chấp nhận xấp xỉ

Nếu giá trị chỉ phục vụ tính toán gần đúng, chẳng hạn một số điểm xếp hạng hoặc phép đo khoa học không yêu cầu decimal chính xác, có thể dùng double.

~~~java
double score = bigDecimal.doubleValue();
~~~

Đây không phải lựa chọn phù hợp cho số dư, giá tiền, thuế hoặc các phép tính phải đối soát chính xác. Khi chuyển BigDecimal thành double, một số giá trị thập phân không thể được biểu diễn chính xác trong dạng nhị phân.

## 5. Đăng ký custom conversions trong Spring Data Neo4j

Các converter có thể được đăng ký tập trung thông qua bean Neo4jConversions. Ví dụ:

~~~java
@Configuration
public class Neo4jConversionConfiguration {

    @Bean
    Neo4jConversions neo4jConversions() {
        return new Neo4jConversions(List.of(
            new OrderStatusWriteConverter(),
            new OrderStatusReadConverter(),
            new UuidWriteConverter(),
            new UuidReadConverter(),
            new BigDecimalWriteConverter(),
            new BigDecimalReadConverter()
        ));
    }
}
~~~

Các converter phải được đặt trong package được ứng dụng biên dịch và import đúng kiểu:

- Converter từ org.springframework.core.convert.converter.
- @ReadingConverter và @WritingConverter từ org.springframework.data.convert.
- Neo4jConversions từ org.springframework.data.neo4j.core.convert.
- List từ java.util.

Cấu hình này minh họa cách đăng ký các converter hai chiều. Kiểm tra API và cách cấu hình custom conversions theo phiên bản SDN đang dùng; nếu ứng dụng đã có bean Neo4jConversions, hãy bổ sung converter vào cấu hình hiện hữu thay vì tạo các bean xung đột.

### Áp dụng converter vào entity

Khi converter đã được đăng ký, entity có thể dùng kiểu Java giàu ý nghĩa:

~~~java
@Node("Invoice")
public class Invoice {

    @Id
    private String invoiceId;

    private OrderStatus status;

    private UUID externalId;

    private BigDecimal total;
}
~~~

Khi ghi, SDN chuyển từng property theo converter đã đăng ký. Khi đọc, converter tương ứng chuyển giá trị property về kiểu Java. Ví dụ một node có thể chứa:

~~~text
(:Invoice {
    invoiceId: "inv-001",
    status: "paid",
    externalId: "550e8400-e29b-41d4-a716-446655440000",
    total: "1250.75"
})
~~~

Điều cần nhớ là converter quyết định kiểu lưu thực tế. Nếu total được chuyển thành chuỗi, Cypher sẽ nhìn thấy một string; nếu được lưu thành số nguyên minor units, Cypher sẽ nhìn thấy một integer.

## 6. Chọn biểu diễn theo yêu cầu truy vấn

Không có một cách lưu duy nhất tốt cho mọi loại dữ liệu. Hãy xét cách ứng dụng đọc và cập nhật property.

| Kiểu Java | Biểu diễn gợi ý | Khi phù hợp | Điểm cần lưu ý |
|---|---|---|---|
| Enum | String code ổn định | Trạng thái, loại, phân nhóm hữu hạn | Không dùng ordinal; quản lý thay đổi code |
| UUID | String chuẩn | ID bên ngoài, tham chiếu liên dịch vụ | Không có native UUID property; thống nhất format |
| BigDecimal | String | Precision/scale tùy ý, ưu tiên chính xác khi lưu và đọc | Truy vấn số học không thuận tiện |
| BigDecimal | Long đã scale | Tiền có scale xác định, cần lọc/sắp xếp/tổng hợp | Quản lý scale, currency và giới hạn số nguyên |
| BigDecimal | Double | Đại lượng chấp nhận xấp xỉ | Có sai số biểu diễn nhị phân |

Một số câu hỏi nên đặt ra trước khi chọn:

1. Dữ liệu có cần giữ nguyên từng chữ số thập phân không?
2. Truy vấn có cần so sánh lớn hơn, nhỏ hơn hoặc tính tổng không?
3. Giá trị có scale cố định hay thay đổi theo từng bản ghi?
4. Mã enum có thể được đổi tên hoặc bổ sung theo thời gian không?
5. UUID có được chia sẻ với hệ thống khác không?
6. Property có cần index hoặc uniqueness constraint không?

Ví dụ, trạng thái đơn hàng thường được lọc theo giá trị bằng nhau, vì vậy string code phù hợp. UUID thường được tra cứu theo equality, nên chuỗi chuẩn dễ dùng. Tổng tiền hóa đơn thường cần tính tổng và lọc khoảng; nếu tất cả hóa đơn dùng cùng scale, số nguyên đã scale thường thuận tiện hơn chuỗi.

## 7. Truy vấn Cypher theo kiểu property đã lưu

Cách lưu ảnh hưởng trực tiếp đến câu truy vấn.

Với enum được lưu bằng chuỗi:

~~~cypher
MATCH (o:Order {status: "paid"})
RETURN o.orderId, o.status
~~~

Với UUID lưu thành chuỗi:

~~~cypher
MATCH (c:Customer {
    externalId: "550e8400-e29b-41d4-a716-446655440000"
})
RETURN c
~~~

Với BigDecimal lưu dưới dạng chuỗi, truy vấn equality có thể dùng được:

~~~cypher
MATCH (i:Invoice {total: "1250.75"})
RETURN i
~~~

Nhưng so sánh chuỗi không tương đương so sánh số. Ví dụ, thứ tự từ điển của "100" và "20" không phản ánh thứ tự số học. Nếu cần lọc tổng tiền lớn hơn một ngưỡng, biểu diễn bằng integer đã scale thuận tiện hơn:

~~~cypher
MATCH (i:Invoice)
WHERE i.amountMinor > 100000
RETURN i.invoiceId, i.amountMinor
ORDER BY i.amountMinor DESC
~~~

Đối với số nguyên minor units, ứng dụng cần biết scale để hiển thị lại số tiền. Nếu các node có scale khác nhau, không thể so sánh trực tiếp amountMinor giữa chúng mà chưa chuẩn hóa về cùng đơn vị.

## 8. Các lỗi thường gặp khi chuyển đổi

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Đọc enum thất bại | Chuỗi trong graph không còn tương ứng với hằng số hoặc code hiện tại | Dùng code ổn định, xử lý mã cũ và mã chưa biết |
| Enum thay đổi ý nghĩa sau khi thêm hằng số | Đã lưu ordinal | Chuyển sang string code và migration dữ liệu |
| UUID không chuyển đổi được | Property không phải chuỗi UUID hợp lệ hoặc converter chưa đăng ký | Kiểm tra dữ liệu và converter đọc |
| BigDecimal mất độ chính xác | Đã chuyển qua double | Dùng chuỗi hoặc integer đã scale |
| So sánh số tiền cho kết quả sai | BigDecimal đang lưu dưới dạng chuỗi nhưng truy vấn như số | Chuyển sang integer đã scale hoặc chuẩn hóa ở tầng ứng dụng |
| Converter không được gọi | Bean conversions chưa được cấu hình hoặc source/target type không khớp | Kiểm tra Neo4jConversions, annotation và kiểu converter |
| Dữ liệu cũ không đọc được sau khi đổi converter | Định dạng property đã thay đổi nhưng dữ liệu chưa migration | Triển khai converter tương thích tạm thời hoặc migration có kiểm soát |

Khi thay đổi cách biểu diễn property đã có trong database, cần lập kế hoạch migration. Ví dụ, nếu trước đây enum được lưu bằng "PAID" và nay đổi sang "paid", converter mới có thể không đọc được bản ghi cũ nếu không hỗ trợ cả hai định dạng trong giai đoạn chuyển tiếp.

## 9. Thực hành: lưu hóa đơn với enum, UUID và BigDecimal

Giả sử hệ thống quản lý hóa đơn có các yêu cầu:

- Trạng thái hóa đơn chỉ nhận PENDING, PAID, CANCELLED.
- Mỗi hóa đơn có một UUID dùng để trao đổi với hệ thống thanh toán.
- Tổng tiền cần giữ chính xác hai chữ số thập phân và được lọc theo khoảng.

Có thể thiết kế như sau:

~~~java
@Node("Invoice")
public class Invoice {

    @Id
    private String invoiceId;

    private OrderStatus status;

    private UUID paymentReference;

    private Long totalMinor;

    private String currency;

    public Invoice(
            String invoiceId,
            OrderStatus status,
            UUID paymentReference,
            BigDecimal total,
            String currency) {

        this.invoiceId = invoiceId;
        this.status = status;
        this.paymentReference = paymentReference;
        this.totalMinor = total.movePointRight(2).longValueExact();
        this.currency = currency;
    }

    public BigDecimal getTotal() {
        return BigDecimal.valueOf(totalMinor, 2);
    }
}
~~~

Trong ví dụ này:

- status được chuyển thành mã string ổn định.
- paymentReference được chuyển thành chuỗi UUID chuẩn.
- totalMinor lưu số nguyên đã nhân 100.
- currency xác định đơn vị tiền tệ.

Một node minh họa:

~~~text
(:Invoice {
    invoiceId: "inv-001",
    status: "paid",
    paymentReference: "550e8400-e29b-41d4-a716-446655440000",
    totalMinor: 125075,
    currency: "USD"
})
~~~

Truy vấn tìm hóa đơn đã thanh toán có tổng tiền trên 1.000 đơn vị tiền tệ:

~~~cypher
MATCH (i:Invoice)
WHERE i.status = "paid"
  AND i.currency = "USD"
  AND i.totalMinor > 100000
RETURN i.invoiceId, i.totalMinor, i.currency
ORDER BY i.totalMinor DESC
~~~

Trong ứng dụng thực tế, hãy bảo đảm mọi hóa đơn cùng được quy đổi theo scale phù hợp với currency trước khi so sánh. Ví dụ này dùng scale 2 để minh họa; không áp dụng máy móc cho mọi loại tiền hoặc mọi nghiệp vụ.

Tự kiểm tra:

1. Vì sao không nên lưu enum bằng ordinal?
2. Vì sao UUID thường được lưu dưới dạng chuỗi?
3. Nếu cần so sánh và tổng hợp số tiền, vì sao integer đã scale thường thuận tiện hơn chuỗi?
4. longValueExact() giúp phát hiện vấn đề gì?
5. Converter đọc và converter ghi có nhiệm vụ gì khác nhau?

## Kết luận

Enum, UUID và BigDecimal là các kiểu Java hữu ích, nhưng cần được chuyển thành kiểu property Neo4j có thể lưu. Enum nên dùng mã chuỗi ổn định thay vì ordinal; UUID có thể lưu thành chuỗi chuẩn; BigDecimal nên được biểu diễn bằng chuỗi khi cần giữ decimal tùy ý hoặc bằng integer đã scale khi cần truy vấn số học với scale được kiểm soát.

Spring Data Neo4j cho phép đăng ký converter hai chiều thông qua Neo4jConversions. Hãy chọn biểu diễn theo yêu cầu chính xác dữ liệu, truy vấn, index và khả năng thay đổi schema; khi thay đổi định dạng đã lưu, cần bảo đảm dữ liệu cũ vẫn đọc được hoặc được migration có kế hoạch.
