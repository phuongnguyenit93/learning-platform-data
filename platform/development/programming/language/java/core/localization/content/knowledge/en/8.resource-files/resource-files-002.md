# Ký tự escape, Unicode escape và dấu phân cách trong khóa của tệp tài nguyên

## 1. Mục tiêu và phạm vi

Trong Java Core Localization, tệp tài nguyên `.properties` thường chứa các cặp **khóa = giá trị** cho `ResourceBundle`, ví dụ:

```properties
app.title=Ứng dụng học Java
menu.open=Mở
menu.close=Đóng
```

Định dạng trông giống văn bản thông thường nhưng có **quy tắc phân tích cú pháp riêng**. Dấu `=`, dấu `:`, khoảng trắng, dấu gạch chéo ngược `\` và chuỗi `\uXXXX` có ý nghĩa đặc biệt. Nếu viết sai, chương trình có thể đọc ra **khóa khác với khóa dự kiến**, tạo giá trị bị cắt, làm mất dấu `\` hoặc ném lỗi khi tải tài nguyên.

Sau bài này, bạn cần có khả năng:

- Phân biệt **dấu phân cách giữa key và value** với ký tự thuộc chính key.
- Viết key có khoảng trắng, dấu `:`, dấu `=`, dấu `#`, dấu `!` hoặc dấu `\` một cách chính xác.
- Hiểu các escape `\t`, `\n`, `\r`, `\f`, `\\`, `\uXXXX` và trường hợp dấu `\` không được nhận diện.
- Nhận biết Unicode escape là các **đơn vị mã UTF-16**, ký tự ngoài BMP cần surrogate pair nếu viết toàn bằng escape.
- Phân biệt việc xử lý escape của `.properties` với cách Java source code diễn giải string literal.
- Chọn đúng mã hóa khi dùng `PropertyResourceBundle` và `Properties.load(...)` trên Java 17+; xử lý đúng các dòng nối.

Nội dung tập trung vào **cú pháp tệp tài nguyên**; việc chọn bundle theo ngôn ngữ, vùng và fallback là bước khác của `ResourceBundle`.

## 2. Một dòng `.properties` được phân tích như thế nào?

Đối với `java.util.Properties` và `PropertyResourceBundle`, mỗi **logical line** thông thường mô tả một cặp key/value. Trình đọc tìm key từ ký tự không phải whitespace đầu tiên đến **dấu `=`, dấu `:` hoặc whitespace chưa escape đầu tiên**. Nếu gặp whitespace sau key, nó bỏ qua whitespace đó, tùy chọn bỏ qua một dấu `=`/`:`, sau đó bỏ tiếp whitespace trước value. Phần còn lại là value.

Ba dòng sau tương đương:

```properties
greeting=Hello
greeting: Hello
greeting Hello
```

Cả ba có key `greeting` và value `Hello`. Nếu xuất hiện trong **cùng một file**, lần định nghĩa sau sẽ ghi đè lần trước; đây là ví dụ cú pháp, không phải cách khuyến nghị đặt ba bản ghi trùng khóa.

### Dấu phân cách đầu tiên mới quyết định nơi kết thúc key

| Dòng nguồn | Key thực tế | Value thực tế |
| --- | --- | --- |
| `name=Alice` | `name` | `Alice` |
| `name:Alice` | `name` | `Alice` |
| `name Alice` | `name` | `Alice` |
| `a=b=c` | `a` | `b=c` |
| `a:b=c` | `a` | `b=c` |
| `user name=Alice` | `user` | `name=Alice` |
| `user\ name=Alice` | `user name` | `Alice` |
| `a\:b=Alice` | `a:b` | `Alice` |
| `a\=b:Alice` | `a=b` | `Alice` |
| `noValue` | `noValue` | chuỗi rỗng |

Giữa key và value, dùng `=` cho thống nhất và dễ đọc. **Dấu `:` và `=` bên trong value không nhất thiết phải escape** sau khi trình đọc đã xác định ranh giới key/value. Chẳng hạn:

```properties
url=https://example.org:8443/search?q=java
```

Key là `url` và toàn bộ URL là value. Dấu `:`, `=` ở **phía value** là dữ liệu bình thường.

Whitespace mà parser xem là dấu phân cách là **space (U+0020), tab (U+0009) và form feed (U+000C)**. Đừng mặc định mọi ký tự Unicode có đặc tính "khoảng trắng" đều được xử lý như dấu phân cách `.properties`.

## 3. Escape các ký tự đặc biệt trong key

### 3.1. Khoảng trắng và dấu phân cách

Khi `=`, `:` hoặc whitespace là **một phần của tên key**, đặt `\` phía trước:

```properties
user\ name=Alice
service\:port=8080
data\=version=v2
leading\ space=yes
```

Các key sau khi load lần lượt là:

```text
user name
service:port
data=version
leading space
```

Với key **bắt đầu bằng khoảng trắng**, cũng phải escape khoảng trắng đầu nếu muốn giữ nó. Với key **kết thúc bằng khoảng trắng**, có thể viết `title\ =...`; nhưng nên hạn chế key có dấu cách đầu/cuối vì khó nhìn và dễ nhập sai trong code. Trong dự án thực tế, key như `account.name` hay `menu.save` thường đơn giản và ổn định hơn.

### 3.2. Dấu `#` và `!`: comment hay thành phần của key?

Một dòng trở thành **comment** nếu ký tự không phải whitespace đầu tiên là `#` hoặc `!`:

```properties
# Bản dịch giao diện
   ! Ghi chú cho người bảo trì
title=Trang chủ
```

Nếu thật sự muốn có key **bắt đầu** bằng dấu `#`/`!`, có thể escape:

```properties
\#literal=Hash key
\!important=Bang key
```

Các key là `#literal` và `!important`. Còn khi dấu `#`/`!` nằm **giữa key**, ví dụ `version#1=...`, không cần escape để ngăn comment: dấu comment chỉ có vai trò đặc biệt tại đầu dòng sau khi bỏ qua whitespace đầu.

Bên trong value, `#` và `!` là ký tự thông thường:

```properties
notice=Quan trọng! Xem #huongdan
```

Ở đây không có comment bắt đầu giữa value. Không coi `#` nằm sau dấu `=` là cú pháp comment cuối dòng.

### 3.3. Muốn giữ dấu gạch chéo ngược thật

`\` là ký tự bắt đầu escape. Muốn **một dấu `\` trong dữ liệu sau load**, viết **hai dấu `\\`** trong tệp:

```properties
folder=C:\\data\\reports
key\\part=backslash
```

Kết quả:

- Value của `folder`: `C:\data\reports`.
- Key `key\part` là tên khóa chứa một dấu gạch chéo ngược.

Ví dụ sai dễ gặp:

```properties
folder=C:\temp\reports
```

`\t` trở thành tab, `\r` trở thành carriage return; đường dẫn sau khi load **không còn** là đường dẫn mong muốn. Khi lưu đường dẫn trên Windows, hoặc viết `C:\\temp\\reports`, hoặc dùng dấu `/` phù hợp với API/hệ thống, hoặc chọn một định dạng lưu trữ được kiểm soát rõ.

## 4. Các escape hợp lệ và cách diễn giải

Trong nội dung key/value, nhóm escape cơ bản của `.properties`:

| Dạng trong file | Ký tự sau khi load | Ghi chú |
| --- | --- | --- |
| `\t` | Tab (U+0009) | Không phải hai chữ `\` và `t` |
| `\n` | Xuống dòng LF (U+000A) | Là ký tự trong value/key |
| `\r` | Carriage return (U+000D) | Khác LF |
| `\f` | Form feed (U+000C) | Ít dùng |
| `\\` | Một dấu `\` | Cách lưu backslash thật |
| `\=` | `=` | Cần khi ký tự thuộc key |
| `\:` | `:` | Cần khi ký tự thuộc key |
| `\ ` | Space (U+0020) | Giữ space trong key hoặc ở đầu value |
| `\u0041` | `A` (U+0041) | Chính xác **bốn chữ số hex** |
| `\u00E9` | `é` (U+00E9) | Một đơn vị mã UTF-16 |

**Lưu ý sự khác biệt với Java string literal:** parser `.properties` **không** hỗ trợ escape `\b` như backspace và **không** hỗ trợ octal escape. Nếu `\` đứng trước ký tự không nằm trong tập escape có nghĩa, parser thường **bỏ dấu `\` và giữ ký tự kế tiếp**. Ví dụ `x=\q` đọc được value `q`, không báo lỗi vì `\q` không hợp lệ; đây là lý do gõ sai escape có thể âm thầm làm mất dữ liệu.

Dấu nháy đơn, nháy kép **không cần escape** trong value `.properties` thông thường:

```properties
quote=He said "Hello"
name=O'Reilly
```

Nếu dùng `MessageFormat` để định dạng value có placeholder, dấu nháy đơn có quy tắc **riêng của MessageFormat** và phải xử lý ở tầng định dạng thông điệp; đó không phải quy tắc escape của `.properties`.

## 5. Unicode escape: `\uXXXX` là gì?

Một Unicode escape trong `.properties` có dạng **`\u` ngay sau đó là đúng bốn chữ số hex** (0–9, A–F, a–f), ví dụ:

```properties
letter=\u0041
cafe=caf\u00E9
vietnam=Xin ch\u00E0o
```

Khi load, các value tương ứng là `A`, `café` và `Xin chào`. Ký tự `é` không bắt buộc viết bằng `\u00E9` trong file UTF-8 dành cho `ResourceBundle` Java 9+, nhưng escape vẫn là cú pháp hợp lệ và hữu dụng với file cần biểu diễn ASCII.

**Điểm quan trọng:** `\uXXXX` mã hóa **một UTF-16 code unit**, không phải cú pháp Unicode tùy ý có thể viết nhiều hơn bốn chữ số. Ví dụ ký tự rocket 🚀 (U+1F680) nằm ngoài Basic Multilingual Plane (BMP); dạng escape truyền thống là **một cặp surrogate**:

```properties
rocket=\uD83D\uDE80
```

Hai phần `D83D` (high surrogate) và `DE80` (low surrogate) tạo một code point U+1F680 khi được giải mã thành chuỗi Java hợp lệ. Viết một escape `\u1F680` là **sai về cách biểu diễn ký tự mong muốn**: `\u` chỉ lấy bốn chữ số hex, phần ký tự còn lại không biểu diễn U+1F680 như bạn mong đợi.

### Lỗi Unicode escape

```properties
broken=\u12G4
```

Đây là escape sai vì `G` không phải ký tự hex. Khi load bằng `Properties.load`, nó có thể ném `IllegalArgumentException` cho malformed Unicode escape. Lỗi này khác với việc **byte của file bị giải mã sai charset**; cần phân biệt cú pháp escape và mã hóa bytes.

Không viết `\uu0041` với hai chữ `u` rồi mong parser `.properties` hoạt động giống một số dạng Unicode escape trong Java source; `.properties` chỉ dùng **một chữ `u`** trước bốn chữ số hex.

### Tại sao phải phân biệt với Unicode escape trong Java source?

Java compiler có bước xử lý Unicode escapes từ **mã nguồn trước khi phân tích token**, còn file `.properties` được **đọc lúc runtime** và sau đó parser mới xử lý escape. Khi đưa văn bản của file properties vào `String` trong Java test, dấu `\` thuộc **hai tầng cú pháp khác nhau**:

```java
// Ký tự của String runtime là: \u0041
String propertyLine = "letter=\\u0041";

// Sau khi Properties.load(...), key "letter" có value "A".
```

Đây là **đoạn minh họa nằm trong phương thức**, không phải file Java độc lập. Nó cho thấy literal Java `\\` tạo một dấu `\` trong chuỗi runtime; parser của `.properties` sau đó thấy `\u0041` và giải thành `A`. Tránh dùng lời giải thích "một lớp escape" cho cả Java source và file resource.

## 6. Nối dòng bằng backslash ở cuối dòng

Một cặp key/value có thể chiếm nhiều **natural lines** nhưng vẫn là **một logical line**. Khi một dòng kết thúc bởi **số lượng dấu backslash liên tiếp là số lẻ**, dấu `\` cuối escape dòng mới; parser bỏ dấu `\` tiếp dòng, dấu xuống dòng và whitespace đầu dòng kế tiếp rồi ghép phần còn lại:

```properties
description=Học Java, \
    tìm hiểu Locale, \
    và đọc resource bundle.
```

Value thu được:

```text
Học Java, tìm hiểu Locale, và đọc resource bundle.
```

Lưu ý: khoảng trắng **trước dấu `\` ở cuối hai dòng đầu** vẫn thuộc value nên giữ ngăn cách từ. Nếu viết:

```properties
message=hello\
   world
```

Value sẽ là `helloworld`, **không phải** `hello world`. Muốn có space giữa hai từ, viết `hello \` hoặc đưa khoảng trắng được escape vào phần nối thích hợp. Whitespace đầu dòng tiếp theo **bị bỏ**, không tự chuyển thành dấu cách.

Khi có **số dấu `\` liên tiếp chẵn** ở cuối dòng, các dấu đó được ghép thành các backslash thật, còn line terminator không bị escape bởi một backslash lẻ. Vì thế không thể chỉ nhìn ký tự cuối là `\` để kết luận luôn có nối dòng; phải đếm toàn bộ chuỗi `\` liên tiếp ở cuối.

Một dòng comment không dùng kiểu nối dòng này; các dòng comment vẫn được xử lý độc lập. Ngược lại, sau một dòng dữ liệu đang nối, ký tự `#` ở dòng được nối không tự trở thành comment mới theo ý bạn: nó là một phần logical line đang tiếp tục.

## 7. Ví dụ Java 17+ chạy độc lập: kiểm chứng key và escape

Ví dụ dùng `java.util.Properties.load(Reader)` để trình diễn đúng cú pháp mà `PropertyResourceBundle` cũng dùng; chuỗi thử nghiệm được tạo tại runtime, không cần tạo file vật lý. Tên file: `PropertiesSyntaxDemo.java`.

```java
import java.io.StringReader;
import java.util.Properties;

public class PropertiesSyntaxDemo {
    public static void main(String[] args) throws Exception {
        String source = String.join("\n",
                "# comment",
                "! note",
                "plain=xin chao",
                "a\\:b=colon-key",
                "x\\=y: equals-key",
                "user\\ name=space-key",
                "\\#literal=hash-key",
                "\\!bang=bang-key",
                "empty",
                "spaces=\\ leading",
                "line=first\\nsecond",
                "continued=one\\",
                "    two",
                "rocket=\\uD83D\\uDE80",
                "path=C:\\\\temp\\\\config");

        Properties properties = new Properties();
        properties.load(new StringReader(source));

        System.out.println("plain=" + properties.getProperty("plain"));
        System.out.println("a:b=" + properties.getProperty("a:b"));
        System.out.println("x=y=" + properties.getProperty("x=y"));
        System.out.println("user name=" + properties.getProperty("user name"));
        System.out.println("#literal=" + properties.getProperty("#literal"));
        System.out.println("!bang=" + properties.getProperty("!bang"));
        System.out.println(
                "empty.length=" + properties.getProperty("empty").length());
        System.out.println(
                "spaces.startsWithSpace="
                + properties.getProperty("spaces").startsWith(" "));
        System.out.println(
                "line=" + properties.getProperty("line")
                        .replace("\n", "<NL>"));
        System.out.println(
                "continued=" + properties.getProperty("continued"));
        System.out.println(
                "rocket=" + Integer.toHexString(
                        properties.getProperty("rocket").codePointAt(0)));
        System.out.println("path=" + properties.getProperty("path"));
    }
}
```

Lệnh:

```bash
javac -encoding UTF-8 PropertiesSyntaxDemo.java
java PropertiesSyntaxDemo
```

Stdout:

```text
plain=xin chao
a:b=colon-key
x=y=equals-key
user name=space-key
#literal=hash-key
!bang=bang-key
empty.length=0
spaces.startsWithSpace=true
line=first<NL>second
continued=onetwo
rocket=1f680
path=C:\temp\config
```

Kết quả nêu rõ hai tầng escape:

- Để ký tự `\` xuất hiện trong dữ liệu `source` của Java, string literal viết `\\`; sau đó parser properties mới xử lý các escape theo đúng cú pháp file.
- `a\:b` và `x\=y` trở thành key chứa dấu phân cách; không bị cắt thành hai phần.
- `\#literal`, `\!bang` là key thật, không bị hiểu là comment.
- Dòng `empty` không có dấu phân cách vẫn tạo value rỗng.
- `spaces=\ leading` giữ một khoảng trắng đầu value.
- `line=first\nsecond` tạo newline LF thật, được in thành `<NL>` chỉ để quan sát dễ dàng.
- `continued=one\` nối với dòng `two` thành `onetwo`.
- Cặp escape `\uD83D\uDE80` trả code point `1f680` (hệ 16) khi đọc bằng `codePointAt`.
- `path=C:\\temp\\config` bảo toàn dấu backslash của đường dẫn.

Trong sản phẩm thực, không cần tự dựng các chuỗi test như trên; chỉ cần soạn `.properties` đúng chuẩn rồi tải bằng `ResourceBundle`. Ví dụ `PropertiesSyntaxDemo` giúp bạn **kiểm chứng chính xác parser** và tái hiện lỗi khi học.

## 8. UTF-8, Latin-1 và Unicode escape: ba khái niệm dễ nhầm

**Escape syntax** là cách biểu diễn ký tự trong nội dung `.properties`, còn **charset** quyết định cách đổi byte thành ký tự **trước khi parse**. API khác nhau có quy tắc khác nhau:

| Cách đọc | Charset mặc định / xử lý | Điều cần nhớ |
| --- | --- | --- |
| `Properties.load(InputStream)` | **ISO-8859-1** | Đây là hợp đồng API vẫn tồn tại trên Java 17+; byte UTF-8 cho tiếng Việt có thể bị đọc sai |
| `Properties.load(Reader)` | Do `Reader` đã chọn | Dùng `InputStreamReader(..., UTF_8)` hoặc `Files.newBufferedReader(..., UTF_8)` để đọc UTF-8 |
| `PropertyResourceBundle(InputStream)` (Java 9+) | Thử **UTF-8** trước; nếu gặp byte UTF-8 malformed/unmappable thì fallback **ISO-8859-1** | Có thể ép bằng system property `java.util.PropertyResourceBundle.encoding` đặt khi khởi động |
| `PropertyResourceBundle(Reader)` | Dùng ký tự đã được `Reader` giải mã | Không có lý do đoán charset từ string sau khi đã đọc |
| `ResourceBundle.getBundle(...)` cho bundle `.properties` (Java 9+) | Cơ chế properties bundle theo Java 9+, thường UTF-8 trước | Tập tin có thể chứa Unicode trực tiếp và vẫn hỗ trợ `\uXXXX` |

Lưu ý option `-Djava.util.PropertyResourceBundle.encoding=UTF-8` hoặc `ISO-8859-1` áp dụng cho `PropertyResourceBundle` khi khởi tạo class; không làm thay đổi hợp đồng của `Properties.load(InputStream)`. Nếu ép UTF-8, dữ liệu byte không hợp lệ có thể gây lỗi thay vì fallback Latin-1. Khi tạo bundle mới, nên thống nhất **UTF-8**, lưu tập tin đúng encoding, kiểm thử cùng runtime và công cụ build.

Với file UTF-8 thật:

```properties
welcome=Chào mừng bạn
farewell=Tạm biệt
```

Trên Java 17+, `ResourceBundle` có thể đọc Unicode trực tiếp từ `.properties`; không cần chuyển tất cả thành `\uXXXX` chỉ vì các hướng dẫn cũ từ Java 8 yêu cầu Latin-1. Tuy vậy **`Properties.load(InputStream)` không tự đổi sang UTF-8**; hai lớp API có lịch sử tương thích khác nhau.

### Ví dụ chạy được: một chuỗi UTF-8, hai cách đọc

File `PropertiesEncodingDemo.java`:

```java
import java.io.ByteArrayInputStream;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.util.Properties;

public class PropertiesEncodingDemo {
    public static void main(String[] args) throws Exception {
        String original = "Tiếng Việt";
        byte[] bytes = ("greeting=" + original + "\n")
                .getBytes(StandardCharsets.UTF_8);

        Properties utf8 = new Properties();
        try (var reader = new InputStreamReader(
                new ByteArrayInputStream(bytes),
                StandardCharsets.UTF_8)) {
            utf8.load(reader);
        }

        Properties latin1 = new Properties();
        latin1.load(new ByteArrayInputStream(bytes));

        System.out.println(
                utf8.getProperty("greeting").equals(original));
        System.out.println(
                latin1.getProperty("greeting").equals(original));
    }
}
```

```bash
javac -encoding UTF-8 PropertiesEncodingDemo.java
java PropertiesEncodingDemo
```

Đầu ra:

```text
true
false
```

Hai đối tượng cùng đọc **một dãy byte** ban đầu, nhưng `load(Reader)` giải mã UTF-8 đúng, còn `load(InputStream)` diễn giải byte Latin-1. Đây là vấn đề **charset**, không thể giải quyết bằng cách sửa `Locale.setDefault(...)` hoặc `Locale.forLanguageTag(...)`.

## 9. Tải tài nguyên thực tế bằng `ResourceBundle`

Giả sử bạn tạo file `Messages_vi_VN.properties` (UTF-8, nằm trên classpath):

```properties
welcome=Xin chào
menu.open=Mở
service\:port=Cổng dịch vụ
line.break=Hàng 1\nHàng 2
rocket=\uD83D\uDE80
```

Khi đó, trong một lớp có quyền truy cập resource:

```java
import java.util.Locale;
import java.util.ResourceBundle;

public class ResourceMessageDemo {
    public static void main(String[] args) {
        ResourceBundle bundle = ResourceBundle.getBundle(
                "Messages", Locale.forLanguageTag("vi-VN"));

        System.out.println(bundle.getString("welcome"));
        System.out.println(bundle.getString("service:port"));
        System.out.println(bundle.getString("rocket").codePointAt(0));
    }
}
```

Đặt **cả hai file trong cùng thư mục classpath** với lớp ở default package của ví dụ, rồi chạy:

```bash
javac -encoding UTF-8 ResourceMessageDemo.java
java -cp . ResourceMessageDemo
```

Kết quả khi dùng file đã cho trên Java 17+ với dữ liệu mặc định:

```text
Xin chào
Cổng dịch vụ
128640
```

Tên key truyền vào `getString(...)` phải là **tên sau khi parser đã giải escape**: sử dụng `"service:port"`, không phải `"service\\:port"`. `128640` là code point hệ thập phân của U+1F680 (🚀). Nếu không tìm thấy bundle hoặc key, API có thể ném `MissingResourceException`; đó là lỗi lookup riêng với malformed `\uXXXX` trong file.

Lưu ý: tệp resource Java có quy tắc tên như `Messages_vi_VN.properties`, dùng underscore theo `ResourceBundle`. Cú pháp này khác với language tag BCP 47 (`vi-VN`) dùng dấu gạch nối. Dấu phân cách trong **tên file** và dấu phân cách trong **nội dung key/value** là hai lớp quy tắc khác nhau.

## 10. Những lỗi thường gặp và cách khắc phục

| Lỗi | Kết quả sai | Cách sửa |
| --- | --- | --- |
| `user name=...` nhưng code gọi `getString("user name")` | File chỉ có key `user` | Dùng `user\ name=...` hoặc chuẩn hóa thành `user.name` |
| `server:port=8080` khi muốn key `server:port` | Key là `server` | Viết `server\:port=8080` |
| `flag=one#comment` nhưng mong `#comment` bị bỏ | Value chứa nguyên `one#comment` | Dùng comment ở dòng riêng |
| `folder=C:\temp` | `\t` trở thành tab | Dùng `folder=C:\\temp` |
| `x=\q` và nghĩ parser báo lỗi | Dấu `\` thường bị bỏ, value thành `q` | Chỉ dùng escape đã định nghĩa |
| `\u12G4` | Malformed Unicode escape | Viết đúng bốn chữ số hex |
| `\u1F680` để lưu emoji ngoài BMP | Không biểu diễn U+1F680 như ý | Dùng `\uD83D\uDE80` hoặc Unicode trực tiếp trong UTF-8 |
| Đặt whitespace đầu value không escape | Whitespace trước value thường bị bỏ | Dùng `\ ` cho space cần giữ |
| Mong line continuation tự chèn space | Parser bỏ newline và leading whitespace dòng sau | Chèn space tường minh trước `\` |
| Gọi `Properties.load(InputStream)` với file UTF-8 | Chữ tiếng Việt bị giải mã sai | Dùng `load(Reader)` với UTF-8, hoặc `ResourceBundle` đúng hợp đồng |
| Nhầm cách viết `\\` của Java source với `.properties` | Dấu `\` bị escape sai một hoặc hai tầng | Kiểm tra chuỗi runtime và file riêng biệt |
| Lưu nhiều lần cùng key | Giá trị cuối ghi đè trước | Dùng key duy nhất và kiểm tra duplicate |

## 11. Tự kiểm tra

1. Trong file `.properties`, `host:port=8080` tạo key nào? **`host`**, value `port=8080`; muốn key `host:port` phải viết `host\:port=8080`.
2. `menu.open=Mở` có cần escape dấu chấm không? **Không**. Dấu `.` không phải ký tự ngắt key; cấu trúc dấu chấm chỉ là quy ước tên key.
3. `title=Hello # note` có cắt phần `# note` không? **Không**. Value chứa cả dấu `#` và phần phía sau.
4. Viết literal backslash `\` vào value bằng cách nào? **`\\`** trong file properties.
5. Vì sao Unicode escape của 🚀 cần hai lần `\uXXXX`? **Vì mỗi escape chứa một UTF-16 code unit, còn U+1F680 được biểu diễn bằng cặp surrogate**.
6. Dòng `name=hello\` nối với dòng `   world` thành value gì? **`helloworld`**; không tự thêm space.
7. Hai API `Properties.load(InputStream)` và `PropertyResourceBundle(InputStream)` trên Java 17 có cùng mặc định charset không? **Không**. `Properties` dùng ISO-8859-1; `PropertyResourceBundle` thử UTF-8 trước và có cơ chế fallback.
8. Khi file ghi `service\:port=8080`, code `bundle.getString("service:port")` có tìm đúng không? **Có**, vì key đã giải escape là `service:port`.
9. Khi nào nên viết tiếng Việt trực tiếp thay vì `\uXXXX`? **Khi dùng Java 9+ với resource bundle UTF-8 và hệ thống công cụ lưu file đúng encoding**; vẫn cần biết API đọc file của ứng dụng.

## Tài liệu tham khảo

- [Java SE 21 — Properties](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Properties.html): cú pháp logical line, key separator, escape, Unicode và `load(InputStream)`/`load(Reader)`.
- [Java SE 21 — PropertyResourceBundle](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/PropertyResourceBundle.html): cách đọc bundle UTF-8/ISO-8859-1 trên Java 9+.
- [Java SE 21 — ResourceBundle](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/ResourceBundle.html): lookup bundle và sử dụng `getString`.
- [Java SE 21 — Java Language Specification, Unicode Escapes](https://docs.oracle.com/javase/specs/jls/se21/html/jls-3.html#jls-3.3): cách Java compiler xử lý Unicode escapes của **mã nguồn**, cần phân biệt với parser `.properties`.
