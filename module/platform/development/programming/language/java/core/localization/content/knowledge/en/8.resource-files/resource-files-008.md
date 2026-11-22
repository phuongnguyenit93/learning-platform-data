# Phát hiện khóa trùng, khóa thiếu, khóa thừa và khoảng trắng ngoài ý muốn trong tệp tài nguyên Java

## 1. Vì sao cần kiểm tra chất lượng tệp tài nguyên?

Ứng dụng Java thường lưu văn bản bản địa hóa trong các tệp `.properties` để `ResourceBundle` chọn theo ngôn ngữ và khu vực, chẳng hạn `messages.properties`, `messages_vi.properties`, `messages_en.properties`. Khi số ngôn ngữ và số khóa tăng, bốn lỗi dễ xảy ra:

1. **Khóa trùng:** cùng một khóa được khai báo từ hai lần trở lên trong một tệp. Khi tải bằng `Properties.load`, lần xuất hiện sau ghi đè giá trị trước, thường không có lỗi mặc định.
2. **Khóa thiếu:** một bản dịch không có khóa dự kiến từ danh mục khóa chuẩn. Khi chạy qua `ResourceBundle`, ứng dụng có thể kế thừa bản dịch từ bundle cha, khiến lỗi khó nhận biết.
3. **Khóa thừa:** bản dịch chứa khóa không còn nằm trong danh mục chuẩn hoặc chỉ được viết nhầm tên. Khóa có thể bị bỏ quên mãi và không bao giờ được sử dụng.
4. **Khoảng trắng ngoài ý muốn:** dấu cách hoặc tab ở đầu/cuối **giá trị thực**, ở khóa, hoặc cuối dòng vật lý. Chúng có thể làm lệch giao diện, sai phép so sánh và che lỗi nối dòng.

Tệp tải thành công **không đồng nghĩa tài nguyên đúng**. Kiểm tra cần dựa vào cả **giá trị sau khi parser xử lý** và **văn bản nguồn**. Không thể dùng một trong hai để thay thế hoàn toàn cho bên kia.

Một ví dụ sai thường gặp:

~~~properties
button.save=Lưu
button.save=Lưu ngay
~~~

Đọc bằng `Properties.load(...)` cho kết quả cuối `button.save = Lưu ngay`. Cần quy trình kiểm tra trước khi build/deploy nếu việc ghi đè là không được phép.

## 2. Hiểu đúng cú pháp .properties trước khi viết linter

Tệp `.properties` không chỉ gồm các dòng `key=value`. Java hỗ trợ:

- Các dấu phân tách khóa–giá trị: `=`, `:` hoặc khoảng trắng chưa được escape.
- Dòng trống, dòng chú thích bắt đầu bằng `#` hoặc `!` sau phần trắng dẫn đầu.
- Escape như `\ ` (dấu cách), `\=`, ``, `\n`, `\t` và `\uXXXX`.
- Dòng nối tiếp khi dòng logic kết thúc bằng số lượng lẻ dấu `` liên tiếp (line continuation).
- Các biến thể viết khóa có **cùng giá trị logic** sau unescape.

Ví dụ:

~~~properties
button.save=Save
button\.save=Save again
status : ready
welcome.message = Hello
~~~

Hai dòng đầu tạo ra **hai khóa khác nhau** vì `button\.save` không cần escape dấu chấm và vẫn thành `button.save`? **Không:** theo ngữ nghĩa `Properties`, escape ký tự `.` không phải một dạng escape đặc biệt nhưng dấu `` bị loại bỏ, nên kết quả vẫn là khóa `button.save`; do đó phải coi là *khóa trùng* sau khi parse. Trường hợp này nhấn mạnh việc so sánh nguyên văn bên trái dấu `=` có thể bỏ sót trùng lặp.

Cách viết an toàn cho ví dụ đó là hiểu rõ hiệu ứng parser: `status : ready` sinh `status = ready`, còn `welcome.message = Hello` sinh giá trị `Hello` (khoảng trắng ngay sau delimiter mặc định bị bỏ qua).

Một số quy tắc khoảng trắng dễ nhầm:

| Dạng nguồn | Kết quả khi đọc `Properties` | Kết luận QA |
| --- | --- | --- |
| `label = Hello` | `Hello` | Dấu cách quanh delimiter là cú pháp hợp lệ, không tự coi là lỗi |
| `label=Hello   ` | `Hello   ` | Khoảng trắng cuối **giá trị** có thể là lỗi |
| `label=Hello\u0020` | `Hello ` | Escape Unicode tạo dấu cách có thật trong giá trị |
| `label=  Hello` | `Hello` | Khoảng trắng sau delimiter bị bỏ qua; linter giá trị không nhìn thấy nó |
| `message=Hello\ World` | `Hello World` | Dấu cách trong nội dung có chủ đích |
| `key\ name=value` | Khóa logic `key name` | Khóa có dấu cách là hợp lệ về cú pháp nhưng thường nên hạn chế theo quy ước đặt tên |
| `welcome.message = Hello` | Khóa `welcome.message`, giá trị `Hello` | Khoảng trắng thông thường ở vùng delimiter |

Dấu cách giữa các từ là cần thiết trong bản dịch: **không được xóa mọi khoảng trắng**. Phát hiện whitespace phải cho người dịch biết **vị trí đáng nghi**, để quyết định trường hợp nào là chủ đích.

**Lưu ý encoding:** `Properties.load(InputStream)` đọc byte theo ISO-8859-1; nếu muốn kiểm tra tài nguyên UTF-8, dùng `Properties.load(Reader)` với `Files.newBufferedReader(path, StandardCharsets.UTF_8)`. Với `ResourceBundle` trên Java 17, `PropertyResourceBundle` mặc định thử UTF-8 (có cơ chế fallback sang ISO-8859-1 trong trường hợp dữ liệu không hợp lệ theo UTF-8). Nếu trộn nhiều chế độ đọc, kiểm tra có thể cho kết quả khác nhau. Chốt encoding của dự án và dùng nhất quán.

## 3. Khóa trùng: phải phát hiện ngay trong một tệp

`java.util.Properties` là một `Map` dạng key → value; khi `load` gặp key đã tồn tại, giá trị sau thay thế giá trị trước. Do đó:

~~~java
Properties props = new Properties();
props.load(reader);
System.out.println(props.getProperty("button.save"));
~~~

Đoạn minh họa trên chỉ thấy **giá trị cuối**; `Properties` đã không còn lưu danh sách lần xuất hiện. Muốn phát hiện trùng sau chuẩn hóa cú pháp, cần theo dõi mỗi lần parser thêm key hoặc dùng công cụ kiểm tra chuyên biệt.

Ở Java 17, `Properties.load` đưa các mục đã parse vào `put`. Ta có thể tạo lớp con theo dõi việc key xuất hiện lại:

~~~java
static final class CheckedProperties extends Properties {
    final Set<String> duplicates = new TreeSet<>();

    @Override
    public synchronized Object put(Object key, Object value) {
        if (containsKey(key)) {
            duplicates.add((String) key);
        }
        return super.put(key, value);
    }
}
~~~

Đây là **một phần của chương trình đầy đủ ở mục 6**, không phải file biên dịch riêng. Nó bắt được cả những khai báo khác nhau về dấu phân cách/escape nếu parser đưa chúng về cùng **khóa logic**. Ví dụ:

~~~properties
title=Title
title:Another title
title = Third title
~~~

Kết quả là một key `title` trong `Properties`, nhưng tập `duplicates` phát hiện `title`. Công cụ trong ví dụ chỉ ghi tên key trùng, **không ghi số dòng**; nếu cần số dòng chính xác, phải có parser/lexer giữ metadata dòng vật lý và dòng logic theo đúng quy tắc `.properties`.

Không kiểm tra trùng bằng cách đếm số dòng chứa `=`: phương pháp đó sai cho separator `:`, khoảng trắng, comment, escape và các dòng nối tiếp.

## 4. Khóa thiếu: so với tập khóa chuẩn, không chỉ dựa trên runtime fallback

Giả sử `messages.properties` là **danh mục khóa chuẩn**:

~~~properties
title=Orders
button.save=Save
button.cancel=Cancel
status.new=New
greeting=Hello
~~~

Tệp `messages_vi.properties` chỉ có:

~~~properties
title=Đơn hàng
button.save=Lưu
button.cancel=Hủy
~~~

Tập khóa thiếu trong bản dịch tiếng Việt là:

~~~text
[greeting, status.new]
~~~

Cách tính theo tập hợp:

~~~java
Set<String> missing = new TreeSet<>(base.stringPropertyNames());
missing.removeAll(translated.stringPropertyNames());
~~~

Đây là **đoạn minh họa**, cần `base`, `translated` là hai `Properties` được tải riêng, cùng import `java.util.Set`, `java.util.TreeSet`.

Một điểm quan trọng: `ResourceBundle.getBundle("messages", Locale.forLanguageTag("vi-VN"))` có thể trả về bundle con liên kết với cha, và `bundle.containsKey("greeting")` vẫn trả `true` do key được kế thừa. Vì thế **không dùng `ResourceBundle.keySet()` của bundle con để khẳng định bản dịch trực tiếp đã đủ khóa**. Hãy phân tích file nguồn riêng lẻ hoặc metadata riêng từng bundle.

Khóa thiếu có luôn là lỗi không? Tùy hợp đồng bản địa hóa:

- Nếu mỗi ngôn ngữ phải dịch **100% các khóa bắt buộc**, thiếu là lỗi build/CI.
- Nếu hệ thống cho phép bản dịch vùng (`messages_vi_VN.properties`) chỉ ghi những khác biệt so với tiếng Việt chung (`messages_vi.properties`), thiếu là **kế thừa có chủ đích**.
- Nếu một số message chỉ dùng ở tính năng riêng, danh mục chuẩn nên nêu rõ nhóm optional/feature-specific, không phán đoán bằng một phép so set đơn giản.

Phải quy định **file nào làm chuẩn** và **file nào được phép kế thừa** trước khi kết luận một bản dịch “không đầy đủ”.

## 5. Khóa thừa và khoảng trắng ngoài ý muốn

### 5.1. Phát hiện khóa thừa

Tập khóa thừa:

~~~java
Set<String> extra = new TreeSet<>(translated.stringPropertyNames());
extra.removeAll(base.stringPropertyNames());
~~~

Ví dụ tệp tiếng Việt chứa thêm `obsolete.key`, trong khi tệp gốc không có khóa này, kiểm tra sẽ trả:

~~~text
[obsolete.key]
~~~

Đây là **ứng viên cần rà soát**, không có nghĩa luôn phải xóa: một tệp chuyên biệt có thể được thiết kế để chứa khóa riêng theo region/feature. Ngược lại, khóa bị đánh sai chính tả (`button.svae`) thường đồng thời tạo ra **một khóa thiếu** (`button.save`) và **một khóa thừa** (`button.svae`), là tín hiệu khá tốt để sửa.

### 5.2. Khoảng trắng ở giá trị sau khi parse

Sau `Properties.load(Reader)`, kiểm tra đầu/cuối giá trị bằng `String.strip()`:

~~~java
String value = props.getProperty(key);
if (!value.equals(value.strip())) {
    System.out.println("Suspicious outer whitespace: " + key);
}
~~~

Đây là **đoạn minh họa**; `props` là biến `Properties`, `key` là `String` lấy từ tập khóa. Không tự `strip()` khi ghi lại resource hoặc sửa bản dịch: có thông điệp cố tình chứa xuống dòng hoặc khoảng trắng ở cuối, và việc tự sửa có thể thay đổi ý nghĩa trình bày. `strip()` dựa trên `Character.isWhitespace`; nó không phát hiện mọi loại dấu cách Unicode như no-break space (NBSP). Nếu dự án cần phát hiện `U+00A0`, dấu cách không ngắt dòng hoặc ký tự vô hình, phải bổ sung kiểm tra Unicode có chủ đích.

### 5.3. Khoảng trắng ở nguồn vật lý

Parser `.properties` có thể bỏ qua khoảng trắng sau delimiter, xử lý dòng continuation và diễn giải escape. Vì vậy kiểm tra giá trị đã parse **không thấy được** tất cả lỗi style ở tệp gốc.

Một kiểm tra đơn giản và ít tranh cãi là đánh dấu **dấu cách/tab ở cuối dòng vật lý** trong file nguồn. Các dòng kết thúc bằng dấu cách hoặc tab có thể che dấu `` nối dòng hoặc tạo giá trị có whitespace vô ý. Có thể duyệt `Files.readAllLines` và kiểm tra ký tự cuối từng dòng.

**Không nên tự động xóa whitespace cuối file trước khi kiểm tra cú pháp continuation:** nếu một dòng đang có `` ở cuối và dấu cách phía sau, việc xóa dấu cách có thể biến hai dòng logic độc lập thành một dòng nối tiếp, làm thay đổi key/value. Nên báo và sửa có kiểm thử.

Với **khoảng trắng đầu dòng**, cú pháp properties chấp nhận thụt dòng và bỏ qua khoảng trắng trước key. Vì vậy không được tự đánh dấu mọi dòng thụt đầu là lỗi; thay vào đó thống nhất quy ước code style và linter nhận diện được continuation.

## 6. Chương trình Java 17 hoàn chỉnh: kiểm tra một cặp tệp

Đặt ba file sau trong cùng thư mục. Dữ liệu chủ đích có: một khóa trùng ở tệp dịch; hai khóa thiếu; một khóa thừa; một dấu cách ở cuối giá trị được tạo bằng escape `\u0020`. Chọn escape thay vì gõ dấu cách cuối dòng để người đọc thấy rõ dữ liệu mẫu.

**File `messages.properties`**:

~~~properties
title=Orders
button.save=Save
button.cancel=Cancel
status.new=New
greeting=Hello
~~~

**File `messages_vi.properties`**:

~~~properties
title=Đơn hàng
button.save=Lưu
button.save=Lưu ngay
button.cancel=Hủy\u0020
obsolete.key=Cũ
~~~

**File `ResourceFileAudit.java`**:

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.Properties;
import java.util.Set;
import java.util.TreeSet;

public class ResourceFileAudit {
    static final class CheckedProperties extends Properties {
        final Set<String> duplicates = new TreeSet<>();

        @Override
        public synchronized Object put(Object key, Object value) {
            if (containsKey(key)) {
                duplicates.add((String) key);
            }
            return super.put(key, value);
        }
    }

    static CheckedProperties read(Path path) throws IOException {
        CheckedProperties result = new CheckedProperties();
        try (var reader = Files.newBufferedReader(
                path, StandardCharsets.UTF_8)) {
            result.load(reader);
        }
        return result;
    }

    static Set<String> difference(Set<String> left, Set<String> right) {
        Set<String> result = new TreeSet<>(left);
        result.removeAll(right);
        return result;
    }

    static Set<String> outerWhitespaceKeys(CheckedProperties props) {
        Set<String> result = new TreeSet<>();
        for (String key : props.stringPropertyNames()) {
            if (!key.equals(key.strip())) {
                result.add(key);
            }
        }
        return result;
    }

    static Set<String> outerWhitespaceValues(CheckedProperties props) {
        Set<String> result = new TreeSet<>();
        for (String key : props.stringPropertyNames()) {
            String value = props.getProperty(key);
            if (!value.equals(value.strip())) {
                result.add(key);
            }
        }
        return result;
    }

    static List<Integer> physicalTrailingWhitespace(Path path)
            throws IOException {
        List<String> lines =
                Files.readAllLines(path, StandardCharsets.UTF_8);
        List<Integer> result = new ArrayList<>();
        for (int i = 0; i < lines.size(); i++) {
            String line = lines.get(i);
            if (line.endsWith(" ") || line.endsWith("\t")) {
                result.add(i + 1); // Số dòng trong file bắt đầu từ 1.
            }
        }
        return result;
    }

    public static void main(String[] args) throws IOException {
        if (args.length != 2) {
            System.err.println(
                    "Usage: java ResourceFileAudit base.properties translation.properties");
            System.exit(2);
        }

        Path basePath = Path.of(args[0]);
        Path translationPath = Path.of(args[1]);
        CheckedProperties base = read(basePath);
        CheckedProperties translated = read(translationPath);

        Set<String> baseKeys = base.stringPropertyNames();
        Set<String> translatedKeys = translated.stringPropertyNames();

        System.out.println("base duplicates: " + base.duplicates);
        System.out.println("translation duplicates: "
                + translated.duplicates);
        System.out.println("missing in translation: "
                + difference(baseKeys, translatedKeys));
        System.out.println("extra in translation: "
                + difference(translatedKeys, baseKeys));
        System.out.println("translation outer whitespace keys: "
                + outerWhitespaceKeys(translated));
        System.out.println("translation outer whitespace values: "
                + outerWhitespaceValues(translated));
        System.out.println("translation physical trailing lines: "
                + physicalTrailingWhitespace(translationPath));
    }
}
~~~

Chạy từ thư mục chứa cả ba file với **JDK 17+**:

~~~bash
javac -encoding UTF-8 ResourceFileAudit.java
java ResourceFileAudit messages.properties messages_vi.properties
~~~

**Stdout kỳ vọng** (các tập dùng `TreeSet`, thứ tự ổn định):

~~~text
base duplicates: []
translation duplicates: [button.save]
missing in translation: [greeting, status.new]
extra in translation: [obsolete.key]
translation outer whitespace keys: []
translation outer whitespace values: [button.cancel]
translation physical trailing lines: []
~~~

Giải thích: các dòng `button.save` trùng được parser đưa về một key, nhưng `CheckedProperties.put` ghi nhận lần khai báo lặp; `greeting` và `status.new` thiếu; `obsolete.key` không nằm trong danh mục gốc; escape `\u0020` tạo dấu cách cuối giá trị `button.cancel`; tuy nhiên trong file nguồn, dòng đó kết thúc bằng ký tự `0`, nên **không có dấu cách cuối dòng vật lý**.

Chương trình là **công cụ kiểm tra tối thiểu có thể chạy được**, không phải một parser đưa ra số dòng cho từng khóa trùng. Nó cũng không tự quyết định khóa thiếu/thừa là lỗi theo chính sách: phần đó phải được cấu hình theo mục tiêu dịch thuật của từng ứng dụng.

## 7. Kiểm tra thực tế trong dự án nhiều locale

Khi có `messages.properties`, `messages_vi.properties`, `messages_vi_VN.properties`, `messages_en.properties`…, không nên so sánh mọi file với root bằng cùng một quy tắc:

| Loại tệp | Chính sách đề xuất | Vì sao |
| --- | --- | --- |
| Root `messages.properties` | Định nghĩa danh mục khóa chuẩn, không trùng, không lỗi whitespace | Là cơ sở so sánh |
| Bundle theo ngôn ngữ `messages_vi.properties` | Yêu cầu đầy đủ khóa nếu sản phẩm cam kết dịch hoàn chỉnh | Ngăn thiếu bản dịch bị fallback che |
| Bundle theo khu vực `messages_vi_VN.properties` | Chỉ cần các khóa ghi đè; không bắt buộc trùng toàn bộ root | Phù hợp mô hình kế thừa con–cha |
| Bundle tùy tính năng | So với danh mục khóa riêng của tính năng | Tránh coi các key đặc thù là thừa |
| Bundle được sinh từ nền tảng dịch | Chạy QA sau export, trước khi đóng gói | Tránh để lỗi escape/Unicode lọt vào sản phẩm |

Đối với dự án thật, định nghĩa cấu hình kiểu:

~~~yaml
base: messages.properties
complete:
  - messages_vi.properties
  - messages_en.properties
overrides:
  - messages_vi_VN.properties
required:
  - title
  - button.save
  - button.cancel
~~~

Đây là **một ví dụ chính sách QA ở định dạng YAML**, không phải cấu hình được Java hay `ResourceBundle` tự hiểu. Công cụ build/CI phải được lập trình để áp dụng chính sách này. Với **override bundles**, chỉ kiểm tra key lạ và trùng; khóa thiếu có thể là bình thường.

Cũng nên kiểm tra placeholder (`{0}`, `{1}`...), dấu nháy của `MessageFormat`, bản dịch rỗng, encoding và câu dài bất thường. Những kiểm tra này khác nhóm bốn lỗi của bài hiện tại nhưng thường được kết hợp trong bước kiểm tra tài nguyên trước khi phát hành.

## 8. Các trường hợp biên cần chú ý

### Khóa bị đổi do escape hoặc ký tự Unicode

Hai khóa trông khác trong editor có thể cùng **khóa logic** sau `Properties.load`, ví dụ `title` và `ti\u0074le`. Ngược lại, các ký tự Unicode trông giống nhau có thể có mã điểm khác (ký tự tổ hợp và dạng dựng sẵn). `Properties` không tự chuẩn hóa Unicode theo NFC để giúp nhóm dịch, nên nếu chuẩn tên khóa chỉ cho ASCII hoặc normalization NFC, cần thêm kiểm tra theo chính sách riêng.

### Dòng continuation

Ví dụ:

~~~properties
long.message=Hello \
    world
~~~

Hai dòng vật lý tạo một giá trị logic, và khoảng trắng đầu dòng tiếp nối có thể bị parser bỏ qua. Một linter chỉ đọc từng dòng riêng có thể hiểu sai đây là hai key. Công cụ ví dụ dùng `Properties.load(Reader)` nên so sánh **key/value logic** đúng theo cú pháp Java; phần quét dòng vật lý chỉ báo dấu cách/tab cuối dòng và không đoán key.

### Khóa trùng sau khi parse

Ví dụ:

~~~properties
button.save=Save
button.save:Save again
~~~

`Properties` giữ `Save again`. Để chặn duplicate một cách đáng tin, nên chạy kiểm tra trong pipeline từ **file nguồn**; nếu chỉ nhìn `ResourceBundle` sau khi load thì không còn lịch sử vị trí từng khai báo.

### Khoảng trắng hợp lệ và không hợp lệ về nghiệp vụ

Một thông điệp như `indent=\\u0020\\u0020Name` cố ý có hai dấu cách đầu; một linter `strip()` sẽ cảnh báo. Không coi mọi cảnh báo là bug. Đặc biệt có thể có NBSP, thin space, tab hoặc newline cần giữ nguyên. Thiết kế allowlist theo key, ghi chú cho người dịch và kiểm thử giao diện để xác nhận intent.

### ResourceBundle cache và parent fallback

`ResourceBundle.getBundle` có cache và kế thừa tài nguyên cha. Nếu sửa file trên đĩa trong khi JVM chạy, việc đọc lại bundle không chắc phản ánh nội dung mới ngay. QA file nguồn nên chạy trong build/CI hoặc môi trường kiểm thử sạch, không suy ra tập key trực tiếp từ đối tượng bundle đã cache.

### Trùng giữa hai ngôn ngữ không phải “duplicate key”

Việc `messages.properties` và `messages_vi.properties` cùng có `button.save` là **hợp lệ và cần thiết**: bundle con ghi đè cha. **Duplicate** cần phát hiện là **cùng một khóa xuất hiện lặp lại trong chính một file/bundle đơn**, không phải việc khóa có mặt ở nhiều locale khác nhau.

## 9. Quy trình kiểm tra tự động và kiểm thử

Một quy trình đơn giản để tích hợp vào CI:

1. **Xác định danh mục chuẩn:** root hoặc manifest của ứng dụng, có quy tắc optional và override rõ ràng.
2. **Đọc từng file riêng lẻ bằng charset thống nhất:** ưu tiên UTF-8, bắt lỗi file không hợp lệ và lỗi escape.
3. **Bắt khóa trùng trước khi mất thông tin:** theo dõi ở bước parse như `CheckedProperties.put`.
4. **Tính missing/extra theo chính sách:** file dịch đầy đủ so với root; file chuyên biệt theo vùng có quy tắc khác.
5. **Quét whitespace:** phân biệt semantic value, logical key, physical source line và Unicode invisible characters.
6. **Xuất báo cáo hữu ích:** file, loại lỗi, key, vị trí dòng nếu parser có metadata; với warning, nêu rõ tiêu chí và lý do.
7. **Fail build với lỗi nghiêm trọng:** duplicate, missing-required, extra không được phép; các whitespace warning có thể cần người dịch xác nhận.
8. **Kiểm tra runtime:** đảm bảo resource bundle tải được, override/fallback đúng và UI không lẫn ngôn ngữ do thiếu khóa.

Các trường hợp nên tự tạo trong test: key trùng với `=` và `:`, key dùng escape, comment chứa `=`, key ở dòng continuation, giá trị rỗng có chủ đích, file dùng UTF-8, file có CRLF, file chỉ có root và override vùng, dấu cách cuối giá trị, tab cuối dòng, no-break space và file chưa có tên locale đúng quy ước.

Để tránh false positive, hãy kiểm thử theo **quy tắc cấu hình**: tệp theo vùng được phép thiếu key do kế thừa, tệp theo ngôn ngữ đầy đủ thì không; một số nội dung được phép khoảng trắng có chủ đích.

## 10. Những lỗi phổ biến và cách xử lý

| Lỗi | Vì sao nguy hiểm | Cách sửa |
| --- | --- | --- |
| Chỉ gọi `Properties.load` rồi so số lượng key | Khóa trùng đã bị ghi đè, đếm cuối không phát hiện | Theo dõi số lần khai báo trong parser |
| Dùng `split("=")` để đếm khóa | Bỏ sót `:`, escape, continuation và comment | Dùng parser properties tương thích Java |
| Dùng `ResourceBundle.keySet()` để đo đủ khóa trực tiếp | Key được kế thừa từ cha vẫn xuất hiện | So từng file nguồn, xét chính sách bundle |
| Gọi mọi missing key là lỗi | Bundle vùng cố ý chỉ ghi đè | Phân loại complete vs override |
| Xóa mọi extra key tự động | Một số key dùng riêng cho locale/feature | Xác minh manifest, phạm vi feature |
| Tự gọi `trim()` và ghi đè mọi bản dịch | Có thể thay nội dung hợp lệ; `trim` không đầy đủ với Unicode | Cảnh báo, review, sửa có kiểm chứng |
| Coi whitespace quanh delimiter là phần của value | Parser bỏ các khoảng trắng cú pháp đó | Kiểm tra theo giá trị logic và nguồn |
| Đọc UTF-8 bằng `load(InputStream)` | Dữ liệu có dấu có thể bị giải mã sai | Dùng `Reader` UTF-8 hoặc cơ chế ResourceBundle phù hợp |
| Quên rằng tệp resource đã cache | Test dựa vào dữ liệu cũ | QA trên file build và kiểm soát cache/reload |
| Trông thấy `button.save` ở hai locale rồi báo trùng | Đây là override thông thường | Chỉ bắt trùng **trong một tài nguyên đơn** |

## 11. Bài tập thực hành

Từ hai file mẫu ở mục 6, thử tuần tự:

1. Xóa một trong hai dòng `button.save` của `messages_vi.properties`: danh sách duplicate phải rỗng, còn missing/extra giữ nguyên.
2. Thêm `greeting=Xin chào` vào tệp dịch: missing chỉ còn `status.new`.
3. Xóa `obsolete.key`: extra phải rỗng.
4. Đổi `button.cancel=Hủy\u0020` thành `button.cancel=Hủy`: cảnh báo outer whitespace của giá trị biến mất.
5. Thêm một dấu cách ở **cuối dòng vật lý** (không phải chuỗi escape): `physicalTrailingWhitespace` sẽ liệt kê số dòng đó.
6. Đặt `button.save:Lưu ngay` thay cho cú pháp `=` ở dòng trùng: duplicate vẫn bị phát hiện do hai cách phân tách cùng một khóa logic.
7. Đổi tệp dịch thành override locale theo vùng, cho phép kế thừa mọi khóa không khai báo: thay chính sách kiểm tra, không thay parser.
8. Tạo `button.save` và `button\.save` trong cùng file: thử quan sát hai key có được parser đưa về cùng tên không; đây là lý do không dùng regex thô để kết luận uniqueness.

Mỗi bài tập tách **lỗi dữ liệu**, **cơ chế parser** và **chính sách bản dịch**. Khi hiểu ranh giới đó, bạn sẽ biết khi nào nên fail build, khi nào nên cảnh báo và khi nào một khóa thiếu là kế thừa có chủ đích.

## 12. Ghi nhớ

Với các tệp tài nguyên của Java, hãy kiểm tra **cú pháp nguồn trước khi nạp**, **key/value logic sau khi nạp**, rồi **đối chiếu các tập khóa theo quy tắc từng loại bundle**. Duplicate bị che bởi cơ chế ghi đè; missing có thể bị fallback từ parent che; extra có thể là lỗi chính tả hoặc key chuyên biệt hợp lệ; whitespace có thể bị parser bỏ qua hoặc trở thành một phần giá trị thực.

Một bước QA có kiểm soát, chạy trước khi build/deploy, sẽ bảo đảm resource bundle không chỉ tải được mà còn có nội dung đáng tin cậy, đồng thời tránh làm hỏng những khoảng trắng và override có chủ đích.

**Tài liệu tham khảo:**

- Java SE 17 `Properties`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Properties.html
- Java SE 17 `ResourceBundle`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ResourceBundle.html
- Java SE 17 `PropertyResourceBundle`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/PropertyResourceBundle.html
