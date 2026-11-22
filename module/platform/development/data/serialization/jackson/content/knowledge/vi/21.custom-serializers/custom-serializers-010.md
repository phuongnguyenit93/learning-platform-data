# Giữ serializer dùng chung không chứa trạng thái thay đổi theo yêu cầu

Jackson thường tạo và tái sử dụng các serializer trong suốt vòng đời của ObjectMapper. Serializer có thể được cache để những lần ghi JSON sau không phải xây dựng lại metadata và logic tuần tự hóa. Vì vậy, một custom serializer cần được thiết kế như một thành phần có thể dùng lại an toàn: nó không được giữ trạng thái thay đổi theo từng request, từng người dùng hoặc từng lần ghi.

Một lỗi dễ gặp là đặt locale hiện tại, múi giờ, người dùng đang đăng nhập, cờ ẩn field hoặc một giá trị tạm vào field của serializer. Khi nhiều request chạy đồng thời, cùng một instance serializer có thể được gọi xen kẽ. Request này có thể ghi đè trạng thái của request khác, làm JSON sai, rò rỉ dữ liệu giữa các request hoặc tạo lỗi khó tái hiện.

Nguyên tắc cốt lõi là **serializer dùng chung chỉ giữ cấu hình bất biến; dữ liệu thay đổi theo lần ghi phải nằm trong biến cục bộ hoặc context của chính lần ghi đó**. Với cấu hình gắn cố định cho một property, có thể dùng ContextualSerializer để tạo instance mới mang cấu hình bất biến. Với dữ liệu động theo từng thao tác, có thể truyền qua ObjectWriter và đọc từ SerializerProvider.

## 1. Vì sao serializer có thể được dùng chung?

Custom serializer thường được đăng ký qua module:

~~~java
SimpleModule module = new SimpleModule();
module.addSerializer(Money.class, new MoneySerializer());

ObjectMapper mapper = new ObjectMapper();
mapper.registerModule(module);
~~~

Sau khi cấu hình xong, mapper có thể được tái sử dụng cho nhiều lần serialize. Jackson cũng có cơ chế cache serializer đã tìm thấy cho các kiểu dữ liệu. Do đó, không nên giả định mỗi lần gọi writeValueAsString() sẽ tạo một serializer mới.

ObjectMapper được thiết kế để tái sử dụng an toàn giữa nhiều luồng sau khi đã hoàn tất cấu hình. Điều kiện quan trọng là không tiếp tục thay đổi cấu hình mapper trong khi các thao tác đọc/ghi đang diễn ra. Serializer tùy biến nằm trong pipeline đó cũng phải tuân theo cách dùng đồng thời.

Ví dụ, cùng một mapper có thể phục vụ hai request:

~~~java
String first = mapper.writeValueAsString(orderA);
String second = mapper.writeValueAsString(orderB);
~~~

Nếu cả hai request chạy ở hai thread khác nhau, Jackson có thể gọi cùng một instance serializer cho hai object gần như đồng thời. Nếu serializer không có trạng thái thay đổi dùng chung, điều này bình thường và an toàn.

## 2. Phân biệt cấu hình bất biến và trạng thái theo request

Không phải mọi field trong serializer đều sai. Cần phân biệt loại dữ liệu mà field đó lưu:

| Loại dữ liệu | Ví dụ | Có nên giữ trong serializer dùng chung? |
|---|---|---|
| Cấu hình bất biến | Số chữ số thập phân cố định, tên format cố định | Có, nếu được thiết lập trước khi dùng và không thay đổi |
| Metadata của property | Annotation trên field, tên property, quy tắc riêng của property | Có thể, thông qua contextual serializer bất biến |
| Trạng thái của một lần serialize | Locale request, timezone request, user hiện tại | Không |
| Bộ đệm có thể sửa đổi | StringBuilder, DateFormat dùng chung, mảng ký tự ghi tạm | Không, trừ khi có cơ chế đồng bộ và vòng đời được kiểm soát rất rõ |
| Đối tượng phụ thuộc request | HttpServletRequest, SecurityContext, session | Không |
| Kết quả tính toán bất biến | Bảng tra cứu không sửa đổi, formatter bất biến | Có thể |

Một serializer có thể chứa field final tham chiếu đến một cấu hình bất biến. Điều cần tránh là thay đổi field đó trong serialize() để phản ánh request hiện tại.

Ví dụ cấu hình bất biến:

~~~java
public final class FixedScaleSerializer
        extends JsonSerializer<BigDecimal> {

    private final int scale;

    public FixedScaleSerializer(int scale) {
        this.scale = scale;
    }

    @Override
    public void serialize(
            BigDecimal value,
            JsonGenerator generator,
            SerializerProvider provider) throws IOException {
        generator.writeNumber(
            value.setScale(scale, RoundingMode.HALF_UP)
        );
    }
}
~~~

scale được truyền vào constructor và không thay đổi sau khi tạo serializer. Nhiều thread có thể đọc field này cùng lúc mà không cần khóa.

## 3. Mẫu nguy hiểm: lưu trạng thái thay đổi trong field

Giả sử ứng dụng muốn định dạng số theo locale của người dùng. Cách viết sau có vấn đề:

~~~java
public class UnsafeMoneySerializer extends JsonSerializer<Money> {

    private Locale currentLocale;
    private NumberFormat formatter;

    public void setLocale(Locale locale) {
        this.currentLocale = locale;
        this.formatter = NumberFormat.getNumberInstance(locale);
    }

    @Override
    public void serialize(
            Money value,
            JsonGenerator generator,
            SerializerProvider provider) throws IOException {

        generator.writeString(
            formatter.format(value.amount())
        );
    }
}
~~~

Giả sử request A gọi setLocale(Locale.US), request B gọi setLocale(Locale.GERMANY), rồi cả hai cùng serialize. Request A có thể nhận formatter của request B. Ngoài ra, NumberFormat không an toàn khi nhiều thread cùng sử dụng và sửa đổi.

Một biến thể khác là thay đổi trực tiếp field ngay trong serialize():

~~~java
// Không nên làm:
this.currentLocale = localeFromRequest;
this.formatter = createFormatter(currentLocale);
~~~

Đây là trạng thái dùng chung. Một thao tác ghi có thể làm thay đổi kết quả của thao tác khác.

Kết quả có thể không chỉ sai định dạng. Nếu trạng thái được dùng để quyết định field nào được xuất, dữ liệu riêng tư của một request còn có thể xuất hiện trong JSON của request khác.

## 4. Mẫu đúng: dùng biến cục bộ trong serialize()

Nếu một giá trị chỉ cần tồn tại trong lúc serialize một object, hãy tạo nó thành biến cục bộ:

~~~java
public class SafeMoneySerializer extends JsonSerializer<Money> {

    @Override
    public void serialize(
            Money value,
            JsonGenerator generator,
            SerializerProvider provider) throws IOException {

        NumberFormat formatter =
            NumberFormat.getNumberInstance(Locale.US);
        formatter.setMinimumFractionDigits(2);
        formatter.setMaximumFractionDigits(2);

        generator.writeString(formatter.format(value.amount()));
    }
}
~~~

Mỗi lần gọi serialize() có formatter riêng. Hai thread không chia sẻ formatter đó, nên không có cuộc đua sửa đổi.

Đổi lại, việc tạo formatter ở mỗi lần gọi có chi phí cấp phát. Nếu cần tối ưu, có thể dùng một formatter bất biến và an toàn luồng, hoặc truyền cấu hình động qua context rồi tạo đối tượng mutable cục bộ tương ứng. Không nên tối ưu bằng cách đưa một đối tượng mutable vào field dùng chung nếu chưa có thiết kế đồng bộ phù hợp.

Một số đối tượng định dạng có đặc tính khác nhau:

| API | Đặc tính | Cách dùng phù hợp |
|---|---|---|
| NumberFormat / DecimalFormat | Có trạng thái và không thread-safe | Tạo local cho từng lần dùng hoặc quản lý riêng theo thread |
| SimpleDateFormat | Mutable, không thread-safe | Tránh giữ trong serializer singleton |
| DateTimeFormatter | Immutable và thread-safe | Có thể chia sẻ nếu pattern/locale cố định |
| StringBuilder | Mutable | Tạo local trong mỗi lần serialize |
| ObjectMapper | Có thể tái sử dụng sau khi cấu hình xong | Không thay đổi cấu hình khi đang dùng |

## 5. Serializer stateless hoàn chỉnh

Ví dụ một serializer ghi Money thành object JSON với amount và currency:

~~~java
public record Money(BigDecimal amount, String currency) {
}
~~~

~~~java
public final class MoneySerializer extends JsonSerializer<Money> {

    @Override
    public void serialize(
            Money value,
            JsonGenerator generator,
            SerializerProvider provider) throws IOException {

        generator.writeStartObject();
        generator.writeNumberField("amount", value.amount());
        generator.writeStringField("currency", value.currency());
        generator.writeEndObject();
    }
}
~~~

Serializer không có field mutable. Mỗi lần gọi chỉ đọc value, sử dụng generator và provider được truyền vào, sau đó ghi JSON.

Đăng ký serializer:

~~~java
SimpleModule moneyModule = new SimpleModule();
moneyModule.addSerializer(Money.class, new MoneySerializer());

ObjectMapper mapper = new ObjectMapper();
mapper.registerModule(moneyModule);
~~~

Đối tượng MoneySerializer có thể được dùng chung. Nó không lưu tham chiếu đến object Money, JsonGenerator hoặc SerializerProvider sau khi phương thức kết thúc.

## 6. Không giữ JsonGenerator hoặc SerializerProvider trong field

JsonGenerator và SerializerProvider thuộc về một lần ghi cụ thể. Chúng được Jackson truyền vào serialize() để serializer làm việc trong đúng context hiện tại.

Không nên làm:

~~~java
public class UnsafeSerializer extends JsonSerializer<Money> {
    private JsonGenerator lastGenerator;
    private SerializerProvider lastProvider;

    @Override
    public void serialize(
            Money value,
            JsonGenerator generator,
            SerializerProvider provider) throws IOException {
        lastGenerator = generator;
        lastProvider = provider;
        // ...
    }
}
~~~

Giữ lại các tham chiếu này có thể làm rò rỉ tài nguyên, giữ các object của request cũ và gây truy cập chéo giữa các thao tác. Generator còn có thể đã đóng sau khi ghi xong.

Hãy dùng chúng trực tiếp trong phạm vi phương thức:

~~~java
@Override
public void serialize(
        Money value,
        JsonGenerator generator,
        SerializerProvider provider) throws IOException {
    Object option = provider.getAttribute("display-option");
    // Dùng option cho lần ghi hiện tại
}
~~~

Serializer không nên tự đóng generator hoặc flush output do Jackson quản lý. Nó chỉ ghi nội dung giá trị của mình theo giao thức của generator.

## 7. Truyền dữ liệu động qua ObjectWriter attributes

Có trường hợp serializer thực sự cần một giá trị thay đổi theo từng lần ghi, ví dụ locale hiển thị, múi giờ xuất báo cáo hoặc chế độ trình bày. Không cần lưu giá trị đó vào field serializer. Có thể gắn attribute vào ObjectWriter.

ObjectWriter là đối tượng cấu hình cho thao tác ghi. Các phương thức như withAttribute() tạo writer mới với context attribute tương ứng, không sửa writer ban đầu.

~~~java
ObjectWriter vietnameseWriter = mapper.writer()
    .withAttribute(
        MoneySerializer.DISPLAY_LOCALE,
        Locale.forLanguageTag("vi-VN")
    );

ObjectWriter usWriter = mapper.writer()
    .withAttribute(
        MoneySerializer.DISPLAY_LOCALE,
        Locale.US
    );
~~~

Serializer đọc attribute từ SerializerProvider của thao tác hiện tại:

~~~java
public final class MoneySerializer extends JsonSerializer<Money> {

    public static final Object DISPLAY_LOCALE =
        MoneySerializer.class.getName() + ".displayLocale";

    @Override
    public void serialize(
            Money value,
            JsonGenerator generator,
            SerializerProvider provider) throws IOException {

        Object attribute = provider.getAttribute(DISPLAY_LOCALE);
        Locale locale = attribute instanceof Locale
            ? (Locale) attribute
            : Locale.US;

        NumberFormat formatter = NumberFormat.getNumberInstance(locale);
        formatter.setMinimumFractionDigits(2);
        formatter.setMaximumFractionDigits(2);

        generator.writeStartObject();
        generator.writeNumberField("amount", value.amount());
        generator.writeStringField(
            "displayAmount",
            formatter.format(value.amount()) + " " + value.currency()
        );
        generator.writeStringField("currency", value.currency());
        generator.writeEndObject();
    }
}
~~~

Sử dụng hai writer:

~~~java
Money money = new Money(new BigDecimal("1234.50"), "USD");

String viJson = vietnameseWriter.writeValueAsString(money);
String usJson = usWriter.writeValueAsString(money);
~~~

Với locale khác nhau, displayAmount có thể có dấu phân tách hàng nghìn và thập phân khác nhau. Giá trị amount vẫn là số JSON chuẩn, không phụ thuộc locale.

Điểm quan trọng là locale không được ghi vào field của MoneySerializer. Nó được gắn vào context của writer và đọc trong lần serialize tương ứng. Formatter mutable được tạo thành biến cục bộ nên không bị chia sẻ giữa các thread.

## 8. Attribute không phải cấu hình toàn cục của ObjectMapper

Không nên thay đổi một biến static hoặc cấu hình mapper trước mỗi request để truyền thông tin động:

~~~java
// Không nên dùng một trạng thái toàn cục như thế này:
CurrentRequest.setLocale(requestLocale);
String json = mapper.writeValueAsString(value);
~~~

Nếu hai request cùng thay đổi CurrentRequest hoặc một field dùng chung, dữ liệu có thể đè lên nhau. ThreadLocal cũng không tự động giải quyết mọi vấn đề: thread pool tái sử dụng thread, giá trị có thể sót lại nếu không xóa đúng cách và asynchronous execution có thể chuyển sang thread khác.

Thay vào đó, tạo writer có attribute riêng:

~~~java
String json = mapper.writer()
    .withAttribute(
        MoneySerializer.DISPLAY_LOCALE,
        requestLocale
    )
    .writeValueAsString(value);
~~~

Mỗi writer chứa cấu hình cho một thao tác hoặc một nhóm thao tác. Có thể tạo writer cho mỗi request, hoặc tái sử dụng writer nếu attribute của nó là cố định.

ObjectWriter là immutable; gọi withAttribute() trả về một writer mới. Điều này cho phép nhiều writer với các attribute khác nhau cùng dùng chung một ObjectMapper đã cấu hình.

## 9. Khi nào dùng ContextualSerializer?

ContextualSerializer phù hợp khi serializer cần biết metadata cố định của property đang được serialize. Ví dụ:

- Một property tiền tệ có scale 0, property khác có scale 2.
- Một field có quy tắc hiển thị riêng được khai báo bằng annotation.
- Một property cần định dạng theo một pattern cố định trong model.

Thông tin này gắn với cấu trúc của bean, không thay đổi theo từng request. Jackson gọi createContextual() để serializer có thể trả về một instance phù hợp với property hiện tại.

Ví dụ annotation:

~~~java
@Retention(RetentionPolicy.RUNTIME)
@Target({ElementType.FIELD, ElementType.METHOD})
public @interface DecimalScale {
    int value();
}
~~~

Serializer:

~~~java
public final class ScaledDecimalSerializer
        extends JsonSerializer<BigDecimal>
        implements ContextualSerializer {

    private final int scale;

    public ScaledDecimalSerializer() {
        this(2);
    }

    private ScaledDecimalSerializer(int scale) {
        this.scale = scale;
    }

    @Override
    public JsonSerializer<?> createContextual(
            SerializerProvider provider,
            BeanProperty property) throws JsonMappingException {

        if (property == null) {
            return this;
        }

        DecimalScale annotation =
            property.getAnnotation(DecimalScale.class);

        if (annotation == null || annotation.value() == scale) {
            return this;
        }

        return new ScaledDecimalSerializer(annotation.value());
    }

    @Override
    public void serialize(
            BigDecimal value,
            JsonGenerator generator,
            SerializerProvider provider) throws IOException {

        generator.writeNumber(
            value.setScale(scale, RoundingMode.HALF_UP)
        );
    }
}
~~~

Áp dụng trên model:

~~~java
public class Invoice {
    @DecimalScale(0)
    @JsonSerialize(using = ScaledDecimalSerializer.class)
    private BigDecimal itemCount;

    @DecimalScale(2)
    @JsonSerialize(using = ScaledDecimalSerializer.class)
    private BigDecimal totalAmount;

    // Getter và setter
}
~~~

Jackson có thể tạo serializer contextual với scale phù hợp cho từng property. Instance trả về chứa field final, không thay đổi trong serialize().

## 10. ContextualSerializer phải trả instance mới, không sửa instance đang có

Một cách triển khai sai là giữ serializer rồi cập nhật field khi Jackson contextualize property:

~~~java
// Không nên:
public JsonSerializer<?> createContextual(
        SerializerProvider provider,
        BeanProperty property) {
    this.scale = findScale(property);
    return this;
}
~~~

Jackson có thể tái sử dụng serializer gốc hoặc cache serializer đã contextualize. Nếu instance được dùng cho nhiều property, việc cập nhật scale cho property sau có thể làm thay đổi kết quả của property trước.

Mẫu đúng là:

~~~java
return new ScaledDecimalSerializer(configuredScale);
~~~

Instance mới mang cấu hình bất biến. Serializer gốc vẫn giữ nguyên. Nếu metadata không khác cấu hình hiện tại, có thể trả this vì không thay đổi trạng thái.

createContextual() là nơi đọc metadata của property và tạo cấu hình serializer tương ứng. Nó không phải nơi lưu locale hoặc người dùng của request hiện tại. Metadata property thường ổn định trong suốt vòng đời mapper, còn dữ liệu request phải được truyền theo từng thao tác.

## 11. Phân biệt ContextualSerializer và SerializerProvider attributes

Hai cơ chế phục vụ hai loại thông tin khác nhau:

| Cơ chế | Dùng cho | Vòng đời |
|---|---|---|
| ContextualSerializer | Cấu hình gắn với property như scale, pattern, annotation | Gắn với metadata của property và serializer contextual |
| ObjectWriter attributes | Dữ liệu thay đổi theo thao tác ghi như locale hoặc chế độ hiển thị | Gắn với writer/context của lần ghi |
| Biến cục bộ trong serialize | Giá trị tạm hoặc object mutable chỉ dùng trong một lần gọi | Chỉ tồn tại trong lần gọi phương thức |
| Field final của serializer | Cấu hình bất biến được chia sẻ | Vòng đời serializer |

Có thể kết hợp contextual serializer và provider attributes nếu thực sự cần cả hai. Ví dụ, property có scale cố định nhưng locale hiển thị thay đổi theo request. Khi đó scale nằm trong contextual serializer, còn locale nằm trong provider attribute.

Không nên dùng contextualization để truyền dữ liệu request vì serializer có thể được tạo hoặc cache trước khi request xuất hiện. Cũng không nên dùng provider attribute cho metadata tĩnh của property nếu annotation có thể mô tả rõ ràng hơn.

## 12. Truyền nhiều attribute cho một lần ghi

ObjectWriter hỗ trợ gắn nhiều attribute:

~~~java
Map<Object, Object> attributes = new HashMap<>();
attributes.put(MoneySerializer.DISPLAY_LOCALE, Locale.GERMANY);
attributes.put("display-mode", "verbose");

ObjectWriter writer = mapper.writer()
    .withAttributes(attributes);
~~~

Sau đó serializer có thể đọc các giá trị cần thiết:

~~~java
Object localeValue =
    provider.getAttribute(MoneySerializer.DISPLAY_LOCALE);

Object displayMode = provider.getAttribute("display-mode");
~~~

Hãy dùng key ổn định, tránh các chuỗi dễ trùng giữa module. Một hằng static final riêng của serializer hoặc một lớp key chuyên dụng giúp giảm xung đột.

Không đưa cả request object hoặc session vào attributes nếu serializer chỉ cần một giá trị nhỏ. Truyền đúng dữ liệu cần dùng, ví dụ Locale hoặc một enum presentation mode, giúp giảm phụ thuộc và tránh giữ tham chiếu lớn ngoài ý muốn.

## 13. Attribute không nên thay thế dữ liệu của domain object

Một serializer có thể dùng attribute để điều chỉnh cách trình bày, nhưng không nên biến nó thành nguồn dữ liệu nghiệp vụ bắt buộc.

Ví dụ hợp lý:

- Locale chỉ ảnh hưởng field displayAmount.
- Múi giờ chỉ ảnh hưởng chuỗi ngày giờ dành cho giao diện.
- Chế độ verbose quyết định có xuất thêm metadata trình bày hay không.

Ví dụ nên cân nhắc lại:

- User ID trong attribute quyết định giá trị owner của object.
- Attribute quyết định một khoản thanh toán có được chấp nhận hay không.
- Serializer tự truy cập database để tìm trạng thái quyền.
- Serializer dùng context để thay đổi ý nghĩa nghiệp vụ của field.

Serializer nên chịu trách nhiệm biểu diễn dữ liệu đã được quyết định ở tầng nghiệp vụ. Nếu giá trị đầu ra phụ thuộc quyền, trạng thái giao dịch hoặc dữ liệu cần truy vấn, hãy chuẩn bị DTO/response model phù hợp trước khi serialize.

## 14. Không dùng serializer để thực hiện phân quyền

Một lỗi thiết kế nguy hiểm là ẩn field nhạy cảm bằng cách kiểm tra người dùng hiện tại bên trong serializer:

~~~java
// Tránh dùng serializer như một điểm kiểm soát quyền:
if (SecurityContextHolder.getContext()
        .getAuthentication().getAuthorities().contains(adminRole)) {
    generator.writeStringField("secret", value.secret());
}
~~~

Serializer khi đó phụ thuộc vào trạng thái bảo mật toàn cục, khó kiểm thử độc lập và có nguy cơ dùng sai context khi chạy async hoặc background job.

Hãy kiểm tra quyền ở controller/service, sau đó tạo response DTO phù hợp:

~~~java
UserResponse response = userService.createResponseFor(currentUser, user);
String json = mapper.writeValueAsString(response);
~~~

Nếu hệ thống có chính sách trình bày dựa trên quyền và vẫn chọn dùng một serializer chung, context phải được truyền tường minh và không được xem đó là cơ chế thay thế authorization. Việc kiểm tra quyền vẫn phải diễn ra trước khi dữ liệu nhạy cảm được đưa vào response.

## 15. Tránh lưu request, session và ThreadLocal trong serializer

Serializer thường nằm trong tầng hạ tầng dùng chung, còn request/session thuộc vòng đời ngắn. Giữ các tham chiếu đó trong field có thể:

- Giữ lại object request sau khi request đã kết thúc.
- Làm dữ liệu request A xuất hiện trong request B.
- Gây lỗi khi serializer được gọi từ thread không có request context.
- Làm kiểm thử đơn vị phụ thuộc môi trường web.
- Gây lỗi khi serialize trong job nền hoặc message consumer.

Không nên viết:

~~~java
public class RequestAwareSerializer extends JsonSerializer<Report> {
    private HttpServletRequest request;
    private UserSession session;
}
~~~

Thay vào đó, truyền dữ liệu cần thiết qua response model hoặc attribute của ObjectWriter:

~~~java
ObjectWriter writer = mapper.writer()
    .withAttribute("report-locale", locale);

String json = writer.writeValueAsString(report);
~~~

Nếu ứng dụng dùng framework web, nên lấy thông tin request trong tầng controller/service, sau đó truyền một giá trị tường minh xuống tầng serialization.

## 16. ThreadLocal không phải lựa chọn mặc định

ThreadLocal có thể giữ dữ liệu riêng cho từng thread, nhưng nó không làm cho serializer tự động an toàn trong mọi môi trường.

Các vấn đề:

- Thread pool tái sử dụng thread giữa nhiều request.
- Nếu không gọi remove() đúng lúc, giá trị cũ có thể được dùng lại.
- CompletableFuture, reactive pipeline và async execution có thể đổi thread.
- Việc truyền context trở nên ẩn và khó kiểm tra.
- Test có thể chạy trên thread khác với ứng dụng thật.

Nếu một thư viện cũ bắt buộc dùng ThreadLocal, cần quản lý rõ việc set, restore và remove trong finally. Tuy nhiên, với Jackson, ObjectWriter.withAttribute() hoặc response DTO thường minh bạch hơn.

## 17. Chia sẻ formatter và cache có an toàn không?

Không phải mọi cache đều nguy hiểm. Một cache chỉ đọc, có giá trị bất biến và được xây dựng an toàn có thể dùng chung. Vấn đề là đối tượng cache chứa gì và có thay đổi sau khi được chia sẻ hay không.

Ví dụ DateTimeFormatter:

~~~java
private static final DateTimeFormatter FORMATTER =
    DateTimeFormatter.ofPattern("uuuu-MM-dd");
~~~

DateTimeFormatter là immutable và thread-safe, nên có thể dùng chung nếu pattern và locale cố định.

Ngược lại:

~~~java
private static final SimpleDateFormat FORMATTER =
    new SimpleDateFormat("yyyy-MM-dd");
~~~

SimpleDateFormat mutable và không thread-safe. Nhiều thread cùng gọi format() có thể gây kết quả sai.

Với cache formatter theo locale, có thể dùng cache concurrent nếu giá trị cache an toàn khi dùng đồng thời. Tuy nhiên, một Map<Locale, NumberFormat> vẫn không an toàn nếu nhiều thread cùng sửa đổi cùng một NumberFormat. Có thể cache một factory hoặc cấu hình bất biến rồi tạo formatter local.

## 18. Cấu hình serializer trước khi ObjectMapper được sử dụng

ObjectMapper nên được cấu hình hoàn chỉnh trước khi bắt đầu xử lý request. Ví dụ:

~~~java
ObjectMapper mapper = JsonMapper.builder()
    .addModule(moneyModule)
    .build();
~~~

Sau khi mapper được chia sẻ:

- Không đăng ký thêm serializer tùy tiện trong lúc request đang chạy.
- Không thay đổi naming strategy hoặc visibility configuration theo từng request.
- Không bật/tắt feature toàn cục để đáp ứng một response cụ thể.
- Không thay đổi module registry giữa các lần ghi.

Nếu cần cấu hình khác nhau theo thao tác, tạo ObjectWriter hoặc ObjectReader thay vì sửa mapper dùng chung.

~~~java
ObjectWriter compactWriter = mapper.writer()
    .with(SerializationFeature.INDENT_OUTPUT, false);

ObjectWriter prettyWriter = mapper.writer()
    .with(SerializationFeature.INDENT_OUTPUT);
~~~

Hai writer có cấu hình khác nhau nhưng vẫn dùng chung mapper đã cấu hình. Đây là cách phù hợp để tách các tùy chọn ghi mà không tạo cuộc đua sửa trạng thái mapper.

## 19. Serializer có thể chứa dependency không?

Một custom serializer có thể cần một dịch vụ hoặc component khác, nhưng dependency được chia sẻ cũng phải phù hợp với truy cập đồng thời.

Ví dụ, serializer chỉ dùng một bảng mã bất biến:

~~~java
public final class StatusSerializer extends JsonSerializer<Status> {

    private final Map<Status, String> names;

    public StatusSerializer(Map<Status, String> names) {
        this.names = Map.copyOf(names);
    }

    @Override
    public void serialize(
            Status value,
            JsonGenerator generator,
            SerializerProvider provider) throws IOException {
        generator.writeString(names.get(value));
    }
}
~~~

Map.copyOf() tạo bản sao không thể sửa đổi của map đầu vào. Nếu value trong map cũng bất biến, serializer có thể đọc map an toàn từ nhiều thread.

Không nên inject một service mutable có trạng thái request vào serializer. Nếu cần truy vấn dữ liệu, hãy thực hiện trước khi serialize và đưa kết quả vào response object.

## 20. Trường hợp serializer cần cấu hình theo property

Một class có thể có hai property cùng kiểu Java nhưng cách serialize khác nhau. Ví dụ:

~~~java
public class Product {
    @DecimalScale(0)
    @JsonSerialize(using = ScaledDecimalSerializer.class)
    private BigDecimal unitCount;

    @DecimalScale(2)
    @JsonSerialize(using = ScaledDecimalSerializer.class)
    private BigDecimal unitPrice;
}
~~~

Không nên tạo một serializer singleton rồi mỗi lần xử lý property lại gọi setScale(). ContextualSerializer giải quyết đúng vấn đề metadata theo property.

Luồng hoạt động có thể hình dung:

~~~text
Jackson tìm serializer cho property
          |
          v
createContextual(provider, property)
          |
          v
Đọc annotation của property
          |
          v
Tạo serializer mới với cấu hình final
          |
          v
serialize() chỉ đọc cấu hình và ghi giá trị
~~~

Property A có thể nhận instance scale 0; property B nhận instance scale 2. Không có việc thay đổi trạng thái qua lại trên cùng một serializer.

## 21. Serializer có thể cần cả property metadata và request attribute

Ví dụ một giá trị decimal có scale cố định theo property, nhưng cần chuỗi hiển thị theo locale của request:

~~~java
public final class LocalizedDecimalSerializer
        extends JsonSerializer<BigDecimal>
        implements ContextualSerializer {

    private final int scale;
    public static final Object LOCALE_KEY =
        LocalizedDecimalSerializer.class;

    public LocalizedDecimalSerializer() {
        this(2);
    }

    private LocalizedDecimalSerializer(int scale) {
        this.scale = scale;
    }

    @Override
    public JsonSerializer<?> createContextual(
            SerializerProvider provider,
            BeanProperty property) throws JsonMappingException {
        if (property == null) {
            return this;
        }

        DecimalScale annotation =
            property.getAnnotation(DecimalScale.class);

        return annotation == null
            ? this
            : new LocalizedDecimalSerializer(annotation.value());
    }

    @Override
    public void serialize(
            BigDecimal value,
            JsonGenerator generator,
            SerializerProvider provider) throws IOException {

        BigDecimal normalized =
            value.setScale(scale, RoundingMode.HALF_UP);

        Object configuredLocale = provider.getAttribute(LOCALE_KEY);
        Locale locale = configuredLocale instanceof Locale
            ? (Locale) configuredLocale
            : Locale.US;

        NumberFormat formatter = NumberFormat.getNumberInstance(locale);
        formatter.setMinimumFractionDigits(scale);
        formatter.setMaximumFractionDigits(scale);

        generator.writeStartObject();
        generator.writeNumberField("value", normalized);
        generator.writeStringField(
            "display",
            formatter.format(normalized)
        );
        generator.writeEndObject();
    }
}
~~~

Scale là metadata property và được giữ trong field final của serializer contextual. Locale là dữ liệu động của thao tác ghi và được đọc từ provider. Formatter mutable được tạo local.

Ví dụ sử dụng:

~~~java
ObjectWriter writer = mapper.writer()
    .withAttribute(
        LocalizedDecimalSerializer.LOCALE_KEY,
        Locale.GERMANY
    );

String json = writer.writeValueAsString(invoice);
~~~

Thiết kế này giữ rõ ranh giới giữa cấu hình của model và context của request.

## 22. Tránh side effect trong serialize()

serialize() nên chuyển đổi giá trị đầu vào thành JSON. Không nên dùng nó để:

- Cập nhật object domain.
- Ghi database.
- Gửi message hoặc gọi HTTP.
- Thay đổi cấu hình mapper.
- Thay đổi trạng thái dùng chung.
- Ghi vào biến static theo request.

Jackson có thể serialize cùng object nhiều lần, serialize trong log, hoặc gọi serializer theo một luồng khác dự kiến của ứng dụng. Nếu serialize có side effect, hành vi hệ thống trở nên khó dự đoán.

Ví dụ không nên:

~~~java
@Override
public void serialize(
        Order order,
        JsonGenerator generator,
        SerializerProvider provider) throws IOException {

    auditService.markExported(order.getId());
    order.setLastExportedAt(Instant.now());
    // Ghi JSON
}
~~~

Hãy thực hiện audit hoặc cập nhật trạng thái ở tầng service trước khi serialize. Serializer chỉ nhận dữ liệu đã sẵn sàng và ghi biểu diễn JSON.

## 23. Xử lý lỗi mà không lưu lỗi vào field

Nếu giá trị không hợp lệ, serializer có thể báo lỗi qua SerializerProvider:

~~~java
if (value.amount() == null) {
    provider.reportMappingProblem(
        "Money amount must not be null"
    );
    return;
}
~~~

Hoặc ném JsonMappingException phù hợp. Không nên lưu exception hoặc thông tin lỗi vào field serializer để lần gọi sau kiểm tra. Mỗi lần serialize cần tự xác định lỗi của chính giá trị đang xử lý.

Nếu cần thêm path thông tin, Jackson thường bổ sung path khi exception đi qua databind. Có thể dùng JsonMappingException.from(...) với context thích hợp tùy phiên bản API.

## 24. Kiểm thử serializer dùng chung

Một bài kiểm tra hữu ích là serialize nhiều lần với các attribute khác nhau bằng cùng mapper và xác nhận kết quả không bị lẫn:

~~~java
class MoneySerializerTest {

    private final ObjectMapper mapper = createMapper();

    @Test
    void writerAttributesDoNotLeakBetweenCalls() throws Exception {
        Money money = new Money(
            new BigDecimal("1234.50"),
            "USD"
        );

        ObjectWriter usWriter = mapper.writer()
            .withAttribute(
                MoneySerializer.DISPLAY_LOCALE,
                Locale.US
            );

        ObjectWriter germanWriter = mapper.writer()
            .withAttribute(
                MoneySerializer.DISPLAY_LOCALE,
                Locale.GERMANY
            );

        JsonNode us = mapper.readTree(
            usWriter.writeValueAsString(money)
        );
        JsonNode german = mapper.readTree(
            germanWriter.writeValueAsString(money)
        );

        assertEquals("1,234.50 USD",
            us.get("displayAmount").asText());
        assertEquals("1.234,50 USD",
            german.get("displayAmount").asText());
    }

    private static ObjectMapper createMapper() {
        SimpleModule module = new SimpleModule();
        module.addSerializer(Money.class, new MoneySerializer());

        ObjectMapper mapper = new ObjectMapper();
        mapper.registerModule(module);
        return mapper;
    }
}
~~~

Kiểm tra này dùng cùng một mapper và cùng một serializer class nhưng hai writer có context khác nhau. Kết quả của writer thứ nhất không bị ảnh hưởng bởi writer thứ hai.

## 25. Kiểm thử serializer với nhiều thread

Để phát hiện lỗi trạng thái dùng chung, có thể chạy nhiều tác vụ đồng thời với context khác nhau:

~~~java
@Test
void concurrentWritersKeepTheirOwnAttributes() throws Exception {
    Money money = new Money(
        new BigDecimal("1234.50"),
        "USD"
    );

    ObjectWriter usWriter = mapper.writer()
        .withAttribute(
            MoneySerializer.DISPLAY_LOCALE,
            Locale.US
        );

    ObjectWriter germanWriter = mapper.writer()
        .withAttribute(
            MoneySerializer.DISPLAY_LOCALE,
            Locale.GERMANY
        );

    ExecutorService executor = Executors.newFixedThreadPool(4);
    try {
        List<Callable<String>> tasks = new ArrayList<>();
        for (int i = 0; i < 100; i++) {
            ObjectWriter selected =
                i % 2 == 0 ? usWriter : germanWriter;
            tasks.add(() -> selected.writeValueAsString(money));
        }

        List<Future<String>> results = executor.invokeAll(tasks);
        for (int i = 0; i < results.size(); i++) {
            JsonNode node = mapper.readTree(results.get(i).get());
            String display = node.get("displayAmount").asText();

            if (i % 2 == 0) {
                assertEquals("1,234.50 USD", display);
            } else {
                assertEquals("1.234,50 USD", display);
            }
        }
    } finally {
        executor.shutdown();
    }
}
~~~

Ví dụ tập trung vào việc các lần ghi có context độc lập vẫn giữ đúng định dạng. Trong kiểm thử thực tế, cần bảo đảm thứ tự task và kết quả được ghép đúng; ví dụ này tạo danh sách task theo thứ tự và invokeAll() trả kết quả theo thứ tự tương ứng.

Một test concurrency không thể chứng minh tuyệt đối không có race condition, nhưng có thể phát hiện lỗi do field mutable dùng chung. Quan trọng hơn vẫn là thiết kế serializer không có trạng thái request trong field.

## 26. Kiểm tra serializer contextual cho từng property

Với ContextualSerializer, cần xác nhận cấu hình property này không ảnh hưởng property khác:

~~~java
class Invoice {
    @DecimalScale(0)
    @JsonSerialize(using = ScaledDecimalSerializer.class)
    private BigDecimal quantity = new BigDecimal("2.6");

    @DecimalScale(2)
    @JsonSerialize(using = ScaledDecimalSerializer.class)
    private BigDecimal price = new BigDecimal("10.456");

    public BigDecimal getQuantity() {
        return quantity;
    }

    public BigDecimal getPrice() {
        return price;
    }
}
~~~

Kết quả mong đợi theo cấu hình:

~~~json
{
  "quantity": 3,
  "price": 10.46
}
~~~

Test nên kiểm tra cả hai field trong cùng một lần serialize. Nếu serializer thay đổi field scale trên instance dùng chung, kết quả có thể phụ thuộc thứ tự property được xử lý.

## 27. Cấu hình theo request trong Spring hoặc framework web

Trong ứng dụng web, controller/service thường biết locale, timezone hoặc định dạng mà người dùng yêu cầu. Hãy lấy thông tin đó ở tầng web rồi truyền xuống writer:

~~~java
@GetMapping("/invoice/{id}")
public ResponseEntity<String> getInvoice(
        @PathVariable long id,
        Locale locale) throws JsonProcessingException {

    InvoiceResponse response = invoiceService.findResponse(id);

    String json = mapper.writer()
        .withAttribute(
            MoneySerializer.DISPLAY_LOCALE,
            locale
        )
        .writeValueAsString(response);

    return ResponseEntity.ok()
        .contentType(MediaType.APPLICATION_JSON)
        .body(json);
}
~~~

Đây là ví dụ dùng ObjectMapper trực tiếp để minh họa context. Nếu ứng dụng đang dựa vào Spring HttpMessageConverter tự serialize response, có thể cần một integration riêng để tạo writer với attributes hoặc chuẩn bị DTO đã có field trình bày. Không nên thay đổi ObjectMapper singleton trong controller để thiết lập locale cho một request.

Nếu API cần JSON ổn định cho máy đọc, nên giữ số và ngày giờ ở dạng chuẩn, không phụ thuộc locale. Locale-specific display có thể là một field bổ sung hoặc được tạo ở tầng giao diện.

## 28. Khi nào tạo serializer instance riêng là hợp lý?

Không phải lúc nào cũng phải dùng đúng một serializer instance. Nếu cấu hình cố định khác nhau theo kiểu hoặc property, việc tạo các instance bất biến riêng là hợp lý:

- Serializer scale 0 và serializer scale 2.
- Serializer dùng pattern ngày giờ cố định A và B.
- Serializer contextual cho từng property.

Điều cần tránh là tái sử dụng một instance mutable rồi cập nhật cấu hình trước mỗi lần gọi. Một instance bất biến cho mỗi cấu hình là an toàn hơn.

Ví dụ:

~~~java
JsonSerializer<BigDecimal> integerSerializer =
    new FixedScaleSerializer(0);

JsonSerializer<BigDecimal> decimalSerializer =
    new FixedScaleSerializer(2);
~~~

Hai serializer có thể được chia sẻ vì field cấu hình là final và phương thức serialize không thay đổi chúng.

## 29. Không dùng synchronized để che một thiết kế có trạng thái

Có thể khóa phương thức serialize để ngăn hai thread cùng truy cập formatter mutable:

~~~java
@Override
public synchronized void serialize(
        Money value,
        JsonGenerator generator,
        SerializerProvider provider) throws IOException {
    // Dùng formatter mutable dùng chung
}
~~~

Điều này có thể tránh một số race condition nhưng làm tất cả request phải chờ nhau khi cùng dùng serializer. Nó còn khiến việc thay đổi trạng thái request trên field trở thành nguồn lỗi logic nếu thứ tự set và serialize không được khóa đồng bộ toàn bộ.

synchronized không giải quyết việc request A và request B ghi đè locale của nhau nếu setLocale() nằm ngoài vùng khóa hoặc được gọi trước khi serialize. Nó cũng không giải quyết rò rỉ trạng thái giữa các lần gọi.

Ưu tiên thiết kế stateless hoặc dùng context per-call. Chỉ dùng đồng bộ khi có một tài nguyên mutable thực sự cần chia sẻ và đã xác định rõ phạm vi khóa, hiệu năng và vòng đời.

## 30. Dùng cache có kiểm soát nếu thực sự cần tối ưu

Nếu tạo formatter mỗi lần serialize gây chi phí đáng kể, có thể cân nhắc cache theo một cấu hình hữu hạn. Cache phải được quản lý riêng và chỉ trả về đối tượng an toàn khi chia sẻ.

Không nên:

~~~java
private static final Map<Locale, NumberFormat> FORMATTERS =
    new HashMap<>();
~~~

Map trên vừa mutable, vừa không thread-safe; các NumberFormat bên trong cũng mutable và không thread-safe.

Các phương án an toàn hơn:

- Cache pattern hoặc cấu hình bất biến rồi tạo formatter local.
- Dùng DateTimeFormatter nếu phù hợp với kiểu dữ liệu.
- Dùng cache concurrent nhưng value phải immutable hoặc không bị chia sẻ mutable.
- Chỉ tối ưu sau khi đo đạc bằng profiling.

Nếu locale có số lượng không giới hạn, cache không giới hạn có thể làm tăng bộ nhớ. Cần cân nhắc eviction hoặc giới hạn miền giá trị.

## 31. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Request có định dạng locale của request khác | Serializer lưu locale trong field dùng chung | Dùng ObjectWriter attribute |
| Kết quả số/ngày giờ không ổn định khi tải cao | Chia sẻ NumberFormat hoặc SimpleDateFormat | Tạo local hoặc dùng formatter immutable |
| Hai property dùng cùng serializer nhưng có scale sai | ContextualSerializer sửa instance hiện có | Trả serializer mới có cấu hình final |
| Dữ liệu request cũ xuất hiện trong job nền | Serializer giữ request/session hoặc ThreadLocal | Truyền dữ liệu cần thiết tường minh |
| JSON thay đổi sau khi serialize lần trước | Serializer có side effect hoặc giữ trạng thái | Làm serializer stateless |
| Lỗi chỉ xuất hiện khi chạy nhiều thread | Mutable field dùng chung | Loại bỏ trạng thái thay đổi theo request |
| Mapper thay đổi hành vi giữa các request | Thay đổi feature/module trên mapper singleton | Cấu hình mapper trước khi dùng; tạo ObjectWriter riêng |
| Bộ nhớ tăng sau nhiều request | Serializer giữ generator, provider hoặc request | Không giữ tham chiếu per-call trong field |
| Test chạy riêng thì qua nhưng chạy suite thì sai | Trạng thái dùng chung còn sót giữa các lần gọi | Làm sạch thiết kế, kiểm thử nhiều lần và song song |

## 32. Quy trình thiết kế serializer dùng chung

Khi viết một custom serializer, có thể xác định vị trí của từng loại dữ liệu theo trình tự:

1. Liệt kê cấu hình cần thiết để biểu diễn giá trị.
2. Xác định cấu hình nào cố định cho serializer.
3. Xác định cấu hình nào thuộc property và có thể đọc qua annotation.
4. Xác định dữ liệu nào thay đổi theo từng lần ghi.
5. Đặt dữ liệu tạm trong biến cục bộ.
6. Truyền dữ liệu per-call bằng ObjectWriter attributes khi phù hợp.
7. Không lưu JsonGenerator, SerializerProvider hoặc request object vào field.
8. Không gọi service hoặc thay đổi trạng thái domain trong serialize().
9. Đảm bảo mọi field dùng chung là final hoặc an toàn khi đọc đồng thời.
10. Kiểm tra cùng mapper với nhiều writer/context và nhiều thread.

Sơ đồ phân loại:

~~~text
Thông tin serializer cần dùng
          |
          +--> Cố định cho mọi lần ghi?
          |       |
          |       +--> Field final, immutable
          |
          +--> Cố định theo property?
          |       |
          |       +--> ContextualSerializer
          |            trả instance mới, immutable
          |
          +--> Thay đổi theo lần ghi?
          |       |
          |       +--> ObjectWriter.withAttribute()
          |            đọc qua SerializerProvider
          |
          +--> Chỉ là biến tạm?
                  |
                  +--> Biến cục bộ trong serialize()
~~~

## 33. Nguyên tắc thực hành

- Xem custom serializer như thành phần có thể được cache và gọi đồng thời.
- Không giả định Jackson tạo instance serializer mới cho mỗi request.
- Giữ serializer stateless hoặc chỉ có cấu hình bất biến.
- Không thay đổi field serializer trong serialize().
- Dùng biến cục bộ cho formatter, buffer và giá trị tạm mutable.
- Dùng ContextualSerializer cho metadata cố định theo property.
- Trong createContextual(), trả instance mới có cấu hình final thay vì sửa instance đang có.
- Dùng ObjectWriter.withAttribute() cho dữ liệu động theo thao tác ghi.
- Đọc attribute qua SerializerProvider.getAttribute().
- Không giữ request, session, generator, provider hoặc domain object trong field.
- Không dùng ThreadLocal làm cơ chế truyền context mặc định.
- Không dùng serializer để thực hiện phân quyền, truy vấn database hoặc side effect.
- Cấu hình ObjectMapper và module trước khi chia sẻ mapper.
- Kiểm tra hành vi bằng nhiều writer và nhiều thread.

Serializer dùng chung an toàn khi trạng thái của nó không thay đổi theo request. Cấu hình cố định có thể nằm trong field final; metadata của property nên được chuyển thành instance contextual bất biến; dữ liệu động nên đi theo context của lần ghi hoặc biến cục bộ. Cách phân chia này giúp một ObjectMapper phục vụ nhiều request đồng thời mà không trộn lẫn dữ liệu, đồng thời làm custom serializer dễ kiểm thử và bảo trì hơn.
