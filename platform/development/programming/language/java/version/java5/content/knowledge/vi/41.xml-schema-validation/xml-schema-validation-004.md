# Tạo Validator cho mỗi lần kiểm tra phù hợp

## 1. Tách bộ quy tắc khỏi một lượt kiểm tra

Khi kiểm tra XML theo XSD, có hai công việc khác nhau: chuẩn bị bộ quy tắc và dùng bộ quy tắc đó kiểm tra một tài liệu. JAXP biểu diễn chúng bằng `Schema` và `Validator`.

`Schema` là biểu diễn ngữ pháp đã được chuẩn bị. `Validator` là bộ xử lý cho một lượt kiểm tra: nó có cấu hình, bộ nhận lỗi, bộ phân giải tài nguyên và trạng thái xử lý liên quan. Để nhiều yêu cầu cùng kiểm tra theo một XSD ổn định, mô hình rõ ràng thường là **dùng chung Schema, tạo Validator riêng cho mỗi lần kiểm tra**.

```text
Khởi tạo ứng dụng:
    XSD đã biết → SchemaFactory → Schema

Yêu cầu A: Schema → Validator A + handler A + nguồn XML A
Yêu cầu B: Schema → Validator B + handler B + nguồn XML B
Yêu cầu C: Schema → Validator C + handler C + nguồn XML C
```

Nhờ vậy, việc dùng lại bộ quy tắc không bị nhầm thành chia sẻ một bộ xử lý có trạng thái. Đây là mô hình dùng API hiện hành, không phải cách né tránh một lỗi của riêng một phiên bản JDK.

## 2. Hợp đồng của ba đối tượng chính

| Đối tượng | Vai trò | Phạm vi sử dụng cần nhớ |
| --- | --- | --- |
| `SchemaFactory` | Đọc/biên dịch XSD thành Schema | Không dùng cùng instance đồng thời; không gọi newSchema lồng khi lượt trước đang hoạt động |
| `Schema` | Giữ bộ quy tắc đã chuẩn bị | Bất biến theo ngữ nghĩa ràng buộc và an toàn luồng; có thể dùng chung |
| `Validator` | Kiểm tra một nguồn XML theo Schema | Không an toàn luồng, không tái nhập; cần một chủ sở hữu tại một thời điểm |

`Schema.newValidator()` tạo bộ kiểm tra cho chính schema đó. Không cần gọi lại `newSchema(...)` chỉ để xử lý thêm một tài liệu cùng hợp đồng. [Schema](https://docs.oracle.com/en/java/javase/25/docs/api/java.xml/javax/xml/validation/Schema.html), [SchemaFactory](https://docs.oracle.com/en/java/javase/25/docs/api/java.xml/javax/xml/validation/SchemaFactory.html)

API không cho phép nhiều luồng cùng dùng một `Validator` tại một thời điểm. Cũng không cho phép một callback gọi lại `validate()` trên chính validator khi lần ngoài chưa kết thúc, dù chỉ có một luồng. [Validator](https://docs.oracle.com/en/java/javase/25/docs/api/java.xml/javax/xml/validation/Validator.html)

Từ khóa `final` chỉ cố định tham chiếu; một trường `private final Validator` trong singleton vẫn có thể bị nhiều yêu cầu gọi đồng thời. Trái lại, giữ một `private final Schema` rồi tạo validator cục bộ cho từng lời gọi phù hợp với cách chia sẻ mà API hỗ trợ, nếu dịch vụ được khởi tạo và công bố đúng.

## 3. Một lượt kiểm tra nên có những gì riêng?

Ngoài `Validator`, hãy xác định quyền sở hữu của các thành phần liên quan:

- **Nguồn XML:** mỗi lượt có `Source`/reader/stream riêng; không chia sẻ một con trỏ đọc đang thay đổi.
- **ErrorHandler hoặc bộ thu lỗi:** trạng thái lỗi phải thuộc đúng tài liệu đang kiểm tra, không cộng vào danh sách dùng chung thiếu định danh.
- **ResourceResolver:** có chính sách nguồn rõ ràng; nếu có trạng thái theo yêu cầu thì không để yêu cầu khác thay đổi trong lúc kiểm tra.
- **Đối tượng kết quả:** trả thông tin của lượt này và không để lộ trạng thái bộ xử lý cho bên khác sử dụng đồng thời.
- **Tài nguyên bên ngoài:** nguồn nào do bên gọi mở thì cần có trách nhiệm đóng phù hợp, kể cả khi XML bị từ chối.

Không cần nhân bản mọi đối tượng bất biến. Một chuỗi XSD hoặc cấu hình bất biến có thể được dùng chung. Nhưng một danh sách lỗi, stream, DOM đang được sửa hoặc resolver giữ “tài liệu hiện tại” không tự trở thành an toàn chỉ vì validator đã tách riêng.

## 4. Quy trình tạo Validator cho từng lời gọi

Một phương thức dịch vụ có thể đi theo thứ tự:

1. Chọn đúng `Schema` theo loại/phiên bản hợp đồng đã cho phép.
2. Gọi `schema.newValidator()`.
3. Áp dụng feature/property cần thiết cho lượt kiểm tra.
4. Tạo và gắn handler/resolver theo chính sách của lượt đó.
5. Chuẩn bị nguồn đọc riêng và gọi `validate(source)`.
6. Kết hợp trạng thái lỗi đã được handler ghi nhận với kết quả/ngoại lệ của lời gọi.
7. Đóng nguồn và trả kết quả theo hợp đồng dịch vụ.

Việc thiết lập cần hoàn tất trước validate, không đổi handler hoặc resolver trên cùng validator trong khi kiểm tra còn chạy. Cấu hình không hỗ trợ phải được phát hiện rõ; không bỏ qua lỗi rồi báo rằng một chính sách đã có hiệu lực.

Trong ứng dụng có schema cố định, bước biên dịch schema có thể thực hiện khi khởi tạo. Nếu XSD không hợp lệ hoặc cấu hình biên dịch sai, nên xử lý như lỗi chuẩn bị bộ quy tắc; không trộn nó vào kết quả “XML của khách hàng không hợp lệ”.

## 5. validate trở về bình thường có luôn nghĩa hợp lệ không?

Không phải với mọi `ErrorHandler`. Validator gửi lỗi đến handler. Nếu handler nhận lỗi kiểm tra có thể tiếp tục rồi **không ném ngoại lệ**, validate có thể trở về bình thường dù đã báo lỗi. Cần đọc trạng thái mà handler ghi nhận hoặc chọn chính sách ném ngay khi có lỗi. [Ngữ nghĩa trả về của Validator.validate](https://docs.oracle.com/en/java/javase/25/docs/api/java.xml/javax/xml/validation/Validator.html#validate(javax.xml.transform.Source,javax.xml.transform.Result))

Có hai chính sách điển hình:

| Chính sách | Hành vi handler | Cách quyết định |
| --- | --- | --- |
| Dừng ở lỗi đầu tiên | `error`/`fatalError` ném `SAXException` | Thành công khi validate hoàn tất và không ghi nhận lỗi theo chính sách |
| Thu lỗi phù hợp | `error` ghi nhận rồi cho tiếp tục; `fatalError` có thể dừng | Kiểm tra bộ thu lỗi sau lượt validate; không chỉ dựa vào không có ngoại lệ |

Không coi mọi `warning` là lỗi làm tài liệu không hợp lệ nếu đặc tả không yêu cầu như vậy. Ngược lại, đừng dùng `DefaultHandler` với phương thức `error` rỗng rồi báo “accepted” chỉ vì không có ngoại lệ. Phải chọn và viết rõ chính sách.

## 6. Chương trình hoàn chỉnh: một Schema, nhiều Validator

Ví dụ kiểm tra các đơn hàng có `sku` và `quantity`; XSD yêu cầu quantity là số nguyên dương. Ba tài liệu được gửi vào pool hai worker, nhưng mỗi lời gọi tạo validator và handler riêng.

Lưu thành `ValidatorPerCallDemo.java`, chạy với JDK 17 trở lên:

```java
import java.io.IOException;
import java.io.StringReader;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import javax.xml.XMLConstants;
import javax.xml.transform.stream.StreamSource;
import javax.xml.validation.Schema;
import javax.xml.validation.SchemaFactory;
import javax.xml.validation.Validator;
import org.xml.sax.ErrorHandler;
import org.xml.sax.SAXException;
import org.xml.sax.SAXParseException;

public class ValidatorPerCallDemo {
    private static final String XSD = """
            <xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
                <xs:element name="order">
                    <xs:complexType>
                        <xs:sequence>
                            <xs:element name="sku" type="xs:string"/>
                            <xs:element name="quantity" type="xs:positiveInteger"/>
                        </xs:sequence>
                    </xs:complexType>
                </xs:element>
            </xs:schema>
            """;

    private static final class Issues implements ErrorHandler {
        private boolean invalid;

        @Override
        public void warning(SAXParseException exception) {
            // This demo does not reject a document for warnings alone.
        }

        @Override
        public void error(SAXParseException exception) {
            invalid = true;
        }

        @Override
        public void fatalError(SAXParseException exception) throws SAXException {
            invalid = true;
            throw exception;
        }
    }

    private static final class OrderChecker {
        private final Schema schema;

        OrderChecker(Schema schema) {
            this.schema = schema;
        }

        boolean accepts(String xml) throws SAXException, IOException {
            Validator validator = schema.newValidator();
            validator.setFeature(XMLConstants.FEATURE_SECURE_PROCESSING, true);
            validator.setProperty(XMLConstants.ACCESS_EXTERNAL_DTD, "");
            validator.setProperty(XMLConstants.ACCESS_EXTERNAL_SCHEMA, "");
            Issues issues = new Issues();
            validator.setErrorHandler(issues);

            try (StringReader reader = new StringReader(xml)) {
                try {
                    validator.validate(new StreamSource(reader));
                } catch (SAXException rejectedInput) {
                    return false;
                }
            }
            return !issues.invalid;
        }
    }

    private static Schema compileSchema() throws SAXException {
        SchemaFactory factory = SchemaFactory.newDefaultInstance();
        factory.setFeature(XMLConstants.FEATURE_SECURE_PROCESSING, true);
        factory.setProperty(XMLConstants.ACCESS_EXTERNAL_DTD, "");
        factory.setProperty(XMLConstants.ACCESS_EXTERNAL_SCHEMA, "");
        try (StringReader reader = new StringReader(XSD)) {
            return factory.newSchema(new StreamSource(reader));
        }
    }

    public static void main(String[] args) throws Exception {
        OrderChecker checker = new OrderChecker(compileSchema());
        List<String> documents = List.of(
                "<order><sku>A</sku><quantity>2</quantity></order>",
                "<order><sku>B</sku><quantity>0</quantity></order>",
                "<order><sku>C</sku><quantity>3</quantity></order>");

        ExecutorService pool = Executors.newFixedThreadPool(2);
        try {
            List<Future<Boolean>> results = List.of(
                    pool.submit(() -> checker.accepts(documents.get(0))),
                    pool.submit(() -> checker.accepts(documents.get(1))),
                    pool.submit(() -> checker.accepts(documents.get(2))));
            for (int i = 0; i < results.size(); i++) {
                boolean accepted = results.get(i).get(10, TimeUnit.SECONDS);
                System.out.println("order-" + (i + 1) + "="
                        + (accepted ? "accepted" : "rejected"));
            }
            System.out.println("later-valid=" + checker.accepts(documents.get(0)));
        } finally {
            pool.shutdownNow();
        }
    }
}
```

Biên dịch và chạy:

```shell
javac ValidatorPerCallDemo.java
java ValidatorPerCallDemo
```

Stdout khi các tác vụ hoàn thành trong thời hạn thí nghiệm:

```text
order-1=accepted
order-2=rejected
order-3=accepted
later-valid=true
```

### Đọc theo vòng đời đối tượng

`compileSchema()` chỉ chạy một lần trong `main`. Factory và reader của XSD thuộc giai đoạn chuẩn bị đó; dịch vụ chỉ giữ `Schema` đã tạo xong. Hai worker cùng gọi checker nhưng không cùng giữ một validator.

Mỗi lời gọi `accepts` có `Validator`, `Issues` và `StringReader` riêng. Đơn thứ hai có quantity bằng `0`, không phù hợp `xs:positiveInteger`. Handler đặt cờ `invalid`; kể cả nếu validator báo lỗi không nghiêm trọng rồi trở về bình thường, kết quả vẫn là rejected.

Đơn thứ ba và lượt gọi sau vẫn được nhận. Chúng không thừa hưởng cờ lỗi của đơn thứ hai vì không dùng chung handler. Nếu lỗi parse nghiêm trọng làm `fatalError` được gọi, handler đánh dấu rồi ném ngoại lệ; đường validate bắt lỗi đầu vào ấy và trả false.

Luồng chính đọc từng Future theo thứ tự gửi để giữ stdout dễ kiểm tra. Điều này không ép worker chạy theo cùng thứ tự; thời điểm thực thi có thể xen kẽ. Chương trình minh họa một thiết kế có quyền sở hữu đúng, không dùng một phép thử không lỗi để suy ra validator dùng chung được phép chạy đồng thời.

### Vì sao cấu hình nằm ngoài khối catch của validate?

Các lệnh `setFeature`, `setProperty` được thực hiện trước khối bắt `SAXException` của lần validate. Vì vậy, lỗi cấu hình thuộc tính không được hỗ trợ không bị đổi thành “tài liệu bị rejected”. Nó truyền ra cho bên điều phối qua hợp đồng ngoại lệ của phương thức/Future.

`IOException` cũng truyền ra; ví dụ không coi lỗi đọc nguồn là một vi phạm quy tắc số lượng đơn hàng. Helper trả boolean để giữ chương trình tập trung vào vòng đời validator; trong dịch vụ thật, nên có kết quả phân loại rõ lỗi dữ liệu, lỗi nguồn, chính sách từ chối và lỗi cấu hình.

### Cấu hình nguồn ngoài không thay thế mọi giới hạn

Ví dụ dùng các chuỗi XML/XSD nhỏ, có kiểm soát và không tham chiếu nguồn ngoài. FSP cùng `ACCESS_EXTERNAL_DTD`/`ACCESS_EXTERNAL_SCHEMA` rỗng thể hiện chính sách không truy cập nguồn ngoài. Các thiết lập được áp ở bước biên dịch schema và bước kiểm tra tài liệu; không chỉ đặt ở một nơi rồi quên giai đoạn còn lại.

Với nguồn không tin cậy, còn phải giới hạn byte, thời gian đọc, cấu trúc và mức đồng thời. Nếu cần chính sách riêng như từ chối DOCTYPE ngay, chuẩn bị parser/source phù hợp với chính sách đó; tạo validator mới không tự cung cấp một ngân sách tài nguyên đầy đủ. [Hướng dẫn JAXP Security](https://docs.oracle.com/en/java/javase/25/security/java-api-xml-processing-jaxp-security-guide.html)

## 7. Handler và resolver: tránh nhầm phạm vi cấu hình

Handler phục vụ **biên dịch schema** và handler phục vụ **kiểm tra XML** thuộc các giai đoạn khác nhau. Một lỗi trong XSD không cùng ý nghĩa với XML vi phạm XSD. Gắn handler rõ ràng ở từng nơi cần quan sát, không dựa vào một bộ thu lỗi của factory rồi kỳ vọng nó tự trở thành bộ thu lỗi theo yêu cầu cho mọi validator.

Resolver cũng có hai câu hỏi: XSD import/include được tìm ở đâu khi biên dịch, và tài nguyên nào được phép phân giải trong lúc kiểm tra. Nếu ứng dụng cho phép catalog hoặc nguồn cục bộ, cấu hình rõ và giữ giới hạn. Đừng đưa URL do người gửi XML tự chọn vào một resolver mở mọi nguồn chỉ vì muốn “tự động tìm schema”.

Callback không nên gọi lại `validate` trên chính validator đang báo lỗi hoặc đang phân giải. Đó là tái nhập dù chỉ có một luồng. Nếu cần kiểm tra một tài liệu khác từ một bước xử lý, tổ chức nó như một lượt độc lập với validator/handler/nguồn riêng và kiểm soát độ lồng theo thiết kế ứng dụng.

## 8. Tạo mới mỗi lượt có phải yêu cầu tuyệt đối không?

Hợp đồng cấm dùng đồng thời và tái nhập; nó không cấm mọi hình thức dùng lại tuần tự. `Validator.reset()` tồn tại để khôi phục cấu hình ban đầu và hỗ trợ tái sử dụng. Tuy nhiên, tạo mới từ Schema thường là mặc định dễ quản lý vì ít nguy cơ mang trạng thái/callback của lượt trước sang lượt sau.

Khi có bằng chứng chi phí tạo validator đáng kể với tải thực tế, có thể cân nhắc dùng lại theo một chủ sở hữu. Khi đó phải bảo đảm:

- Không có lượt validate khác hoạt động trên cùng instance.
- Không có đường gọi ngoài lớp bao vượt qua cơ chế bảo vệ.
- Reset/dọn trạng thái và thiết lập lại chính sách cần thiết trước lượt tiếp theo.
- Xóa trạng thái thu lỗi của riêng lượt, không để dữ liệu trước còn ảnh hưởng kết quả.
- Không trả một validator đang được dùng hoặc đã được dùng sai vào pool cho người khác.

`reset()` đưa validator về trạng thái như khi mới được `Schema.newValidator()` tạo, không bảo đảm các đối tượng handler/resolver giữ đúng danh tính tham chiếu mà ứng dụng đã gắn trước đó. Sau reset, áp lại những cấu hình ứng dụng cần cho lượt mới; đừng giả định handler thu lỗi của mình vẫn còn. [Validator.reset](https://docs.oracle.com/en/java/javase/25/docs/api/java.xml/javax/xml/validation/Validator.html#reset())

Cũng không gọi reset trong khi validate chưa kết thúc như một cách “hủy” lượt đang chạy. Reset là thao tác quản lý vòng đời, không phải tín hiệu đồng bộ hoặc lệnh dừng xử lý.

## 9. Khóa, ThreadLocal và pool thay đổi trách nhiệm ra sao?

| Cách quản lý | Điều cần bảo đảm | Hạn chế cần cân nhắc |
| --- | --- | --- |
| Tạo mới mỗi lời gọi | Mỗi lượt có bộ xử lý/callback/nguồn riêng | Có chi phí tạo đối tượng |
| Một validator dùng tuần tự qua khóa | Bảo vệ toàn bộ cấu hình–validate–dọn, không để tham chiếu thoát | Tuần tự hóa các lượt; khóa tái nhập không tự ngăn callback gọi lồng |
| ThreadLocal | Mỗi luồng sở hữu instance và dọn dữ liệu giữa tác vụ | Một worker xử lý nhiều tác vụ; tái nhập cùng luồng vẫn là nguy cơ |
| Pool validator | Mỗi lần mượn độc quyền, trả đúng sau kết thúc và dọn cấu hình | Thêm hàng chờ, giới hạn dung lượng, xử lý instance lỗi và vòng đời |

Không cần chọn cơ chế phức tạp trước khi đo. Một ThreadLocal hoặc pool được thêm sớm có thể biến lỗi vòng đời đơn giản thành rò trạng thái giữa yêu cầu. Nếu phải tạo/mượn rồi dọn rất nhiều callback theo yêu cầu, tạo validator mới đôi khi làm hợp đồng rõ hơn.

Với khóa, không chỉ bọc riêng `validate` nếu các setter và bộ thu lỗi được đổi ngoài khóa. A có thể cài handler A, B cài handler B, rồi A kiểm tra với handler của B. Cần giữ cả đơn vị thao tác trong một phạm vi sở hữu.

## 10. Dùng đúng Source và trách nhiệm đóng nguồn

`StreamSource` bọc reader/stream không tự biến dữ liệu thành có thể đọc lại vô hạn. Sau một lượt, con trỏ có thể đã ở cuối nguồn. Kiểm tra lại cùng nội dung cần mở reader/stream mới hoặc dữ liệu có thể tạo nguồn mới.

Nếu dùng `DOMSource`, cần quản lý cây DOM: validator riêng không tự bảo vệ DOM bị nhiều bên đọc/sửa không đúng hợp đồng. Nếu dùng `SAXSource` với XMLReader do ứng dụng cấp, parser và handler của nó cũng cần phạm vi riêng phù hợp. Các loại `Source`/`Result` được hỗ trợ và tương thích được API quy định; không ghép tùy ý các loại rồi coi lỗi đó là lỗi dữ liệu XSD.

Mẫu trong bài dùng `try-with-resources` ở nơi mở reader để việc đóng không phụ thuộc đường thành công hay lỗi. Validator không triển khai `AutoCloseable`; không có bước `validator.close()` cần thêm. Giải phóng tham chiếu theo vòng đời không đồng nghĩa phải gọi một phương thức đóng không tồn tại.

Khi chỉ cần kiểm tra, `validate(source)` không yêu cầu một Result. Nếu muốn kết quả có bổ sung thông tin từ quá trình kiểm tra, cần hiểu hành vi Source/Result và tác động lên cây thay vì giả định validate luôn là thao tác chỉ đọc mọi kiểu nguồn. [Validator và ma trận Source/Result](https://docs.oracle.com/en/java/javase/25/docs/api/java.xml/javax/xml/validation/Validator.html)

## 11. Thiết kế kết quả và kiểm thử theo từng lượt

Kết quả nên gắn với định danh tài liệu/lượt xử lý, không chỉ tên luồng vì một worker có thể kiểm tra nhiều tài liệu. Nếu thu nhiều lỗi, lưu mức độ, vị trí nguồn và thông báo cần thiết với giới hạn số lượng/kích thước phù hợp. Không để một đầu vào tạo danh sách lỗi hoặc log không giới hạn.

Phân loại ít nhất những trường hợp có ý nghĩa với bên gọi:

- Kiểm tra hoàn tất và không có lỗi theo chính sách: chấp nhận.
- XML sai cấu trúc hoặc vi phạm XSD: từ chối dữ liệu, có thông tin chẩn đoán phù hợp.
- Nguồn đọc thất bại hoặc tài nguyên cần thiết không có: lỗi xử lý/nguồn theo hợp đồng, không tự gọi là lỗi trường quantity.
- Schema/cấu hình hệ thống không hợp lệ: lỗi chuẩn bị hoặc cấu hình dịch vụ.

Các ca kiểm thử hữu ích gồm:

| Ca | Điều muốn kiểm chứng |
| --- | --- |
| Hợp lệ → không hợp lệ → hợp lệ | Lỗi lượt trước không làm bẩn lượt sau |
| Hai tài liệu song song, mỗi bên có lỗi khác | Handler/kết quả không lẫn dữ liệu |
| Handler thu lỗi không ném ở error | Không chấp nhận sai chỉ vì validate trả bình thường |
| XML sai cú pháp nghiêm trọng | Kết thúc lượt và dọn nguồn đúng |
| Thuộc tính cấu hình bắt buộc không hỗ trợ | Không nuốt lỗi rồi chạy dưới giả định chính sách đã áp |
| Tái nhập qua callback nếu ứng dụng có đường đó | Được ngăn hoặc tách lượt theo thiết kế, không dùng lại cùng validator |

Không cần tạo một phép thử dựa vào lỗi cạnh tranh ngẫu nhiên để quyết định liệu được chia sẻ validator hay không. Quy tắc API đã rõ; kiểm thử xác nhận thiết kế ứng dụng tuân thủ quy tắc và trả đúng kết quả của từng tài liệu.

## 12. Tự kiểm tra

1. **Một Schema có thể dùng để tạo Validator cho nhiều luồng không?** Có. Schema được thiết kế để dùng chung; mỗi lượt có validator riêng là mô hình phù hợp.
2. **Tại sao không giữ một static final Validator giống Schema?** Validator không có hợp đồng an toàn luồng/tái nhập như Schema; final không thay đổi hợp đồng đối tượng.
3. **Không có SAXException có luôn nghĩa XML hợp lệ không?** Không nếu handler đã nhận lỗi mà không ném. Cần xem kết quả bộ thu lỗi theo chính sách.
4. **Có cần biên dịch XSD lại cho mỗi XML không?** Không khi cùng bộ quy tắc đã chuẩn bị phù hợp; dùng lại Schema để tạo bộ kiểm tra mới.
5. **reset có nghĩa giữ nguyên mọi handler ứng dụng đã gắn không?** Không nên dựa vào điều đó. Nó khôi phục trạng thái ban đầu; thiết lập lại cấu hình cần cho lượt mới.
6. **Hai validator riêng có cho phép cùng đọc một InputStream hay sửa một DOM tùy ý không?** Không. Nguồn đầu vào và các đối tượng liên quan vẫn có quy tắc sở hữu/truy cập riêng.
