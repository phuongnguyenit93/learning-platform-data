# Indexer trên string và chuỗi ký tự

Trong Spring Expression Language (SpEL), **indexer** dùng cú pháp dấu ngoặc vuông **[index]** để lấy một phần tử tại vị trí xác định của một cấu trúc dữ liệu. Với String, indexer trả về ký tự ở vị trí được chỉ định dưới dạng một **String** có độ dài một đơn vị UTF-16, không phải đối tượng Character.

Chỉ số bắt đầu từ **0**: vị trí 0 là ký tự đầu tiên, vị trí 1 là ký tự thứ hai và vị trí cuối cùng là **length - 1**. Cách truy cập này hữu ích khi biểu thức cần lấy một ký tự từ mã định danh, kiểm tra tiền tố hoặc hậu tố đơn giản, hay kết hợp ký tự với những phần dữ liệu khác.

## Cú pháp indexing trên String

Cú pháp cơ bản:

~~~text
someString[index]
~~~

Trong đó **someString** là một giá trị String có thể truy cập từ root object hoặc biến trong EvaluationContext; **index** là biểu thức cho ra một chỉ số nguyên hợp lệ.

Ví dụ, dùng một biến trong context:

~~~java
ExpressionParser parser = new SpelExpressionParser();

StandardEvaluationContext context =
        new StandardEvaluationContext();

context.setVariable("text", "Spring");

Expression expression =
        parser.parseExpression("#text[0]");

String firstCharacter =
        expression.getValue(context, String.class);
~~~

Kết quả của biểu thức là **"S"**. Biến **#text** tham chiếu chuỗi Spring được đưa vào EvaluationContext. Index **0** lấy ký tự đầu tiên.

Có thể lấy các vị trí tiếp theo:

~~~java
String second =
        parser.parseExpression("#text[1]")
                .getValue(context, String.class);

String fourth =
        parser.parseExpression("#text[3]")
                .getValue(context, String.class);
~~~

Với chuỗi Spring, kết quả lần lượt là **"p"** và **"i"**.

## Chỉ số bắt đầu từ 0

Indexer của SpEL dùng chỉ số zero-based, tương tự cách Java truy cập phần tử mảng và String. Với chuỗi **"Spring"**, bảng vị trí như sau:

| Index | Ký tự |
|---:|:---|
| 0 | S |
| 1 | p |
| 2 | r |
| 3 | i |
| 4 | n |
| 5 | g |

Vì vậy:

- **#text[0]** lấy ký tự đầu tiên.
- **#text[2]** lấy ký tự thứ ba.
- **#text[5]** lấy ký tự cuối cùng của chuỗi có sáu đơn vị UTF-16.

Không có vị trí 6 trong chuỗi này. Chỉ số hợp lệ phải nằm trong khoảng từ 0 đến **text.length() - 1**.

## Indexer trả về String, không phải Character

Một điểm dễ nhầm là Java có phương thức **String.charAt(int)** trả về kiểu **char**, nhưng indexer của SpEL trên String trả về một **String** chứa ký tự được lấy ra.

~~~java
String character =
        parser.parseExpression("#text[0]")
                .getValue(context, String.class);
~~~

Trong ví dụ này, kết quả có kiểu String và giá trị là **"S"**. Nếu ứng dụng cần một giá trị kiểu Character hoặc char, hãy chuyển đổi rõ ràng trong Java tại nơi sử dụng. Không nên mặc định rằng kết quả indexer có cùng kiểu với giá trị mà String.charAt(...) trả về.

Việc trả về String giúp kết quả indexer có thể được sử dụng trực tiếp trong những biểu thức tiếp theo vốn làm việc với chuỗi, ví dụ nối chuỗi hoặc gọi các method của String khi context cho phép.

## Lấy ký tự từ property của root object

Indexer không chỉ làm việc với biến. Nó cũng có thể truy cập String được lấy từ property của root object.

~~~java
public class Customer {
    private final String code;

    public Customer(String code) {
        this.code = code;
    }

    public String getCode() {
        return code;
    }
}
~~~

~~~java
Customer customer = new Customer("CUS-2048");

ExpressionParser parser = new SpelExpressionParser();

Expression expression =
        parser.parseExpression("code[0]");

String prefix =
        expression.getValue(customer, String.class);
~~~

Trong ví dụ, **customer** là root object. SpEL đọc property **code**, sau đó indexer lấy ký tự ở vị trí 0. Kết quả là **"C"**.

Có thể kết hợp property access với indexing trong cùng một biểu thức:

~~~java
"customer.code[4]"
~~~

Nếu customer có property code là **CUS-2048**, biểu thức trên lấy ký tự ở vị trí 4 của chuỗi mã. Cách viết này giúp truy cập dữ liệu lồng nhau mà không cần tạo một biểu thức riêng cho từng bước.

## Dùng biểu thức để tính chỉ số

Phần nằm trong ngoặc vuông cũng là một biểu thức SpEL. Vì vậy, chỉ số có thể được tính từ literal, biến hoặc property:

~~~java
String character =
        parser.parseExpression("#text[1 + 2]")
                .getValue(context, String.class);
~~~

Với **#text = "Spring"**, biểu thức lấy vị trí 3 và trả về **"i"**.

Nếu cần lấy ký tự cuối cùng, có thể tính chỉ số từ độ dài chuỗi:

~~~java
Expression lastCharacterExpression =
        parser.parseExpression("#text[#text.length() - 1]");

String lastCharacter =
        lastCharacterExpression.getValue(context, String.class);
~~~

Ví dụ này gọi method **length()** trên String rồi trừ 1 để lấy chỉ số cuối. Nó yêu cầu EvaluationContext hỗ trợ instance method invocation. Với context chỉ đọc dành cho data binding, khả năng gọi method có thể không được bật; khi đó hãy tính chỉ số trong Java và truyền biến vào context, hoặc dùng context phù hợp với chính sách truy cập của ứng dụng.

Một cách khác là cung cấp sẵn biến chỉ số:

~~~java
context.setVariable("lastIndex", 5);

String last =
        parser.parseExpression("#text[#lastIndex]")
                .getValue(context, String.class);
~~~

Cách này giúp biểu thức ngắn và không cần gọi method trên String.

## Indexer có thể kết hợp với thao tác String khác

Vì kết quả indexing là String, có thể tiếp tục dùng nó trong biểu thức:

~~~java
String upper =
        parser.parseExpression("#text[0].toUpperCase()")
                .getValue(context, String.class);
~~~

Trong ví dụ, indexer lấy ký tự đầu tiên, sau đó biểu thức gọi **toUpperCase()** trên String vừa nhận được. Khả năng gọi instance method phụ thuộc vào EvaluationContext. Nếu context không cho phép method invocation, hãy thực hiện bước chuyển đổi trong Java hoặc chọn context có bề mặt truy cập phù hợp.

Có thể dùng indexer trong biểu thức so sánh:

~~~java
Boolean startsWithS =
        parser.parseExpression("#text[0] == 'S'")
                .getValue(context, Boolean.class);
~~~

Biểu thức lấy ký tự đầu tiên rồi so sánh với string literal **'S'**. Kết quả là true khi ký tự đầu tiên của text đúng bằng S.

Nếu mục tiêu chỉ là kiểm tra tiền tố, phương thức **startsWith(...)** của String thường diễn đạt ý định rõ hơn. Indexer phù hợp khi cần lấy chính ký tự hoặc vị trí cụ thể để dùng tiếp trong một biểu thức.

## Indexing trên chuỗi rỗng và chỉ số ngoài phạm vi

Chuỗi rỗng không có ký tự nào, nên không có chỉ số hợp lệ. Tương tự, chỉ số âm hoặc chỉ số lớn hơn hay bằng độ dài chuỗi đều không hợp lệ.

~~~java
context.setVariable("emptyText", "");

Expression expression =
        parser.parseExpression("#emptyText[0]");

String value = expression.getValue(context, String.class);
~~~

Khi đánh giá biểu thức trên, SpEL phát sinh lỗi vì chuỗi rỗng không có phần tử ở index 0. Lỗi tương tự xảy ra khi truy cập **#text[6]** với chuỗi Spring hoặc dùng một chỉ số âm.

Indexer String không tự trả về chuỗi rỗng hay null khi chỉ số không hợp lệ. Hãy kiểm tra độ dài và chỉ số trước khi đánh giá, đặc biệt nếu index đến từ đầu vào bên ngoài.

Ví dụ kiểm tra trong Java:

~~~java
if (text != null && index >= 0 && index < text.length()) {
    context.setVariable("text", text);
    context.setVariable("index", index);

    String character =
            parser.parseExpression("#text[#index]")
                    .getValue(context, String.class);
}
~~~

Việc xác thực trong Java giúp tránh lỗi evaluation không cần thiết và cho phép ứng dụng quyết định cách xử lý chuỗi rỗng hoặc vị trí không tồn tại.

## Xử lý chuỗi null với null-safe indexing

Nếu giá trị String có thể null, cú pháp indexing thông thường sẽ phát sinh lỗi khi cố truy cập phần tử của null. Từ **Spring Framework 6.2**, SpEL hỗ trợ **null-safe indexing** bằng toán tử **?.** trước dấu ngoặc vuông:

~~~java
context.setVariable("text", null);

Expression expression =
        parser.parseExpression("#text?.[0]");

String first =
        expression.getValue(context, String.class);
~~~

Khi **#text** là null, biểu thức trả về null thay vì cố truy cập index 0. Nếu text không null, SpEL thực hiện indexing như bình thường.

Null-safe indexing chỉ xử lý trường hợp đối tượng đích null. Nó không làm cho một chỉ số ngoài phạm vi trở thành hợp lệ. Nếu chuỗi tồn tại nhưng rỗng, **#text?.[0]** vẫn có thể phát sinh lỗi do index 0 không tồn tại.

Với phiên bản Spring trước 6.2, cú pháp null-safe indexing này không được hỗ trợ. Khi phải tương thích nhiều phiên bản, hãy kiểm tra null trong Java hoặc dùng một biểu thức điều kiện phù hợp với phiên bản SpEL đang triển khai.

## Unicode, emoji và đơn vị UTF-16

Java String được biểu diễn bằng chuỗi đơn vị mã UTF-16. Indexer SpEL trên String sử dụng chỉ số theo cách truy cập ký tự của Java String, tương đương thao tác trên từng đơn vị UTF-16, chứ không phải theo Unicode code point hay ký tự người dùng nhìn thấy.

Với chữ cái thông thường trong bảng Latin, mỗi ký tự thường chiếm một đơn vị UTF-16 nên chỉ số có vẻ trùng với số ký tự. Nhưng một số ký tự Unicode nằm ngoài Basic Multilingual Plane, chẳng hạn nhiều emoji, được biểu diễn bằng **hai đơn vị UTF-16** (một cặp surrogate).

Ví dụ, chuỗi **"A😀B"** có ba Unicode code point nhưng có bốn đơn vị UTF-16:

| Index UTF-16 | Nội dung đơn vị |
|---:|---|
| 0 | A |
| 1 | High surrogate của emoji |
| 2 | Low surrogate của emoji |
| 3 | B |

Vì vậy, indexer tại vị trí 1 hoặc 2 không trả về toàn bộ emoji như một ký tự người dùng nhìn thấy. Nó lấy từng đơn vị UTF-16 riêng lẻ. Một cụm ký tự có dấu kết hợp cũng có thể gồm nhiều code point dù người dùng cảm nhận là một ký tự.

Nếu ứng dụng cần xử lý Unicode theo code point hoặc grapheme cluster, không nên dùng trực tiếp SpEL String indexer để đếm ký tự hiển thị. Hãy xử lý bằng Java với **String.codePoints()**, **Character** hoặc thư viện xử lý grapheme phù hợp, rồi đưa kết quả đã chuẩn hóa vào biểu thức nếu cần.

## String indexer là thao tác đọc

String trong Java là immutable, vì vậy indexer của SpEL trên String chỉ hỗ trợ đọc. Nó không thể thay đổi ký tự bên trong chuỗi thông qua phép gán vào vị trí index.

~~~java
Expression expression =
        parser.parseExpression("#text[0] = 's'");
~~~

Biểu thức trên không phải cách hợp lệ để thay ký tự đầu tiên của String. Nếu cần tạo chuỗi mới, hãy dùng Java, ví dụ tạo String mới từ các phần con hoặc dùng StringBuilder. Việc thay đổi nội dung chuỗi nên được thể hiện bằng thao tác tạo giá trị mới, không phải cập nhật tại chỗ.

Điểm này khác với indexing trên List, nơi một phần tử có thể được thay thế nếu collection và EvaluationContext cho phép ghi.

## Phân biệt String indexing với các cấu trúc khác

Cùng cú pháp ngoặc vuông được SpEL dùng cho nhiều cấu trúc, nhưng ý nghĩa và kiểu kết quả khác nhau:

| Cấu trúc | Ví dụ | Ý nghĩa |
|---|---|---|
| String | **#text[0]** | Lấy ký tự tại vị trí, kết quả là String |
| Array | **numbers[0]** | Lấy phần tử đầu tiên của mảng |
| List | **items[0]** | Lấy phần tử đầu tiên của List |
| Map | **settings['theme']** | Lấy giá trị theo key |
| Object | **#root['name']** | Truy cập property theo tên nếu accessor hỗ trợ |

Với String, index phải là số nguyên và xác định vị trí. Với Map, nội dung trong ngoặc vuông là key; với object, một index dạng tên property có thể được xử lý thông qua property accessor. Không nên nhầm các quy tắc này chỉ vì cùng dùng dấu ngoặc vuông.

## Lỗi thường gặp và cách xử lý

Khi dùng String indexer, các lỗi phổ biến gồm:

- **Index bắt đầu từ 1:** Java và SpEL dùng index bắt đầu từ 0, vì vậy vị trí đầu tiên là 0.
- **Index vượt độ dài:** cần kiểm tra index nhỏ hơn length của chuỗi.
- **Chuỗi null:** dùng null-safe indexing từ Spring 6.2 hoặc kiểm tra null trước khi truy cập.
- **Nhầm kiểu trả về:** indexer trả về String, không phải Character.
- **Nhầm ký tự Unicode:** index hoạt động trên đơn vị UTF-16, không phải ký tự hiển thị hoặc code point.
- **Cố gắng gán vào String:** String immutable và String indexer không hỗ trợ ghi.

Nếu biểu thức parse thành công nhưng lỗi khi gọi getValue, đó thường là lỗi evaluation do dữ liệu đầu vào hoặc chỉ số không hợp lệ. Có thể bắt **EvaluationException** ở lớp Java để chuyển thành thông báo nghiệp vụ phù hợp. Không nên che giấu mọi lỗi bằng cách trả về một ký tự mặc định nếu điều đó làm mất thông tin về dữ liệu sai.

## Khi nào nên dùng String indexer?

String indexer phù hợp khi cần lấy một vị trí cụ thể từ chuỗi có định dạng đơn giản và đã được xác thực, ví dụ:

- Lấy ký tự đầu của mã để phân loại nhanh.
- Lấy một ký tự ở vị trí cố định trong mã định danh.
- Trích xuất ký tự từ một chuỗi cấu trúc đơn giản.
- Kết hợp ký tự với điều kiện hoặc biểu thức khác trong một điểm tích hợp SpEL.

Nếu cần xử lý chuỗi phức tạp, Unicode nâng cao, kiểm tra định dạng toàn chuỗi hoặc thao tác nhiều bước, nên viết logic trong Java. Các phương thức như **startsWith**, **substring**, **charAt**, **codePoints** và các thư viện xử lý chuỗi chuyên dụng thường thể hiện rõ ý định hơn một biểu thức SpEL dài.

## Kết luận

Indexer SpEL trên String dùng cú pháp **string[index]**, với chỉ số bắt đầu từ 0. Kết quả là một String chứa ký tự tại vị trí đó. Indexer có thể truy cập chuỗi từ biến, root object hoặc property lồng nhau; nó chỉ đọc và sẽ phát sinh lỗi nếu chỉ số nằm ngoài phạm vi.

Khi chuỗi có thể null, Spring Framework 6.2 trở lên hỗ trợ cú pháp null-safe **?.[index]**. Khi xử lý emoji hoặc ký tự Unicode phức tạp, cần nhớ chỉ số String dựa trên UTF-16 của Java, không tương ứng một-một với ký tự người dùng nhìn thấy. Hãy xác thực độ dài và chỉ số trước khi evaluate, đồng thời chuyển logic xử lý chuỗi phức tạp sang Java.
