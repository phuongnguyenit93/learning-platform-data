# Giữ nguyên câu hoàn chỉnh để người dịch thay đổi trật tự trong Java

## 1. Vấn đề: ghép từng mảnh câu làm mất khả năng dịch đúng

Khi xây ứng dụng đa ngôn ngữ, một lỗi thiết kế thường gặp là chia thông điệp thành các mảnh nhỏ, dịch từng mảnh rồi **ghép lại bằng code**:

```java
// CÁCH KHÔNG NÊN DÙNG
String message = bundle.getString("actor") + " "
        + actor + " "
        + bundle.getString("sent") + " "
        + count + " "
        + bundle.getString("files") + " "
        + bundle.getString("to") + " "
        + receiver + ".";
```

Thoạt nhìn đây là cách tái sử dụng từ dịch: có sẵn “sent”, “files”, “to”, chỉ cần thay tên người nhận và số lượng. Nhưng ngữ pháp các ngôn ngữ **không phải phép nối một-một theo trật tự tiếng Anh**.

Ví dụ cùng một sự kiện “Lan gửi ba tệp cho Minh” có thể được trình bày theo các thứ tự khác nhau:

- Tiếng Anh: **Lan sent 3 files to Minh.**
- Tiếng Việt theo hướng nhấn mạnh người nhận: **Minh đã nhận 3 tệp do Lan gửi.**

Các chuỗi trên không chỉ khác từng từ. **Chủ ngữ, động từ, vị trí số lượng, giới từ, sắc thái và trật tự thông tin** đều có thể được tổ chức lại. Một khi code Java khóa sẵn thứ tự mảnh như `actor + sent + count + files + to + receiver`, người dịch **không có quyền chuyển “Minh” lên đầu câu** mà không sửa chương trình.

**Quy tắc trọng tâm:** mỗi thông điệp giao diện có ý nghĩa **một câu hoàn chỉnh** nên được lưu dưới dạng **một khóa tài nguyên** chứa **một mẫu câu hoàn chỉnh**, còn các dữ liệu thay đổi như tên, số lượng, thời gian được truyền qua **placeholder có vị trí hoặc tên rõ ràng**. Người dịch có thể chuyển placeholder đến vị trí ngữ pháp thích hợp.

Trong Java Core, có thể sử dụng:

- `ResourceBundle` để lấy mẫu câu theo `Locale`.
- `MessageFormat` để thay các placeholder như `{0}`, `{1}`, `{2}` và định dạng số/ngày theo locale.
- Bộ quy tắc plural/select nâng cao như ICU MessageFormat nếu ứng dụng cần chọn biến thể ngữ pháp phức tạp.

Mục tiêu không chỉ là “hết lỗi ngữ pháp”: cách thiết kế này giúp **bản dịch có đủ ngữ cảnh, dễ kiểm thử, có thể được biên dịch/kiểm tra tự động và thay đổi mà không sửa code**.

## 2. Câu hoàn chỉnh là đơn vị dịch, không phải từ rời

Hãy so sánh hai cách thiết kế:

| Nội dung | Ghép mảnh trong Java | Mẫu câu hoàn chỉnh trong resource |
| --- | --- | --- |
| Đơn vị dịch | Các từ “sent”, “files”, “to” | Toàn bộ “{0} sent {1} files to {2}.” |
| Trật tự | Cố định trong code | Người dịch sắp xếp placeholder |
| Ngữ cảnh | Dịch giả chỉ thấy từ rời | Thấy đầy đủ ai làm gì cho ai |
| Số nhiều | Dễ áp một từ “files” cho mọi số lượng | Có chỗ lựa chọn mẫu theo số |
| Dấu câu/khoảng trắng | Nằm rải trong code và nhiều resource | Thuộc mẫu câu |
| Kiểm thử | Phải dựng nhiều tổ hợp ghép mảnh | Có thể format từng thông điệp với tham số mẫu |
| Bảo trì | Đổi cách diễn đạt có thể cần sửa code | Thường đổi bản dịch trong resource |

Với câu tiếng Anh:

```properties
upload={0} sent {1,number,integer} files to {2}.
```

và tiếng Việt:

```properties
upload={2} đã nhận {1,number,integer} tệp do {0} gửi.
```

Ngữ nghĩa placeholder được quy định cố định:

- `{0}`: **người gửi**.
- `{1}`: **số lượng tệp**.
- `{2}`: **người nhận**.

Cả hai locale dùng **cùng bộ đối số**, nhưng bản dịch sắp xếp lại vị trí các đối số theo ngữ pháp. `MessageFormat` không biết “người gửi” là gì; chính **hợp đồng lập trình và ghi chú cho người dịch** phải giải thích được ý nghĩa của chúng.

Nếu chỉ dùng `String.format("%s sent %d files to %s", ...)` với format string để trong source Java, bạn vẫn bị ràng buộc trật tự tại call site. Có thể dùng `Formatter` với positional argument syntax, nhưng đối với workflow bản địa hóa chuẩn Java, `ResourceBundle + MessageFormat` thường thể hiện rõ trách nhiệm của từng lớp hơn.

## 3. Thiết kế một thông điệp từ dữ liệu có nghĩa

Thay vì phân tích mẫu câu tiếng Anh thành các mảnh ngôn ngữ, hãy bắt đầu từ **một sự kiện/dữ liệu có nghĩa**:

```text
Event: FILES_SENT
senderName = "Lan"
fileCount  = 3
receiverName = "Minh"
```

Đây là **mô tả dữ liệu**, không phải syntax Java. Giao diện chọn một message key, ví dụ `notification.filesSent`, rồi đưa ba giá trị vào bộ format.

Một nguyên tắc thiết kế hữu ích: **đối số là dữ liệu, mẫu câu là ngôn ngữ**.

- `senderName` và `receiverName` là dữ liệu ứng dụng: giá trị thay đổi giữa từng request.
- `fileCount` là dữ liệu số: locale có thể quyết định cách hiển thị `1,000` hay `1.000`, và bản dịch quyết định cấu trúc số ít/nhiều.
- Dấu câu, từ nối, vị trí tham số và toàn bộ văn phong thuộc bản dịch.
- Thông điệp chỉ có nghĩa trong ngữ cảnh cụ thể: “Open” là động từ mở cửa sổ hay tính từ trạng thái đang mở? Cần dùng **khóa và ghi chú phù hợp**.

Không đặt toàn bộ câu như `"Lan gửi 3 tệp cho Minh"` vào một cột dữ liệu rồi dịch theo phép tìm-thay tên, vì các giá trị động có thể trùng từ, chứa dấu câu hoặc mang cấu trúc khó tách.

## 4. ResourceBundle: để mỗi locale sở hữu nguyên câu

Với ứng dụng classpath thường, có thể đặt cấu trúc:

```text
src/main/
├── java/
│   └── com/example/app/WholeSentenceDemo.java
└── resources/
    └── com/example/i18n/
        ├── Messages.properties
        ├── Messages_en.properties
        └── Messages_vi.properties
```

Base name dùng trong code là `"com.example.i18n.Messages"`. Với Java 17+, các file property resource bundle có thể lưu UTF-8 trực tiếp (theo cơ chế `PropertyResourceBundle` từ Java 9; không nhầm với `Properties.load(InputStream)` vốn có quy tắc byte khác).

### 4.1. File mặc định Messages.properties

```properties
notification.filesSent={0} sent {1,number,integer} files to {2}.
invitation={0} invited {1} to {2}.
fallback.help=Contact support.
```

File gốc `Messages.properties` giúp có bản fallback khi locale chưa được dịch hoặc một số key còn thiếu. Nhưng fallback không phải giấy phép để vô tình để bản giao diện đa ngôn ngữ hiển thị các câu pha trộn; nên kiểm tra độ phủ bản dịch ở CI.

### 4.2. Messages_en.properties

```properties
notification.filesSent={0} sent {1,number,integer} files to {2}.
invitation={0} invited {1} to {2}.
```

Người dịch tiếng Anh có toàn câu và có thể đổi giọng điệu/dấu câu nếu phù hợp sản phẩm. Các placeholder vẫn tham chiếu đến dữ liệu đã được tài liệu hóa.

### 4.3. Messages_vi.properties

```properties
notification.filesSent={2} đã nhận {1,number,integer} tệp do {0} gửi.
invitation={1} được {0} mời tham gia {2}.
```

Bản tiếng Việt:

- Đưa người nhận `{2}` lên đầu thông điệp gửi tệp.
- Đưa người được mời `{1}` lên trước người mời `{0}`.
- Chọn cấu trúc tự nhiên hơn mà không thay đổi code Java.
- Có thể dùng ký tự tiếng Việt ngay trong file UTF-8.

**Không cần dịch placeholder**: `{0}`, `{1}` và `{2}` là ký hiệu của hệ thống. Người dịch có thể di chuyển và lặp lại chúng khi có lý do, nhưng không được tự ý đổi chỉ số hoặc bỏ tham số bắt buộc mà không kiểm tra. Giá trị `Locale` dùng để chọn file cũng nên được truyền tường minh, không phụ thuộc locale mặc định của server.

## 5. Chương trình Java 17+ độc lập với resources: đảo trật tự mà không đổi code

Tạo file **`src/main/java/com/example/app/WholeSentenceDemo.java`**:

```java
package com.example.app;

import java.text.MessageFormat;
import java.util.Locale;
import java.util.ResourceBundle;

public class WholeSentenceDemo {
    private static String format(
            Locale locale, String key, Object... args) {

        ResourceBundle messages = ResourceBundle.getBundle(
                "com.example.i18n.Messages", locale);
        String pattern = messages.getString(key);
        MessageFormat formatter = new MessageFormat(pattern, locale);
        return formatter.format(args);
    }

    public static void main(String[] args) {
        Locale english = Locale.US;
        Locale vietnamese = Locale.forLanguageTag("vi-VN");

        String enInvite = format(english, "invitation",
                "Lan", "Minh", "Java Club");
        String viInvite = format(vietnamese, "invitation",
                "Lan", "Minh", "Câu lạc bộ Java");

        String enUpload = format(english, "notification.filesSent",
                "Lan", 3, "Minh");
        String viUpload = format(vietnamese, "notification.filesSent",
                "Lan", 3, "Minh");

        System.out.println("EN invite: " + enInvite);
        System.out.println("VI invite: " + viInvite);
        System.out.println("EN upload: " + enUpload);
        System.out.println("VI upload: " + viUpload);

        System.out.println("Fallback: " +
                format(vietnamese, "fallback.help"));
    }
}
```

Đây là chương trình Java đầy đủ, nhưng cần **ba file `.properties`** ở classpath đúng như mục 4. Không chỉ copy `.java` rồi chạy khi classpath chưa chứa resources.

Với Java 17+, có thể biên dịch thủ công từ gốc dự án:

Linux/macOS:

```bash
javac -encoding UTF-8 -d out src/main/java/com/example/app/WholeSentenceDemo.java
java -cp "out:src/main/resources" com.example.app.WholeSentenceDemo
```

Windows PowerShell:

```powershell
javac -encoding UTF-8 -d out src/main/java/com/example/app/WholeSentenceDemo.java
java -cp "out;src/main/resources" com.example.app.WholeSentenceDemo
```

Output khi chạy đúng resource và console có thể hiển thị Unicode:

```text
EN invite: Lan invited Minh to Java Club.
VI invite: Minh được Lan mời tham gia Câu lạc bộ Java.
EN upload: Lan sent 3 files to Minh.
VI upload: Minh đã nhận 3 tệp do Lan gửi.
Fallback: Contact support.
```

### Từng bước diễn ra như thế nào?

1. `format` nhận `Locale`, một **key** và các đối số có ý nghĩa đã xác định.
2. `ResourceBundle.getBundle` chọn tài nguyên tiếng Anh/tiếng Việt.
3. `getString(key)` trả **toàn bộ mẫu câu**.
4. `new MessageFormat(pattern, locale)` phân tích pattern với locale phù hợp; format số/ngày sẽ theo locale của formatter.
5. `formatter.format(args)` gán dữ liệu theo **chỉ số placeholder**, không dựa vào thứ tự xuất hiện trong bản dịch.
6. Ở câu tiếng Việt, `{1}` có thể xuất hiện trước `{0}` — không cần đổi thứ tự đối số của Java.
7. `fallback.help` không nằm trong file `_vi`, nên được tra từ bundle gốc trong parent chain.

Lưu ý output mã nguồn này dùng những câu có chủ đích đơn giản; đối với hệ thống thực, cần có chuyên gia ngôn ngữ kiểm tra bản dịch cuối cùng. Điều quan trọng về kỹ thuật là **người dịch được quyền kiểm soát toàn bộ cấu trúc câu**.

## 6. MessageFormat đánh số placeholder như thế nào?

`java.text.MessageFormat` sử dụng placeholder dạng:

```text
{0}
{1}
{2}
{0,number}
{1,number,integer}
{2,date,short}
{3,time,medium}
```

Chỉ số bắt đầu từ **0** và ứng với `Object[]` được truyền. Phần type/style tùy chọn quyết định cách định dạng giá trị.

Ví dụ:

```java
String english = "{0} sent {1,number,integer} files to {2}.";
String vietnamese = "{2} đã nhận {1,number,integer} tệp do {0} gửi.";

Object[] values = {"Lan", 3, "Minh"};

String en = new MessageFormat(english, Locale.US).format(values);
String vi = new MessageFormat(
        vietnamese, Locale.forLanguageTag("vi-VN"))
        .format(values);
```

Đây là **snippet** có các import `java.text.MessageFormat`, `java.util.Locale`. Kết quả:

```text
Lan sent 3 files to Minh.
Minh đã nhận 3 tệp do Lan gửi.
```

Khi đổi mẫu từ `{0} ... {2}` sang `{2} ... {0}`, code vẫn truyền `{"Lan",3,"Minh"}`. Đây là điểm ưu việt so với nối string cứng theo một ngôn ngữ.

### Có thể lặp placeholder

Một bản dịch có thể cần nhắc tên người nhận hai lần, ví dụ:

```properties
notice={0}, vui lòng kiểm tra tài khoản của {0}.
```

`MessageFormat` sẽ dùng lại cùng giá trị cho hai chỗ `{0}`. **Không cần truyền tham số trùng lặp** chỉ để khớp số lần placeholder xuất hiện.

### Không tự ý chuyển đổi ý nghĩa chỉ số

Trong code có thể chọn thứ tự logical arguments bất kỳ, nhưng phải tài liệu hóa:

| Chỉ số | Ý nghĩa | Kiểu Java | Ví dụ |
| --- | --- | --- | --- |
| `{0}` | Người gửi | `String` | `"Lan"` |
| `{1}` | Số tệp | `Integer`/`Number` | `3` |
| `{2}` | Người nhận | `String` | `"Minh"` |

Bản dịch **được đổi trật tự xuất hiện**, nhưng không được tùy tiện biến `{1}` thành người nhận. Nếu người dịch cần đổi loại dữ liệu hay thêm đối số mới, đây là thay đổi **hợp đồng message schema**, cần cập nhật code và kiểm thử.

## 7. Những thành phần phải nằm trong câu dịch

Đừng cố giữ một “khung tiếng Anh” trong code Java rồi chỉ đưa một số danh từ/động từ vào resource. Những thành phần sau nên thuộc **mẫu câu hoàn chỉnh** nếu có vai trò ngôn ngữ:

- **Trật tự từ:** ai, làm gì, cho ai, ở đâu.
- **Từ nối/giới từ:** “to”, “from”, “by”, “ở”, “từ”.
- **Mạo từ và cấu trúc xác định:** “a/an/the”, dạng phù hợp ngữ pháp đích.
- **Dấu câu:** dấu phẩy, dấu chấm, dấu hỏi, dấu chấm than, dấu ngoặc phù hợp văn bản.
- **Khoảng trắng:** số lượng và vị trí do cách viết của từng ngôn ngữ quyết định, không cộng thêm `" "` giữa các mảnh.
- **Sắc thái/văn phong:** câu chủ động, bị động, lịch sự/trang trọng, độ ngắn của lời nhắn.
- **Chỉ thị ngữ pháp:** số ít/số nhiều, giống/ngôi/cách nếu ngôn ngữ đích yêu cầu.
- **Vị trí thông tin động:** placeholder ở đúng chỗ sau khi dịch.

Nếu giao diện có câu “You have ...” với số lượng, đừng chỉ dịch riêng “You have” và “items” rồi nối lại. Tiếng Việt, Anh, Ả Rập, Nga, Ba Lan… có thể dùng các cấu trúc và biến thể số nhiều khác nhau.

**Ngược lại**, không phải mọi chuỗi UI đều phải dài một câu. Nhãn nút độc lập như “Lưu”, tiêu đề “Cài đặt”, danh mục “Tài khoản” vẫn là **đơn vị dịch phù hợp** nếu chúng độc lập về mặt chức năng và có ngữ cảnh. Quy tắc “giữ nguyên câu” nhắm vào **những thông điệp có quan hệ ngữ pháp**, không ép gộp mọi label không liên quan thành một resource key.

## 8. Khi số lượng thay đổi: không ghép từ số ít/số nhiều

Mẫu:

```properties
notification.filesSent={0} sent {1,number,integer} files to {2}.
```

đủ để minh họa **đảo trật tự** nhưng **chưa xử lý ngữ pháp số ít tiếng Anh**: `1 files` không tự nhiên. Không nên sửa bằng cách ghép thêm `file + (count == 1 ? "" : "s")` vào code, bởi quy tắc plural có thể phức tạp hơn trong các ngôn ngữ khác.

### 8.1. Mẫu theo nhánh khi bài toán đơn giản

Với ngôn ngữ/trường hợp thực sự chỉ cần vài nhánh, ứng dụng có thể chọn **một khóa câu hoàn chỉnh** theo count:

```properties
# en (minh họa)
files.one={0} sent one file to {2}.
files.other={0} sent {1,number,integer} files to {2}.
```

và ở `Messages_vi.properties`, mỗi nhánh cũng nên là **một mẫu câu hoàn chỉnh**:

```properties
files.one={2} đã nhận một tệp do {0} gửi.
files.other={2} đã nhận {1,number,integer} tệp do {0} gửi.
```

Đoạn properties trên chỉ là **mẫu dữ liệu**; code phải chọn đúng key, truyền đủ các đối số, và thực hiện quy tắc số nhiều theo **locale** đích.

### 8.2. Không giả định chỉ có one/other

Nhiều ngôn ngữ có nhóm plural như zero, one, two, few, many, other; cách chọn nhóm thường liên quan cả giá trị và chữ số phần lẻ. Đối với sản phẩm đa ngôn ngữ nghiêm túc, có thể cân nhắc **ICU MessageFormat** hoặc một hệ thống message plural/select dựa trên CLDR. Đây là công cụ khác với `java.text.MessageFormat` chuẩn của Java SE.

`ChoiceFormat` trong Java SE có thể chọn thông điệp theo **khoảng số**, và phối hợp với `MessageFormat` trong những trường hợp phù hợp. Tuy nhiên `ChoiceFormat` không tự cung cấp đầy đủ các nhóm plural CLDR; đừng quảng cáo nó là giải pháp ngữ pháp số nhiều cho mọi locale.

### 8.3. Giữ cả nhánh điều kiện là một câu dịch

Ngay cả khi chọn key trong code:

```java
String key = (count == 1) ? "files.one" : "files.other";
```

đừng chỉ trả một danh từ `file/files` rồi ghép vào câu đã bị đóng đinh trật tự. Mỗi nhánh nên chứa **toàn thông điệp**, để người dịch có thể thay đổi cấu trúc độc lập. Khi ứng dụng mở rộng ra nhiều ngôn ngữ, chuyển việc chọn plural category sang một bộ xử lý đúng quy tắc locale.

## 9. Số, ngày và tiền phải được format theo locale

Một ưu điểm khác của `MessageFormat` là nó cho phép đặt định dạng ngay trong mẫu:

```properties
summary={0} đã tạo {1,number,integer} báo cáo.
amount=Giá trị còn lại: {0,number,currency}.
reminder=Hạn chót: {0,date,long}.
```

Chẳng hạn `{1,number,integer}` sử dụng định dạng số nguyên của `MessageFormat` theo locale; `{0,number,currency}` định dạng tiền theo ngữ cảnh locale. Nếu **loại tiền giao dịch** không được quyết định bởi locale người dùng, cần thiết kế thêm policy Currency tường minh thay vì dựa vào currency mặc định của vùng.

Một đoạn minh họa chạy độc lập là:

```java
import java.text.MessageFormat;
import java.util.Locale;

public class MessageNumberDemo {
    public static void main(String[] args) {
        String pattern =
                "{0} sent {1,number,integer} files to {2}.";
        Object[] values = {"Lan", 1234, "Minh"};

        String result = new MessageFormat(
                pattern, Locale.US).format(values);
        System.out.println(result);
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 MessageNumberDemo.java
java MessageNumberDemo
```

Stdout với `Locale.US`:

```text
Lan sent 1,234 files to Minh.
```

Code không ghép `count.toString()` vào vị trí được định dạng, giúp các nhóm chữ số và cách hiển thị có thể thay đổi theo locale. Khi định dạng ngày/giờ, nhớ rằng **Locale chỉ quyết định cách viết**, còn múi giờ của thời điểm hiển thị phải được chọn tường minh theo ngữ cảnh. `MessageFormat` truyền thống cũng gắn với một số kiểu ngày giờ cũ; khi dùng `java.time` hiện đại, có thể định dạng ngày giờ theo `DateTimeFormatter` hoặc adapter rõ ràng trước khi truyền vào mẫu. Không ngầm đổi `Instant` sang ngày theo default timezone của server.

Vẫn phải phân biệt formatting dữ liệu với ngữ pháp câu: dấu nhóm số có thể tự xử lý, nhưng số lượng tác động đến plural/case của từ xung quanh thì cần mẫu message có biến thể thích hợp.

## 10. Dấu nháy và dấu ngoặc nhọn trong MessageFormat

`MessageFormat` có cú pháp pattern riêng:

- `{0}`, `{1}`… là các placeholder.
- Dấu nháy đơn `'` dùng để **quote phần chữ literal** trong pattern.
- Muốn in **một dấu nháy đơn** thông thường, trong nhiều trường hợp cần viết `''` (hai dấu nháy đơn).
- Muốn in dấu ngoặc nhọn là nội dung literal, cần quote phù hợp với `MessageFormat`.

Ví dụ lỗi thường gặp:

```properties
# CÓ THỂ SAI: dấu nháy đơn làm thay đổi cách parse pattern
owner=It's {0}'s book.
```

Mẫu đúng với cú pháp MessageFormat:

```properties
owner=It''s {0}''s book.
```

Chương trình Java 17+ độc lập:

```java
import java.text.MessageFormat;
import java.util.Locale;

public class MessageQuoteDemo {
    public static void main(String[] args) {
        MessageFormat format = new MessageFormat(
                "It''s {0}''s book.", Locale.US);

        System.out.println(format.format(
                new Object[]{"Lan"}));
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 MessageQuoteDemo.java
java MessageQuoteDemo
```

Stdout:

```text
It's Lan's book.
```

**Cảnh báo:** dấu `'` trong câu tiếng Anh, tiếng Pháp, các ngôn ngữ dùng apostrophe và trong những ví dụ có `{braces}` là nguồn lỗi bản địa hóa khá phổ biến. Khi tài nguyên được chuyển cho dịch giả, cần hướng dẫn cú pháp format rõ ràng và **tự động parse/format tất cả bản dịch** trong test để phát hiện mẫu không hợp lệ.

Không thay các ký tự `{0}` bằng regex hoặc String.replace tùy tiện chỉ để tránh cú pháp MessageFormat. Cách đó bỏ qua việc định dạng số, escape và validation của mẫu, còn có thể tạo lỗi khi giá trị động chứa chuỗi trông giống placeholder.

## 11. Hợp đồng dịch thuật: ghi chú ngữ cảnh cho translator

Một câu đúng ngữ pháp đòi hỏi dịch giả hiểu **ai, làm gì, cho ai**. Resource key và placeholder number một mình có thể chưa đủ.

Bảng thông tin nên đi kèm message catalog:

| Trường | Ví dụ |
| --- | --- |
| Key | `notification.filesSent` |
| Nguồn | `{0} sent {1,number,integer} files to {2}.` |
| Bối cảnh | Thông báo một người gửi tệp tới người nhận trong ứng dụng |
| `{0}` | Tên hiển thị người gửi; có thể có khoảng trắng hoặc ký tự Unicode |
| `{1}` | Số lượng tệp, kiểu `Number`, không âm |
| `{2}` | Tên hiển thị người nhận |
| Khu vực UI | Notification list và detail |
| Yêu cầu style | Văn phong trung tính, không thêm thông tin nghiệp vụ |
| Plural | Cần nhánh số lượng phù hợp locale khi sản phẩm hỗ trợ count=1 |
| Rich text | Chỉ dữ liệu thuần; không nhúng HTML tùy ý |

Nếu ứng dụng sử dụng định dạng XLIFF, ARB, ICU message catalog hoặc hệ thống quản lý dịch thuật khác, ghi chú nên được lưu trong metadata tương ứng. Đối với `.properties` đơn giản, comment có thể giúp người dịch trong repository, nhưng không phải hệ thống QA nào cũng tự hiểu comment; hợp đồng placeholder nên được lưu nơi pipeline dịch có thể kiểm tra.

**Không dùng một key cho hai ngữ cảnh khác nghĩa chỉ vì tiếng Anh trùng chữ.** Ví dụ `"Open"` là động từ trên nút và `"Open"` là trạng thái phiếu hỗ trợ có thể dịch khác nhau. Hãy chọn key riêng theo mục đích như `action.openDocument` và `status.open`.

## 12. Khi có UI component ở giữa câu

Một tình huống khó là:

```text
I agree to [Terms] and [Privacy Policy].
```

Nếu code cố định thứ tự các thành phần:

```java
label("I agree to") + link("Terms") + label("and")
        + link("Privacy Policy")
```

bản dịch mất quyền di chuyển các link. Với một số ngôn ngữ, thứ tự mệnh đề, vị trí tên tài liệu và cách nối có thể khác.

Cách thiết kế nên dựa vào **thông điệp hoàn chỉnh chứa các vùng placeholder có kiểu**:

```text
agree=I agree to {termsLink} and {privacyLink}.
```

Dòng trên là **minh họa một hệ thống message hỗ trợ named placeholders/rich text**, **không phải** pattern hợp lệ có thể đưa thẳng vào `java.text.MessageFormat` chuẩn, vì Java SE MessageFormat thông thường sử dụng **chỉ số số nguyên** như `{0}`.

Với Java SE, có thể dùng thông điệp số vị trí và một tầng UI renderer để xác định **text span và component link**; hoặc dùng một message framework hỗ trợ rich-text placeholders có cấu trúc. Điều quan trọng là:

1. Toàn câu do bản dịch sở hữu, kể cả trật tự các link.
2. Placeholder chỉ tới **component được khai báo** chứ không chứa HTML ngẫu nhiên.
3. Văn bản link có nhãn truy cập (accessibility) đúng ngôn ngữ.
4. Kết quả render được escape/sanitize theo UI framework, không biến bản dịch hay dữ liệu người dùng thành HTML không kiểm soát.
5. Không cắt chuỗi đã format để dự đoán vị trí link bằng cách đếm các byte/ký tự của câu nguồn.

Nếu yêu cầu dùng **hai button/checkbox riêng** trong layout, không phải lúc nào một câu duy nhất cũng phù hợp về semantic HTML hoặc accessibility. Khi đó thiết kế lại cấu trúc UI để message vẫn có ngữ cảnh dịch đầy đủ mà không trộn logic tương tác vào chuỗi text thô.

## 13. Không để formatting che lỗi bảo mật

Một message pattern và một giá trị động có vai trò khác nhau:

```java
String pattern = bundle.getString("notification.filesSent");
Object[] arguments = {senderName, fileCount, receiverName};
String display = new MessageFormat(
        pattern, locale).format(arguments);
```

Đây là snippet; `senderName` và `receiverName` là dữ liệu, không được mặc định coi là pattern. Nếu `senderName` chứa `"{0}"`, việc truyền nó làm **đối số** giúp tránh tự parse nó như template. Ngược lại, nếu code cho phép dữ liệu người dùng tự do trở thành `pattern`, người dùng có thể gây lỗi cú pháp hoặc làm rối định dạng, ngay cả khi ứng dụng không có “code execution”.

**Định dạng message không tự escape HTML, SQL hoặc JavaScript.** Nếu đưa kết quả lên trang web, renderer phải escape theo ngữ cảnh; nếu đưa tên vào log, phải có chính sách chống log injection; nếu đưa vào SQL, phải dùng prepared statements chứ không ghép câu.

Không sử dụng `MessageFormat` để tự động ghép HTML bằng cách chèn các fragment đã được đánh dấu là “safe” nếu hợp đồng UI không bảo đảm escaping và cấu trúc. Với rich text, dùng framework cấp UI có placeholder có kiểu.

## 14. Tránh biến một câu thành nhiều khóa vì “tái sử dụng”

Một pattern chống lại khả năng dịch đúng:

```properties
message.prefix=You have
message.quantity=files
message.suffix=remaining.
```

và Java:

```java
String result = prefix + " " + count + " " + noun + " " + suffix;
```

Người dịch không thể hoán đổi nhiều thành phần quan trọng; nếu dùng chung `message.quantity` cho hàng chục câu, một thay đổi số nhiều/giống/biến cách có thể gây lỗi ở nơi khác.

Thay bằng mẫu câu:

```properties
storage.remaining=You have {0,number,integer} files remaining.
```

Bản tiếng Việt có thể là:

```properties
storage.remaining=Bạn còn {0,number,integer} tệp.
```

Dù các câu hiện có trật tự tương tự, bản dịch vẫn sở hữu **trọn câu** và có thể thay đổi về sau.

### Khi nào tái sử dụng là hợp lý?

Tái sử dụng **cùng một message key** chỉ nên xảy ra khi các ngữ cảnh thật sự giống nhau về:

- hành động/ngữ nghĩa;
- vai trò người nói/người nghe;
- mức độ trang trọng;
- số lượng và loại tham số;
- quy tắc số ít/số nhiều;
- vị trí/lối viết phù hợp với loại giao diện.

Đừng tái sử dụng chỉ vì cả hai nơi đều chứa từ “Save”, “Back” hoặc “Account”. Hai key riêng giúp dịch giả dịch đúng và tránh sửa một nơi làm thay đổi nơi khác ngoài ý muốn.

## 15. Kiểm thử bản dịch với placeholder được đảo

Một bộ test tốt phải kiểm tra **format thật** thay vì chỉ kiểm tra key có tồn tại. Hãy kiểm tra:

| Trường hợp | Ví dụ | Kỳ vọng |
| --- | --- | --- |
| Bản tiếng Anh | `{0} ... {2}` | Người gửi ở đầu |
| Bản tiếng Việt | `{2} ... {0}` | Người nhận ở đầu |
| Đổi dữ liệu | Tên khác Lan/Minh | Mọi placeholder hiển thị đúng giá trị |
| Số lượng lớn | `1234` | `{1,number,integer}` theo locale, không ghép `toString` |
| Số lượng một | `1` | Dùng nhánh plural phù hợp; không “1 files” |
| Pattern có apostrophe | `It''s {0}''s book` | In đúng dấu nháy đơn |
| Thiếu tham số | Bản dịch dùng `{3}` nhưng code chỉ có 0..2 | QA báo lỗi schema, không chỉ dựa vào output |
| Tham số sai kiểu | Truyền `String` vào `{1,number}` | Test phát hiện lỗi format |
| Thiếu key | Locale không có message key | Fallback rõ ràng hoặc báo lỗi theo policy |
| Văn bản dài hơn | Bản dịch dài gấp 1,5–2 lần | UI wrap/resize, không cắt mất nội dung |
| Right-to-left | Locale RTL | Trật tự giao diện và bidi isolation đúng |
| Tên chứa Unicode | `Đặng Văn A`, emoji, dấu nháy | Không hỏng ký tự; escape theo ngữ cảnh UI |

### Trường hợp đảo vị trí phải được test có chủ đích

Đừng chỉ truyền các giá trị giống nhau như `"A"` cho cả `{0}` và `{2}`: khi đó một bản dịch dùng nhầm placeholder cũng có thể trông đúng.

Trong ví dụ Java, dùng `"Lan"` và `"Minh"` giúp quan sát rõ hoán đổi. Với kiểm thử tự động, có thể dùng các giá trị đánh dấu riêng như `"SENDER_0"`, `"RECEIVER_2"` và `1234` rồi xác nhận tất cả xuất hiện đúng chỗ.

Để phát hiện thiếu placeholder, CI có thể phân tích pattern với `MessageFormat` hoặc thư viện validation phù hợp. Tuy nhiên **đếm chuỗi con `"{0}"` bằng regex đơn giản là không đủ** vì cú pháp MessageFormat có escaping, định dạng lồng, nhánh choice và quoted literals. Bộ kiểm tra nên hiểu cú pháp message đang sử dụng.

### Kiểm thử độ phủ bản dịch

Không phải lúc nào mọi locale đều có cùng câu vì một số bản dịch đang dùng fallback. Hãy xác định chính sách: cho phép fallback ngôn ngữ gốc trong bản phát triển, hay chặn release nếu thiếu key cho locale được hỗ trợ. `ResourceBundle` tự fallback là tính năng runtime, không thay thế báo cáo translation coverage trong quy trình phát hành.

## 16. Độ dài, bố cục và trách nhiệm của UI

Khi giữ trọn câu trong bản dịch, câu có thể dài hơn hoặc ngắn hơn rất nhiều so với source. Đây là vấn đề **thiết kế giao diện**, không nên giải quyết bằng cách tách câu ra thành mảnh nhỏ.

- Cho phép wrap và mở rộng chiều cao phù hợp, không đặt chiều rộng cố định chỉ cho tiếng Anh.
- Tránh cắt `substring` ở chỉ số tùy tiện vì có thể chẻ surrogate pair hoặc grapheme cluster, làm mất nghĩa của câu.
- Không nối thêm dấu chấm trong UI nếu câu dịch đã sở hữu dấu câu.
- Không ngầm thêm khoảng trắng trước/sau placeholder: một số ngôn ngữ không có khoảng trắng tương tự tiếng Anh.
- Đối với RTL, chiều dòng (text direction) và vị trí nhãn/nút nên được xử lý bằng hệ thống layout và bidi phù hợp, không đảo string.
- Tên hoặc mã ID chèn vào câu RTL có thể cần Unicode bidi isolation hoặc UI primitives hỗ trợ, tránh làm xáo trộn thứ tự ký tự.
- Với accessibility, nội dung được screen reader đọc phải có nghĩa **như một câu**, thay vì ghép các label không liên quan.

Một UI đủ linh hoạt là **điều kiện để việc dịch nguyên câu phát huy tác dụng**. Nếu bản tiếng Anh đã ép label vào một hàng không thể co giãn, người dịch vẫn bị giới hạn dù file resource cho phép đảo vị trí tham số.

## 17. Những lỗi phổ biến và cách khắc phục

| Lỗi | Tác hại | Hướng sửa |
| --- | --- | --- |
| Ghép `prefix + count + suffix` | Khóa trật tự câu | Đưa cả câu vào một resource key |
| Dịch riêng từng động từ/giới từ | Mất ngữ cảnh, sai ngữ pháp | Dịch nguyên thông điệp có placeholder |
| Dùng `String.format` với pattern hardcode trong Java | Không thay được trật tự từ bản dịch | Lấy mẫu từ `ResourceBundle`, format theo locale |
| Truyền tham số theo thứ tự xuất hiện của từng locale | Code khó bảo trì, dễ tráo nghĩa | Thứ tự đối số cố định theo schema; bản dịch đổi vị trí |
| Tạo message có `1 files` | Không xử lý plural | Chọn nhánh câu theo quy tắc locale |
| Dùng cùng key cho trạng thái và hành động khác nhau | Dịch sai ngữ cảnh | Tách key theo vai trò và mục đích |
| Bỏ qua escape apostrophe của MessageFormat | Pattern có thể parse sai | Dùng `''` cho dấu nháy đơn khi cần, test |
| Đổi `{1}` thành `{2}` vì muốn đảo trật tự | Thay đổi ý nghĩa tham số | Chỉ thay vị trí xuất hiện, không đổi chỉ số tùy tiện |
| Thiếu mô tả placeholder | Dịch giả không biết ai là ai | Cung cấp ghi chú vai trò, kiểu và ví dụ |
| Không kiểm tra translation coverage | Bản release trộn hai ngôn ngữ | QA key set và fallback |
| Dùng count.toString() | Số không theo locale | Truyền `Number` và dùng định dạng số |
| Cho dữ liệu người dùng thành MessageFormat pattern | Lỗi cú pháp/khó kiểm soát | Pattern từ catalog đã kiểm soát; dữ liệu là arguments |
| Cho rằng MessageFormat escape HTML | Có thể xuất hiện HTML injection | Escape theo ngữ cảnh UI |
| Cắt câu dịch để vừa button/toast | Mất nghĩa, hỏng Unicode | Sửa layout, dùng bản thông điệp ngắn được dịch riêng nếu cần |
| Tách câu để tạo link trong UI | Người dịch không đảo được vị trí links | Dùng rich placeholders/component rendering có cấu trúc |
| Chỉ kiểm thử tiếng Anh | Bỏ sót các ngôn ngữ đổi trật tự | Test ít nhất một bản dịch đảo placeholder |
| Dùng locale mặc định của JVM trong server | Request khác nhau nhận định dạng sai | Truyền `Locale` per user/request |

## 18. Bài tập thực hành

**Bài 1.** Code tạo câu:

```java
String text = "Welcome " + user + " to " + product + ".";
```

Hãy thiết kế tài nguyên để người dịch có thể đổi vị trí `user` và `product`.

**Gợi ý đáp án:**

```properties
welcome=Welcome {0} to {1}.
```

Một locale khác có thể chọn `welcome={1} chào đón {0}.` — thay đổi vị trí xuất hiện của `{1}` và `{0}` mà không sửa thứ tự đối số Java.

**Bài 2.** Vì sao `ResourceBundle` chứa `files=files` và `prefix=You have` chưa đủ cho một giao diện đa ngôn ngữ?

**Đáp án:** Đây là các mảnh rời; người dịch không kiểm soát được ngữ pháp cả câu, trong đó có vị trí số lượng và biến thể plural. Nên thiết kế `files.remaining=You have {0,number,integer} files remaining.` cùng chính sách plural phù hợp.

**Bài 3.** Trong code `Object[] args = {"Lan",3,"Minh"}`, dịch giả muốn người nhận xuất hiện trước. Có cần thay thứ tự phần tử trong mảng không?

**Đáp án:** Không. Giữ hợp đồng `{0}` = người gửi, `{1}` = số lượng, `{2}` = người nhận; bản dịch bắt đầu bằng `{2}`.

**Bài 4.** Mẫu `It''s {0}''s book.` in ra gì với `{0} = Lan`?

**Đáp án:** `It's Lan's book.`. Trong syntax `MessageFormat`, dấu nháy đơn phải được escape khi dùng như literal.

**Bài 5.** Người dịch muốn nhấn mạnh người nhận và viết `"{2} đã nhận {1} tệp do {0} gửi."`. Điều gì cần đảm bảo trong QA?

**Đáp án:** Ba placeholder có đúng vai trò, số `{1}` được định dạng theo locale khi cần, câu không thiếu key/biến thể plural, và UI có đủ không gian hiển thị.

**Bài 6.** Một trang có link “Điều khoản” ở giữa câu. Có nên tách câu thành ba resource keys và nối text/link trong Java?

**Đáp án:** Không nên nếu việc đó khóa trật tự ngữ pháp. Dùng một mẫu rich-text có placeholders kiểu component hoặc thiết kế UI tương đương để dịch giả sắp xếp phần link an toàn.

**Bài 7.** Tại sao không dùng cùng một key `open` cho nút mở tài liệu và nhãn trạng thái “đang mở”?

**Đáp án:** Từ tiếng Anh có thể giống nhau nhưng vai trò ngữ pháp và nghĩa khác; ngôn ngữ đích có thể cần hai bản dịch khác nhau. Tách key theo ngữ cảnh.

**Bài 8.** Nếu dịch nguyên câu làm text dài hơn source, có nên cắt message trong ResourceBundle để vừa giao diện?

**Đáp án:** Không phải biện pháp mặc định. Ưu tiên layout linh hoạt, wrap/resize, test nhiều locale; nếu thật sự cần biến thể ngắn, cung cấp **một thông điệp ngắn độc lập** có ngữ cảnh và QA riêng, không cắt bừa câu dài.

## 19. Tổng kết

- **Thông điệp là một đơn vị ngôn ngữ có nghĩa**: lưu **toàn bộ câu** trong một resource entry, không chia thành các từ/cụm rồi ghép cố định trong Java.
- **Đối số là dữ liệu; trật tự câu thuộc bản dịch.** `MessageFormat` cho phép người dịch đặt `{2}` trước `{0}` mà code truyền tham số vẫn giữ nguyên.
- Dùng **`ResourceBundle` + `MessageFormat(pattern, locale)`** với schema placeholder được tài liệu hóa, quản lý bản dịch và fallback rõ ràng.
- **Số ít/nhiều, giống/ngôi/cách và rich text** có thể cần lựa chọn message variants hoặc framework mạnh hơn; không giải quyết bằng phép nối từ đơn giản.
- Kiểm tra **escaping `MessageFormat`, kiểu tham số, tính đầy đủ của key, ngữ cảnh, khả năng thay đổi trật tự, giao diện co giãn và accessibility**.
- Phân biệt nội dung ngôn ngữ tự nhiên với **UI behavior/security**: không tự nhét HTML vào bản dịch hay biến dữ liệu người dùng thành template.
- Chất lượng bản địa hóa đến từ **cấu trúc code cho phép dịch đúng**, không chỉ từ việc thay ngôn ngữ của từng chuỗi rời rạc.

**Tài liệu tham khảo:**

- [Java SE 21 — ResourceBundle](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/ResourceBundle.html)
- [Java SE 21 — MessageFormat](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/text/MessageFormat.html)
- [Java SE 21 — ChoiceFormat](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/text/ChoiceFormat.html)
- [Unicode CLDR — Plural Rules](https://cldr.unicode.org/index/cldr-spec/plural-rules)
- [Unicode UTS #35 — MessageFormat and locale data](https://unicode.org/reports/tr35/)
