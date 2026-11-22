# Locale, múi giờ, encoding và dữ liệu ngẫu nhiên trong build

Một build Java có thể chạy thành công trên máy developer và CI nhưng tạo ra artifact khác nhau dù cùng commit. Nguyên nhân không nhất thiết nằm ở source code hoặc dependency. Các giá trị mặc định của hệ điều hành và JVM như locale, múi giờ, charset, thứ tự file, thời điểm hiện tại và dữ liệu ngẫu nhiên cũng có thể ảnh hưởng đến mã nguồn được sinh, resource được đóng gói, nội dung tài liệu, test và byte của archive cuối cùng.

Muốn build có thể tái tạo, cần kiểm soát những giá trị này như các đầu vào build thực sự. Không nên để kết quả phụ thuộc ngầm vào ngôn ngữ của máy, timezone của agent, encoding mặc định, thứ tự duyệt thư mục hoặc seed ngẫu nhiên không được ghi nhận.

Bài này giải thích từng nguồn biến thiên, phân biệt môi trường chạy build với môi trường chạy ứng dụng, cách cố định cấu hình trong Java/Maven/Gradle và cách kiểm tra để xác định vì sao hai lần build tạo kết quả khác nhau.

## 1. Tái lập build và các nguồn biến thiên của môi trường

Một build có tính tái lập khi cùng source, dependency, cấu hình và các đầu vào được kiểm soát có thể tạo ra đầu ra tương đương. Với reproducible artifact theo nghĩa chặt, archive có thể giống nhau ở mức byte. Để đạt điều đó, build cần tránh hoặc kiểm soát những đầu vào ngầm.

Các nguồn biến thiên thường gặp:

| Nguồn | Ví dụ | Tác động có thể xảy ra |
|---|---|---|
| Locale | en_US, vi_VN, tr_TR | Định dạng số/ngày, chữ hoa-thường, sắp xếp, thông báo |
| Timezone | UTC, Asia/Ho_Chi_Minh, America/Los_Angeles | Ngày giờ được sinh, timestamp trong file, test qua nửa đêm |
| Charset | UTF-8, Windows-1252, Shift_JIS | Đọc/ghi source và resource khác nhau, ký tự bị lỗi |
| Line ending | LF, CRLF | Nội dung file hoặc archive khác byte |
| Random seed | Seed ngẫu nhiên theo thời gian | File sinh, test data, tên ID và thứ tự dữ liệu khác nhau |
| Đồng hồ hệ thống | Thời điểm build hiện tại | Version metadata, banner, manifest hoặc file được sinh khác nhau |
| Thứ tự file | Thứ tự duyệt thư mục phụ thuộc filesystem | Archive, index hoặc resource tổng hợp khác nhau |
| Phiên bản runtime | JDK/CLDR/tzdb khác nhau | Charset, timezone rules, locale data hoặc compiler output khác |
| Môi trường CI | Biến môi trường, user home, OS | Đường dẫn, cấu hình mặc định và dependency resolution khác |

Không phải mọi khác biệt đều là lỗi. Một ứng dụng cần hiển thị ngày theo timezone người dùng thì kết quả theo timezone là hành vi mong muốn. Nhưng build phát hành thư viện thường cần một quy ước ổn định, ví dụ luôn sinh metadata theo UTC và UTF-8.

## 2. Phân biệt môi trường build với môi trường chạy ứng dụng

Một quy trình Java có thể có nhiều tiến trình JVM khác nhau:

1. JVM chạy Gradle hoặc Maven.
2. JVM/compiler được dùng để biên dịch source.
3. JVM fork để chạy unit test hoặc integration test.
4. JVM chạy ứng dụng sau khi deploy.

Các tiến trình này có thể dùng JDK khác nhau, nhận system property khác nhau và chạy trong môi trường khác nhau. Đặt timezone hoặc encoding cho Maven process không tự động bảo đảm test forked JVM hay ứng dụng production dùng cùng giá trị.

~~~text
CI agent
  |
  +-- JVM của Gradle/Maven
  |      Locale, timezone, charset của build tool
  |
  +-- javac / compiler toolchain
  |      Đọc source và tạo bytecode
  |
  +-- JVM test fork
  |      Chạy test với system properties riêng
  |
  +-- JVM ứng dụng khi deploy
         Cấu hình runtime do môi trường triển khai cấp
~~~

Khi một file được sinh trong build sai ngày hoặc sai ký tự, cần xác định tiến trình nào tạo file đó. Khi test lỗi do timezone, phải kiểm tra JVM chạy test chứ không chỉ JVM chạy build tool. Khi ứng dụng production hiển thị ngày sai, cấu hình JVM runtime hoặc dữ liệu đầu vào của ứng dụng mới là nơi cần xem.

## 3. Locale: ngôn ngữ, quy tắc định dạng và so sánh

Locale mô tả quy ước ngôn ngữ và vùng văn hóa mà chương trình dùng khi định dạng hoặc xử lý dữ liệu. Java biểu diễn locale bằng lớp **java.util.Locale**.

Locale có thể ảnh hưởng đến:

- Định dạng ngày, tháng, giờ và số.
- Dấu thập phân và dấu phân nhóm hàng nghìn.
- Ký hiệu tiền tệ.
- Quy tắc viết hoa/viết thường của một số ngôn ngữ.
- So sánh và sắp xếp chuỗi theo quy tắc ngôn ngữ.
- Nội dung message từ ResourceBundle.
- Nội dung tài liệu hoặc file cấu hình do build task sinh ra.

Ví dụ, cùng một số có thể được hiển thị với dấu phân cách khác nhau:

~~~java
import java.text.NumberFormat;
import java.util.Locale;

public class NumberExample {
    public static void main(String[] args) {
        double amount = 12345.67;

        System.out.println(
            NumberFormat.getNumberInstance(Locale.US).format(amount)
        );
        System.out.println(
            NumberFormat.getNumberInstance(Locale.GERMANY).format(amount)
        );
        System.out.println(
            NumberFormat.getNumberInstance(Locale.forLanguageTag("vi-VN"))
                .format(amount)
        );
    }
}
~~~

Các locale có thể tạo ra chuỗi khác nhau cho cùng giá trị số. Nếu build sinh file JSON, CSV, SQL seed hoặc tài liệu từ dữ liệu số mà dùng locale mặc định của máy, artifact có thể khác nhau.

### 3.1. Không dùng locale mặc định cho dữ liệu máy đọc

Nếu chuỗi là dữ liệu dành cho giao tiếp giữa các hệ thống, hãy chọn định dạng rõ ràng thay vì dựa vào default locale.

Ví dụ, định dạng số theo locale mặc định có thể tạo dấu thập phân khác nhau trên các máy. Nếu định dạng cần ổn định theo quy ước giao thức, dùng locale cụ thể:

~~~java
String text = NumberFormat.getNumberInstance(Locale.ROOT)
    .format(1234.5);
~~~

Với định dạng cần tuân theo chuẩn API hoặc file format, tốt hơn nữa là dùng serializer có quy tắc xác định. Ví dụ JSON number phải dùng dấu chấm theo cú pháp JSON chứ không phụ thuộc locale hiển thị.

Locale mặc định phù hợp với giao diện người dùng khi sản phẩm chủ động muốn theo ngôn ngữ/vùng của người dùng. Nó không phù hợp làm quy tắc ngầm cho file build, tên artifact, khóa cấu hình, ID hoặc dữ liệu giao tiếp.

### 3.2. Viết hoa và viết thường: dùng Locale.ROOT cho identifier

Một lỗi kinh điển xuất hiện với locale tiếng Thổ Nhĩ Kỳ. Chuyển chữ i thành chữ hoa có thể cho kết quả khác với quy tắc tiếng Anh. Nếu dùng String.toUpperCase() hoặc toLowerCase() không truyền locale, Java dùng default locale của JVM.

Không nên dùng cách chuyển chữ thường theo locale mặc định nếu chuỗi là identifier kỹ thuật, tên biến cấu hình, token hoặc khóa không phụ thuộc ngôn ngữ. Hãy dùng:

~~~java
String key = input.toLowerCase(Locale.ROOT);
String normalized = input.toUpperCase(Locale.ROOT);
~~~

Locale.ROOT biểu thị locale trung lập, phù hợp với thao tác chuẩn hóa chuỗi không dành cho ngôn ngữ cụ thể. Nếu mục tiêu là hiển thị văn bản tự nhiên cho người dùng, hãy truyền locale người dùng một cách tường minh.

### 3.3. Sắp xếp chuỗi và dữ liệu

Thứ tự từ điển phụ thuộc locale nếu dùng Collator. Cùng một danh sách tên có thể được sắp xếp khác nhau theo tiếng Việt, tiếng Anh hoặc locale khác. Điều này có thể làm file index, resource tổng hợp hoặc generated source khác nhau.

Nếu build cần thứ tự kỹ thuật ổn định, hãy định nghĩa comparator rõ ràng. Ví dụ sắp xếp theo chuỗi Unicode/code point hoặc một khóa đã chuẩn hóa bằng quy tắc cố định. Không nên dùng locale mặc định để quyết định thứ tự entry trong artifact.

Nếu yêu cầu là thứ tự ngôn ngữ để hiển thị người dùng, locale phải là một đầu vào được khai báo rõ và cần được ghi nhận cùng output.

### 3.4. ResourceBundle và message theo locale

ResourceBundle có thể chọn file resource khác nhau theo locale:

~~~text
messages.properties
messages_en.properties
messages_vi.properties
messages_fr.properties
~~~

Khi code gọi ResourceBundle.getBundle("messages"), Java có thể chọn bundle phù hợp với default locale. Nếu một build task chạy code để sinh tài liệu hoặc fixture, output có thể thay đổi theo locale của agent.

Nếu cần một locale cụ thể, hãy truyền rõ:

~~~java
ResourceBundle bundle = ResourceBundle.getBundle(
    "messages",
    Locale.forLanguageTag("en-US")
);
~~~

Nếu muốn kiểm tra fallback behavior, hãy viết test riêng cho từng locale thay vì phụ thuộc vào locale mặc định của máy chạy test.

## 4. Timezone: thời gian tuyệt đối và thời gian địa phương

Timezone xác định cách ánh xạ một thời điểm tuyệt đối sang giờ địa phương. Java có API trong java.time, bao gồm:

- Instant: một thời điểm trên timeline, không gắn timezone hiển thị.
- LocalDate: ngày lịch không chứa giờ hoặc timezone.
- LocalTime: giờ trong ngày không chứa ngày/timezone.
- LocalDateTime: ngày và giờ địa phương, không xác định một thời điểm tuyệt đối nếu chưa có zone/offset.
- ZoneId: múi giờ như UTC hoặc Asia/Ho_Chi_Minh.
- ZonedDateTime: ngày giờ kết hợp timezone.
- OffsetDateTime: ngày giờ kết hợp UTC offset cụ thể.

Timezone mặc định của JVM thường được truy vấn bằng ZoneId.systemDefault(). Nó phụ thuộc môi trường hệ điều hành/JVM và có thể khác giữa developer, container và CI agent.

### 4.1. Dùng UTC cho timestamp kỹ thuật

Nếu cần ghi thời điểm build vào metadata, log hoặc file machine-readable, thường nên dùng Instant và biểu diễn theo UTC:

~~~java
import java.time.Instant;

String generatedAt = Instant.now().toString();
~~~

Kết quả có dạng ISO-8601 UTC, ví dụ 2026-11-13T08:00:00Z. Nó tránh việc cùng một thời điểm được ghi dưới dạng giờ địa phương khác nhau trên các máy.

Tuy nhiên, dùng UTC không tự làm build tái lập nếu vẫn gọi Instant.now() trong mỗi lần build. Giá trị vẫn thay đổi theo thời điểm chạy. Nếu timestamp không cần thiết cho artifact, tốt nhất bỏ nó khỏi output. Nếu cần timestamp release, lấy từ một đầu vào release được kiểm soát và dùng cùng giá trị cho mọi artifact của release đó.

### 4.2. Tránh dùng LocalDateTime.now() cho metadata cần tái lập

LocalDateTime.now() dựa vào đồng hồ và timezone mặc định của máy. Cùng một thời điểm có thể tạo giá trị khác ở hai timezone. Nếu cần chuyển một Instant sang giờ địa phương, chỉ rõ ZoneId:

~~~java
ZonedDateTime vietnamTime = Instant.now()
    .atZone(ZoneId.of("Asia/Ho_Chi_Minh"));
~~~

Đối với build artifact, hãy quyết định rõ output cần UTC hay một timezone cụ thể. Đừng để ZoneId.systemDefault() tự quyết định.

### 4.3. Daylight Saving Time và dữ liệu timezone

Một số timezone có quy tắc Daylight Saving Time (DST), khiến offset thay đổi theo ngày. Một local date-time có thể bị mơ hồ hoặc không tồn tại tại thời điểm chuyển đổi DST. Các quy tắc timezone cũng được cập nhật theo thay đổi pháp lý và dữ liệu tzdb đi kèm JDK.

Nếu test hoặc build logic tính lịch theo timezone, kết quả có thể thay đổi khi JDK/tzdb được nâng cấp. Hãy:

- Dùng ZoneId cụ thể thay vì timezone mặc định.
- Dùng Instant cho timestamp tuyệt đối.
- Dùng ZonedDateTime khi quy tắc lịch địa phương thực sự cần thiết.
- Pin JDK trong CI khi cần output nhất quán qua nhiều lần build.
- Tạo test cho ngày chuyển DST và các mốc biên nếu logic có xử lý lịch.

## 5. Encoding: cách chuyển byte thành ký tự

Encoding xác định cách biểu diễn ký tự thành byte và ngược lại. Nếu cùng một file được đọc bằng charset khác nhau, nội dung chuỗi có thể bị sai hoặc không giải mã được.

Các nguồn encoding trong build Java gồm:

- Encoding của source file khi compiler đọc .java.
- Encoding của resource khi build tool copy/filter.
- Encoding của file được sinh bởi plugin hoặc task.
- Encoding khi ứng dụng đọc/ghi file.
- Encoding của console/terminal khi in log.
- Encoding của archive entry hoặc manifest theo quy tắc định dạng tương ứng.

Đừng gộp các nguồn này thành một khái niệm duy nhất. Ví dụ đặt encoding cho compiler không tự động cấu hình mọi API đọc file của ứng dụng hoặc encoding của console.

### 5.1. Ưu tiên UTF-8 một cách tường minh

Với source code và resource text, UTF-8 thường là lựa chọn phù hợp để chia sẻ giữa các hệ điều hành và IDE.

Maven có thể khai báo:

~~~xml
<properties>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    <project.reporting.outputEncoding>UTF-8</project.reporting.outputEncoding>
</properties>
~~~

Gradle Java compile task:

~~~kotlin
tasks.withType<JavaCompile>().configureEach {
    options.encoding = "UTF-8"
}
~~~

Khi dùng javac trực tiếp:

~~~bash
javac -encoding UTF-8 -d out src/main/java/com/example/Main.java
~~~

Khai báo này làm rõ encoding compiler dùng để đọc source. Nó không tự chuyển các file source đang lưu bằng encoding khác sang UTF-8; cần bảo đảm nội dung file thực sự được lưu bằng encoding đã khai báo.

### 5.2. Đọc và ghi file với charset rõ ràng

Không nên dựa vào default charset cho dữ liệu cần tái lập. Hãy chỉ định charset:

~~~java
String text = Files.readString(path, StandardCharsets.UTF_8);

Files.writeString(
    path,
    text,
    StandardCharsets.UTF_8
);
~~~

Với stream:

~~~java
try (BufferedReader reader = Files.newBufferedReader(
        path, StandardCharsets.UTF_8)) {
    // đọc nội dung
}
~~~

Tương tự, khi dùng InputStreamReader hoặc OutputStreamWriter, truyền StandardCharsets.UTF_8 thay vì constructor không có charset.

### 5.3. Charset mặc định của Java qua các phiên bản

Từ JDK 18, UTF-8 là default charset chuẩn của Java theo JEP 400 trong hầu hết môi trường thông thường. Trên JDK cũ hơn, default charset có thể phụ thuộc hệ điều hành và locale/code page. Dù JDK hiện đại mặc định UTF-8, vẫn nên chỉ định charset trong code và build configuration vì:

- Dự án có thể build trên JDK cũ.
- Một số API hoặc plugin có quy tắc encoding riêng.
- Console encoding có thể khác file encoding.
- File nguồn/resource có thể không thực sự là UTF-8.
- Explicit encoding giúp người đọc biết hợp đồng dữ liệu.

Không nên dùng việc đổi file.encoding như cách sửa dữ liệu đã được lưu sai encoding. Hãy xác định byte nguồn và charset đúng trước.

### 5.4. Encoding của console khác encoding file

Khi log có tiếng Việt bị lỗi trên terminal, có thể file được đọc đúng nhưng console/terminal dùng code page khác. Trên Windows, PowerShell, Command Prompt, CI agent và JVM có thể có thiết lập console riêng.

Để chẩn đoán:

1. Kiểm tra file output bằng editor hỗ trợ hiển thị encoding.
2. Ghi một chuỗi Unicode vào file UTF-8 rồi đọc lại bằng UTF-8.
3. So sánh nội dung file với nội dung console.
4. Kiểm tra terminal code page và cấu hình console của CI.

Đừng thay đổi encoding của artifact chỉ để log console hiển thị đúng. File format và giao diện console là hai lớp khác nhau.

## 6. Line ending và chuẩn hóa file text

Ngoài charset, kiểu xuống dòng cũng có thể làm nội dung file khác nhau:

- LF (\n) phổ biến trên Linux/macOS.
- CRLF (\r\n) phổ biến trên Windows.

Nếu một task đọc file rồi ghi lại, hoặc archive chứa source/resource text, line ending khác nhau có thể làm checksum khác nhau dù nội dung nhìn bằng mắt gần như giống nhau.

Git có thể chuẩn hóa line ending bằng .gitattributes, ví dụ:

~~~text
* text=auto
*.java text eol=lf
*.xml text eol=lf
*.properties text eol=lf
*.sh text eol=lf
*.bat text eol=crlf
~~~

Quy tắc cụ thể tùy repository. Sau khi thay đổi .gitattributes, nhóm cần chuẩn hóa file hiện có theo chính sách đã chọn và thống nhất cách checkout trên các máy.

Khi sinh file text, hãy quy định cả charset và line ending. Đừng dùng System.lineSeparator() nếu output cần byte-for-byte giống nhau giữa Windows và Linux; có thể ghi LF cố định theo format.

## 7. Dữ liệu ngẫu nhiên: seed quyết định kết quả

Randomness thường được dùng trong build/test để sinh dữ liệu mẫu, ID, thứ tự, khóa, tên file hoặc fixture. Nếu mỗi lần chạy dùng seed khác nhau, output cũng thay đổi.

Ví dụ:

~~~java
Random random = new Random();
int value = random.nextInt(1000);
~~~

Constructor không truyền seed tạo chuỗi số phụ thuộc seed được khởi tạo tự động. Hai lần chạy có thể tạo value khác nhau.

Nếu dữ liệu cần tái lập, hãy dùng seed tường minh:

~~~java
Random random = new Random(123456789L);
int value = random.nextInt(1000);
~~~

Với cùng thuật toán Random và cùng chuỗi lời gọi, seed cố định giúp tái tạo chuỗi kết quả. Điều này hữu ích cho fixture, test property-based hoặc dữ liệu demo được sinh trong build.

### 7.1. Seed phải là đầu vào được ghi nhận

Một seed cố định trong code làm output ổn định nhưng kém linh hoạt. Có thể nhận seed từ property hoặc biến môi trường, đồng thời ghi lại seed dùng cho lần build:

~~~java
long seed = Long.parseLong(
    System.getProperty("fixture.seed", "123456789")
);
Random random = new Random(seed);
~~~

Khi test thất bại, log seed giúp tái hiện trường hợp đó. Với build task, seed phải được khai báo là input của task. Nếu task đọc seed từ environment mà Gradle/Maven không biết đó là input, build cache có thể trả lại output cũ dù seed đã thay đổi.

Một quy tắc hữu ích:

- Seed cố định cho build phát hành cần output tái lập.
- Seed được ghi nhận cho test fuzz/property-based để tái tạo lỗi.
- Seed thay đổi có chủ đích cho stress test, nhưng lưu seed vào log/artifact test report.

### 7.2. Chọn random generator phù hợp

java.util.Random là lựa chọn đơn giản và có thuật toán xác định theo seed. SplittableRandom hữu ích cho một số tác vụ sinh dữ liệu và parallel computation có phân tách luồng random. Các API mới hơn trong java.util.random cung cấp abstraction RandomGenerator.

Ví dụ:

~~~java
RandomGenerator generator = RandomGeneratorFactory
    .<RandomGenerator>of("L64X128MixRandom")
    .create(123456789L);
~~~

Khi cần tái lập lâu dài, hãy pin thuật toán/generator cụ thể và JDK version liên quan. Không chỉ ghi seed mà bỏ qua loại generator, vì các thuật toán khác nhau có thể tạo chuỗi khác nhau từ cùng seed.

### 7.3. Không cố định seed cho mục đích bảo mật

Seed cố định chỉ phù hợp với dữ liệu test, fixture hoặc output cần tái lập. Không dùng seed cố định cho password, token, session ID, nonce, key hoặc dữ liệu bảo mật.

Với mục đích bảo mật, dùng SecureRandom và để hệ thống cung cấp entropy phù hợp. Không hy sinh tính an toàn chỉ để làm output giống nhau giữa các lần chạy.

## 8. Randomness trong test và property-based testing

Test có thể dùng dữ liệu ngẫu nhiên để mở rộng phạm vi đầu vào. Tuy nhiên, test không lưu seed hoặc không ghi dữ liệu gây lỗi sẽ khó tái hiện.

Một pattern tốt là truyền seed vào generator và in seed khi test thất bại:

~~~java
long seed = Long.getLong("test.seed", 20261113L);
Random random = new Random(seed);

// Tạo fixture từ random và chạy assertion.
System.out.println("Test seed: " + seed);
~~~

Với property-based testing, framework thường có cơ chế lưu seed hoặc shrink failing input. Hãy giữ lại thông tin replay mà framework cung cấp thay vì tự tạo random không kiểm soát.

Tránh dùng random trong test nếu test chỉ cần một fixture đơn giản. Dữ liệu cố định thường dễ đọc, dễ debug và ít gây flakiness hơn. Khi cần random, hãy làm cho seed và dữ liệu đầu vào có thể tái tạo.

## 9. Thời gian hiện tại cũng là một nguồn không xác định

Ngay cả khi timezone là UTC, gọi đồng hồ hiện tại vẫn tạo output khác theo thời điểm:

~~~java
String buildDate = Instant.now().toString();
~~~

Các ví dụ thường gặp:

- Generated source chứa ngày tạo file.
- Resource properties chứa build.timestamp.
- Manifest hoặc banner ghi thời điểm build.
- Test giả định ngày hôm nay.
- Archive entry lưu modification time.
- Version metadata có build number dựa trên clock.

Nếu timestamp không cần thiết, hãy loại bỏ nó khỏi artifact. Nếu cần, truyền giá trị từ pipeline như một input có kiểm soát và dùng cùng giá trị cho mọi bước release.

### 9.1. Tiêm Clock thay vì gọi đồng hồ toàn cục trong logic test

Java cung cấp Clock để tách nguồn thời gian khỏi logic:

~~~java
public final class ExpirationPolicy {
    private final Clock clock;

    public ExpirationPolicy(Clock clock) {
        this.clock = clock;
    }

    public boolean isExpired(Instant expiresAt) {
        return !clock.instant().isBefore(expiresAt);
    }
}
~~~

Trong production có thể truyền Clock.systemUTC(). Trong test, dùng clock cố định:

~~~java
Clock fixedClock = Clock.fixed(
    Instant.parse("2026-01-15T10:00:00Z"),
    ZoneOffset.UTC
);
~~~

Test không còn phụ thuộc thời điểm chạy hoặc timezone của máy. Đây là cách thiết kế ứng dụng/test; nó cũng hữu ích cho code generator hoặc task build cần tính toán ngày giờ.

### 9.2. SOURCE_DATE_EPOCH và timestamp của build

Một số hệ sinh thái build/release dùng biến môi trường SOURCE_DATE_EPOCH như quy ước biểu diễn thời điểm nguồn cố định để tạo archive tái lập. Không phải mọi plugin Maven, Gradle hoặc Java tool đều tự đọc biến này.

Nếu dự án chọn dùng quy ước đó, pipeline cần:

1. Chọn một timestamp ổn định, ví dụ thời điểm commit hoặc thời điểm release.
2. Cấp cùng giá trị cho mọi job tạo artifact.
3. Cấu hình plugin/task đọc giá trị này.
4. Không để một bước khác ghi timestamp hiện tại vào archive sau đó.

Không nên giả định chỉ đặt SOURCE_DATE_EPOCH là toàn bộ build đã reproducible. Cần kiểm tra plugin thực sự hỗ trợ và xác nhận output.

## 10. Thứ tự duyệt file và dữ liệu collection

Một task có thể quét thư mục để sinh index, resource bundle, source registry hoặc archive. Thứ tự trả về từ filesystem không nên được xem là ổn định giữa các OS hoặc filesystem.

Không nên phụ thuộc trực tiếp vào thứ tự duyệt:

~~~java
try (Stream<Path> paths = Files.list(inputDir)) {
    paths.forEach(this::process);
}
~~~

Nếu output cần ổn định, hãy sắp xếp rõ ràng:

~~~java
try (Stream<Path> paths = Files.list(inputDir)) {
    paths.sorted(Comparator.comparing(
        path -> path.getFileName().toString()
    )).forEach(this::process);
}
~~~

Tương tự, không nên phụ thuộc vào iteration order của collection không cam kết thứ tự. Nếu thứ tự output quan trọng:

- Dùng List đã sắp xếp.
- Dùng TreeMap/TreeSet với comparator xác định.
- Sắp xếp key trước khi serialize.
- Chuẩn hóa đường dẫn thành slash / nếu ghi vào archive/metadata.
- Không dùng absolute path của máy developer trong output.

### 10.1. Parallel processing và kết quả không xác định

Parallel task hoặc stream có thể hoàn tất theo thứ tự khác nhau giữa các lần chạy. Nếu mỗi worker ghi nối vào cùng một file hoặc cập nhật collection dùng chung, output có thể thay đổi hoặc gặp race condition.

Hãy để mỗi worker tạo output riêng, sau đó hợp nhất theo một thứ tự xác định. Nếu dùng parallel stream, không dựa vào side effect có thứ tự trong forEach; cân nhắc forEachOrdered khi thứ tự thực sự cần thiết hoặc gom kết quả rồi sort trước khi ghi.

## 11. Chuẩn hóa đường dẫn và tên file

Windows thường không phân biệt chữ hoa/chữ thường trong tên file theo cách mặc định của Linux; filesystem cũng có thể khác về Unicode normalization. Nếu build tạo tên file từ input, cần tránh tạo hai tên chỉ khác hoa/thường hoặc dạng Unicode mà một filesystem không phân biệt được.

Thực hành tốt:

- Dùng quy tắc tên file ổn định, chẳng hạn chữ thường và ký tự ASCII cho generated identifier khi phù hợp.
- Không đưa absolute path vào nội dung generated file hoặc manifest nếu không cần.
- Chuẩn hóa separator thành slash / khi tạo entry archive.
- Sắp xếp đường dẫn theo comparator xác định.
- Kiểm tra case sensitivity và tên file trên cả Windows/Linux nếu hỗ trợ hai môi trường.

Ví dụ, đường dẫn source src/main/resources/com/example/config.json nên được biểu diễn trong archive bằng slash /, bất kể hệ điều hành build.

## 12. Maven: cố định locale, timezone và encoding

Maven chạy trong một JVM. Các JVM system properties có thể được cấp qua MAVEN_OPTS, file .mvn/jvm.config hoặc cách khởi chạy CI. Cần phân biệt các thuộc tính dành cho Maven process với thuộc tính dành cho Surefire/Failsafe forked JVM.

### 12.1. Cấu hình JVM của Maven

File .mvn/jvm.config có thể chứa các JVM options áp dụng khi Maven Wrapper/launcher khởi chạy Maven:

~~~text
-Duser.language=en
-Duser.country=US
-Duser.timezone=UTC
-Dfile.encoding=UTF-8
~~~

Hoặc cấp qua MAVEN_OPTS trong CI. Các thuộc tính trên ảnh hưởng default locale, timezone và một số API charset trong JVM Maven theo phiên bản/runtime. Đừng coi đây là cấu hình tự động cho mọi JVM con mà plugin fork ra.

### 12.2. Encoding source và resource trong POM

Khai báo:

~~~xml
<properties>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    <project.reporting.outputEncoding>UTF-8</project.reporting.outputEncoding>
</properties>
~~~

project.build.sourceEncoding là property phổ biến được nhiều Maven plugin dùng cho source/resource. project.reporting.outputEncoding thường được dùng cho output báo cáo. Vẫn cần kiểm tra plugin cụ thể và cấu hình encoding riêng nếu plugin không đọc các property này.

Maven Compiler Plugin có thể cấu hình:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-compiler-plugin</artifactId>
    <version>3.13.0</version>
    <configuration>
        <release>21</release>
        <encoding>UTF-8</encoding>
    </configuration>
</plugin>
~~~

### 12.3. Cấu hình test JVM

Nếu test được fork bởi Maven Surefire/Failsafe, hãy đặt system properties cho đúng plugin. Ví dụ với Surefire:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-surefire-plugin</artifactId>
    <version>3.5.2</version>
    <configuration>
        <systemPropertyVariables>
            <user.timezone>UTC</user.timezone>
            <user.language>en</user.language>
            <user.country>US</user.country>
            <file.encoding>UTF-8</file.encoding>
        </systemPropertyVariables>
    </configuration>
</plugin>
~~~

Nếu test chạy trong cùng JVM Maven thay vì fork, thuộc tính Maven process có thể được dùng. Cần kiểm tra fork configuration và log của plugin. Failsafe dùng cho integration test có cấu hình tương ứng riêng.

### 12.4. Timestamp archive Maven

Nhiều Maven archive plugin dựa trên Maven Archiver hỗ trợ property project.build.outputTimestamp để đặt timestamp ổn định cho entry archive. Ví dụ:

~~~xml
<properties>
    <project.build.outputTimestamp>2026-01-01T00:00:00Z</project.build.outputTimestamp>
</properties>
~~~

Hỗ trợ và hành vi phụ thuộc plugin/version tạo archive. Hãy kiểm tra tài liệu plugin đang dùng và xác nhận cả JAR, WAR, source/Javadoc archive hoặc assembly đều sử dụng timestamp được kiểm soát. Một property không được plugin tiêu thụ sẽ không thay đổi output.

## 13. Gradle: cố định locale, timezone và encoding

Gradle có nhiều nơi để cấu hình JVM chạy build và JVM chạy test. File gradle.properties có thể cung cấp JVM arguments cho Gradle daemon:

~~~properties
org.gradle.jvmargs=-Xmx2g -Dfile.encoding=UTF-8 -Duser.timezone=UTC -Duser.language=en -Duser.country=US
~~~

Các thuộc tính này áp dụng cho JVM daemon của Gradle. Nếu một task fork JVM riêng, cần cấu hình task đó.

### 13.1. Encoding cho compiler

Kotlin DSL:

~~~kotlin
tasks.withType<JavaCompile>().configureEach {
    options.encoding = "UTF-8"
    options.release = 21
}
~~~

Groovy DSL:

~~~groovy
tasks.withType(JavaCompile).configureEach {
    options.encoding = 'UTF-8'
    options.release = 21
}
~~~

Đặt encoding rõ ràng để compiler đọc source nhất quán. Nếu project có Kotlin, Scala hoặc generator plugin, cấu hình encoding cho từng compiler/task tương ứng.

### 13.2. Cấu hình test JVM

Kotlin DSL:

~~~kotlin
tasks.withType<Test>().configureEach {
    systemProperty("user.timezone", "UTC")
    systemProperty("user.language", "en")
    systemProperty("user.country", "US")
    systemProperty("file.encoding", "UTF-8")
}
~~~

Groovy DSL:

~~~groovy
tasks.withType(Test).configureEach {
    systemProperty 'user.timezone', 'UTC'
    systemProperty 'user.language', 'en'
    systemProperty 'user.country', 'US'
    systemProperty 'file.encoding', 'UTF-8'
}
~~~

Điều này đặt system property cho test process theo cách Gradle cấu hình. Nếu test chạy qua plugin hoặc container task khác, hãy cấu hình đúng task fork đó.

### 13.3. Reproducible JAR với Gradle

Gradle archive tasks có thể được cấu hình để không giữ timestamp gốc của file và sắp xếp entry theo thứ tự tái lập:

~~~kotlin
tasks.withType<AbstractArchiveTask>().configureEach {
    isPreserveFileTimestamps = false
    isReproducibleFileOrder = true
}
~~~

Hai tùy chọn này giúp archive không phụ thuộc timestamp sửa file và thứ tự filesystem theo cách mặc định. Chúng không bảo đảm toàn bộ nội dung artifact giống nhau nếu generated file vẫn chứa thời gian hiện tại, random seed, absolute path hoặc dữ liệu môi trường khác.

## 14. Cố định môi trường trong CI

CI nên khai báo rõ các đầu vào môi trường cần thiết thay vì dựa vào default của runner.

Ví dụ shell trên Linux:

~~~bash
export LANG=en_US.UTF-8
export LC_ALL=en_US.UTF-8
export TZ=UTC

./mvnw -B clean verify
~~~

Hoặc với Gradle:

~~~bash
export LANG=en_US.UTF-8
export LC_ALL=en_US.UTF-8
export TZ=UTC

./gradlew --no-daemon clean build
~~~

Các biến LANG/LC_ALL là thiết lập locale của môi trường Unix-like; TZ là thiết lập timezone thường được nhiều chương trình nhận biết. Java cũng có system properties riêng như user.timezone, user.language và user.country. Cần kiểm tra môi trường runner thực tế, vì container image có thể thiếu locale được yêu cầu hoặc có cách cấu hình khác.

Trên Windows, có thể đặt JVM system properties qua cấu hình Gradle/Maven hoặc biến môi trường của job. Không nên giả định biến LANG hoạt động giống Unix trên mọi phiên bản Windows.

### 14.1. Ghi nhận môi trường build

Khi cần tái hiện khác biệt giữa hai job, lưu lại:

- JDK vendor và version.
- Gradle/Maven wrapper version.
- OS và architecture.
- Locale mặc định.
- Timezone mặc định.
- Default charset.
- Các biến môi trường có ảnh hưởng đến build (không ghi secret).
- Seed ngẫu nhiên.
- Commit hash và dependency lock/metadata.

Có thể in một số giá trị từ Java:

~~~java
System.out.println("locale=" + Locale.getDefault());
System.out.println("timezone=" + ZoneId.systemDefault());
System.out.println("charset=" + Charset.defaultCharset());
System.out.println("java.version=" + System.getProperty("java.version"));
~~~

Nếu in trong test, giá trị phản ánh test JVM. Nếu in trong task/plugin, nó phản ánh JVM thực thi đoạn code đó. Đặt cùng đoạn diagnostic ở sai tiến trình có thể dẫn đến kết luận nhầm.

## 15. Dữ liệu ngẫu nhiên trong build task và build cache

Một Gradle task hoặc Maven plugin có thể sinh dữ liệu từ random generator. Nếu seed thay đổi mà task không khai báo nó là input, cache có thể trả output cũ hoặc build không nhận biết output cần tạo lại.

Với Gradle task custom, mọi giá trị ảnh hưởng output cần được khai báo bằng input property. Ví dụ khái niệm:

~~~kotlin
abstract class GenerateFixtures : DefaultTask() {
    @get:Input
    abstract val seed: Property<Long>

    @get:OutputDirectory
    abstract val outputDirectory: DirectoryProperty

    @TaskAction
    fun generate() {
        val random = Random(seed.get())
        val output = outputDirectory.get().asFile
        // Tạo file fixture theo seed và ghi output ổn định.
    }
}
~~~

Đoạn code minh họa cách mô hình hóa seed như input và thư mục sinh ra như output. Task thực tế cần tạo nội dung xác định, quản lý file cũ và tránh ghi ngoài output directory.

Nếu seed lấy từ environment, map nó vào task input property. Không đọc biến môi trường tùy tiện bên trong action mà không khai báo, vì build cache và up-to-date checking cần biết giá trị nào làm thay đổi output.

Với Maven plugin, cần bảo đảm parameter được khai báo trong Mojo và được đưa vào trạng thái/input của goal theo cách phù hợp. Không có cơ chế cache task giống Gradle trong mọi Maven build, nhưng việc khai báo parameter rõ ràng vẫn giúp build minh bạch và tái lập.

## 16. Dữ liệu được sinh theo thứ tự ổn định

Ngay cả khi seed đã cố định, output vẫn có thể khác nếu thứ tự input thay đổi. Ví dụ một generator:

1. Duyệt danh sách file không sắp xếp.
2. Gán số thứ tự hoặc ID tăng dần cho từng file.
3. Ghi kết quả vào JSON.

Nếu filesystem trả file theo thứ tự khác, cùng seed có thể gán dữ liệu cho file khác nhau. Vì vậy, cần ổn định cả input order lẫn random seed.

Một pattern tốt:

~~~java
List<Path> inputs;
try (Stream<Path> stream = Files.walk(sourceDirectory)) {
    inputs = stream
        .filter(Files::isRegularFile)
        .sorted(Comparator.comparing(
            path -> sourceDirectory.relativize(path)
                .toString()
                .replace(File.separatorChar, '/')
        ))
        .toList();
}

Random random = new Random(seed);
for (Path input : inputs) {
    // Sinh output theo thứ tự đã chuẩn hóa.
}
~~~

Nếu generator chạy song song, cần xác định cách chia random stream và cách hợp nhất output. Dùng chung một Random từ nhiều thread có thể làm kết quả phụ thuộc lịch chạy. Có thể chia seed theo input một cách xác định, ví dụ hash của seed gốc và đường dẫn chuẩn hóa, rồi mỗi input có generator riêng.

## 17. Kiểm tra reproducibility bằng hai lần build sạch

Một cách thực tế để tìm nguồn biến thiên là build hai lần từ cùng commit trong môi trường được kiểm soát, sau đó so sánh artifact.

Quy trình cơ bản:

1. Checkout cùng commit vào hai workspace sạch.
2. Dùng cùng JDK, build tool wrapper, dependency và cấu hình.
3. Cố định locale, timezone, charset và seed.
4. Build artifact ở cả hai workspace.
5. Tính checksum và so sánh.
6. Nếu khác, liệt kê nội dung archive và so sánh từng entry.

Ví dụ:

~~~bash
sha256sum build-a/libs/app.jar
sha256sum build-b/libs/app.jar
~~~

Nếu checksum khác, so sánh nội dung:

~~~bash
jar --list --file build-a/libs/app.jar
jar --list --file build-b/libs/app.jar
~~~

Giải nén hai archive vào hai thư mục rồi so sánh file. Nếu chỉ khác META-INF/MANIFEST.MF, kiểm tra build metadata/timestamp. Nếu khác resource, kiểm tra filtering, encoding, locale hoặc generator. Nếu entry giống nhưng archive hash khác, kiểm tra ZIP timestamps, entry order và compression metadata.

### 17.1. Không nhầm cache với reproducibility

Build nhanh do cache không đồng nghĩa build tái lập. Cache có thể che việc một task đọc đầu vào ngầm hoặc giữ output cũ. Hãy thử build sạch hoặc tắt cache khi điều tra:

~~~bash
./gradlew clean build --no-build-cache
~~~

Với Maven, dùng clean build và workspace/local repository phù hợp để loại trừ output cũ; không cần xóa toàn bộ local repository nếu chưa có lý do. Mục tiêu là xác định output có thể được tạo lại từ các đầu vào đã biết hay không.

## 18. Ví dụ kiểm tra môi trường Java

Một chương trình diagnostic nhỏ có thể in các default quan trọng:

~~~java
import java.nio.charset.Charset;
import java.time.ZoneId;
import java.util.Locale;

public class BuildEnvironment {
    public static void main(String[] args) {
        System.out.println("java.version=" +
            System.getProperty("java.version"));
        System.out.println("locale=" + Locale.getDefault());
        System.out.println("timezone=" + ZoneId.systemDefault());
        System.out.println("charset=" + Charset.defaultCharset());
        System.out.println("line.separator=" +
            System.getProperty("line.separator")
                .replace("\r", "\\r")
                .replace("\n", "\\n"));
    }
}
~~~

Chạy cùng chương trình trên developer machine và CI để so sánh. Nếu build có fork test JVM, đặt chương trình diagnostic trong test hoặc task tương ứng để quan sát đúng tiến trình.

## 19. Những lỗi thường gặp

| Dấu hiệu | Nguồn biến thiên có thể | Hướng xử lý |
|---|---|---|
| Generated JSON dùng dấu phẩy thập phân trên một máy | NumberFormat dùng default locale | Dùng serializer hoặc locale được chỉ định |
| Tên property bị đổi chữ khác nhau | toLowerCase() dùng default locale | Dùng Locale.ROOT cho identifier |
| Test ngày giờ chỉ lỗi ở CI | Timezone/JDK/tzdb khác | Cố định timezone hoặc dùng Clock/ZoneId tường minh |
| File tiếng Việt bị lỗi ký tự | Source/resource được đọc sai charset | Chuẩn hóa UTF-8 và khai báo encoding rõ |
| Checksum JAR khác nhưng class giống nhau | ZIP timestamp hoặc entry order | Cấu hình reproducible archive |
| Test ngẫu nhiên thất bại không tái hiện được | Seed không được lưu | Ghi seed/failing input và hỗ trợ replay |
| Build output khác dù seed giống | Input order hoặc parallel scheduling khác | Sort input và hợp nhất output xác định |
| CI dùng cache cho output cũ | Task không khai báo seed/environment là input | Khai báo task inputs đầy đủ |
| Source archive khác giữa Windows và Linux | Line ending hoặc filesystem ordering | Chuẩn hóa line ending và đường dẫn |
| Javadoc/report khác ngôn ngữ | Locale mặc định khác | Chọn locale cho process tạo tài liệu |
| Artifact có timestamp khác | Build dùng đồng hồ hiện tại | Bỏ timestamp hoặc dùng timestamp release cố định |
| Một JDK tạo output khác JDK khác | JDK/CLDR/tzdb/tool version khác | Pin JDK và ghi nhận môi trường |

## 20. Quy tắc thực hành cho build có thể tái lập

- Dùng UTF-8 tường minh cho source, resource và file text.
- Cố định locale cho các task sinh dữ liệu; dùng Locale.ROOT cho identifier và format kỹ thuật.
- Dùng UTC cho timestamp kỹ thuật; không dùng timezone hệ thống một cách ngầm định.
- Tiêm Clock vào logic cần kiểm thử theo thời gian.
- Bỏ timestamp hiện tại khỏi artifact nếu không cần; nếu cần thì truyền timestamp release ổn định.
- Dùng seed tường minh cho dữ liệu random phục vụ test/generator và ghi seed để replay.
- Không dùng seed cố định cho cryptographic randomness.
- Khai báo seed, environment và các giá trị ảnh hưởng output là task inputs.
- Sort danh sách file, key và resource trước khi sinh output.
- Chuẩn hóa đường dẫn, line ending và tên file giữa các hệ điều hành.
- Cố định JDK, Maven/Gradle wrapper và version plugin/dependency.
- Bật reproducible archive settings phù hợp với build tool.
- So sánh artifact từ hai workspace sạch để tìm nguồn biến thiên còn sót.

## 21. Những điều cần ghi nhớ

- Locale, timezone, charset, line ending, random seed, clock và file ordering đều có thể ảnh hưởng output build.
- JVM chạy build, JVM chạy test và JVM chạy ứng dụng có thể có cấu hình khác nhau; phải cố định đúng tiến trình tạo output.
- Dùng locale rõ ràng cho dữ liệu; Locale.ROOT phù hợp với chuẩn hóa identifier không phụ thuộc ngôn ngữ.
- Dùng Instant/UTC cho timestamp kỹ thuật và Clock.fixed trong test cần thời gian xác định.
- Chỉ định UTF-8 trong compiler, resource processing và API đọc/ghi file; không dựa vào default charset.
- Chuẩn hóa line ending và thứ tự file để tránh khác biệt giữa filesystem/OS.
- Seed cố định giúp tái tạo dữ liệu random nhưng phải đi cùng generator algorithm và input order xác định.
- Không dùng random có seed cố định cho mục đích bảo mật.
- Maven/Gradle cần cấu hình riêng cho build JVM, test JVM, compiler và archive task.
- Checksum giống nhau qua hai lần build là bằng chứng hữu ích; nếu khác, hãy so sánh từng entry để tìm nguồn biến thiên.

Khi muốn hai máy tạo cùng artifact, hãy coi môi trường là một phần của build input. Ghi nhận JDK và build tool, cố định locale/timezone/encoding, kiểm soát clock và random seed, sắp xếp dữ liệu đầu vào, rồi bật cấu hình archive tái lập. Khi một trong các giá trị đó thay đổi có chủ đích, hãy biểu diễn nó thành input rõ ràng để kết quả có thể được giải thích và tái tạo.
