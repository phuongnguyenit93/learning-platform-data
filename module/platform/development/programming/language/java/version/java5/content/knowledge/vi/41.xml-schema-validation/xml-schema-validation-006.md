# ErrorHandler và phân biệt cảnh báo, lỗi, lỗi nghiêm trọng

## 1. ErrorHandler nằm ở đâu trong việc kiểm tra XML?

Khi một tài liệu được kiểm tra theo XML Schema, bộ xử lý có thể phát hiện vấn đề rồi gửi thông tin cho ứng dụng qua `org.xml.sax.ErrorHandler`. Dù thuộc gói SAX, interface này cũng được JAXP `Validator` sử dụng. Nó cho ứng dụng quyết định cách ghi nhận và khi nào dừng lượt xử lý.

Điểm dễ nhầm là **khả năng tiếp tục kiểm tra** khác **tính hợp lệ của tài liệu**. Bộ kiểm tra có thể nhận ra một giá trị không phù hợp XSD, vẫn đọc tiếp để tìm lỗi khác, rồi trở về bình thường nếu handler không ném ngoại lệ. Tài liệu vẫn không hợp lệ theo bộ quy tắc đó.

Ba callback phản ánh ba mức thông báo:

```text
Bộ xử lý phát hiện vấn đề
    → warning(exception): cảnh báo
    → error(exception): lỗi có thể tiếp tục xử lý
    → fatalError(exception): lỗi nghiêm trọng, không thể tin vào xử lý bình thường tiếp
```

Chúng là các phương thức khác nhau của cùng interface, không phải ba lớp ngoại lệ riêng. Bài dùng API JAXP/SAX còn áp dụng trên Java hiện hành và ví dụ Java 17 trở lên. [ErrorHandler](https://docs.oracle.com/en/java/javase/25/docs/api/java.xml/org/xml/sax/ErrorHandler.html)

## 2. Hiểu đúng từng mức

| Callback | Ý nghĩa thực hành | Chính sách thường dùng |
| --- | --- | --- |
| `warning(SAXParseException e)` | Điều kiện đáng lưu ý, chưa phải một lỗi làm tài liệu không hợp lệ theo cách phân loại đó | Ghi cảnh báo, tiếp tục; có thể có quy tắc ứng dụng nghiêm hơn |
| `error(SAXParseException e)` | Vi phạm được bộ xử lý báo là lỗi nhưng vẫn có thể tiếp tục để kiểm tra thêm | Đánh dấu không hợp lệ; ném ngay hoặc tiếp tục thu lỗi theo chính sách |
| `fatalError(SAXParseException e)` | Lỗi khiến không thể tiếp tục xử lý bình thường một cách đáng tin | Ghi nhận và dừng lượt, thường bằng cách ném lại ngoại lệ |

Ví dụ quantity bằng `0` trong khi XSD yêu cầu `xs:positiveInteger`: XML vẫn có thể đúng cú pháp, nhưng giá trị không thỏa bộ quy tắc. Đây là kiểu lỗi kiểm tra XSD mà bộ xử lý có thể báo qua `error`.

Tài liệu thiếu thẻ đóng hoặc có cấu trúc XML sai nghiêm trọng không còn là một cây hợp lệ để tiếp tục suy luận như bình thường; parser có thể báo `fatalError`. Không được đọc “fatal” thành JVM chắc chắn bị dừng: đó là mức nghiêm trọng của lượt xử lý XML, không phải lệnh thoát toàn bộ tiến trình.

Cảnh báo cụ thể phát sinh thế nào còn phụ thuộc bộ xử lý, loại tài liệu và cấu hình. Không bịa một XML “luôn sinh warning trên mọi JDK” nếu hợp đồng không bảo đảm điều đó. Khi kiểm tra chính sách warning của handler, có thể gọi callback trực tiếp trong một phép thử và ghi rõ đó là thông báo mô phỏng.

## 3. Recoverable không có nghĩa đã được sửa

Từ “có thể tiếp tục” trong `error` nói rằng bộ xử lý có thể còn thu thập thông tin, không có nghĩa nó tự sửa XML hoặc làm tài liệu trở thành hợp lệ. Nếu nhập sai số lượng, việc handler chỉ in log rồi trả về không đổi giá trị ấy thành số hợp lệ.

Có hai lựa chọn hợp lý tùy mục tiêu:

- **Dừng sớm:** ngay lỗi đầu tiên, đánh dấu rồi ném `SAXException` để không làm công việc thừa.
- **Thu nhiều lỗi:** ghi lỗi, cho xử lý tiếp ở mức có thể tiếp tục, rồi từ chối tài liệu dựa trên toàn bộ báo cáo; đặt giới hạn số lượng/kích thước thông báo.

Với `fatalError`, ứng dụng phải coi phần xử lý bình thường còn lại không đáng tin. Không dùng việc handler đã trở về để tiếp tục nhập dữ liệu nghiệp vụ từ một cây/sự kiện không còn bảo đảm đúng. Cũng không kỳ vọng sẽ có đầy đủ các callback kết thúc như khi tài liệu hợp lệ. [Hợp đồng fatalError](https://docs.oracle.com/en/java/javase/25/docs/api/java.xml/org/xml/sax/ErrorHandler.html#fatalError(org.xml.sax.SAXParseException))

## 4. Callback và ngoại lệ: hai kênh phải được kết hợp

Handler nhận một `SAXParseException`, nhưng có thể chỉ đọc thông tin, ghi nhận rồi trả về. Việc callback nhận đối tượng ngoại lệ không đồng nghĩa ngoại lệ đó đã được ném lên stack của bên gọi validate.

```text
Tài liệu vi phạm XSD
    → validator gọi handler.error(e)
        → handler ghi lỗi và trở về
            → validator có thể tiếp tục
            → validate có thể trở về bình thường
    → ứng dụng vẫn phải xem báo cáo lỗi và từ chối
```

Nếu handler ném `SAXException`, lượt validate có thể bị ngắt và bên gọi nhận ngoại lệ. Với `Validator`, lỗi nghiêm trọng cũng làm validate không hoàn thành bình thường theo hợp đồng, ngay cả khi handler không tự ném. Khi thiết kế handler dừng ở fatal, ném lại chính ngoại lệ vừa nhận giúp giữ vị trí/nguyên nhân. [Validator.validate và ErrorHandler](https://docs.oracle.com/en/java/javase/25/docs/api/java.xml/javax/xml/validation/Validator.html)

Một công thức quyết định rõ ràng cho chính sách “warning được phép, error/fatal bị từ chối” là:

```text
accepted = lượt kiểm tra hoàn tất bình thường
           VÀ không có ERROR
           VÀ không có FATAL
```

Nếu hệ thống muốn từ chối cả warning, hãy ghi rõ đó là quy tắc chấp nhận nghiêm hơn của ứng dụng. Đừng sửa nhãn warning thành fatal chỉ để ép kết quả mà không giải thích ý nghĩa.

## 5. SAXParseException chứa thông tin gì?

Cả ba callback nhận cùng một kiểu `SAXParseException`. Cần giữ mức độ từ callback đã nhận, không suy mức độ bằng tên lớp ngoại lệ hoặc bằng cách tìm một chữ trong thông báo.

| Thông tin | Cách lấy | Lưu ý |
| --- | --- | --- |
| Thông báo | `getMessage()` | Nội dung có thể khác theo provider/JDK; không dùng như giao thức duy nhất |
| Định danh nguồn | `getSystemId()`, `getPublicId()` | Có thể không có; URI/đường dẫn có thể là thông tin nội bộ |
| Dòng | `getLineNumber()` | Có thể là `-1` khi không có vị trí |
| Cột | `getColumnNumber()` | Có thể là `-1`; vị trí được báo không luôn là chính ký tự bắt đầu gây lỗi |
| Nguyên nhân lồng | `getCause()` khi có | Hữu ích cho chẩn đoán lỗi được bọc |

Một lần `error` thường chỉ cho một điểm phát hiện cụ thể; nó không tự cung cấp đường dẫn nghiệp vụ như “đơn hàng thứ 27” nếu nguồn/ứng dụng chưa gắn thông tin ấy. Nên lưu định danh tài liệu/lượt xử lý cạnh chẩn đoán. [SAXParseException](https://docs.oracle.com/en/java/javase/25/docs/api/java.xml/org/xml/sax/SAXParseException.html)

Không phân loại mức độ bằng cách kiểm tra `line > 0`: warning, error và fatal đều có thể có hoặc thiếu vị trí. Nếu cần hiển thị, biểu diễn “không xác định” thay vì làm người đọc mở dòng -1.

## 6. Chương trình hoàn chỉnh: thu lỗi có giới hạn

Ví dụ dùng XSD có một phần tử quantity kiểu số nguyên dương. Handler giữ tối đa 16 chẩn đoán, cắt thông báo được giữ về mức nhỏ trong mẫu, cho tiếp tục sau `error` và dừng ở `fatalError`.

Lưu thành `SchemaErrorLevelsDemo.java`:

```java
import java.io.IOException;
import java.io.StringReader;
import java.util.ArrayList;
import java.util.List;
import javax.xml.XMLConstants;
import javax.xml.transform.stream.StreamSource;
import javax.xml.validation.Schema;
import javax.xml.validation.SchemaFactory;
import javax.xml.validation.Validator;
import org.xml.sax.ErrorHandler;
import org.xml.sax.SAXException;
import org.xml.sax.SAXParseException;

public class SchemaErrorLevelsDemo {
    enum Severity { WARNING, ERROR, FATAL }

    record Diagnostic(Severity severity, String systemId,
                      int line, int column, String message) {}

    record Report(boolean returnedNormally, List<Diagnostic> diagnostics) {
        boolean has(Severity severity) {
            return diagnostics.stream().anyMatch(
                    diagnostic -> diagnostic.severity() == severity);
        }

        boolean accepted() {
            return returnedNormally
                    && !has(Severity.ERROR) && !has(Severity.FATAL);
        }
    }

    static final class CollectingHandler implements ErrorHandler {
        private static final int MAX_DIAGNOSTICS = 16;
        private final List<Diagnostic> diagnostics = new ArrayList<>();

        private void add(Severity severity, SAXParseException exception)
                throws SAXException {
            if (diagnostics.size() >= MAX_DIAGNOSTICS) {
                throw new SAXException("Diagnostic limit exceeded");
            }
            String message = exception.getMessage();
            if (message != null && message.length() > 256) {
                message = message.substring(0, 256);
            }
            diagnostics.add(new Diagnostic(severity, exception.getSystemId(),
                    exception.getLineNumber(), exception.getColumnNumber(),
                    message));
        }

        @Override
        public void warning(SAXParseException exception) throws SAXException {
            add(Severity.WARNING, exception);
        }

        @Override
        public void error(SAXParseException exception) throws SAXException {
            add(Severity.ERROR, exception);
        }

        @Override
        public void fatalError(SAXParseException exception) throws SAXException {
            add(Severity.FATAL, exception);
            throw exception;
        }

        List<Diagnostic> snapshot() {
            return List.copyOf(diagnostics);
        }
    }

    private static Schema schema() throws SAXException {
        String xsd = """
                <xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
                    <xs:element name="quantity" type="xs:positiveInteger"/>
                </xs:schema>
                """;
        SchemaFactory factory = SchemaFactory.newDefaultInstance();
        factory.setFeature(XMLConstants.FEATURE_SECURE_PROCESSING, true);
        factory.setProperty(XMLConstants.ACCESS_EXTERNAL_DTD, "");
        factory.setProperty(XMLConstants.ACCESS_EXTERNAL_SCHEMA, "");
        try (StringReader reader = new StringReader(xsd)) {
            return factory.newSchema(new StreamSource(reader));
        }
    }

    private static Report check(Schema schema, String id, String xml)
            throws SAXException, IOException {
        Validator validator = schema.newValidator();
        validator.setFeature(XMLConstants.FEATURE_SECURE_PROCESSING, true);
        validator.setProperty(XMLConstants.ACCESS_EXTERNAL_DTD, "");
        validator.setProperty(XMLConstants.ACCESS_EXTERNAL_SCHEMA, "");
        CollectingHandler handler = new CollectingHandler();
        validator.setErrorHandler(handler);

        boolean returnedNormally = false;
        try (StringReader reader = new StringReader(xml)) {
            StreamSource source = new StreamSource(reader);
            source.setSystemId("urn:sample:" + id);
            try {
                validator.validate(source);
                returnedNormally = true;
            } catch (SAXException stopped) {
                // The callback already recorded its diagnostic when available.
                // Do not record the same exception a second time here.
            }
        }
        return new Report(returnedNormally, handler.snapshot());
    }

    private static void print(String label, Report report) {
        System.out.println(label + ": returned=" + report.returnedNormally()
                + " accepted=" + report.accepted()
                + " error=" + report.has(Severity.ERROR)
                + " fatal=" + report.has(Severity.FATAL));
    }

    public static void main(String[] args) throws Exception {
        Schema schema = schema();
        print("valid", check(schema, "valid", "<quantity>2</quantity>"));
        print("invalid", check(schema, "invalid", "<quantity>0</quantity>"));
        print("malformed", check(schema, "malformed", "<quantity>2"));

        // Test our warning policy directly, not a warning generated by XML.
        CollectingHandler warningPolicy = new CollectingHandler();
        warningPolicy.warning(new SAXParseException(
                "Synthetic warning", null, "urn:sample:policy-test", 1, 1));
        System.out.println("warning-policy: count="
                + warningPolicy.snapshot().size()
                + " level=" + warningPolicy.snapshot().get(0).severity());
    }
}
```

Biên dịch/chạy bằng JDK 17 trở lên:

```shell
javac SchemaErrorLevelsDemo.java
java SchemaErrorLevelsDemo
```

Stdout đã kiểm tra trên JDK 24:

```text
valid: returned=true accepted=true error=false fatal=false
invalid: returned=true accepted=false error=true fatal=false
malformed: returned=false accepted=false error=false fatal=true
warning-policy: count=1 level=WARNING
```

### Tài liệu hợp lệ

`<quantity>2</quantity>` đúng cú pháp và thỏa kiểu số nguyên dương. Lượt validate hoàn tất, handler không ghi error/fatal, nên `accepted()` là true.

### Tài liệu sai XSD nhưng parser có thể đọc tiếp

`<quantity>0</quantity>` có cấu trúc XML đúng nhưng giá trị không phù hợp `xs:positiveInteger`. `error` ghi chẩn đoán rồi không ném. Trên môi trường thực nghiệm, validate trở về bình thường, nhưng `accepted()` vẫn false vì báo cáo chứa ERROR.

Ví dụ không in tổng số lỗi của tài liệu này: một giá trị sai có thể dẫn đến nhiều chẩn đoán liên quan và số/thông báo chi tiết có thể thay đổi theo bộ xử lý. Mục tiêu kiểm chứng là mức lỗi đã được ghi và tài liệu không được chấp nhận, không phải học thuộc số dòng log của provider.

### Tài liệu không đóng thẻ

`<quantity>2` thiếu thẻ đóng. Handler nhận FATAL, ghi rồi ném lại. Lượt không hoàn tất bình thường nên `returned=false` và tài liệu bị từ chối. Chương trình không cố tiếp tục lấy dữ liệu từ lượt parse đã lỗi nghiêm trọng.

### Phép thử warning là mô phỏng chính sách

Dòng cuối **không** có nghĩa một trong ba XML đã sinh cảnh báo. Chương trình tạo `SAXParseException` nhỏ rồi gọi `warning()` trực tiếp để xác nhận handler lưu mức WARNING. Nó tách việc kiểm tra chính sách callback khỏi hành vi phát cảnh báo tùy thuộc parser.

Phép thử trực tiếp ấy không phải một lượt validation của tài liệu. Vì thế chương trình chỉ in số thông báo và nhãn mức độ, không tuyên bố rằng một XML đã được validator xác nhận hợp lệ từ callback mô phỏng.

## 7. Vì sao catch không ghi lại cùng lỗi lần nữa?

Khi `fatalError` ghi ngoại lệ rồi ném chính nó, `check` nhận lại ngoại lệ từ validate. Nếu catch lại thêm cùng lỗi vào danh sách, một vấn đề có thể xuất hiện hai lần và làm số liệu sai.

Mã chỉ đổi `returnedNormally` thành false bằng cách không đặt nó thành true; thông tin callback đã được ghi một lần. Với một báo cáo sản phẩm đầy đủ, có thể giữ thêm trạng thái “bị dừng”, loại nguyên nhân dừng và lỗi không có thông tin vị trí, nhưng cần tránh ghi trùng chẩn đoán đã được callback tiếp nhận.

Giới hạn 16 chẩn đoán có thể chủ động dừng quá trình thu thập bằng `SAXException`. Khi đó, báo cáo không được accepted vì lượt chưa hoàn tất, kể cả nếu các thông báo đã giữ mới chỉ là warning. Không được diễn giải báo cáo một phần là “không có ERROR nên hợp lệ”. Đây là lý do công thức chấp nhận cần cả trạng thái hoàn tất.

Các setter cấu hình nằm ngoài khối catch chỉ bao quanh validate. Nếu provider không hỗ trợ một thuộc tính bắt buộc, lỗi cấu hình truyền ra thay vì bị đổi thành lỗi dữ liệu. `IOException` cũng được truyền theo hợp đồng để tầng điều phối phân biệt thất bại đọc nguồn với vi phạm XSD.

Không bắt `Throwable` để ép mọi sự cố thành một danh sách lỗi XML. Lỗi lập trình trong handler, lỗi cấu hình hoặc lỗi hệ thống không nên tự mang nhãn “quantity không hợp lệ”.

## 8. Chọn dừng sớm khi không cần thu thêm lỗi

Đây là đoạn handler minh họa, đặt trong một phương thức có các import SAX tương ứng; không phải chương trình độc lập:

```java
ErrorHandler stopOnError = new ErrorHandler() {
    @Override
    public void warning(SAXParseException exception) {
        // Chính sách ở đây cho phép cảnh báo, không coi là lỗi dữ liệu.
    }

    @Override
    public void error(SAXParseException exception) throws SAXException {
        throw exception;
    }

    @Override
    public void fatalError(SAXParseException exception) throws SAXException {
        throw exception;
    }
};
validator.setErrorHandler(stopOnError);
```

Cách này phù hợp khi bên gọi chỉ cần lỗi đầu tiên. Nó không tạo báo cáo đầy đủ mọi vấn đề trong tài liệu. Nếu handler muốn ghi thông tin trước khi ném, giữ một chủ sở hữu ghi lỗi để catch ở tầng ngoài không lại coi đó là một sự cố khác.

Lựa chọn “thu lỗi” hay “dừng sớm” không đổi ý nghĩa của XML Schema. Nó đổi lượng thông tin thu thập và công việc thực hiện sau khi đã biết tài liệu bị từ chối.

## 9. DefaultHandler và handler null không có nghĩa giống nhau

`DefaultHandler` là lớp tiện ích để override các callback cần thiết. Bản hiện hành bỏ qua warning/error theo mặc định và ném ở fatalError. Do đó, cài một `new DefaultHandler()` vào Validator có thể làm các lỗi XSD không nghiêm trọng được bỏ qua ở mức ứng dụng nếu chỉ nhìn validate có ném hay không. [DefaultHandler](https://docs.oracle.com/en/java/javase/25/docs/api/java.xml/org/xml/sax/helpers/DefaultHandler.html)

Riêng `Validator`, khi handler là null, hợp đồng quy định hành vi tương đương một handler bỏ qua warning nhưng ném ở error và fatalError. Vì vậy, `validator.setErrorHandler(null)` không đồng nghĩa “tắt mọi lỗi” và cũng không giống gắn một DefaultHandler không override error. [Validator.setErrorHandler](https://docs.oracle.com/en/java/javase/25/docs/api/java.xml/javax/xml/validation/Validator.html#setErrorHandler(org.xml.sax.ErrorHandler))

Không áp quy tắc mặc định của Validator cho mọi API SAX/XML khác. Khi dùng parser, schema compiler hoặc pipeline riêng, kiểm tra đúng hợp đồng thành phần đó và gắn handler cần thiết. Nhớ tách lỗi biên dịch XSD ở `SchemaFactory` khỏi lỗi XML vi phạm XSD ở `Validator`.

## 10. Vòng đời, an toàn luồng và nguồn dữ liệu

`Validator` không an toàn luồng và không tái nhập. Một handler chứa danh sách/cờ theo tài liệu cũng nên có phạm vi riêng cho từng lượt. Dùng chung handler có một danh sách dù đã tạo nhiều validator có thể làm lỗi của tài liệu A xuất hiện trong kết quả B.

Trong ví dụ, mỗi `check` gọi `schema.newValidator()`, tạo handler và reader mới. `Schema` là bộ quy tắc dùng lại. Báo cáo trả về bản sao danh sách bất biến, tránh để các callback sau đó sửa dữ liệu mà bên gọi đang đọc.

Không gọi `validate` lồng trên cùng validator từ `error`, `warning` hoặc một resolver. Callback đang chạy là một phần của lượt validate ngoài. Nếu cần kiểm tra tài liệu khác, tổ chức lượt độc lập theo hợp đồng và kiểm soát luồng xử lý của ứng dụng.

`systemId` được đặt thành nhãn `urn:sample:...` để chẩn đoán mẫu có ngữ cảnh. Trong hệ thống thật, systemId còn có thể làm URI cơ sở cho việc phân giải tài nguyên liên quan, nên không coi nó luôn chỉ là một nhãn log vô hại. Chính sách truy cập nguồn ngoài và resolver phải được cấu hình riêng, không để handler lỗi thay nhiệm vụ đó.

Ví dụ dùng XML/XSD nhỏ do chương trình tạo. Với nguồn không tin cậy, bổ sung giới hạn byte, cấu trúc, thời gian đọc, số thông báo và mức đồng thời. Một handler thu lỗi có giới hạn chỉ giới hạn phần báo cáo ứng dụng giữ, không tự giới hạn mọi CPU/bộ nhớ mà parser đã tiêu trước callback.

## 11. Báo cáo lỗi để người dùng sửa được

Một chẩn đoán hữu ích thường gồm định danh tài liệu/lượt, mức độ, vị trí khi có và mô tả ngắn. Cần xác định đối tượng nhận: người sửa XML có thể cần vị trí và lỗi kiểu dữ liệu; log kỹ thuật có thể cần thêm nguyên nhân/provider. Không phải mọi thông tin nội bộ trong exception đều cần đưa nguyên văn ra phản hồi công khai.

Đặt giới hạn số lượng và độ dài thông báo, đồng thời cho biết báo cáo có bị dừng/cắt hay không. Tránh lưu toàn bộ XML hoặc một stack trace lặp lại cho mỗi callback vì một tài liệu sai có thể tạo nhiều vấn đề liên quan. Không dùng thông báo lỗi hiển thị làm khóa nghiệp vụ duy nhất khi provider/JDK có thể thay cách diễn đạt.

Nếu chương trình phải trả lỗi có mã ổn định, phân loại ở tầng ứng dụng bằng giai đoạn xử lý và dữ liệu đáng tin, giữ thông báo của provider như phần chẩn đoán. Cũng không khẳng định mỗi chẩn đoán ứng với một trường riêng: một lỗi gốc có thể kéo theo nhiều thông báo dây chuyền.

## 12. Ca kiểm tra và lỗi phổ biến

| Ca kiểm tra | Điều cần khẳng định |
| --- | --- |
| XML hợp lệ | Hoàn tất bình thường và không có error/fatal |
| XML đúng cú pháp nhưng sai XSD | Bị từ chối ngay cả khi handler thu lỗi không ném |
| XML sai cú pháp nghiêm trọng | Lượt không được chấp nhận; không dùng dữ liệu tiếp như bình thường |
| Gọi warning trực tiếp trong phép thử handler | Lưu đúng WARNING mà không giả mạo một lần parser thực sự sinh warning |
| Vượt giới hạn chẩn đoán | Báo cáo không được coi là kết quả validation đầy đủ |
| Hợp lệ sau một lượt lỗi | Không thừa hưởng chẩn đoán từ tài liệu trước |
| Lỗi cấu hình hoặc I/O | Không bị gán nhầm thành lỗi XSD của một trường dữ liệu |

Các lỗi thiết kế thường gặp là chỉ in log rồi quên cờ không hợp lệ, trả accepted chỉ vì không có exception, ghi trùng tại callback và catch, cho fatalError trở về rồi tiếp tục nhập dữ liệu, hoặc dùng một danh sách lỗi chung cho nhiều lượt.

## 13. Tự kiểm tra

1. **error có nghĩa dữ liệu vẫn được chấp nhận vì parser còn tiếp tục không?** Không. Nó cho phép tiếp tục xử lý để thu thêm thông tin; tài liệu đã có lỗi theo bộ kiểm tra.
2. **Có thể phân biệt warning/error/fatal bằng lớp SAXParseException không?** Không. Cả ba callback dùng cùng lớp; phải giữ mức từ callback.
3. **validate không ném nhưng handler có ERROR thì sao?** Từ chối theo chính sách của bài; không có ngoại lệ chưa đủ chứng minh hợp lệ.
4. **fatalError có nghĩa toàn JVM phải dừng không?** Không. Cần dừng và từ chối lượt xử lý XML tương ứng theo hợp đồng, không tự thoát tiến trình.
5. **Handler chỉ ghi warning rồi tự giới hạn báo cáo, làm validate dừng sớm, có được accepted không?** Không. Kiểm tra chưa hoàn tất; báo cáo một phần không chứng minh hợp lệ.
6. **Gắn DefaultHandler rỗng có giống setErrorHandler(null) trên Validator không?** Không. Hành vi error mặc định khác nhau theo các hợp đồng đã nêu.
