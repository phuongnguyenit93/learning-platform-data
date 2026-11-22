# Schema có thể dùng chung và giới hạn chia sẻ Validator

## 1. Tách bộ quy tắc khỏi một lần kiểm tra tài liệu

Trong một dịch vụ nhận nhiều tài liệu XML, các tài liệu có thể cùng phải tuân theo một XSD. Nếu mỗi yêu cầu đều đọc và biên dịch lại XSD, chương trình lặp lại phần chuẩn bị không cần thiết.

JAXP tách hai trách nhiệm:

```text
XSD
    ↓ SchemaFactory biên dịch
Schema: bộ quy tắc đã chuẩn bị
    ↓ newValidator()
Validator: bộ xử lý cho một lần kiểm tra hoặc một chuỗi dùng tuần tự
    ↓ validate(XML)
Kết quả kiểm tra
```

Điểm thiết kế quan trọng:

- **Schema có thể được dùng chung giữa nhiều luồng.**
- **Validator không được dùng đồng thời tùy ý và không được gọi validate tái nhập.**

Vì vậy tối ưu đúng thường là chia sẻ Schema, còn trạng thái của từng lượt kiểm tra được tách qua các Validator riêng.

Các lớp `javax.xml.validation` này vẫn là API Java SE được hỗ trợ trong module `java.xml`; tên gói không cần đổi sang Jakarta.

## 2. Hợp đồng của ba đối tượng không giống nhau

| Đối tượng | Vai trò | Quy tắc chia sẻ |
| --- | --- | --- |
| `SchemaFactory` | Biên dịch XSD thành Schema | Không an toàn đồng thời, không tái nhập |
| `Schema` | Biểu diễn bất biến của tập ràng buộc | An toàn khi dùng chung giữa nhiều luồng |
| `Validator` | Thực hiện kiểm tra XML và giữ cấu hình xử lý lượt kiểm tra | Không an toàn đồng thời, không tái nhập |

Hợp đồng Schema khuyến khích dùng chung đối tượng giữa nhiều parser/luồng; xem [Schema](https://docs.oracle.com/en/java/javase/21/docs/api/java.xml/javax/xml/validation/Schema.html).

Hợp đồng Validator yêu cầu ứng dụng bảo đảm một Validator không bị dùng bởi nhiều luồng cùng lúc và không gọi validate lồng vào chính Validator đang chạy; xem [Validator](https://docs.oracle.com/en/java/javase/21/docs/api/java.xml/javax/xml/validation/Validator.html).

Hợp đồng SchemaFactory cũng không cho phép cùng một factory được sử dụng đồng thời hoặc biên dịch tái nhập; xem [SchemaFactory](https://docs.oracle.com/en/java/javase/21/docs/api/java.xml/javax/xml/validation/SchemaFactory.html).

Không suy từ việc một lớp được sinh ra bởi đối tượng an toàn đồng thời rằng bản thân lớp đó cũng có cùng đặc tính.

## 3. Vì sao Schema phù hợp để chia sẻ?

Schema biểu diễn bộ ràng buộc đã được chuẩn bị từ nguồn schema. Về hợp đồng, tập ràng buộc không bị sửa sau khi đối tượng được tạo.

Nhiều lượt kiểm tra có thể đọc cùng bộ quy tắc:

```text
                  Schema dùng chung
                 /        |        \
        Validator A  Validator B  Validator C
             ↓            ↓            ↓
           XML A        XML B        XML C
```

Mỗi Validator được tạo qua `schema.newValidator()`.

Chia sẻ Schema giúp tách vòng đời:

- Nguồn XSD được tải và biên dịch khi khởi tạo hoặc khi phiên bản quy tắc thay đổi.
- Các yêu cầu bình thường dùng Schema đã chuẩn bị.
- Mỗi lượt kiểm tra tạo hoặc nhận một Validator riêng theo giao thức quản lý rõ.

Không có nghĩa mọi phần phụ thuộc đều tự an toàn: nếu nhiều lượt kiểm tra đọc cùng một InputStream hoặc dùng cùng callback khả biến, các tài nguyên đó vẫn cần được tách hoặc bảo vệ riêng.

## 4. Vì sao một Validator static final vẫn có thể sai?

Đoạn sau có một tham chiếu không đổi, nhưng đối tượng được tham chiếu vẫn là một Validator có trạng thái và hợp đồng không an toàn đồng thời:

```java
// Mã minh họa thiết kế không phù hợp cho validate đồng thời.
private static final Validator SHARED = schema.newValidator();
```

Nếu nhiều yêu cầu cùng gọi:

```java
SHARED.validate(source);
```

chúng đang chia sẻ cùng bộ xử lý cho nhiều lượt kiểm tra chồng lấn.

`final` chỉ ngăn việc gán lại biến tham chiếu. Nó không biến đối tượng thành bất biến và không thêm khả năng đồng bộ vào `validate()`.

Những phần cấu hình có thể khác giữa các yêu cầu gồm:

- ErrorHandler nhận thông báo lỗi.
- LSResourceResolver phân giải tài nguyên.
- Feature và property.
- Đích kết quả nếu dùng dạng validate có Result.
- Trạng thái do callback của ứng dụng lưu.

Không cần chứng minh có lỗi bằng cách chạy thử đến khi xuất hiện thông báo nội bộ nào đó. Khi hợp đồng không cho phép dùng đồng thời, việc một vài lần thử “vẫn chạy được” không tạo ra bảo đảm.

## 5. Cách mặc định rõ ràng: một Validator cho mỗi lượt

```java
// Mã minh họa.
Schema schema = loadSchemaOnce();

void validateOne(Source source) throws SAXException, IOException {
    Validator validator = schema.newValidator();
    configureForThisValidation(validator);
    validator.validate(source);
}
```

Phần cấu hình của một lượt được hoàn tất trước khi validate. Đối tượng không bị công bố để một luồng khác đổi handler hoặc property trong lúc kiểm tra đang chạy.

Một dịch vụ có thể giữ Schema trong trường final sau khi constructor đã nhận một Schema hợp lệ:

```java
// Mã minh họa cấu trúc, không phải chương trình độc lập.
final class XmlValidationService {
    private final Schema schema;

    XmlValidationService(Schema schema) {
        this.schema = Objects.requireNonNull(schema);
    }

    void validate(Source source) throws SAXException, IOException {
        Validator validator = schema.newValidator();
        configureForThisValidation(validator);
        validator.validate(source);
    }
}
```

Chỉ schema được dùng chung ở lớp này. Nguồn, bộ nhận lỗi và Validator của từng yêu cầu cần được quản lý đúng theo hợp đồng của chúng.

Tạo Validator mới mỗi lượt là lựa chọn đơn giản để tránh rò cấu hình. Không khẳng định nó luôn rẻ nhất trong mọi tải; nếu cần tối ưu thêm thì đo trước và giữ nguyên các ràng buộc an toàn.

## 6. Ví dụ đầy đủ: ba tác vụ dùng cùng Schema

XSD trong ví dụ yêu cầu order có quantity là `xs:positiveInteger`, nên 2 và 7 hợp lệ nhưng 0 không hợp lệ.

Tệp `SchemaValidatorSharingDemo.java`, chạy trên JDK 17 trở lên, không cần thư viện ngoài:

```java
import java.io.IOException;
import java.io.StringReader;
import java.util.List;
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import javax.xml.XMLConstants;
import javax.xml.transform.stream.StreamSource;
import javax.xml.validation.Schema;
import javax.xml.validation.SchemaFactory;
import javax.xml.validation.Validator;
import org.xml.sax.SAXException;

public class SchemaValidatorSharingDemo {
    private static Schema compileSchema() throws SAXException {
        String xsd = """
                <xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
                  <xs:element name="order">
                    <xs:complexType>
                      <xs:sequence>
                        <xs:element name="quantity" type="xs:positiveInteger"/>
                      </xs:sequence>
                    </xs:complexType>
                  </xs:element>
                </xs:schema>
                """;

        SchemaFactory factory = SchemaFactory.newDefaultInstance();
        factory.setFeature(XMLConstants.FEATURE_SECURE_PROCESSING, true);
        factory.setProperty(XMLConstants.ACCESS_EXTERNAL_DTD, "");
        factory.setProperty(XMLConstants.ACCESS_EXTERNAL_SCHEMA, "");
        return factory.newSchema(new StreamSource(new StringReader(xsd)));
    }

    private static String validate(
            Schema schema, String label, String xml) throws IOException, SAXException {
        Validator validator = schema.newValidator();
        validator.setFeature(XMLConstants.FEATURE_SECURE_PROCESSING, true);
        validator.setProperty(XMLConstants.ACCESS_EXTERNAL_DTD, "");
        validator.setProperty(XMLConstants.ACCESS_EXTERNAL_SCHEMA, "");

        try (StringReader input = new StringReader(xml)) {
            try {
                validator.validate(new StreamSource(input));
                return label + "=VALID";
            } catch (SAXException invalidXml) {
                return label + "=INVALID";
            }
        }
    }

    public static void main(String[] args) throws Exception {
        Schema schema = compileSchema();
        ExecutorService pool = Executors.newFixedThreadPool(3);

        try {
            List<Callable<String>> tasks = List.of(
                    () -> validate(schema, "A",
                            "<order><quantity>2</quantity></order>"),
                    () -> validate(schema, "B",
                            "<order><quantity>0</quantity></order>"),
                    () -> validate(schema, "C",
                            "<order><quantity>7</quantity></order>"));

            List<Future<String>> results = pool.invokeAll(tasks);
            for (Future<String> result : results) {
                System.out.println(result.get());
            }
        } finally {
            pool.shutdownNow();
        }
    }
}
```

Biên dịch và chạy:

```shell
javac SchemaValidatorSharingDemo.java
java SchemaValidatorSharingDemo
```

Kết quả:

```text
A=VALID
B=INVALID
C=VALID
```

Điểm cần quan sát trong mã:

1. `compileSchema()` được gọi một lần trước khi gửi các tác vụ.
2. Cả ba lambda giữ cùng một Schema.
3. Mỗi lần `validate(...)` gọi `schema.newValidator()` riêng.
4. Mỗi tác vụ có StringReader riêng, không tranh nhau đọc một nguồn.
5. Kết quả được đọc theo thứ tự danh sách Future, nên dòng in ổn định dù thứ tự hoàn tất có thể khác.

Ví dụ không cài ErrorHandler tùy chỉnh; đường xử lý mặc định của Validator làm lỗi kiểm tra thoát ra thành SAXException để mã minh họa phân loại.

Các lệnh cấu hình Validator nằm ngoài khối catch phân loại tài liệu, nên lỗi thiết lập không bị nhầm thành việc XML vi phạm quantity.

Mẫu chỉ in VALID/INVALID cho dữ liệu cố định nhằm tập trung vào chia sẻ đối tượng. Ứng dụng thật cần giữ thông tin lỗi cụ thể và phân biệt lỗi dữ liệu, lỗi đọc nguồn hoặc lỗi cấu hình/tài nguyên khi phù hợp.

## 7. Không tái nhập, kể cả khi chỉ có một luồng

Không an toàn đồng thời nói về hai lần sử dụng chồng lấn giữa các luồng. Không tái nhập còn cấm một tình huống khác:

```text
Validator V đang validate XML A
    ↓ gọi callback xử lý lỗi hoặc phân giải tài nguyên
Callback gọi tiếp V.validate(XML B)
    ↓
V bị dùng lồng khi lần kiểm tra A chưa kết thúc
```

Một khóa `synchronized` không tự chặn lỗi này nếu cùng luồng đi vào lại, vì monitor Java cho phép tái nhập.

Nếu callback cần kiểm tra một tài liệu độc lập, phải dùng một Validator khác và thiết kế rõ vì sao cần gọi việc đó ở trong callback. Không gọi lại chính bộ xử lý đang hoạt động.

Tương tự, `SchemaFactory.newSchema` không được gọi lồng vào cùng factory đang biên dịch, kể cả từ một callback trong cùng luồng.

## 8. Có thể tái sử dụng tuần tự, nhưng phải kiểm soát cấu hình

Một Validator có thể được dùng cho nhiều tài liệu **theo lượt không chồng lấn**, nếu ứng dụng duy trì đúng vòng đời cấu hình và trạng thái.

Khi tái sử dụng, cần xác định:

- ErrorHandler cũ có còn giữ lỗi của lượt trước không?
- Resolver cũ có giữ ngữ cảnh yêu cầu trước không?
- Feature/property nào phải áp dụng cho lượt mới?
- Nguồn và Result có còn được giữ ngoài ý muốn không?
- Sau một lượt thất bại, Validator có được đưa về trạng thái phù hợp trước lượt sau không?

`reset()` đưa Validator về cấu hình ban đầu theo hợp đồng. Không coi nó là cách cho phép nhiều luồng dùng đồng thời. Không gọi reset khi một lượt validate còn đang chạy.

Sau reset, áp dụng lại những cấu hình mà giao thức của ứng dụng yêu cầu, gồm cả chính sách truy cập tài nguyên nếu cần. Không mặc định handler hoặc property được cài cho lượt trước vẫn là cấu hình của lượt tiếp theo.

Nếu việc reset/tái cấu hình làm mã phức tạp hơn lợi ích đã đo, dùng Validator mới cho mỗi lần là lựa chọn dễ kiểm tra hơn.

## 9. Đồng bộ hóa toàn bộ lượt dùng có thể tuần tự hóa Validator

Một phương án khác là bảo vệ một Validator bằng khóa và không cho callback gọi lồng:

```java
// Mã minh họa phạm vi bảo vệ cần xem xét.
synchronized (validatorLock) {
    prepareValidatorForThisRequest();
    validator.validate(source);
    finishValidationAndCollectResult();
}
```

Chỉ khóa đúng dòng validate nhưng để các luồng khác gọi setErrorHandler hoặc setProperty ngoài khóa vẫn không bảo vệ trọn lượt dùng.

Phương án này làm các lượt kiểm tra đi tuần tự qua một bộ xử lý. Nó có thể phù hợp với một số nhu cầu, nhưng không còn khai thác khả năng nhiều Validator kiểm tra song song từ cùng Schema.

Đừng gọi `synchronized(schema)` chỉ vì Schema được dùng chung. Hợp đồng đã cho phép chia sẻ Schema; thứ cần bảo vệ là đối tượng hoặc tài nguyên thực sự có trạng thái dùng chồng lấn.

## 10. ThreadLocal và pool không tự giải quyết vòng đời

Có thể gặp các phương án giữ một Validator theo luồng hoặc mượn từ pool. Chúng chỉ an toàn khi có giao thức đầy đủ.

### Validator theo luồng

Một ThreadLocal hạn chế chia sẻ giữa các luồng, nhưng vẫn phải:

- Không gọi tái nhập trên cùng Validator.
- Xóa dữ liệu riêng của lần kiểm tra trước.
- Tái áp dụng cấu hình cần thiết.
- Quản lý việc luồng được tái sử dụng lâu dài.
- Thay Validator khi Schema phiên bản mới được áp dụng.

### Pool Validator

Mỗi Validator phải được mượn độc quyền đến khi validate và dọn trạng thái xong. Không trả về pool trước khi callback hoặc công việc liên quan thật sự kết thúc.

Một lượt lỗi cũng cần chính sách rõ: reset và kiểm chứng trước khi dùng lại, hoặc loại đối tượng đó ra theo thiết kế. Không đưa lại một đối tượng đang dùng dở cho yêu cầu khác.

Những phương án này có chi phí quản lý và kiểm thử. Không dùng chúng chỉ vì thấy chữ “tái sử dụng” mà chưa có số liệu cho thấy tạo Validator mới là nút thắt.

## 11. Callback dùng chung có thể tạo tranh chấp dù Validator đã tách

Giả sử mỗi tác vụ có Validator riêng nhưng tất cả cùng dùng một ErrorHandler giữ danh sách lỗi:

```text
Validator A ─┐
Validator B ─┼→ cùng một List lỗi khả biến
Validator C ─┘
```

Khi đó kết quả của các tài liệu có thể bị trộn hoặc danh sách bị sửa đồng thời không an toàn.

Cách rõ ràng hơn là mỗi lượt có bộ thu lỗi riêng. Nếu một handler được dùng chung, phải thiết kế nó phù hợp đồng thời và gắn lỗi đúng định danh lượt kiểm tra.

ErrorHandler còn quyết định cách lỗi được báo:

- Một handler ném ở error/fatalError tạo đường thất bại rõ.
- Một handler chỉ lưu thông báo rồi cho tiếp tục cần được kiểm tra trạng thái sau validate.
- Không được kết luận XML hợp lệ chỉ vì validate trở về bình thường khi chính handler đã chọn không ném lỗi.

Xem [ErrorHandler](https://docs.oracle.com/en/java/javase/21/docs/api/java.xml/org/xml/sax/ErrorHandler.html) cùng hợp đồng setErrorHandler của Validator.

LSResourceResolver cũng có thể chứa cache hoặc trạng thái riêng. Chia sẻ callback phải dựa vào hợp đồng của callback đó, không dựa vào tính an toàn của Schema.

## 12. Cấu hình tài nguyên áp dụng ở đúng giai đoạn

Có hai giai đoạn cần xem:

```text
Biên dịch schema:
SchemaFactory đọc XSD và tài nguyên phụ thuộc

Kiểm tra XML:
Validator đọc XML và xử lý các tài nguyên được phép theo cấu hình
```

Ví dụ hạn chế truy cập DTD/schema ngoài cả ở factory và Validator vì nguồn minh họa không cần các tài nguyên đó.

Không tự giả định mọi property cài lên factory đều luôn được truyền sang mọi đối tượng về sau theo đúng chính sách ứng dụng mong muốn. Hãy cấu hình và xác minh ở đúng đối tượng/giai đoạn.

Nếu XSD thật cần include/import, phải thiết kế nguồn phụ thuộc hoặc resolver được phép tương ứng; không bỏ mọi giới hạn truy cập chỉ để một lỗi tải tài nguyên biến mất.

Xem [JAXP Security Guide](https://docs.oracle.com/en/java/javase/21/security/java-api-xml-processing-jaxp-security-guide.html) để phân biệt các cơ chế giới hạn và giai đoạn áp dụng.

Một Schema dùng chung không khiến việc nhiều tác vụ cùng đọc một InputStream trở nên hợp lệ. Mỗi lần kiểm tra vẫn cần một nguồn mới hoặc một mô hình đầu vào có vòng đời được quản lý riêng.

## 13. Cache Schema theo bộ quy tắc thật sự

Nếu dùng lại Schema đã biên dịch, khóa cache phải phản ánh bộ quy tắc:

- Phiên bản hoặc nội dung XSD chính.
- Các include/import và cách phân giải phụ thuộc có liên quan.
- Loại bộ cung cấp/ngôn ngữ schema nếu ứng dụng cho phép thay đổi.
- Cấu hình biên dịch có ảnh hưởng đến kết quả hoặc quyền truy cập.

Không chỉ dựa vào tên tệp mà mặc định nội dung không đổi.

Khi XSD thay đổi, đối tượng Schema cũ không tự trở thành phiên bản mới. Cần biên dịch một Schema mới thành công rồi công bố phiên bản đó theo cơ chế an toàn của ứng dụng.

Một lượt kiểm tra nên giữ một tham chiếu Schema đã chọn trong suốt lượt, thay vì lấy lại “schema hiện tại” nhiều lần và trộn cấu hình của hai phiên bản.

Nếu biên dịch mới thất bại, phải báo lỗi cập nhật quy tắc theo chính sách. Không thay một Schema đang dùng bằng trạng thái dở dang hoặc null rồi để các yêu cầu kiểm tra chịu lỗi ngẫu nhiên.

## 14. Thực hành kiểm tra thiết kế

1. Tìm các trường singleton/static: đối tượng được giữ là Schema hay Validator?
2. Với mỗi Validator, chỉ ra ai đang sở hữu lượt dùng và khi nào lượt kết thúc.
3. Kiểm tra handler, resolver, nguồn đầu vào và kết quả có bị dùng chung khả biến không.
4. Nếu tái sử dụng tuần tự, mô tả việc reset/tái cấu hình và đường xử lý lỗi.
5. Nếu có callback, kiểm tra không gọi validate lồng lên cùng đối tượng.
6. Khi đổi XSD, xác định cách tạo và công bố Schema phiên bản mới.

Bài tập với ví dụ:

- Thay quantity của B từ 0 thành 1: cả ba kết quả hợp lệ.
- Cố đưa một Validator ra ngoài hàm validate và cho ba tác vụ dùng cùng: vì sao việc chạy thử chưa thấy lỗi vẫn không đủ? Hợp đồng không bảo đảm dùng đồng thời.
- Giữ Validator riêng nhưng chia sẻ một bộ thu lỗi chưa đồng bộ: vì sao vẫn có thể sai? Trạng thái dùng chung đã chuyển sang callback.
- Thêm reset trong lúc một luồng đang validate: vì sao không phải cách làm sạch an toàn? Nó chồng một thao tác cấu hình lên lượt dùng đang hoạt động.

Nguyên tắc là **chia sẻ bộ quy tắc bất biến, còn bộ xử lý và trạng thái của từng lần kiểm tra phải có quyền sử dụng rõ ràng**.
