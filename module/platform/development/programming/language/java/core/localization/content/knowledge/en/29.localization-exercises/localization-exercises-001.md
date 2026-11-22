# Thực hành tổng hợp: xây dựng chương trình dòng lệnh đổi ngôn ngữ bằng ResourceBundle trong Java

## 1. Mục tiêu và sản phẩm cần xây dựng

Bài thực hành xây dựng một **CLI (command-line interface)** chạy trên Java 17 trở lên. Người dùng có thể **đổi ngôn ngữ ngay trong phiên chạy**, không phải khởi động lại JVM. Chương trình có các lệnh:

| Lệnh | Tác dụng |
| --- | --- |
| `help` | Hiển thị hướng dẫn trong ngôn ngữ hiện tại |
| `lang en` | Chuyển thông điệp sang tiếng Anh |
| `lang vi` | Chuyển thông điệp sang tiếng Việt |
| `greet TÊN` | In lời chào có tên động |
| `count N` | In số lượng tin nhắn; định dạng số theo locale |
| `quit` | Thoát bằng lời chào tạm biệt đã bản địa hóa |

Ví dụ một phiên tương tác:

```text
Language Switch CLI
Welcome! Type help for commands.
Commands: lang en | lang vi | greet NAME | count N | help | quit
> greet Lan
Hello, Lan!
> count 1234
You have 1,234 messages.
> lang vi
Đã chuyển sang tiếng Việt.
> greet Minh
Xin chào, Minh!
> count 1234
Bạn có 1.234 tin nhắn.
> help
Lệnh: lang en | lang vi | greet TÊN | count N | help | quit
> lang en
Language switched to English.
> quit
Goodbye!
```

Dấu `>` là prompt của chương trình; các dòng sau prompt là lệnh người dùng gõ. Đối với số `1234`, tiếng Anh Mỹ thường dùng dấu phẩy nhóm nghìn, còn tiếng Việt Việt Nam thường dùng dấu chấm. Việc trình bày này phụ thuộc dữ liệu locale của JDK; đầu ra trên minh họa cách định dạng của JDK hiện đại. Font/encoding terminal có thể ảnh hưởng việc hiển thị dấu tiếng Việt, không thay đổi bản chất của `ResourceBundle`.

Sau bài này, bạn sẽ biết:

1. Tách **logic điều khiển CLI** khỏi **ngôn ngữ hiển thị**.
2. Tạo và tổ chức `.properties` theo đúng **base name**, **classpath root** và **locale suffix**.
3. Dùng `Locale`, `ResourceBundle.getBundle`, `getString` và `MessageFormat`.
4. Đổi ngôn ngữ có kiểm soát, không gọi `Locale.setDefault` trên toàn JVM.
5. Định dạng tham số động, số lượng và câu hoàn chỉnh.
6. Xử lý đầu vào, ngôn ngữ không hỗ trợ, key thiếu, lỗi tài nguyên và encoding.
7. Biên dịch, chạy, đóng gói JAR và kiểm thử một ứng dụng i18n thực tế.

## 2. Kiến trúc: dữ liệu nghiệp vụ không phụ thuộc ngôn ngữ

Ứng dụng có hai lớp trách nhiệm:

- **Logic CLI:** đọc lệnh, kiểm tra lệnh hợp lệ, lưu ngôn ngữ đang chọn, chuyển đến chức năng tương ứng.
- **Localization:** chọn `ResourceBundle` tương ứng locale, lấy mẫu thông điệp theo key và format dữ liệu.

Sơ đồ tư duy:

```text
Người dùng nhập "count 1234"
             |
             v
  Bộ xử lý lệnh CLI
             |
             v
   Phân tích số 1234 (long)
             |
             v
  Chọn message key "count.other"
             |
             v
 ResourceBundle theo locale hiện tại
             |
             v
   MessageFormat với tham số [1234]
             |
             v
  "You have 1,234 messages."
             hoặc
  "Bạn có 1.234 tin nhắn."
```

**Quan trọng:** chương trình **không** viết `if (locale == vi) System.out.println("Bạn có...")` cho từng câu. Nó dùng **cùng key** nhưng tài nguyên cung cấp mẫu câu tương ứng. Nhờ đó, thêm ngôn ngữ mới chủ yếu là thêm bản dịch và cập nhật danh sách ngôn ngữ được hỗ trợ, không sao chép toàn bộ logic xử lý lệnh.

### Tên key phải ổn định và mô tả mục đích

Bộ key của bài:

| Key | Ý nghĩa |
| --- | --- |
| `app.name` | Tên ứng dụng trung lập |
| `welcome` | Dòng giới thiệu |
| `help` | Cú pháp các lệnh |
| `language.changed` | Thông báo chuyển ngôn ngữ thành công |
| `greeting` | Câu chào có đối số tên `{0}` |
| `count.one` | Câu số lượng khi `N == 1` |
| `count.other` | Câu số lượng cho các số nguyên không âm còn lại |
| `error.locale` | Mã ngôn ngữ không hỗ trợ |
| `error.name` | Thiếu tên cho lệnh `greet` |
| `error.number` | Giá trị số lượng không hợp lệ |
| `error.command` | Lệnh không nhận diện được |
| `goodbye` | Thông báo thoát |

Đây là key kỹ thuật: **không cần dịch tên key**. Người dịch chỉ chỉnh giá trị tương ứng. Tránh đặt tên `message1`, `message2` vì khó hiểu chức năng và khó quản lý bản dịch.

## 3. Cấu trúc thư mục đúng để Java tìm bundle

Dự án đơn giản **không cần thư viện bên ngoài**:

```text
language-cli/
├── src/
│   └── main/
│       ├── java/
│       │   └── LanguageCli.java
│       └── resources/
│           ├── Messages.properties
│           ├── Messages_en.properties
│           └── Messages_vi.properties
└── out/                      # thư mục tạo sau khi javac
```

Vì các file `.properties` đặt **ngay gốc resource directory**, base name là `"Messages"`, không phải `"src.main.resources.Messages"` và không phải `"Messages.properties"`. Khi classpath chứa `src/main/resources` hoặc khi các file đã được chép vào **gốc JAR**, Java tìm:

```text
Messages.properties
Messages_en.properties
Messages_vi.properties
```

Nếu đặt resource sâu hơn, chẳng hạn `src/main/resources/com/example/i18n/Messages_vi.properties`, base name tương ứng phải là `com.example.i18n.Messages`. Đừng truyền đường dẫn filesystem tới `getBundle`.

Một phương thức điển hình:

```java
ResourceBundle messages =
        ResourceBundle.getBundle("Messages", locale);
```

Java dùng base name, locale và cơ chế tìm trong classpath/module để tải tài nguyên. Với `Locale.US` (language `en`) và các file hiện có, bundle `Messages_en.properties` được chọn; với `vi-VN`, tìm `Messages_vi_VN.properties` nếu có rồi tới `Messages_vi.properties`. Những key thiếu trong bundle con có thể được tìm trong parent bundle như `Messages.properties`.

### Tại sao cần root Messages.properties?

Một file `Messages.properties` không có suffix locale đóng vai trò root fallback. Bài này để **bản tiếng Anh đầy đủ** trong root nhằm có giá trị dự phòng và đặt các bản dịch theo locale ở file riêng. Để giảng dạy rõ ràng, `Messages_en.properties` được cung cấp đầy đủ dù nhiều key trùng với root. Trong dự án thật, có thể chọn một ngôn ngữ nguồn làm root hoặc dùng chính sách fallback riêng, nhưng phải kiểm tra coverage bản dịch trước khi phát hành.

**Fallback không phải cách hỗ trợ ngôn ngữ chính thức:** `ResourceBundle.getBundle("Messages", Locale.forLanguageTag("xx"))` vẫn có thể tìm thấy root rồi trả về tiếng Anh. Vì vậy, CLI phải **tự giới hạn mã ngôn ngữ được hỗ trợ**, không dựa vào ngoại lệ để phát hiện yêu cầu `xx` không hợp lệ.

## 4. Tạo tài nguyên gốc và bản dịch

Ba file sau đều là **tệp UTF-8**. Java 9+ hỗ trợ UTF-8 cho `PropertyResourceBundle` theo JEP 226, có cơ chế tương thích với ISO-8859-1 khi byte không phải UTF-8 hợp lệ. `Properties.load(InputStream)` là API khác và không nên nhầm với quy tắc này.

### 4.1. src/main/resources/Messages.properties

```properties
app.name=Language Switch CLI
welcome=Welcome! Type help for commands.
help=Commands: lang en | lang vi | greet NAME | count N | help | quit
language.changed=Language switched to English.
greeting=Hello, {0}!
count.one=You have {0,number,integer} message.
count.other=You have {0,number,integer} messages.
error.locale=Unsupported language. Use en or vi.
error.name=Please provide a name.
error.number=Enter a non-negative integer.
error.command=Unknown command. Type help.
goodbye=Goodbye!
```

File root có tất cả key. Điều này quan trọng khi một bản dịch thiếu key: Java có thể lấy từ parent bundle, thay vì lập tức báo lỗi. Nhưng trong pipeline dịch, vẫn nên phát hiện những key bị bỏ sót.

### 4.2. src/main/resources/Messages_en.properties

```properties
welcome=Welcome! Type help for commands.
help=Commands: lang en | lang vi | greet NAME | count N | help | quit
language.changed=Language switched to English.
greeting=Hello, {0}!
count.one=You have {0,number,integer} message.
count.other=You have {0,number,integer} messages.
error.locale=Unsupported language. Use en or vi.
error.name=Please provide a name.
error.number=Enter a non-negative integer.
error.command=Unknown command. Type help.
goodbye=Goodbye!
```

Lưu ý `app.name` không có trong file `_en`. Nó được kế thừa từ root; đây là chủ ý để minh họa **parent bundle lookup**. Ngay cả khi `Locale.US` không có file `Messages_en_US.properties`, Java vẫn tìm được `Messages_en.properties` và tra `app.name` ở root.

### 4.3. src/main/resources/Messages_vi.properties

```properties
welcome=Chào mừng! Gõ help để xem các lệnh.
help=Lệnh: lang en | lang vi | greet TÊN | count N | help | quit
language.changed=Đã chuyển sang tiếng Việt.
greeting=Xin chào, {0}!
count.one=Bạn có {0,number,integer} tin nhắn.
count.other=Bạn có {0,number,integer} tin nhắn.
error.locale=Ngôn ngữ không hỗ trợ. Hãy dùng en hoặc vi.
error.name=Vui lòng nhập tên.
error.number=Nhập số nguyên không âm.
error.command=Lệnh không hợp lệ. Gõ help.
goodbye=Tạm biệt!
```

Ở đây hai key `count.one` và `count.other` có cùng cách viết tiếng Việt. **Đó là lựa chọn ngữ pháp cho hai ngôn ngữ minh họa, không phải quy tắc mọi ngôn ngữ chỉ có hai nhóm plural.** Tiếng Anh cần `message`/`messages`, còn tiếng Việt không biến đổi danh từ theo số lượng như vậy trong câu mẫu. Với tiếng Ả Rập, Nga hoặc các ngôn ngữ khác, quy tắc chọn plural phải theo CLDR hoặc framework phù hợp thay vì chỉ `N == 1`.

### Placeholder là dữ liệu, không phải phần cần dịch

Mẫu:

```properties
greeting=Xin chào, {0}!
count.other=Bạn có {0,number,integer} tin nhắn.
```

Dùng `{0}` làm vị trí đối số. `MessageFormat` thay nội dung nhưng không cần người dịch biết tên Java của biến. Cú pháp `{0,number,integer}` cho biết đối số là số và cần định dạng thành một số nguyên để trình bày theo locale.

Nếu bản dịch muốn đổi vị trí thông tin, placeholder có thể di chuyển trong mẫu mà Java code vẫn truyền cùng một mảng đối số. **Đừng tách câu thành nhiều fragment rồi nối string** vì mỗi ngôn ngữ có thứ tự ngữ pháp khác nhau.

## 5. Lập trình LanguageCli.java hoàn chỉnh, chạy trên Java 17+

Tạo file **src/main/java/LanguageCli.java**:

```java
import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.text.MessageFormat;
import java.util.Locale;
import java.util.ResourceBundle;

public final class LanguageCli {
    private static final String BUNDLE_BASE = "Messages";
    private static final Locale VI =
            Locale.forLanguageTag("vi-VN");

    // Trạng thái ngôn ngữ thuộc riêng CLI này.
    private Locale locale = Locale.US;
    private ResourceBundle messages =
            ResourceBundle.getBundle(BUNDLE_BASE, locale);

    private String tr(String key) {
        return messages.getString(key);
    }

    private String trf(String key, Object... arguments) {
        return new MessageFormat(tr(key), locale)
                .format(arguments);
    }

    private void changeLanguage(String code) {
        Locale requested;
        switch (code.toLowerCase(Locale.ROOT)) {
            case "en" -> requested = Locale.US;
            case "vi" -> requested = VI;
            default -> {
                System.out.println(tr("error.locale"));
                return;
            }
        }

        ResourceBundle selected =
                ResourceBundle.getBundle(BUNDLE_BASE, requested);
        locale = requested;
        messages = selected;
        System.out.println(tr("language.changed"));
    }

    private void run() throws IOException {
        try (BufferedReader input = new BufferedReader(
                new InputStreamReader(
                        System.in, StandardCharsets.UTF_8))) {

            System.out.println(tr("app.name"));
            System.out.println(tr("welcome"));
            System.out.println(tr("help"));

            while (true) {
                System.out.print("> ");
                System.out.flush();

                String line = input.readLine();
                if (line == null) {
                    // EOF khi stdin đóng: không tạo vòng lặp vô hạn.
                    System.out.println();
                    return;
                }

                line = line.strip();
                if (line.isEmpty()) {
                    continue;
                }

                String[] parts = line.split("\\s+", 2);
                String command = parts[0].toLowerCase(Locale.ROOT);
                String argument = parts.length == 2
                        ? parts[1].strip() : "";

                switch (command) {
                    case "help" -> System.out.println(tr("help"));
                    case "lang" -> changeLanguage(argument);
                    case "greet" -> {
                        if (argument.isBlank()) {
                            System.out.println(tr("error.name"));
                        } else {
                            System.out.println(
                                    trf("greeting", argument));
                        }
                    }
                    case "count" -> {
                        try {
                            long count = Long.parseLong(argument);
                            if (count < 0) {
                                System.out.println(
                                        tr("error.number"));
                            } else {
                                String key = count == 1
                                        ? "count.one"
                                        : "count.other";
                                System.out.println(trf(key, count));
                            }
                        } catch (NumberFormatException ex) {
                            System.out.println(
                                    tr("error.number"));
                        }
                    }
                    case "quit" -> {
                        System.out.println(tr("goodbye"));
                        return;
                    }
                    default -> System.out.println(
                            tr("error.command"));
                }
            }
        }
    }

    public static void main(String[] args) throws IOException {
        new LanguageCli().run();
    }
}
```

Đây là **một class Java độc lập về mã nguồn**, nhưng chương trình cần ba file `Messages*.properties` **trên runtime classpath**. Với Java 17+, các cú pháp `switch ->`, `String.strip()`, `String.isBlank()` đều được hỗ trợ.

### 5.1. Vì sao trạng thái locale nằm ở instance?

`locale` và `messages` là trường của **một đối tượng `LanguageCli`**, không phải trạng thái JVM toàn cục. Khi người dùng gõ `lang vi`, chỉ đối tượng đó cập nhật bundle.

Không làm như sau:

```java
Locale.setDefault(Locale.forLanguageTag("vi-VN"));
```

Việc thay default locale của JVM tác động đến các thư viện/chức năng khác dùng locale ngầm và có thể gây xung đột khi ứng dụng phục vụ nhiều người. CLI một người dùng vẫn nên truyền locale tường minh để ví dụ dễ mở rộng sang server hoặc giao diện có nhiều phiên.

### 5.2. Vì sao chọn ngôn ngữ bằng whitelist?

Đoạn `switch` chỉ nhận `en` hoặc `vi`. Nếu nhận `fr` rồi chuyển thẳng sang `Locale.FRENCH`, `ResourceBundle` có thể tìm được file root tiếng Anh nên **không ném lỗi**. Chương trình sẽ báo đã đổi ngôn ngữ dù thực ra không có bản dịch tiếng Pháp.

Whitelist giúp hai việc:

- Bảo đảm mã ngôn ngữ thuộc các ngôn ngữ sản phẩm chính thức hỗ trợ.
- Giúp người dùng nhận lỗi rõ ràng khi `lang zz`, thay vì ngầm fallback.

Đối với sản phẩm lớn, có thể quản lý danh sách này trong cấu hình ứng dụng hoặc dùng cấu trúc `Map<String, Locale>`. Không tin rằng `Locale.forLanguageTag` tự xác thực file bundle có tồn tại.

### 5.3. Vì sao đổi cả locale và ResourceBundle?

`ResourceBundle.getBundle(BUNDLE_BASE, requested)` chọn bản dịch. Nhưng `MessageFormat` còn dùng locale để quyết định **quy tắc số**, như dấu nhóm nghìn. Nếu chỉ đổi `messages` mà quên cập nhật `locale`, câu có thể là tiếng Việt nhưng số vẫn theo định dạng Mỹ.

Trình tự trong `changeLanguage`:

1. Xác thực ngôn ngữ.
2. Tạo locale tương ứng (`Locale.US` hoặc `vi-VN`).
3. Tải bundle cho locale mới.
4. Cập nhật hai trường `locale` và `messages`.
5. In thông báo từ **bundle mới**.

Vì vậy lệnh `lang vi` in `Đã chuyển sang tiếng Việt.` chứ không phải dòng English từ bundle cũ.

### 5.4. Vì sao dùng Locale.ROOT cho tên lệnh?

Lệnh `LANG`, `Lang`, `greet`, `COUNT` là **từ khóa kỹ thuật ASCII**, không phải văn bản cần chuyển chữ theo ngữ pháp người dùng. `toLowerCase(Locale.ROOT)` tránh các biến đổi bất ngờ khi default locale là Turkish (ví dụ chữ `I` có quy tắc đặc biệt). Với dữ liệu người dùng thực sự, không áp `Locale.ROOT` bừa bãi để thay thế xử lý ngôn ngữ tự nhiên.

### 5.5. Vì sao BufferedReader chỉ đọc theo dòng?

CLI hoạt động theo **một lệnh trên một dòng**. `readLine()` trả chuỗi không chứa ký tự kết thúc dòng. Nếu stdin kết thúc (`EOF`), trả `null`; code thoát thay vì gọi `split` trên `null`.

`line.strip()` bỏ whitespace đầu/cuối theo định nghĩa Java; `split("\\s+", 2)` tách **tên lệnh** và **phần đối số còn lại**. Tham số thứ hai bằng 2 giúp `greet Nguyễn Văn A` giữ được cả tên `Nguyễn Văn A` thay vì chỉ lấy `Nguyễn`.

**Lưu ý:** đây là CLI demo, không phải bộ parser dòng lệnh tổng quát. `greet "Nguyễn Văn A"` sẽ giữ cả dấu nháy kép như một phần tên, vì chương trình không triển khai shell-style quote parsing. Nếu cần tên tham số có escape, option flags, nhiều tham số với quote hoặc command completion, hãy thiết kế parser riêng hoặc dùng thư viện CLI chuyên dụng.

### 5.6. Vì sao xử lý số bằng long, không ghép string?

`Long.parseLong(argument)` chấp nhận chuỗi số nguyên theo quy tắc parse của Java và sẽ ném `NumberFormatException` khi giá trị không hợp lệ hoặc vượt phạm vi `long`. Sau đó:

- `count < 0` bị từ chối.
- `count == 1` chọn mẫu số ít.
- Các giá trị còn lại chọn mẫu `count.other`.
- `trf(key, count)` truyền `Long` cho `MessageFormat`, nên `{0,number,integer}` có thể định dạng số theo locale.

Không lấy `argument` là chuỗi rồi nhét trực tiếp vào pattern: điều đó giữ nguyên `1234` dù locale cần `1,234` hoặc `1.234`. Nếu sản phẩm cần số lớn hơn `long`, có thể cân nhắc `BigInteger`, quy tắc định dạng riêng và validation hợp đồng.

## 6. Biên dịch và chạy trực tiếp bằng JDK

Không cần Maven/Gradle cho bài thực hành này. Từ thư mục `language-cli`, biên dịch:

```bash
javac -encoding UTF-8 -d out src/main/java/LanguageCli.java
```

`-encoding UTF-8` quy định encoding của **source Java**. Tùy hệ thống, thư mục `out` sẽ được `javac` dùng làm root cho class output.

Trên Linux/macOS, chạy:

```bash
java -cp "out:src/main/resources" LanguageCli
```

Trên Windows PowerShell:

```powershell
java -cp "out;src/main/resources" LanguageCli
```

Dấu phân cách classpath:

- `:` trên hệ Unix (Linux/macOS).
- `;` trên Windows.

Java cần **cả class directory** và **resource directory** trên runtime classpath. `out` chứa `LanguageCli.class`; `src/main/resources` chứa `Messages.properties`, `Messages_en.properties` và `Messages_vi.properties`.

Nếu lệnh chỉ có:

```bash
java -cp out LanguageCli
```

mà `out` chưa chứa file properties, `ResourceBundle.getBundle` không thể tìm thấy base name và có thể ném `MissingResourceException` ngay khi tạo `LanguageCli`.

### Không nhầm charset của tệp nguồn, stdin và stdout

Chương trình dùng `new InputStreamReader(System.in, StandardCharsets.UTF_8)` để **giải mã byte nhập** theo UTF-8. Vì vậy, terminal hoặc pipe **phải thực sự cung cấp byte UTF-8** nếu bạn nhập tên có dấu. Nếu terminal đang gửi một charset khác, tên có thể bị sai. Trên JDK 18+ default charset nhiều API là UTF-8, nhưng bài vẫn truyền tường minh vì **giao thức stdin đã được chọn là UTF-8**.

`System.out`/`System.err` có cơ chế gắn với console và có thể dùng charset khác default charset của JVM. Nếu emoji/dấu tiếng Việt hiện thành ký tự sai, cần kiểm tra encoding ở cả phía Java output và terminal renderer, chứ không vội kết luận file resource sai.

## 7. Chạy thử theo các tình huống

### 7.1. Chuyển sang tiếng Việt và quay lại tiếng Anh

Lần lượt gõ:

```text
lang vi
greet Minh
count 1234
lang en
greet Lan
quit
```

Các thông điệp theo thứ tự:

```text
Đã chuyển sang tiếng Việt.
Xin chào, Minh!
Bạn có 1.234 tin nhắn.
Language switched to English.
Hello, Lan!
Goodbye!
```

Đây là **các dòng phản hồi**, đã lược prompt và các dòng welcome ở đầu phiên. Các dòng định dạng số minh họa JDK hiện đại.

### 7.2. Nhập lệnh sai

Lần lượt thử:

```text
greet
count abc
count -3
lang fr
unknown
```

Khi vẫn ở tiếng Anh, phản hồi tương ứng:

```text
Please provide a name.
Enter a non-negative integer.
Enter a non-negative integer.
Unsupported language. Use en or vi.
Unknown command. Type help.
```

Nếu chuyển sang tiếng Việt **trước** các lệnh sai, cùng các key lỗi sẽ hiển thị bằng tiếng Việt. Không có câu thông báo lỗi nào được hardcode trong phương thức `run()`; tất cả lấy qua `tr(key)`.

### 7.3. Kiểm thử số ít và số nhiều

Với English:

```text
> count 0
You have 0 messages.
> count 1
You have 1 message.
> count 2
You have 2 messages.
```

Với Vietnamese:

```text
> lang vi
Đã chuyển sang tiếng Việt.
> count 1
Bạn có 1 tin nhắn.
> count 2
Bạn có 2 tin nhắn.
```

Code xử lý số lượng **một lần** và chỉ thay mẫu theo key. Mỗi mẫu vẫn là **một câu đầy đủ**, để người dịch có thể đổi trật tự và ngữ pháp khi cần.

Giới hạn của demo: chọn `count.one` khi đúng 1 và `count.other` cho phần còn lại chỉ đủ minh họa hai locale tiếng Anh/Việt được hỗ trợ trong bài. Không áp logic `count == 1` cho mọi ngôn ngữ. Hệ thống sản xuất đa ngôn ngữ nên tham khảo **CLDR plural rules** hoặc một thư viện ICU MessageFormat/MessageFormat có hỗ trợ plural category phù hợp.

## 8. Bài tập mở rộng: ghi nhận key theo tên có nghĩa

Trong chương trình, `tr("greeting")` giúp logic không biết câu bản dịch. `trf("count.other", count)` vừa lấy mẫu vừa định dạng dữ liệu. Đây là bước đầu của một lớp cung cấp thông điệp có thể tái sử dụng.

Với ứng dụng thực tế, có thể tạo giao diện dịch:

```java
interface Localizer {
    String text(String key);
    String format(String key, Object... arguments);
}
```

Đoạn trên là **snippet giao diện**, không phải class chạy độc lập. Implementation có thể nhận `Locale` của phiên/request và `ResourceBundle`; cách này giúp logic nghiệp vụ phụ thuộc một abstraction nhỏ thay vì gọi static `ResourceBundle.getBundle` ở nhiều nơi.

Tuy nhiên, **đừng làm abstraction phức tạp trước khi có nhu cầu**. Với CLI một tệp, hai phương thức `tr`/`trf` đã đủ giải thích nguyên lý. Lớp Localizer có giá trị hơn khi ứng dụng lớn, có mock trong unit tests và nhiều kênh xuất thông điệp.

## 9. ResourceBundle fallback và cache

### 9.1. Locale được chọn không đồng nghĩa có file đúng vùng

Khi dùng `Locale.US` (en-US), Java thường xét các candidate bundle `Messages_en_US`, `Messages_en` rồi root. Trong dự án này không có `Messages_en_US.properties` nên bundle `Messages_en.properties` được dùng.

Tương tự, `vi-VN` không có `Messages_vi_VN.properties` nhưng có `Messages_vi.properties`. Vì thế vẫn in tiếng Việt như mong muốn.

**Không được suy luận rằng `getBundle` sẽ ném lỗi nếu thiếu một locale cụ thể.** Nó có logic fallback. Bản tiếng Anh ở root giúp chương trình vẫn có thông điệp trong một số tình huống, nhưng có thể che giấu lỗi thiếu bản dịch nếu không có translation-coverage test.

### 9.2. Cache là bình thường

`ResourceBundle` có cơ chế cache. Gọi `getBundle` nhiều lần có thể trả một bundle đã tải trước đó. Đối với CLI này:

- `lang vi` lấy bundle tiếng Việt.
- `lang en` lấy bundle tiếng Anh.
- Quay lại `lang vi` không cần reload file từ disk trong mọi trường hợp.

Đừng gọi `ResourceBundle.clearCache()` sau mỗi lệnh `lang`; đổi ngôn ngữ **không có nghĩa** file trên đĩa đã thay đổi. Nếu đang xây hệ thống chỉnh bản dịch trong runtime, cần chiến lược reload/cache control rõ ràng và kiểm thử. Bài thực hành chỉ đọc tài nguyên đi kèm ứng dụng.

## 10. Đóng gói thành JAR để chạy không cần cây source

Biên dịch lại nếu chưa có class:

```bash
javac -encoding UTF-8 -d out src/main/java/LanguageCli.java
```

Tạo JAR từ **nội dung** class output và resource root:

```bash
jar --create --file language-cli.jar -C out . -C src/main/resources .
```

Kiểm tra entry:

```bash
jar tf language-cli.jar
```

Trong output phải có ít nhất các entry liên quan (đây là **trích đoạn**, không phải toàn bộ danh sách):

```text
LanguageCli.class
Messages.properties
Messages_en.properties
Messages_vi.properties
```

Chạy:

```bash
java -cp language-cli.jar LanguageCli
```

Vì ví dụ không cấu hình `Main-Class` trong manifest, chạy `java -jar language-cli.jar` có thể báo không có main manifest attribute. Để tạo executable JAR, có thể dùng:

```bash
jar --create --file language-cli-run.jar --main-class LanguageCli -C out . -C src/main/resources .
java -jar language-cli-run.jar
```

Hai cách đều cần **đóng gói các `Messages*.properties` đúng đường dẫn**. Nếu đóng gói entry `src/main/resources/Messages_vi.properties` bên trong JAR thay vì `Messages_vi.properties` tại root, `getBundle("Messages", ...)` sẽ không tìm được file.

### Dùng Maven/Gradle thì sao?

Trong Maven/Gradle Java project theo cấu trúc chuẩn, `src/main/resources` thường được copy vào classpath output và package vào JAR. Đừng đưa `src/main/resources` làm một thư mục con nằm nguyên bên trong artifact. Kiểm tra bằng `jar tf` sau mỗi thay đổi build liên quan đến resources.

Bài dùng package mặc định để dễ biên dịch thủ công. Với code production, nên dùng package như `com.example.cli` cho Java source và namespace như `com.example.i18n.Messages` cho bundle; khi đó đặt file ở `com/example/i18n` bên trong resources và truyền đúng base name tương ứng.

## 11. Lỗi thường gặp và nguyên nhân

| Hiện tượng | Nguyên nhân thường gặp | Cách sửa |
| --- | --- | --- |
| `MissingResourceException` ngay khi bắt đầu | Không thấy `Messages.properties` hoặc bundle phù hợp | Kiểm tra classpath và file paths |
| IDE chạy nhưng JAR không chạy | Bỏ sót resources khi package | `jar tf` kiểm tra các entry |
| Đổi `lang vi` nhưng vẫn tiếng Anh | Thiếu `Messages_vi.properties`; fallback root | Kiểm tra locale/bundle và translation coverage |
| Gõ `lang fr` nhưng không báo lỗi nếu gọi getBundle trực tiếp | Fallback trả root tiếng Anh | Whitelist supported languages |
| Có câu tiếng Việt nhưng số dùng dấu phẩy Mỹ | Dùng `MessageFormat` với locale US cũ | Cập nhật locale cùng bundle |
| Bản dịch chứa `{0}` nhưng không được thay | In `getString` trực tiếp thay vì format | `new MessageFormat(pattern, locale).format(args)` |
| Lỗi khi xử lý `greet` không có tên | Truy cập đối số rỗng hoặc thiếu | Validation và key `error.name` |
| `count abc` gây crash | Parse số không bắt lỗi | `catch NumberFormatException` |
| `count -5` được xem là số lượng hợp lệ | Không kiểm tra điều kiện nghiệp vụ | Kiểm tra `count >= 0` |
| Dấu tiếng Việt thành ký tự lạ | Charset đầu vào/output, tài nguyên hoặc terminal | Xác định nơi byte bị encode/decode sai |
| Thêm bản dịch nhưng ứng dụng không đổi | Bundle cache hoặc artifact cũ | Kiểm tra đúng bản JAR, vòng đời cache |
| Dùng `Locale.setDefault` giữa nhiều request | Trạng thái JVM chung ảnh hưởng tác vụ khác | Locale per session/request |
| Dịch từng từ rồi nối câu | Trật tự ngữ pháp bị khóa trong code | Mẫu câu nguyên vẹn theo locale |
| Dùng `count == 1` cho mọi ngôn ngữ | Quy tắc plural đa dạng hơn one/other | Sử dụng CLDR/ICU theo locale |
| Đưa tên người dùng thành pattern MessageFormat | Tên có dấu `{ }` hoặc apostrophe có thể gây lỗi syntax | Pattern từ catalog, tên là argument |
| Không escape dấu `'` trong pattern | MessageFormat dùng apostrophe làm syntax | Dùng `''` cho apostrophe literal trong pattern |
| Chia lệnh bằng `split(" ")` không giới hạn | Tên nhiều từ bị tách không mong muốn | `split("\\s+", 2)` |

### Bẫy đặc biệt: MessageFormat và dấu nháy đơn

`MessageFormat` dùng dấu `'` để quote phần literal; muốn hiển thị apostrophe trong pattern, thường phải viết `''`. Ví dụ:

```java
MessageFormat fmt = new MessageFormat(
        "It''s {0}''s message.", Locale.US);
System.out.println(fmt.format(new Object[]{"Lan"}));
// It's Lan's message.
```

Đây là **snippet**, khác với ứng dụng CLI nguyên vẹn. Khi thêm tiếng Anh có dấu nháy trong file `Messages_en.properties`, hãy kiểm thử parse mẫu. Nếu tên người dùng chứa dấu nháy như `O'Connor` thì nó được truyền làm **argument**, không phải template syntax.

## 12. Kiểm thử tự động theo hành vi

Với một CLI đa ngôn ngữ, kiểm tra nhiều hơn việc `getBundle` không ném lỗi. Các nhóm test:

| Nhóm | Dữ liệu | Kỳ vọng |
| --- | --- | --- |
| Start | Không nhập lệnh | Hiển thị app name, welcome, help tiếng Anh |
| Switch vi | `lang vi` | Thông báo tiếng Việt |
| Switch en | `lang en` | Thông báo tiếng Anh |
| Greeting | `greet Lan` | `Hello, Lan!` hoặc `Xin chào, Lan!` |
| Multi-word name | `greet Nguyễn Văn A` | Giữ nguyên tên, không bỏ phần sau khoảng trắng |
| Count 0 | `count 0` | Mẫu `count.other` |
| Count 1 | `count 1` | Mẫu `count.one` |
| Count 2 | `count 2` | Mẫu `count.other` |
| Grouping | `count 1234` | EN có `1,234`; VI có `1.234` theo JDK thử |
| Invalid number | `count NaN` | Trả `error.number`, không crash |
| Negative number | `count -3` | Trả `error.number` |
| Overflow | Số vượt phạm vi `long` | `NumberFormatException` được xử lý |
| Unsupported locale | `lang fr` | Không đổi locale; báo `error.locale` |
| Unknown command | `whatever` | Báo `error.command` trong ngôn ngữ hiện tại |
| Blank line | Chỉ nhập spaces | Bỏ qua mà không crash |
| EOF | Đóng stdin | Thoát sạch, không lặp vô hạn |
| Keys | Mỗi locale | Có đủ key hoặc fallback được chấp nhận theo policy |
| Packaging | Sau tạo JAR | Chạy không cần source resource directory |
| UTF-8 | `greet Đặng Văn A` | Đọc và hiển thị đúng ký tự khi terminal hỗ trợ |

### Các bất biến nên giữ

1. Một chuỗi key giống nhau có thể trả những câu khác nhau theo `Locale`.
2. **Dữ liệu người dùng** như tên không được dịch tự động hoặc thay đổi khi đổi locale.
3. Đổi ngôn ngữ chỉ thay thông điệp/format ở **những lệnh sau**; không cần sửa kết quả đã in.
4. Lệnh `lang fr` không làm mất trạng thái ngôn ngữ cũ.
5. `ResourceBundle` có thể fallback; phải có validation riêng cho danh sách locale sản phẩm hỗ trợ.
6. Resource path trong JAR phải đúng với base name.
7. Bản dịch có thể đổi thứ tự placeholder; điều đó không được làm code phải đổi thứ tự arguments.
8. Input/output byte encoding và locale là **hai trục độc lập**.

### Kiểm thử kiểm tra đủ key

Đối với bộ file ví dụ, có thể dùng `ResourceBundle` để kiểm tra rằng các key cần thiết có thể truy xuất:

```java
ResourceBundle vi = ResourceBundle.getBundle(
        "Messages", Locale.forLanguageTag("vi-VN"));
if (!vi.containsKey("greeting")
        || !vi.containsKey("count.one")
        || !vi.containsKey("count.other")) {
    throw new IllegalStateException("Missing required message");
}
```

Đây là **snippet** trong method. Chú ý `containsKey` xét cả parent, nên không chứng minh **file `Messages_vi.properties` tự có toàn bộ các key**. Muốn bảo đảm translation coverage cho từng file, CI cần đọc trực tiếp catalog hoặc dùng công cụ kiểm tra các key dịch gốc trước khi fallback.

## 13. Cải tiến bài thực hành theo nhu cầu thực tế

### 13.1. Thêm ngôn ngữ thứ ba

Để thêm tiếng Pháp:

1. Tạo `Messages_fr.properties` với các key tương ứng.
2. Bổ sung `case "fr" -> requested = Locale.FRENCH;` vào whitelist.
3. Dịch toàn bộ mẫu câu, kiểm tra apostrophe và grammar.
4. Mở rộng chuỗi help/menu được dịch ở tất cả locale.
5. Test số và cách phân cách nhóm nghìn theo locale Pháp thực tế.
6. Kiểm tra fallback không che các key chưa được dịch.

**Không đủ** nếu chỉ thêm file `Messages_fr.properties` nhưng không thêm `fr` vào whitelist; CLI của bài cố ý chỉ hỗ trợ en và vi. Đồng thời không đủ nếu chỉ thêm `case "fr"` mà chưa có file, bởi `ResourceBundle` vẫn có thể fallback tiếng Anh.

### 13.2. Lưu tùy chọn ngôn ngữ giữa các phiên

CLI demo lưu ngôn ngữ trong **bộ nhớ của một lần chạy**. Khi thoát và mở lại, mặc định English. Nếu cần nhớ lựa chọn, có thể lưu language tag như `"vi"` vào file cấu hình hoặc cơ sở dữ liệu, rồi validate giá trị khi startup.

Không dùng biến môi trường hoặc `Locale.getDefault()` làm kho lưu lựa chọn của một người dùng đa ngôn ngữ nếu hệ thống có nhiều account. Việc lưu preference phải có hợp đồng rõ về người dùng, quyền truy cập và cách fallback khi ngôn ngữ bị gỡ hỗ trợ.

### 13.3. Sử dụng Locale cho số và ngày mà không trộn logic

Trong bài, `MessageFormat` dùng locale hiện hành để định dạng số. Nếu bổ sung `today`, có thể dùng `java.time.format.DateTimeFormatter.ofLocalizedDate(...)` với `withLocale(locale)`, còn ngày/giờ thực tế cần zone riêng nếu ứng dụng có timestamps. **Locale không phải timezone.**

Ví dụ snippet:

```java
DateTimeFormatter formatter =
        DateTimeFormatter.ofLocalizedDate(FormatStyle.LONG)
                .withLocale(locale);
String today = java.time.LocalDate.of(2026, 10, 28)
                .format(formatter);
```

Đoạn này cần import `java.time.format.DateTimeFormatter` và `FormatStyle`, biến `locale` đã định nghĩa. Nó minh họa phần trách nhiệm giao diện; không thêm vào core CLI để tránh làm lệch bài thực hành tập trung ở `ResourceBundle`.

### 13.4. Đổi ngôn ngữ trong ứng dụng nhiều người dùng

Đối với web/server, không nên dùng một biến `static Locale currentLocale` chung cho tất cả request. Một request của user A chọn Vietnamese không được làm request của user B bất ngờ đổi ngôn ngữ. Khi đó, mỗi request/session có locale riêng, và localizer được truyền locale như tham số. Mẫu xử lý của CLI là nền tảng để tách state theo phiên.

## 14. Bài tập có đáp án

**Bài 1.** Vì sao file `Messages_vi.properties` phải nằm trong runtime classpath?

**Đáp án:** `ResourceBundle.getBundle("Messages", locale)` tra tên resource tương ứng từ classpath/module, không tự tìm theo đường dẫn source repo. Nếu file không được copy/đưa vào classpath, Java có thể fallback sang root hoặc báo `MissingResourceException` nếu không tìm được bundle nào.

**Bài 2.** CLI phải đổi gì khi gõ `lang vi`?

**Đáp án:** Chọn `Locale.forLanguageTag("vi-VN")`, tải `ResourceBundle` cho locale đó, lưu cả locale và bundle để bản dịch **và định dạng số** dùng cùng locale, rồi in thông báo bằng bundle mới.

**Bài 3.** Tại sao dùng `Locale.setDefault` không phải cách tốt để đổi ngôn ngữ theo phiên?

**Đáp án:** Default locale là trạng thái JVM có thể ảnh hưởng code khác. Một ứng dụng nhiều request có thể bị rò trạng thái ngôn ngữ. Truyền `Locale` tường minh và giữ nó theo instance/session.

**Bài 4.** Vì sao `count 1` cần key riêng tiếng Anh, còn tiếng Việt trong bài có thể dùng mẫu giống nhau cho one và other?

**Đáp án:** Tiếng Anh trong câu minh họa phân biệt danh từ `message/messages`; tiếng Việt thường dùng `tin nhắn` cho cả hai số lượng. Hai nhánh là minh họa cụ thể, không phải đầy đủ plural rules toàn cầu.

**Bài 5.** Nếu muốn lệnh `greet Nguyễn Văn A` giữ nguyên tên, tại sao phải split với limit 2?

**Đáp án:** Vì phần sau tên lệnh là **một đối số chuỗi nhiều từ**. `split("\\s+", 2)` tách tên lệnh và phần còn lại, không chia nhỏ tên theo khoảng trắng.

**Bài 6.** Nếu `count 1234` in `1,234` ở English nhưng `1.234` ở Vietnamese, logic tính số có đổi không?

**Đáp án:** Không. `count` vẫn là cùng giá trị `long` 1234, chỉ cách trình bày qua `MessageFormat` với locale khác nhau.

**Bài 7.** Lệnh `lang fr` không báo lỗi vì Java vẫn trả một bundle root tiếng Anh. Đây là bug ở đâu?

**Đáp án:** Ở logic hỗ trợ ngôn ngữ của ứng dụng: `ResourceBundle` có fallback. Phải validate supported language tags theo whitelist trước khi gọi/chấp nhận chuyển locale.

**Bài 8.** Để chạy `java -cp language-cli.jar LanguageCli` sau đóng gói, JAR cần entry nào?

**Đáp án:** `LanguageCli.class` và các entry `Messages*.properties` ngay tại JAR root theo base name `Messages`. Có thể kiểm tra bằng `jar tf language-cli.jar`.

**Bài 9.** Thêm chuỗi `title=It's OK` vào file properties rồi format bằng `MessageFormat` có thể có vấn đề gì?

**Đáp án:** Dấu nháy đơn có ý nghĩa cú pháp trong pattern MessageFormat. Muốn literal apostrophe thường cần viết `It''s` và kiểm thử formatter. Nếu không dùng MessageFormat cho key đó, `getString` sẽ trả raw text; phải hiểu rõ key nào là pattern.

**Bài 10.** Vì sao không chỉ kiểm tra `messages.containsKey("greeting")` để kết luận bản tiếng Việt đã dịch?

**Đáp án:** Vì `containsKey` có thể trả true nhờ key kế thừa từ parent/root. Cần kiểm tra coverage trên **file bản dịch thực tế** hoặc dùng pipeline quản lý dịch.

## 15. Tóm tắt kiến thức

- Chương trình CLI đa ngôn ngữ nên tách **command handling** khỏi **localized messages**.
- `ResourceBundle.getBundle(baseName, locale)` đọc tài nguyên theo base name/locale; file phải ở **đúng classpath root**, có suffix `_en`, `_vi` tương ứng.
- `Locale` quyết định quy tắc ngôn ngữ/định dạng; `MessageFormat` đặt giá trị động `{0}` vào **mẫu câu hoàn chỉnh**.
- Chuyển `lang vi` hoặc `lang en` chỉ cần cập nhật **locale + bundle** của phiên, không gọi `Locale.setDefault`.
- Không giả định thiếu một bản dịch sẽ ném lỗi, bởi `ResourceBundle` có fallback. Hãy **validate** ngôn ngữ hỗ trợ và độ phủ key.
- Với số lượng, validation đầu vào và logic plural phải tách khỏi text; nhánh one/other chỉ là khởi đầu cho hai locale minh họa.
- Biên dịch/chạy bằng `javac`/`java -cp` hoặc đóng gói `jar`; kiểm tra đúng file `Messages*.properties` trong artifact cuối.
- Khi kiểm thử i18n, phải kiểm tra **đổi ngôn ngữ trong cùng phiên**, số/placeholder, lỗi nhập liệu, Unicode, fallback và JAR packaging.

**Tài liệu chính thức:**

- [Java SE 21 — ResourceBundle](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/ResourceBundle.html)
- [Java SE 21 — PropertyResourceBundle](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/PropertyResourceBundle.html)
- [Java SE 21 — MessageFormat](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/text/MessageFormat.html)
- [Java SE 21 — Locale](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Locale.html)
- [OpenJDK JEP 226 — UTF-8 Property Resource Bundles](https://openjdk.org/jeps/226)
- [CLDR — Plural Rules](https://cldr.unicode.org/index/cldr-spec/plural-rules)
