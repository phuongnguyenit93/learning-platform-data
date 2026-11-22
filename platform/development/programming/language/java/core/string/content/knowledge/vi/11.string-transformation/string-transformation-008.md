# Giữ chuỗi gốc khi cần đối chiếu hoặc hiển thị lại

Khi biến đổi nội dung văn bản trong Java, việc giữ **chuỗi ban đầu** và tạo **giá trị đã biến đổi** riêng là một cách thiết kế quan trọng. Dữ liệu gốc có thể cần để hiển thị đúng như người dùng đã nhập, đối chiếu với phiên bản xử lý, giải thích lỗi xác thực, hoàn nguyên thao tác hoặc đáp ứng quy tắc nghiệp vụ. Bản đã biến đổi lại thuận tiện cho tìm kiếm, so sánh, phân loại hay chuẩn hóa.

**Ý chính:** String là *immutable* (bất biến). Các phương thức như strip(), trim(), replace(), toLowerCase(), toUpperCase() và phép nối tạo/trả về giá trị String kết quả, không thay đổi nội dung đối tượng String ban đầu. Tuy nhiên, nếu lập trình viên **gán đè biến tham chiếu** hoặc chỉ lưu bản đã chuẩn hóa, ứng dụng vẫn có thể **đánh mất cách truy cập dữ liệu gốc**.

## 1. Phân biệt nội dung String bất biến và biến đang trỏ đến nó

Xét đoạn mã Java sau:

~~~java
String original = "  Java  ";
String cleaned = original.strip();

System.out.println("original=[" + original + "]");
System.out.println("cleaned=[" + cleaned + "]");
~~~

Kết quả:

~~~text
original=[  Java  ]
cleaned=[Java]
~~~

Lời gọi strip() không xóa hai dấu cách ở đầu và cuối của đối tượng original. Nó trả về String biểu diễn nội dung đã bỏ whitespace ở hai đầu. Biến cleaned giữ kết quả, còn biến original vẫn giữ giá trị cũ.

Điều thường gây nhầm lẫn:

~~~java
String text = "  Java  ";
text = text.strip();

System.out.println("[" + text + "]"); // [Java]
~~~

Đối tượng String ban đầu vẫn bất biến, nhưng biến text giờ trỏ tới kết quả đã strip(). Nếu không còn tham chiếu hữu ích nào khác đến nội dung đầu vào, chương trình không thể lấy lại chính xác cách người dùng đã nhập từ biến text. **Bất biến không đồng nghĩa ứng dụng tự động giữ lịch sử.**

Có thể giữ lại bản gốc bằng một biến khác:

~~~java
String original = textFromUser;
String normalized = original == null ? null : original.strip();
~~~

Đây là **đoạn minh họa**, giả định biến textFromUser đã được khai báo. Trong Java, original và normalized chỉ là các tham chiếu tới những giá trị String; lưu hai biến không bắt buộc phải nhân bản đối tượng gốc.

## 2. Khi nào phải giữ dữ liệu gốc?

| Tình huống | Vai trò của bản gốc | Vai trò của bản biến đổi |
|---|---|---|
| Ô nhập tên hiển thị | Giữ cách viết, khoảng trắng hoặc dấu theo yêu cầu UI | Tạo khóa tìm kiếm hay phiên bản đã cắt whitespace |
| Tìm kiếm không phân biệt hoa/thường | Hiển thị nguyên văn văn bản | Dùng chuỗi chuẩn hóa nhất quán để tìm |
| Kiểm tra và báo lỗi dữ liệu | Cho biết đầu vào nào không hợp lệ | Đưa dữ liệu qua bước xử lý hoặc đối chiếu |
| Nhập dữ liệu từ tệp hay API | Phục vụ đối chiếu hoặc phát hiện bất đồng nếu chính sách cho phép lưu | Tạo định dạng nội bộ cần thiết |
| Chỉnh sửa nội dung có chức năng “Hoàn tác” | Lưu phiên bản trước khi biến đổi | Dùng bản hiện tại để hiển thị hoặc xử lý |
| Mã định danh hoặc giá trị theo quy tắc nghiêm ngặt | Bảo toàn byte/ký tự theo hợp đồng, nếu cần | Chuẩn hóa chỉ khi hệ thống cho phép |
| Phân tích sự khác biệt Unicode | Phân biệt biểu diễn người dùng đưa vào | Áp dụng chuẩn hóa Unicode để so sánh theo yêu cầu |

Giữ dữ liệu gốc **không có nghĩa lưu mọi chuỗi vô thời hạn**. Với mật khẩu, token, thông tin cá nhân hoặc dữ liệu nhạy cảm, lưu nhiều bản có thể làm tăng rủi ro. Hãy giữ bản gốc khi có mục đích, thời hạn và quyền truy cập phù hợp; đừng đưa dữ liệu nhạy cảm nguyên văn vào log để “dễ đối chiếu”.

## 3. Dùng tên biến hoặc record để thể hiện rõ hai mục đích

Đối với logic nhỏ, hai biến có tên rõ ràng thường là đủ:

~~~java
String rawTitle = "  Java Basics  ";
String displayTitle = rawTitle.strip();

System.out.println("raw=[" + rawTitle + "]");       // [  Java Basics  ]
System.out.println("display=[" + displayTitle + "]"); // [Java Basics]
~~~

Khi dữ liệu đi qua nhiều tầng ứng dụng, có thể dùng một **record** Java 17 để đưa các biểu diễn thành một giá trị có cấu trúc, ví dụ gồm raw, display và searchKey. Cách này giúp phương thức nhận dữ liệu biết nó đang thao tác với phiên bản nào.

| Trường | Ý nghĩa |
|---|---|
| original / raw | Dữ liệu đầu vào được giữ nguyên theo hợp đồng |
| display | Giá trị dùng để trình bày, có thể đã bỏ whitespace đầu/cuối nếu nghiệp vụ cho phép |
| searchKey | Giá trị chuẩn hóa dùng để tra cứu, thường không được trình bày thay bản gốc |
| validationMessage | Kết quả đánh giá đầu vào, tách riêng khỏi chuỗi đầu vào |

Không nhất thiết mọi chương trình đều phải giữ cả ba bản. Hãy xác định cần bản nào từ yêu cầu nghiệp vụ rồi đặt tên để tránh truyền nhầm searchKey vào nơi muốn hiển thị nguyên văn.

### Chương trình Java 17+ đầy đủ: original, display và searchKey

Lưu tệp **KeepOriginalStringDemo.java**:

~~~java
import java.util.Locale;

public class KeepOriginalStringDemo {
    record TextVersions(String original, String display, String searchKey) {}

    static TextVersions prepare(String input) {
        if (input == null) {
            return new TextVersions(null, null, null);
        }

        String display = input.strip();
        String searchKey = display.toLowerCase(Locale.ROOT);
        return new TextVersions(input, display, searchKey);
    }

    public static void main(String[] args) {
        String received = "  Hello  JAVA  ";
        TextVersions versions = prepare(received);

        System.out.println("original=[" + versions.original() + "]");
        System.out.println("display=[" + versions.display() + "]");
        System.out.println("searchKey=[" + versions.searchKey() + "]");

        System.out.println("originalLength=" + versions.original().length());
        System.out.println("displayLength=" + versions.display().length());
        System.out.println("originalUnchanged="
                + received.equals(versions.original()));

        TextVersions missing = prepare(null);
        System.out.println("missing=" + (missing.original() == null));
    }
}
~~~

Biên dịch và chạy với JDK 17+:

~~~bash
javac KeepOriginalStringDemo.java
java KeepOriginalStringDemo
~~~

Kết quả chính xác:

~~~text
original=[  Hello  JAVA  ]
display=[Hello  JAVA]
searchKey=[hello  java]
originalLength=15
displayLength=11
originalUnchanged=true
missing=true
~~~

Trong ví dụ:

1. original giữ đủ **hai dấu cách đầu, hai dấu cách giữa Hello và JAVA, hai dấu cách cuối**.
2. display chỉ bỏ whitespace hai đầu. strip() không tự xóa hai dấu cách nằm giữa.
3. searchKey chuyển nội dung display sang chữ thường theo Locale.ROOT, phù hợp khi ứng dụng đã **chọn** chính sách tra cứu không phụ thuộc locale.
4. Lời gọi prepare(null) không thực hiện phương thức instance trên null. Từ đây, ứng dụng có thể phân biệt “không có văn bản” với một String rỗng.
5. Việc giữ các giá trị không tự làm việc chuẩn hóa trở thành phép biến đổi khả nghịch. Nếu chỉ lưu searchKey thì không thể khôi phục chính xác cách viết hoa và khoảng trắng của original.

**Chú ý về Locale.ROOT:** nó giúp tránh phụ thuộc vào locale mặc định của máy khi tạo khóa kỹ thuật. Tuy nhiên, chuyển hoa/thường vẫn có thể thay đổi độ dài hoặc quan hệ giữa ký tự ở một số trường hợp Unicode; đối chiếu ngôn ngữ tự nhiên cần quy tắc riêng, không mặc định toLowerCase() là giải pháp cho mọi locale.

## 4. Không gán đè đầu vào khi cần đối chiếu

Đoạn sau dễ mất ngữ cảnh:

~~~java
String input = "  AbC  ";
input = input.strip();
input = input.toLowerCase(java.util.Locale.ROOT);
System.out.println(input); // abc
~~~

Từng phép biến đổi đều hợp lệ và không sửa đối tượng String cũ. Vấn đề là tên input không còn nói đúng **giá trị đang được giữ**: chuỗi ban đầu có khoảng trắng và chữ viết hoa đã không còn trong tham chiếu input.

Viết rõ từng bước giúp kiểm chứng:

~~~java
String rawInput = "  AbC  ";
String trimmedInput = rawInput.strip();
String lookupInput = trimmedInput.toLowerCase(java.util.Locale.ROOT);

System.out.println("raw=[" + rawInput + "]");         // [  AbC  ]
System.out.println("trimmed=[" + trimmedInput + "]"); // [AbC]
System.out.println("lookup=[" + lookupInput + "]");   // [abc]
~~~

Bản raw giữ nguyên, mỗi bản sau có mục đích rõ. Nếu kết quả tìm kiếm không đúng, có thể biết vấn đề đến từ nội dung gốc, quy tắc strip hay quy tắc lowercasing, miễn là hệ thống cho phép quan sát các bản tương ứng.

Một điểm khác cần lưu ý: **biến final không khiến thao tác strip trở thành phép biến đổi tại chỗ**. Bạn có thể dùng:

~~~java
final String original = "  AbC  ";
final String key = original.strip().toLowerCase(java.util.Locale.ROOT);
~~~

Cả hai biến giữ tham chiếu ổn định, còn đối tượng String đã bất biến từ đầu. final chủ yếu giúp giảm khả năng vô tình gán lại các biến đó.

## 5. Khi đối chiếu, cần xác định thế nào là “bằng nhau”

Không có một quy tắc so sánh duy nhất cho mọi tình huống. Hai phiên bản có thể bằng nhau theo **nội dung chính xác** nhưng khác nhau theo một quy tắc chuẩn hóa, hoặc ngược lại.

| Mục tiêu | Cách kiểm tra | Ý nghĩa |
|---|---|---|
| So sánh chính xác hai String | original.equals(other) khi receiver không-null | So sánh dãy đơn vị mã UTF-16, phân biệt hoa/thường và khoảng trắng |
| So sánh hai String có thể null | java.util.Objects.equals(a, b) | null/null được coi bằng nhau; null/chuỗi rỗng vẫn khác nhau |
| Bỏ whitespace ở hai đầu rồi so sánh | a.strip().equals(b.strip()), sau null-check | Chỉ phù hợp khi nghiệp vụ cho phép coi whitespace hai đầu là không đáng kể |
| So sánh sau chuẩn hóa Unicode | Normalizer.normalize(a, Form.NFC).equals(Normalizer.normalize(b, Form.NFC)) | Gộp các dạng biểu diễn Unicode tương đương theo NFC |
| So sánh không phân biệt hoa/thường | Chính sách case-folding/collation phù hợp | Không chỉ đơn giản là bỏ mọi khác biệt ngôn ngữ |

String.equals() **không tự gọi strip(), trim(), normalize() hoặc toLowerCase()**. Nếu muốn đối chiếu theo quy tắc chuẩn hóa, hãy thực hiện bước đó một cách có chủ đích, giữ bản gốc khi cần.

### Ví dụ Unicode: văn bản nhìn giống nhau nhưng mã khác

`"Caf\u00E9"` có ký tự `é` dựng sẵn, còn `"Cafe\u0301"` gồm `e` và dấu sắc kết hợp. `String.equals()` phân biệt hai dãy mã; nếu nghiệp vụ muốn xem chúng tương đương theo chuẩn chính tắc, hãy chuẩn hóa nhất quán về NFC; trong ví dụ, `composed` vốn đã ở dạng NFC:

~~~java
String original = "Cafe\u0301";
String composed = "Caf\u00E9";
String normalized = java.text.Normalizer.normalize(
        original, java.text.Normalizer.Form.NFC);
System.out.println(original.equals(composed));   // false
System.out.println(normalized.equals(composed)); // true
System.out.println(original.length());           // 5
System.out.println(normalized.length());         // 4
~~~

`Normalizer` trả về giá trị mới và không sửa `original`. Khi chỉ lưu bản NFC, không thể tái tạo chắc chắn biểu diễn người dùng đã nhập. Ví dụ này minh họa trực tiếp lý do giữ cả **raw** và bản **so sánh**; bài về tính bảo toàn dữ liệu trước đó giải thích chi tiết tính đảo ngược và va chạm.

## 6. Lưu ý với trim(), strip(), replace() và biểu diễn để hiển thị

Các phép biến đổi thường dùng có thể làm mất thông tin có ý nghĩa với việc hiển thị lại:

- **strip()** loại whitespace đầu/cuối theo Character.isWhitespace của Java. Với chuỗi chỉ có whitespace thuộc tập này, có thể trả về String rỗng.
- **trim()** loại đơn vị mã ở hai đầu có giá trị <= U+0020; tập bị loại khác strip().
- **replace()** thay nội dung theo quy tắc đã chỉ định; bản kết quả không cho biết chính xác phần nào đã được thay khi không giữ thông tin ban đầu.
- **toLowerCase()/toUpperCase()** có thể thay đổi cách viết hoa, thậm chí số lượng đơn vị mã trong một số trường hợp.
- **Normalizer.normalize()** có thể thay đổi biểu diễn Unicode trong khi hình thức hiển thị tương tự.

Ví dụ khi người dùng nhập mã định danh **" AB-01 "**, nếu hệ thống lưu **"AB-01"** sau strip() thì sau đó không thể chắc chắn người dùng đã nhập một hay nhiều dấu cách ở hai đầu. Điều này có thể không quan trọng cho tìm kiếm, nhưng có thể quan trọng khi điều tra lỗi nhập, hiển thị bản nháp hoặc thực hiện chức năng hoàn tác.

### Hiển thị lại bản gốc có nghĩa là giữ nguyên nội dung, không bỏ qua an toàn đầu ra

Khi trình bày văn bản do người dùng cung cấp trên HTML, terminal, CSV hoặc log, mỗi môi trường có quy tắc escape riêng. **Giữ bản gốc không có nghĩa ghép thẳng nội dung chưa được escape vào HTML hoặc câu lệnh SQL.** Bạn có thể bảo toàn original trong mô hình dữ liệu, rồi dùng cơ chế render an toàn của giao diện, tham số hóa câu lệnh SQL hoặc công cụ xuất dữ liệu đúng định dạng.

Tương tự, không tự động ghi nguyên văn token, mật khẩu hay dữ liệu cá nhân vào log chỉ để so sánh. Hãy kiểm tra yêu cầu lưu trữ và chỉ ghi thông tin thực sự cần thiết.

## 7. StringBuilder và bộ đệm mutable: khác với việc giữ String gốc

String bất biến cho phép bạn giữ hai tham chiếu đến cùng đối tượng mà không sợ một lời gọi replace()/strip() làm đối tượng ban đầu thay đổi:

~~~java
String a = "Java";
String b = a;

a = a.concat(" 17");

System.out.println(a); // Java 17
System.out.println(b); // Java
~~~

Với **StringBuilder**, hai biến có thể trỏ đến cùng một đối tượng mutable:

~~~java
StringBuilder first = new StringBuilder("Java");
StringBuilder second = first;

first.append(" 17");

System.out.println(first);  // Java 17
System.out.println(second); // Java 17
~~~

Vì vậy, giữ thêm một **tham chiếu** đến StringBuilder **không phải** là giữ snapshot nội dung. Nếu đang xây dựng bằng StringBuilder và cần giữ một phiên bản ổn định, hãy gọi toString() tại thời điểm cần chụp lại:

~~~java
StringBuilder draft = new StringBuilder("version 1");
String snapshot = draft.toString();

draft.replace(0, draft.length(), "version 2");

System.out.println(snapshot); // version 1
System.out.println(draft);    // version 2
~~~

String snapshot giữ giá trị bất biến; những thay đổi sau đó trong builder không làm snapshot đổi theo.

Tuy nhiên, **không giả định rằng bản String luôn có thể tái tạo nguyên trạng toàn bộ đầu vào dạng byte**. Nếu dữ liệu nguồn là tệp UTF-8, việc giải mã, chuẩn hóa newline hoặc xử lý ký tự không hợp lệ có thể khiến một String không còn đủ để khôi phục byte ban đầu. Nếu yêu cầu lưu vết ở cấp byte, phải bảo toàn byte nguồn theo cơ chế phù hợp, độc lập với bản String được dùng để thao tác văn bản.

## 8. Quy trình xử lý đầu vào có thể kiểm tra lại

Một luồng xử lý thường dễ bảo trì khi chia rõ các bước:

1. **Nhận đầu vào:** xác định dữ liệu có thể null hay không, có cần giữ nguyên số dấu cách, newline và biểu diễn Unicode hay không.
2. **Giữ raw:** chỉ lưu đúng phạm vi yêu cầu, với chính sách bảo mật và thời gian giữ phù hợp.
3. **Biến đổi vào biến mới:** gọi strip(), replace(), normalize() hoặc chuyển hoa/thường tùy quy tắc, không gán đè biến raw nếu còn cần đối chiếu.
4. **Kiểm tra:** xác thực bản raw, bản biến đổi hoặc cả hai tùy hợp đồng nghiệp vụ; chẳng hạn mã đăng nhập có thể đòi hỏi cú pháp gốc rất nghiêm ngặt.
5. **Sử dụng đúng phiên bản:** raw để đối chiếu, display để hiển thị, searchKey để tìm kiếm. Đừng vô tình thay searchKey cho raw trong chức năng “hiển thị lại”.
6. **Làm rõ quyền lưu trữ:** tránh giữ nhiều bản chứa dữ liệu nhạy cảm khi không cần.

Ví dụ hàm nhận đầu vào có thể null:

~~~java
record DisplayValue(String original, String visible) {}

static DisplayValue prepareDisplay(String value) {
    if (value == null) {
        return new DisplayValue(null, null);
    }
    return new DisplayValue(value, value.strip());
}
~~~

Đây là **đoạn mã minh họa**, cần đặt trong một lớp Java. Nó phân biệt null với chuỗi rỗng và giữ được cả bản raw lẫn bản đã strip. Một record riêng giúp tránh đặt hai phiên bản vào hai biến dễ bị truyền nhầm trong nhiều phương thức.

Một thiết kế khác là giữ raw trong đối tượng bất biến và **tính ra bản đã chuẩn hóa khi cần**, thay vì lưu tất cả phiên bản. Lựa chọn dựa trên tần suất truy cập, chi phí chuẩn hóa, tính ổn định của chính sách chuẩn hóa và yêu cầu lưu trữ. Quan trọng là giá trị raw vẫn có thể truy cập khi nghiệp vụ thật sự cần.

## 9. Những lỗi thường gặp

1. **Tưởng String được sửa tại chỗ:** gọi raw.strip() hoặc raw.replace() không làm raw đổi; phải dùng giá trị trả về cho bản đã biến đổi.
2. **Gán đè biến trước khi lưu raw:** text = text.strip() hợp lệ nhưng mất tham chiếu ban đầu qua text; nếu cần so sánh hãy giữ rawInput và normalizedInput riêng.
3. **Cho rằng hai tham chiếu String khác nhau là không bằng nhau:** sử dụng equals() để so nội dung thay vì ==. Hai bản có nội dung giống nhau có thể là cùng hoặc khác đối tượng.
4. **Tự động strip mọi đầu vào:** khoảng trắng có thể là dữ liệu cần bảo toàn, đặc biệt với mật khẩu, văn bản tự do hoặc chuỗi định dạng.
5. **Dùng bản searchKey để hiển thị:** chuẩn hóa để tìm kiếm có thể làm mất hoa/thường, dấu hoặc định dạng ban đầu; hiển thị từ bản gốc/bản display đúng chính sách.
6. **Tưởng normalize Unicode luôn giữ nguyên length():** NFC có thể gộp một chuỗi code point thành biểu diễn khác; ví dụ "Cafe\u0301" và "Café".
7. **Bỏ qua null:** raw.strip() khi raw null gây NullPointerException. Kiểm tra null trước mọi lời gọi instance.
8. **Giữ tham chiếu StringBuilder để chụp nội dung:** builder là mutable; muốn snapshot văn bản hãy gọi toString().
9. **Nhầm giữ String với giữ byte nguồn:** String là biểu diễn văn bản sau giải mã; yêu cầu khôi phục tệp chính xác byte cần giữ byte gốc.
10. **Tự lưu tất cả raw input vào log:** lưu bản gốc có thể tăng nguy cơ lộ dữ liệu nhạy cảm; chỉ lưu trong thời hạn và phạm vi thật sự cần.
11. **Giả định mọi trường hợp tìm kiếm đều dùng cùng quy tắc chuẩn hóa:** Locale.ROOT và NFC là các lựa chọn thường gặp cho khóa kỹ thuật, nhưng không thay thế chính sách collation/ngôn ngữ phù hợp.
12. **Dùng bản raw và normalized không nhất quán trong so sánh:** khi chính sách yêu cầu chuẩn hóa, cả hai phía phải theo cùng một quy trình rõ ràng.

## 10. Câu hỏi tự kiểm tra

Với đoạn mã:

~~~java
String raw = "  JaVa  ";
String display = raw.strip();
String key = display.toLowerCase(java.util.Locale.ROOT);
~~~

Hãy dự đoán:

1. raw và display lần lượt có nội dung gì?
2. raw.length() và display.length() bằng bao nhiêu?
3. raw.equals(display) trả về gì? Vì sao?
4. key có nội dung gì? Nếu chỉ lưu key, có thể biết chắc cách viết hoa của raw không?
5. Nếu sau đó gán raw = key, đối tượng chứa "  JaVa  " có bị sửa không?
6. Vì sao muốn giữ snapshot StringBuilder phải gọi toString(), không chỉ tạo biến tham chiếu thứ hai?

**Đáp án:**

1. raw vẫn là **"  JaVa  "**, display là **"JaVa"**.
2. raw có độ dài **8** (hai dấu cách + bốn chữ + hai dấu cách); display có độ dài **4**.
3. **false**, vì nội dung hai chuỗi khác nhau.
4. key là **"java"**; chỉ từ đó không khôi phục chắc chắn cách viết hoa và khoảng trắng gốc.
5. **Không**. Lệnh gán chỉ khiến biến raw trỏ sang String khác, không thay đổi nội dung đối tượng cũ. Tuy nhiên nếu không còn tham chiếu nào khác, ứng dụng có thể không truy cập lại được bản gốc.
6. Hai biến tham chiếu cùng StringBuilder vẫn quan sát các thay đổi trên một đối tượng mutable; toString() tạo giá trị String bất biến tại thời điểm chụp.

**Ghi nhớ:** Khi văn bản được biến đổi để phục vụ tìm kiếm, chuẩn hóa hoặc hiển thị, hãy **giữ chuỗi đầu vào theo đúng nhu cầu nghiệp vụ và tạo bản kết quả riêng**. Tính bất biến của String bảo vệ nội dung từng giá trị; còn **việc lưu được bản gốc, chọn đúng phiên bản khi sử dụng và quản lý dữ liệu nhạy cảm** là trách nhiệm của thiết kế chương trình.
