# SchemaFactory và lựa chọn ngôn ngữ schema

## 1. SchemaFactory giải quyết việc gì?

Một tài liệu XML có thể đúng cú pháp nhưng sai cấu trúc mà ứng dụng yêu cầu. Ví dụ:

```xml
<order>
  <quantity>0</quantity>
</order>
```

Nếu đơn hàng bắt buộc có số lượng nguyên dương, XML trên vẫn đọc được nhưng không hợp lệ theo hợp đồng ấy. Schema mô tả các ràng buộc; bộ xác thực dùng schema để kiểm tra tài liệu.

Trong API chuẩn Java, `SchemaFactory` là điểm bắt đầu: nó chọn bộ xử lý hiểu một **ngôn ngữ schema**, đọc nguồn schema rồi tạo `Schema`. Sau đó `Schema` tạo `Validator` để kiểm tra XML.

```text
URI ngôn ngữ schema
        ↓
SchemaFactory
        + nguồn schema cụ thể, chẳng hạn order.xsd
        ↓ newSchema(...)
Schema
        ↓ newValidator()
Validator
        + tài liệu XML
        ↓ validate(...)
Kết quả xác thực hoặc lỗi
```

Ba đối tượng có nhiệm vụ khác nhau:

| Đối tượng | Trách nhiệm |
|---|---|
| `SchemaFactory` | Biên dịch schema của ngôn ngữ được chọn |
| `Schema` | Giữ tập ràng buộc đã được chuẩn bị |
| `Validator` | Kiểm tra một tài liệu theo tập ràng buộc ấy |

`SchemaFactory` không tự suy ra ngôn ngữ từ đuôi tên tệp và không sinh schema từ dữ liệu XML. [Tổng quan API xác thực XML của Java](https://docs.oracle.com/en/java/javase/25/docs/api/java.xml/javax/xml/validation/package-summary.html).

Bài dùng `javax.xml.validation`, API chuẩn vẫn được cung cấp trong Java hiện hành. Mã ví dụ chạy với Java 17+.

## 2. Tham số ngôn ngữ là URI định danh, không phải đường dẫn

Cách tạo factory cho W3C XML Schema:

```java
SchemaFactory factory =
        SchemaFactory.newInstance(XMLConstants.W3C_XML_SCHEMA_NS_URI);
```

Giá trị hằng là:

```text
http://www.w3.org/2001/XMLSchema
```

Nó cho biết “cần bộ xử lý ngôn ngữ W3C XML Schema”. Lời gọi này không có nghĩa “tải tệp schema ở địa chỉ đó”.

Không truyền những giá trị sau thay cho ngôn ngữ:

- `"order.xsd"`: tên nguồn schema, không phải định danh ngôn ngữ.
- `"XSD"`: tên viết tắt không phải giá trị URI chuẩn.
- `"https://www.w3.org/2001/XMLSchema"`: chuỗi khác với URI chuẩn, không tự tương đương chỉ vì chuyển từ HTTP sang HTTPS.
- `"urn:example:orders"`: có thể là namespace nghiệp vụ của dữ liệu, không phải ngôn ngữ XSD.

Dùng hằng `XMLConstants.W3C_XML_SCHEMA_NS_URI` giúp tránh lỗi gõ sai. Sau khi đã có factory, nguồn `order.xsd` được truyền vào `newSchema(...)`.

### Ba loại thông tin thường bị nhầm

| Thông tin | Ví dụ | Ý nghĩa |
|---|---|---|
| Ngôn ngữ schema | `http://www.w3.org/2001/XMLSchema` | Quy tắc mà bộ biên dịch schema cần hiểu |
| Namespace nghiệp vụ | `urn:example:orders` | Định danh các phần tử/kiểu trong miền dữ liệu |
| Vị trí nguồn schema | `order.xsd` hoặc tài nguyên đã kiểm soát | Nơi chứa schema cụ thể |

Trong XSD, tiền tố `xs` thường ánh xạ đến namespace của ngôn ngữ schema. Tiền tố này là cách viết; `xs:schema` và `xsd:schema` cùng biểu diễn một tên nếu cả hai được ánh xạ về cùng URI. Nó không phải một tên factory Java khác.

## 3. Ngôn ngữ nào được bảo đảm hỗ trợ?

API yêu cầu bộ thực thi tuân thủ hỗ trợ **W3C XML Schema 1.0**. Không suy ra rằng mọi ngôn ngữ có hằng trong `XMLConstants` đều có provider được cài sẵn.

| Nhu cầu | Điều cần biết |
|---|---|
| XSD 1.0 | Là mức hỗ trợ bắt buộc của API |
| RELAX NG | Có định danh chuẩn `XMLConstants.RELAXNG_NS_URI`, nhưng cần provider hỗ trợ thực tế |
| XSD 1.1 | Không được bảo đảm chỉ từ việc JAXP hỗ trợ XSD 1.0 |
| DTD | Không nên coi là một lựa chọn thay thế tương đương qua SchemaFactory; DTD gắn với quá trình phân tích XML |
| Ngôn ngữ khác | Cần định danh và bộ thực thi tương ứng |

Một hằng là định danh, không phải gói triển khai. Nếu không có bộ thực thi cho ngôn ngữ được yêu cầu, `newInstance(language)` báo `IllegalArgumentException`; tham số ngôn ngữ `null` gây `NullPointerException`. [Hỗ trợ ngôn ngữ và hợp đồng SchemaFactory](https://docs.oracle.com/en/java/javase/25/docs/api/java.xml/javax/xml/validation/SchemaFactory.html).

### XSD 1.1 không được chọn bằng cách đoán URI mới

XSD 1.1 là một phiên bản riêng của đặc tả XSD và vẫn dùng namespace schema `http://www.w3.org/2001/XMLSchema`. Do đó, chỉ nhìn namespace trong tệp không đủ để kết luận bộ xử lý đang dùng thực thi được mọi tính năng 1.1.

Nếu dự án cần đặc điểm riêng của XSD 1.1, cần chọn bộ thực thi có hỗ trợ được tài liệu hóa, cấu hình theo bộ đó và kiểm thử bằng schema có tính năng cần dùng. Không tự thay URI bằng đuôi `/1.1`, không coi thuộc tính `version="1.1"` trong schema là thao tác cài đặt hoặc nâng cấp bộ biên dịch. [Đặc tả W3C XSD 1.1](https://www.w3.org/TR/xmlschema11-1/).

## 4. Chọn provider và kiểm tra năng lực

Có ba cách tạo thường gặp:

### Chọn theo ngôn ngữ qua cơ chế tìm của JAXP

```java
SchemaFactory factory =
        SchemaFactory.newInstance(XMLConstants.W3C_XML_SCHEMA_NS_URI);
```

Cách này cho phép môi trường triển khai có provider thích hợp. Dependency, cấu hình JAXP và class loader có thể ảnh hưởng bộ thực thi được chọn.

Đây là lựa chọn tự nhiên khi ứng dụng muốn nói rõ ngôn ngữ, còn cách cung cấp provider được quản lý bởi môi trường.

### Chọn bộ thực thi mặc định có sẵn trong JDK

```java
SchemaFactory factory = SchemaFactory.newDefaultInstance();
```

Phương thức này có từ Java 9 và có sẵn trên mốc Java 17 của ví dụ. Dùng nó khi chủ đích là bộ thực thi có sẵn trong JDK, thay vì một provider được tìm từ môi trường.

Không diễn giải “default” thành “tự chọn mọi phiên bản XSD mới nhất”.

### Chỉ định lớp provider khi cần kiểm soát rõ

API còn có overload:

```java
// Doan minh hoa trong phuong thuc da nhan ten lop va class loader hop le.
SchemaFactory factory = SchemaFactory.newInstance(
        languageUri, providerClassName, providerClassLoader);
```

Dùng tên lớp do nhà cung cấp công bố và bảo đảm thư viện có trên đường nạp lớp. Không sao chép tên lớp nội bộ `com.sun.*` của JDK để cố định triển khai: đó không phải hợp đồng sử dụng công khai của ứng dụng.

Nếu cần chẩn đoán bộ đang được nạp, có thể ghi `factory.getClass().getName()` vào thông tin chẩn đoán lúc khởi động. Không dùng tên lớp ấy làm logic xác thực nghiệp vụ.

### isSchemaLanguageSupported chỉ trả lời về factory đang có

```java
boolean supportsXsd = factory.isSchemaLanguageSupported(
        XMLConstants.W3C_XML_SCHEMA_NS_URI);
```

Phép kiểm tra này không tìm hoặc cài thêm provider, không tải tệp XSD, không chứng minh một schema cụ thể biên dịch được và không kiểm tra tài liệu XML. Nó trả lời năng lực ngôn ngữ của chính đối tượng factory đang gọi.

## 5. Chương trình hoàn chỉnh: chọn XSD, biên dịch schema, kiểm tra XML

Lưu thành `SchemaLanguageDemo.java`. Chương trình chỉ dùng thư viện chuẩn JDK.

```java
import java.io.StringReader;
import javax.xml.XMLConstants;
import javax.xml.transform.stream.StreamSource;
import javax.xml.validation.Schema;
import javax.xml.validation.SchemaFactory;
import javax.xml.validation.Validator;
import org.xml.sax.SAXException;
import org.xml.sax.SAXParseException;
import org.xml.sax.helpers.DefaultHandler;

public class SchemaLanguageDemo {
    static final String XSD = """
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

    static StreamSource source(String text) {
        return new StreamSource(new StringReader(text));
    }

    static void check(Schema schema, String label, String xml,
                      boolean expectedValid) throws Exception {
        Validator validator = schema.newValidator();
        validator.setProperty(XMLConstants.ACCESS_EXTERNAL_DTD, "");
        validator.setProperty(XMLConstants.ACCESS_EXTERNAL_SCHEMA, "");
        validator.setErrorHandler(new DefaultHandler() {
            @Override
            public void error(SAXParseException failure) throws SAXException {
                throw failure;
            }

            @Override
            public void fatalError(SAXParseException failure) throws SAXException {
                throw failure;
            }
        });

        boolean valid;
        try {
            validator.validate(source(xml));
            valid = true;
        } catch (SAXException invalid) {
            valid = false;
        }
        if (valid != expectedValid) {
            throw new AssertionError(label + ": unexpected validation result");
        }
        System.out.println(label + ": " + (valid ? "VALID" : "INVALID"));
    }

    public static void main(String[] args) throws Exception {
        String language = XMLConstants.W3C_XML_SCHEMA_NS_URI;
        SchemaFactory factory = SchemaFactory.newInstance(language);

        if (!factory.isSchemaLanguageSupported(language)) {
            throw new AssertionError("XSD language not supported");
        }
        System.out.println("language: " + language);
        System.out.println("supports-XSD: true");

        SchemaFactory builtin = SchemaFactory.newDefaultInstance();
        System.out.println("builtin-supports-XSD: "
                + builtin.isSchemaLanguageSupported(language));

        factory.setFeature(XMLConstants.FEATURE_SECURE_PROCESSING, true);
        factory.setProperty(XMLConstants.ACCESS_EXTERNAL_DTD, "");
        factory.setProperty(XMLConstants.ACCESS_EXTERNAL_SCHEMA, "");
        Schema schema = factory.newSchema(source(XSD));

        check(schema, "positive", "<order><quantity>3</quantity></order>", true);
        check(schema, "zero", "<order><quantity>0</quantity></order>", false);
        check(schema, "wrong-root", "<invoice><quantity>3</quantity></invoice>", false);

        try {
            SchemaFactory.newInstance("urn:example:no-schema-provider");
            throw new AssertionError("Unexpected provider for demo language");
        } catch (IllegalArgumentException expected) {
            System.out.println("unknown-language: NO_PROVIDER");
        }
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 SchemaLanguageDemo.java
java SchemaLanguageDemo
```

Với JDK không cài provider cho ngôn ngữ giả `urn:example:no-schema-provider`, stdout là:

```text
language: http://www.w3.org/2001/XMLSchema
supports-XSD: true
builtin-supports-XSD: true
positive: VALID
zero: INVALID
wrong-root: INVALID
unknown-language: NO_PROVIDER
```

Cách đọc chương trình:

1. `newInstance(language)` tìm factory hiểu XSD.
2. `isSchemaLanguageSupported` kiểm tra ngôn ngữ trên factory đã có.
3. `newDefaultInstance()` minh họa cách chọn trực tiếp bộ thực thi của JDK.
4. Factory được cấu hình trước khi gọi `newSchema(source(XSD))`.
5. XSD khai báo phần tử gốc `order`, bên trong phải có `quantity` kiểu `xs:positiveInteger`.
6. `3` hợp lệ; `0` không phải số nguyên dương; gốc `invoice` không được schema khai báo.
7. Mỗi lần kiểm tra tạo một `Validator` mới từ cùng một `Schema`.
8. Ngôn ngữ giả không có provider cho thấy lỗi chọn ngôn ngữ khác với dữ liệu không hợp lệ.

Không đưa tên lớp provider vào stdout dự kiến vì đó là chi tiết có thể thay đổi theo môi trường.

Trong hàm `check`, dữ liệu đều là hằng nội bộ; cờ `expectedValid` khiến ví dụ thất bại nếu hành vi không đúng dự kiến. Việc bắt `SAXException` để in `INVALID` chỉ phục vụ những ca kiểm tra đã kiểm soát này, không phải quy tắc gộp mọi lỗi của ứng dụng thành dữ liệu không hợp lệ.

## 6. Phân biệt ba nhóm lỗi

### Không tạo được factory cho ngôn ngữ

Lỗi nằm ở định danh, dependency, cấu hình provider hoặc class loader. Chưa có schema nào được biên dịch, nên không thể kết luận XML đầu vào hợp lệ hay không.

Ví dụ: truyền `"order.xsd"` vào `newInstance` không yêu cầu Java mở tệp đó; nó yêu cầu tìm provider cho một định danh ngôn ngữ không đúng ý định.

### Không biên dịch được schema

Factory hiểu XSD không có nghĩa mọi tệp đuôi `.xsd` đều đúng. Nguồn có thể sai cú pháp XML, sai cấu trúc XSD, tham chiếu kiểu không tồn tại hoặc dùng tính năng bộ xử lý không hỗ trợ.

`factory.newSchema(source)` có thể báo `SAXException`. Đây là lỗi của schema hoặc quá trình chuẩn bị nó, cần xử lý trước khi nhận tài liệu để xác thực.

### Không xác thực được tài liệu

Khi đã có `Schema`, `validator.validate(source)` kiểm tra tài liệu cụ thể. Có thể gặp tài liệu sai ràng buộc, XML sai cú pháp hoặc lỗi trong quá trình xử lý nguồn; các nguyên nhân cần được phân loại theo thông tin lỗi, không chỉ nhìn một nhãn `INVALID`.

Trong ứng dụng thực, tách lỗi đọc dữ liệu, lỗi khởi tạo/schema và lỗi nội dung. Giữ `cause`, thông tin dòng/cột nếu có; không làm mất nguyên nhân bằng cách trả `false` từ mọi khối `catch`. [Hành vi của Validator.validate và ErrorHandler](https://docs.oracle.com/en/java/javase/25/docs/api/java.xml/javax/xml/validation/Validator.html).

Một `ErrorHandler` tùy chỉnh có thể nhận lỗi rồi không ném ngoại lệ. Khi đó, việc `validate` trả về bình thường không tự chứng minh không có lỗi đã được báo. Ví dụ dùng handler ném ở `error` và `fatalError` để tiêu chí thành công rõ ràng.

## 7. Vòng đời, tái sử dụng và cấu hình nguồn

Một `Schema` đại diện cho tập ràng buộc đã chuẩn bị, có thể tái sử dụng và an toàn khi chia sẻ giữa các luồng. Thông thường, ứng dụng biên dịch schema đã biết khi khởi tạo, giữ `Schema`, rồi tạo validator cho từng lần kiểm tra. [Hợp đồng Schema](https://docs.oracle.com/en/java/javase/25/docs/api/java.xml/javax/xml/validation/Schema.html).

Ngược lại, không dùng đồng thời một `SchemaFactory` hoặc một `Validator` đang hoạt động giữa nhiều luồng. Tái sử dụng `Schema` không đồng nghĩa mọi đối tượng trong chuỗi đều chia sẻ theo cách giống nhau.

Chọn ngôn ngữ cũng không phải cấp quyền tải tài nguyên. Nguồn XSD có thể có `include`/`import`; XML hoặc schema có thể dẫn đến tài nguyên phụ nếu cấu hình cho phép. Ví dụ giới hạn truy cập ngoài bằng chuỗi rỗng và dùng nguồn hằng trong bộ nhớ để tập trung vào việc chọn ngôn ngữ. Các hằng `ACCESS_EXTERNAL_DTD` và `ACCESS_EXTERNAL_SCHEMA` điều khiển phạm vi tài nguyên tương ứng; chúng không tự kiểm soát một kết nối mà ứng dụng đã mở ở nơi khác. [Các thuộc tính truy cập ngoài của JAXP](https://docs.oracle.com/en/java/javase/25/docs/api/java.xml/javax/xml/XMLConstants.html).

Nếu schema được chia thành nhiều nguồn hợp lệ, thiết kế cách cung cấp những nguồn ấy qua tài nguyên và resolver được kiểm soát. Không đổi quyền truy cập thành `"all"` để che một lỗi cấu hình nguồn.

Ngoài ra, `factory.newSchema()` không tham số có ngữ nghĩa riêng; đừng dùng nó thay cho `newSchema(sourceXsd)` rồi cho rằng ứng dụng vẫn đang áp dụng đúng schema cụ thể do mình chọn. Với hợp đồng cố định, cung cấp nguồn schema rõ ràng như ví dụ.

## 8. Lỗi phổ biến khi chọn ngôn ngữ

| Nhầm lẫn | Cách hiểu đúng |
|---|---|
| Thấy tệp `.xsd` nên factory tự biết ngôn ngữ | Chọn ngôn ngữ khi tạo factory; nguồn được cung cấp sau |
| URI ngôn ngữ là URL phải tải | Nó là định danh cho việc chọn bộ xử lý |
| Dùng namespace nghiệp vụ làm tham số ngôn ngữ | Hai loại namespace có vai trò khác nhau |
| Có hằng RELAX NG nghĩa là JDK đã cài provider | Hằng không thay thế triển khai |
| Hỗ trợ XSD nghĩa là chắc chắn có XSD 1.1 | Cần xác minh đúng bộ thực thi và tính năng cần dùng |
| isSchemaLanguageSupported trả true nghĩa là tệp XSD hợp lệ | Cần gọi `newSchema` với nguồn thực |
| Bắt IllegalArgumentException rồi đổi sang ngôn ngữ khác | Có thể che lỗi cấu hình và thay đổi hợp đồng kiểm tra |
| Biên dịch lại cùng schema cho từng tài liệu | Thường có thể giữ lại `Schema` và tạo validator mới |
| Chia sẻ Schema thì chia sẻ luôn Validator | Hai đối tượng có hợp đồng an toàn luồng khác nhau |

## 9. Thực hành

1. Đổi số lượng `3` thành `1`, `-1`, rồi `abc`. Dự đoán ca nào đáp ứng `xs:positiveInteger` trước khi chạy.
2. Đổi URI truyền vào `newInstance` thành `"order.xsd"`. Xác định vì sao lỗi xuất hiện trước giai đoạn biên dịch schema.
3. Thay `newInstance(language)` bằng `newDefaultInstance()` trong chương trình, giữ kiểm tra hỗ trợ XSD và chạy lại.
4. Sửa schema để phần tử gốc là `invoice`. Phân biệt việc thay nguồn schema với việc thay ngôn ngữ schema.
5. Thêm một lỗi XSD rõ ràng, chẳng hạn tham chiếu `xs:TypeDoesNotExist`. Xác nhận chương trình thất bại ở `newSchema`, trước các ca xác thực XML.
6. Với dự án có provider ngoài, ghi lại định danh ngôn ngữ, tên/thế hệ provider, phiên bản tính năng schema cần dùng và một schema kiểm chứng nhỏ. Không lấy riêng đuôi tệp hoặc namespace làm bằng chứng hỗ trợ.
