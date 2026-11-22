# Ghi giá trị null và kiểu dữ liệu cơ bản tường minh

## 1. Ghi JSON theo luồng với JsonGenerator

Jackson Streaming API cho phép chương trình phát JSON từng token theo đúng thứ tự. Thành phần dùng để ghi là **JsonGenerator**, thuộc Jackson Core. Thay vì tạo trước một object graph hoặc một cây JsonNode, ta gọi các phương thức có kiểu rõ ràng để ghi tên field, giá trị và dấu kết thúc cấu trúc.

Các nhóm phương thức thường dùng:

- **writeStartObject()** và **writeEndObject()** để mở và đóng object.
- **writeStartArray()** và **writeEndArray()** để mở và đóng array.
- **writeFieldName(...)** để ghi tên field trong object.
- **writeString(...)**, **writeNumber(...)**, **writeBoolean(...)** và **writeNull()** để ghi giá trị JSON cơ bản.
- Các phương thức tiện ích như **writeStringField(...)**, **writeNumberField(...)**, **writeBooleanField(...)** và **writeNullField(...)** để ghi cả tên field lẫn giá trị trong một lời gọi.

JSON có sáu nhóm giá trị: object, array, string, number, boolean và null. Java có nhiều kiểu số riêng, nhưng khi ghi JSON chúng được mã hóa theo cú pháp number của JSON; kiểu Java cụ thể quyết định overload được gọi và độ chính xác của giá trị.

## 2. Tạo JsonGenerator và ghi object đầu tiên

Có thể tạo generator trực tiếp từ JsonFactory, hoặc lấy factory từ ObjectMapper. Ví dụ sau ghi vào StringWriter để nhận lại JSON dưới dạng chuỗi:

    import com.fasterxml.jackson.core.JsonGenerator;
    import com.fasterxml.jackson.databind.ObjectMapper;
    import java.io.StringWriter;

    public class BasicGeneratorExample {
        public static void main(String[] args) throws Exception {
            ObjectMapper mapper = new ObjectMapper();
            StringWriter output = new StringWriter();

            try (JsonGenerator generator = mapper.getFactory()
                    .createGenerator(output)) {
                generator.writeStartObject();
                generator.writeStringField("name", "Lan");
                generator.writeNumberField("age", 28);
                generator.writeBooleanField("active", true);
                generator.writeEndObject();
            }

            System.out.println(output);
        }
    }

JSON được ghi có dạng:

    {"name":"Lan","age":28,"active":true}

writeStartObject() bắt đầu một object. Các lời gọi write...Field ghi lần lượt tên và giá trị. writeEndObject() kết thúc object. Generator quản lý dấu ngoặc, dấu phẩy, dấu nháy và escape chuỗi; chương trình không phải tự nối những ký tự đó.

Khi dùng try-with-resources, generator được đóng sau khi hoàn tất. Việc đóng generator hoàn tất đầu ra và giải phóng tài nguyên liên quan. Trong ví dụ, StringWriter giữ nội dung đã ghi để chương trình đọc sau đó.

## 3. Ghi JSON null tường minh

JSON null là một giá trị hợp lệ, khác với property không xuất hiện. Trong Streaming API, phương thức ghi giá trị null là:

    generator.writeNull();

Nếu đang ghi một object và muốn tạo property có giá trị null, dùng phương thức tiện ích:

    generator.writeNullField("middleName");

Ví dụ:

    StringWriter output = new StringWriter();

    try (JsonGenerator generator = mapper.getFactory().createGenerator(output)) {
        generator.writeStartObject();
        generator.writeStringField("name", "Lan");
        generator.writeNullField("middleName");
        generator.writeEndObject();
    }

Kết quả:

    {"name":"Lan","middleName":null}

Property middleName có mặt trong object, và giá trị của nó là JSON null. Đây là cách thể hiện rõ ràng khi hợp đồng dữ liệu yêu cầu gửi trường với giá trị null.

### Phân biệt null với không ghi property

Nếu muốn property không xuất hiện, đơn giản là không gọi phương thức ghi field đó:

    generator.writeStartObject();
    generator.writeStringField("name", "Lan");
    // Không gọi writeNullField hoặc writeStringField cho middleName.
    generator.writeEndObject();

Kết quả chỉ có name. So sánh:

| Ý định | Cách ghi | Kết quả |
|---|---|---|
| Gửi giá trị null | writeNullField("middleName") | {"middleName":null} |
| Bỏ qua property | Không ghi tên field hoặc giá trị | {} nếu object không có field khác |
| Gửi chuỗi rỗng | writeStringField("middleName", "") | {"middleName":""} |

Ba kết quả này mang ý nghĩa khác nhau. Trong API cập nhật một phần, thiếu property thường có thể mang nghĩa “không thay đổi”; null có thể mang nghĩa “xóa giá trị”; chuỗi rỗng là một giá trị string có độ dài bằng không. Quy tắc nghiệp vụ phải được định nghĩa trong hợp đồng API.

### Null trong array

Trong array, mỗi phần tử chiếm một vị trí. Nếu một phần tử có giá trị null, ghi token null tại vị trí đó:

    generator.writeStartArray();
    generator.writeString("admin");
    generator.writeNull();
    generator.writeString("editor");
    generator.writeEndArray();

Kết quả:

    ["admin",null,"editor"]

Nếu bỏ qua phần tử thay vì ghi null, array sẽ ngắn hơn và các index phía sau thay đổi. Vì vậy, trong array, “không có phần tử” và “một phần tử null” là hai cấu trúc khác nhau.

## 4. Ghi string tường minh

Để ghi giá trị JSON string, dùng writeString(...):

    generator.writeString("Hello Jackson");

Trong object, có thể ghi tên và giá trị bằng writeStringField(...):

    generator.writeStringField("message", "Hello Jackson");

Generator tự escape các ký tự cần thiết trong chuỗi. Ví dụ, dấu nháy kép, dấu gạch chéo ngược và ký tự xuống dòng phải được mã hóa hợp lệ trong JSON:

    generator.writeStringField("message", "He said: \"Hello\"\nWelcome!");

Không cần tự thay dấu nháy hoặc tự nối chuỗi JSON. Hãy truyền giá trị Java bình thường để generator xử lý escaping.

### String null và string rỗng

String Java có thể là null hoặc chuỗi rỗng:

- Nếu muốn ghi JSON null, gọi writeNull() hoặc writeNullField(...).
- Nếu muốn ghi string rỗng, gọi writeString("") hoặc writeStringField(name, "").

Với giá trị tham chiếu có thể null, nên kiểm tra trước để ý định được thể hiện rõ:

    String nickname = null;

    if (nickname == null) {
        generator.writeNullField("nickname");
    } else {
        generator.writeStringField("nickname", nickname);
    }

Nếu property không bắt buộc và null có nghĩa là không gửi, có thể bỏ qua cả hai lời gọi trong nhánh null. Không nên để hành vi đó xảy ra ngẫu nhiên; hãy chọn giữa null và omitted theo hợp đồng dữ liệu.

## 5. Ghi số nguyên và số thực

JsonGenerator cung cấp overload writeNumber(...) cho các kiểu số Java thường dùng, bao gồm int, long, float, double, BigInteger và BigDecimal. Trong object, phương thức tiện ích writeNumberField(...) ghi luôn tên field.

    generator.writeStartObject();
    generator.writeNumberField("count", 12);
    generator.writeNumberField("totalBytes", 9876543210L);
    generator.writeNumberField("ratio", 0.75);
    generator.writeEndObject();

Kết quả:

    {"count":12,"totalBytes":9876543210,"ratio":0.75}

Các kiểu byte và short có thể được mở rộng sang overload số nguyên phù hợp. Jackson ghi token JSON number; JSON không có các kiểu int, long, float hay double riêng như Java.

### BigInteger và BigDecimal

Khi cần ghi số nguyên rất lớn, dùng BigInteger. Khi cần giữ giá trị thập phân chính xác theo biểu diễn decimal, chẳng hạn số tiền, dùng BigDecimal:

    import java.math.BigDecimal;
    import java.math.BigInteger;

    generator.writeStartObject();
    generator.writeNumberField(
            "largeId",
            new BigInteger("123456789012345678901234567890")
    );
    generator.writeNumberField(
            "amount",
            new BigDecimal("125000.50")
    );
    generator.writeEndObject();

BigDecimal giúp tránh sai số nhị phân vốn có khi dùng double cho các phép tính thập phân cần chính xác. Nên tạo BigDecimal từ chuỗi có định dạng thập phân mong muốn, ví dụ new BigDecimal("125000.50"), thay vì tạo từ một giá trị double đã có thể mang sai số biểu diễn.

JSON number không quy định một kiểu decimal chính xác ở mọi ngôn ngữ. Dù Jackson có thể ghi chính xác giá trị BigDecimal, consumer JavaScript hoặc hệ thống khác có thể chuyển number sang kiểu dấu phẩy động và làm tròn. Với hợp đồng tài chính liên nền tảng, đôi khi nên biểu diễn số tiền bằng string theo quy ước rõ ràng, hoặc yêu cầu consumer dùng kiểu decimal chính xác.

### Float và double

float và double là kiểu dấu phẩy động nhị phân. Chúng phù hợp cho nhiều phép đo và tính toán khoa học, nhưng không biểu diễn chính xác mọi số thập phân. Khi ghi các giá trị này, Jackson ghi dạng number theo giá trị mà kiểu Java lưu giữ.

JSON number không cho phép NaN, Infinity hoặc -Infinity theo cú pháp chuẩn. Nếu ứng dụng có thể tạo các giá trị không hữu hạn, cần quy định rõ cách xử lý, chẳng hạn từ chối, chuyển thành null hoặc biểu diễn bằng chuỗi. Không nên giả định chúng là number JSON hợp lệ.

## 6. Ghi boolean tường minh

Boolean trong JSON chỉ có hai giá trị true và false. Dùng writeBoolean(...) cho một giá trị hoặc writeBooleanField(...) cho property:

    generator.writeStartObject();
    generator.writeBooleanField("enabled", true);
    generator.writeBooleanField("archived", false);
    generator.writeEndObject();

Kết quả:

    {"enabled":true,"archived":false}

Không đặt dấu nháy quanh boolean nếu API yêu cầu kiểu boolean. "true" là JSON string, còn true là JSON boolean. Hai kiểu này không tương đương.

### Boolean wrapper có thể null

Java boolean luôn là true hoặc false. Boolean là kiểu tham chiếu nên có thể là true, false hoặc null. Khi ghi Boolean, cần kiểm tra null trước khi auto-unbox:

    Boolean verified = null;

    if (verified == null) {
        generator.writeNullField("verified");
    } else {
        generator.writeBooleanField("verified", verified);
    }

Nếu truyền một Boolean null vào nơi cần primitive boolean, Java có thể phát sinh NullPointerException do auto-unboxing. Kiểm tra rõ null giúp tránh lỗi và thể hiện đúng ý nghĩa JSON mong muốn.

## 7. Ghi từng kiểu trong object bằng phương thức tiện ích

Jackson cung cấp các phương thức dạng writeXxxField(name, value) để ghi một cặp field-value trong object:

| Phương thức | JSON value được ghi |
|---|---|
| writeStringField(name, value) | String |
| writeNumberField(name, value) | Number |
| writeBooleanField(name, value) | Boolean |
| writeNullField(name) | Null |
| writeObjectField(name, value) | Giá trị được serialize qua codec gắn với generator |
| writeBinaryField(name, data) | Byte array được mã hóa theo dạng binary mà generator hỗ trợ; với JSON văn bản thường là Base64 string |

Nếu cần kiểm soát rõ kiểu JSON, ưu tiên các phương thức typed như writeStringField, writeNumberField, writeBooleanField và writeNullField. writeObjectField chuyển quyền serialize giá trị cho codec/ObjectMapper; nó tiện khi muốn ghi một object Java phức tạp, nhưng không phải lựa chọn rõ ràng nhất khi bài toán yêu cầu phát từng kiểu primitive một cách tường minh.

## 8. Ghi array chứa các kiểu dữ liệu cơ bản

Trong array, gọi phương thức ghi giá trị trực tiếp vì phần tử không có tên field:

    generator.writeStartArray();
    generator.writeString("reader");
    generator.writeString("editor");
    generator.writeEndArray();

Với các kiểu khác:

    generator.writeStartArray();
    generator.writeNumber(10);
    generator.writeNumber(20L);
    generator.writeBoolean(true);
    generator.writeNull();
    generator.writeEndArray();

Kết quả:

    [10,20,true,null]

Trong object, writeNumberField("age", 28) tương đương về ý nghĩa với việc gọi writeFieldName("age") rồi writeNumber(28). Trong array, không có field name nên chỉ gọi writeNumber(28).

## 9. Ghi cấu trúc lồng nhau và giá trị cơ bản

Ví dụ hoàn chỉnh sau kết hợp object, array, string, number, boolean và null:

    import com.fasterxml.jackson.core.JsonGenerator;
    import com.fasterxml.jackson.databind.ObjectMapper;
    import java.io.StringWriter;
    import java.math.BigDecimal;

    public class ExplicitValueTypes {
        public static void main(String[] args) throws Exception {
            ObjectMapper mapper = new ObjectMapper();
            StringWriter output = new StringWriter();

            String middleName = null;
            Integer loginCount = 7;
            Boolean verified = null;

            try (JsonGenerator generator = mapper.getFactory()
                    .createGenerator(output)) {
                generator.useDefaultPrettyPrinter();

                generator.writeStartObject();
                generator.writeStringField("username", "lan");

                if (middleName == null) {
                    generator.writeNullField("middleName");
                } else {
                    generator.writeStringField("middleName", middleName);
                }

                if (loginCount == null) {
                    generator.writeNullField("loginCount");
                } else {
                    generator.writeNumberField("loginCount", loginCount);
                }

                if (verified == null) {
                    generator.writeNullField("verified");
                } else {
                    generator.writeBooleanField("verified", verified);
                }

                generator.writeNumberField(
                        "balance",
                        new BigDecimal("1250.50")
                );

                generator.writeObjectFieldStart("address");
                generator.writeStringField("city", "Da Nang");
                generator.writeStringField("country", "Vietnam");
                generator.writeEndObject();

                generator.writeArrayFieldStart("roles");
                generator.writeString("reader");
                generator.writeString("editor");
                generator.writeEndArray();

                generator.writeEndObject();
            }

            System.out.println(output);
        }
    }

Phần output có dạng:

    {
      "username" : "lan",
      "middleName" : null,
      "loginCount" : 7,
      "verified" : null,
      "balance" : 1250.50,
      "address" : {
        "city" : "Da Nang",
        "country" : "Vietnam"
      },
      "roles" : [ "reader", "editor" ]
    }

Ở đây, từng kiểu dữ liệu được ghi bằng phương thức tương ứng. middleName và verified được ghi thành null vì biến Java đang null. loginCount được kiểm tra trước khi auto-unbox thành số nguyên. balance dùng BigDecimal để giữ giá trị thập phân theo biểu diễn decimal.

## 10. Ghi byte array và ký tự

JSON không có kiểu byte array hoặc kiểu ký tự đơn riêng. Khi cần ghi dữ liệu nhị phân vào JSON văn bản, Jackson thường mã hóa byte array thành Base64 string:

    byte[] payload = new byte[] { 1, 2, 3, 4 };
    generator.writeBinaryField("payload", payload);

Consumer cần giải mã Base64 để khôi phục byte array. Nếu hợp đồng yêu cầu một dạng mã hóa khác, hãy chọn encoder và quy ước rõ ràng.

Với Java char, JSON không có scalar kiểu character. Thường ghi nó thành string một ký tự:

    char grade = 'A';
    generator.writeStringField("grade", String.valueOf(grade));

Không nên ghi mã số Unicode của ký tự bằng writeNumber trừ khi hợp đồng API thực sự định nghĩa trường đó là số code point. "A" và 65 là hai kiểu JSON và hai ý nghĩa khác nhau.

## 11. Tự ghi field name và value theo từng bước

Các phương thức tiện ích dạng writeXxxField kết hợp ghi tên và giá trị. Nếu cần quyết định kiểu giá trị ở runtime, có thể ghi tên field trước rồi ghi token tương ứng:

    generator.writeStartObject();

    generator.writeFieldName("value");
    if (value == null) {
        generator.writeNull();
    } else if (value instanceof String text) {
        generator.writeString(text);
    } else if (value instanceof Integer number) {
        generator.writeNumber(number);
    } else if (value instanceof Long number) {
        generator.writeNumber(number);
    } else if (value instanceof BigDecimal decimal) {
        generator.writeNumber(decimal);
    } else if (value instanceof Boolean flag) {
        generator.writeBoolean(flag);
    } else {
        throw new IllegalArgumentException("Unsupported JSON value type");
    }

    generator.writeEndObject();

Sau writeFieldName, generator đang chờ một giá trị. Phải ghi đúng một token giá trị trước khi chuyển sang field tiếp theo hoặc kết thúc object. Ví dụ dùng pattern matching cho instanceof của Java hiện đại; với Java cũ hơn, có thể dùng kiểm tra kiểu và ép kiểu tường minh.

Nếu dữ liệu có thể là object hoặc array, cần thêm các nhánh xử lý tương ứng hoặc dùng writeObject(...) khi muốn giao việc serialize object phức tạp cho codec. Không nên âm thầm gọi toString() cho kiểu không hỗ trợ, vì kết quả có thể là JSON string thay vì cấu trúc JSON mà consumer mong đợi.

## 12. Giữ cấu trúc token hợp lệ

Generator theo dõi ngữ cảnh hiện tại để bảo đảm các token được ghi đúng vị trí. Một số quy tắc cơ bản:

- Sau writeStartObject(), các giá trị trong object phải đi theo cặp tên field và value.
- Sau writeStartArray(), có thể ghi trực tiếp nhiều giá trị liên tiếp.
- Mỗi object phải có writeEndObject() tương ứng; mỗi array phải có writeEndArray() tương ứng.
- writeNull() ghi một giá trị; trong object cần có field name trước đó.
- Không ghi field name bên trong array vì phần tử array không có tên.

Trình tự cho một object có array con:

    writeStartObject
      writeStringField("name", ...)
      writeArrayFieldStart("scores")
        writeNumber(...)
        writeNumber(...)
      writeEndArray
    writeEndObject

Các phương thức tiện ích như writeArrayFieldStart và writeObjectFieldStart ghi tên field rồi mở cấu trúc con. Sau khi mở, chương trình vẫn phải đóng cấu trúc con trước khi tiếp tục ghi các field cùng cấp.

Không nên dựa vào hành vi tự đóng cấu trúc khi generator được đóng để thay thế việc viết đầy đủ writeEndObject hoặc writeEndArray. Hãy đóng từng cấu trúc một cách tường minh để JSON có hình dạng như mong muốn và lỗi vị trí token dễ được phát hiện.

## 13. Ghi JSON ra OutputStream hoặc file

Khi dữ liệu cần gửi qua mạng hoặc ghi file, không cần tạo StringWriter. Có thể tạo generator trực tiếp trên OutputStream:

    import com.fasterxml.jackson.core.JsonEncoding;
    import com.fasterxml.jackson.core.JsonFactory;
    import com.fasterxml.jackson.core.JsonGenerator;
    import java.io.OutputStream;
    import java.nio.file.Files;
    import java.nio.file.Path;

    JsonFactory factory = new JsonFactory();

    try (OutputStream output = Files.newOutputStream(Path.of("event.json"));
         JsonGenerator generator = factory.createGenerator(
                 output,
                 JsonEncoding.UTF8
         )) {
        generator.writeStartObject();
        generator.writeStringField("type", "created");
        generator.writeNumberField("version", 1);
        generator.writeNullField("comment");
        generator.writeEndObject();
    }

Ghi trực tiếp ra stream tránh phải giữ thêm một chuỗi JSON lớn trong bộ nhớ. JsonEncoding.UTF8 làm rõ encoding của nội dung JSON được tạo. Nếu output stream do framework hoặc thành phần khác quản lý, hãy thống nhất quyền sở hữu và chính sách đóng stream; không đóng một stream mà caller còn cần sử dụng.

## 14. Khi nào dùng writeObject thay vì phương thức typed?

writeObject(value) yêu cầu generator có ObjectCodec phù hợp để serialize giá trị Java. Khi generator được tạo từ ObjectMapper.getFactory(), mapper thường cung cấp codec đó. Phương thức này thuận tiện để ghi một POJO, collection hoặc kiểu phức tạp:

    generator.writeFieldName("customer");
    generator.writeObject(customer);

Tuy nhiên, khi ghi các giá trị cơ bản và muốn thể hiện rõ token JSON, các phương thức typed có ưu điểm:

- Nhìn mã nguồn biết ngay giá trị được ghi là string, number, boolean hay null.
- Không phụ thuộc vào serializer cho một kiểu object tổng quát.
- Dễ kiểm soát trường hợp wrapper null và cách xử lý property bị bỏ qua.
- Phù hợp với mục tiêu xử lý token trực tiếp của Streaming API.

Hai cách có thể kết hợp: dùng generator để điều khiển cấu trúc lớn và writeObject cho một nhánh POJO đã có serializer phù hợp.

## 15. Các lỗi thường gặp

### Ghi null thành chuỗi "null"

writeString("null") tạo JSON string, có dấu nháy. writeNull() mới tạo token JSON null. Hai kết quả không tương đương:

    "null"

so với:

    null

### Bỏ qua null ngoài ý muốn

Nếu biến Java là wrapper null, kiểm tra trước khi auto-unbox hoặc gọi overload primitive. Quyết định rõ ghi null hay bỏ qua property.

### Ghi sai kiểu JSON

writeStringField("active", "true") tạo string; writeBooleanField("active", true) tạo boolean. Tương tự, writeStringField("age", "28") khác writeNumberField("age", 28).

### Tự ghép dấu ngoặc và dấu phẩy

Không nối chuỗi JSON thủ công. Hãy dùng các phương thức cấu trúc và value của generator để tránh lỗi cú pháp và lỗi escape.

### Quên đóng cấu trúc

Mỗi object/array đã mở phải được đóng đúng cấp. Nếu cấu trúc lồng nhau, đóng node con trước node cha.

### Dùng double cho giá trị tiền tệ cần chính xác

double có thể có sai số nhị phân. Dùng BigDecimal cho decimal chính xác trong Java và thống nhất cách consumer xử lý JSON number.

### Ghi số không hữu hạn như number JSON

NaN và vô cực không thuộc cú pháp JSON chuẩn. Hãy xử lý theo hợp đồng trước khi ghi.

## 16. Tổng hợp các phương thức ghi cơ bản

| Loại dữ liệu | Ghi một giá trị | Ghi field trong object |
|---|---|---|
| String | writeString(value) | writeStringField(name, value) |
| Integer/Long và kiểu số nguyên phù hợp | writeNumber(value) | writeNumberField(name, value) |
| Float/Double | writeNumber(value) | writeNumberField(name, value) |
| BigInteger/BigDecimal | writeNumber(value) | writeNumberField(name, value) |
| Boolean | writeBoolean(value) | writeBooleanField(name, value) |
| Null | writeNull() | writeNullField(name) |
| Binary | writeBinary(data) | writeBinaryField(name, data) |

Đối với array, dùng phương thức ghi giá trị đơn vì array không có tên field. Đối với object, dùng phương thức ...Field để ghi cặp tên-value hoặc ghi writeFieldName rồi một token giá trị riêng.

## 17. Kết luận

Khi ghi JSON theo luồng, JsonGenerator cho phép chọn rõ kiểu token cần phát. Dùng writeNull() hoặc writeNullField() để ghi JSON null; dùng writeString, writeNumber và writeBoolean cùng các biến thể ...Field để ghi string, number và boolean đúng kiểu. Phải phân biệt null với property bị lược bỏ, string rỗng và phần tử null trong array. Với wrapper có thể null, kiểm tra trước khi auto-unbox; với số thập phân cần chính xác, cân nhắc BigDecimal; với dữ liệu lớn, ghi trực tiếp ra stream. Khi kết hợp các token theo đúng cấu trúc object/array và đóng từng cấu trúc tường minh, generator tạo JSON hợp lệ mà không cần thao tác chuỗi thủ công.
