# Chọn text block hoặc tài nguyên ngoài theo kích thước dữ liệu (Java 15+)

## Mục tiêu

Biết quyết định khi nào nên viết văn bản nhiều dòng **ngay trong mã Java bằng text block**, khi nào nên tách ra thành **tệp tài nguyên**, và khi nào phải **đọc theo luồng** thay vì nạp toàn bộ văn bản vào bộ nhớ. Quyết định dựa trên **kích thước thực tế, độ ổn định, nhu cầu chỉnh sửa, cách triển khai và cách sử dụng dữ liệu**; không có một ngưỡng số dòng chung bắt buộc cho mọi dự án.

Text block là cú pháp chính thức từ **Java 15**, tiếp tục hoạt động trên **Java 17 trở lên**. Các API hiện hành dùng trong bài gồm **Class.getResourceAsStream**, **InputStream.readAllBytes**, **Files.readString**, **BufferedReader** và **StandardCharsets.UTF_8**.

## 1. Ba lựa chọn chính

### A. Text block: nội dung nhỏ, cố định, gắn sát logic

~~~java
private static final String MESSAGE = """
        Gửi người dùng:
        Yêu cầu đã được tiếp nhận.
        Vui lòng kiểm tra email.
        """;
~~~

Text block phù hợp nếu văn bản ngắn, **hiếm khi thay đổi**, dễ hiểu khi nằm ngay cạnh mã dùng nó và có lợi khi được xem cùng một lần review mã nguồn. Text block tạo ra giá trị kiểu **String**; đây là literal trong mã nguồn, không phải tệp riêng hoặc cơ chế stream đặc biệt.

Text block đặc biệt hữu ích với câu SQL cố định ngắn, mẫu JSON nhỏ dùng trong test, HTML minh họa, hướng dẫn vài dòng hoặc thông báo ít biến thể. Nếu chỉ có **một dòng đơn giản**, String literal thông thường thường dễ đọc hơn.

Ưu điểm: mã tự chứa nội dung, không cần đường dẫn hoặc thao tác đọc tệp; dễ tìm chỗ sử dụng. Đổi lại, sửa nội dung đòi **sửa mã, biên dịch và triển khai lại**. Nội dung nhiều trang khiến lớp Java khó đọc, diff khó xem, và trộn trách nhiệm dữ liệu với logic chương trình.

Lưu ý: Java loại bỏ phần thụt lề chung không chủ ý và chuẩn hóa dấu kết thúc dòng trong text block khi biên dịch. Hãy kiểm tra chuỗi thực tế nếu byte/khoảng trắng/dấu xuống dòng là phần quan trọng của định dạng.

### B. Tài nguyên văn bản riêng: nội dung vừa hoặc lớn, dễ quản lý hơn khi tách file

Ví dụ cấu trúc dự án:

~~~text
project/
  ContentChoiceDemo.java
  templates/
    message.txt
~~~

Tệp **templates/message.txt** được giữ tách khỏi mã Java. Với ứng dụng có đóng gói JAR, nơi thường đặt tài nguyên là **src/main/resources/** trong dự án Maven hoặc Gradle; công cụ build sẽ đưa chúng lên classpath của ứng dụng.

Đọc tài nguyên được đóng gói trên **classpath** bằng:

~~~java
try (InputStream input =
         ContentChoiceDemo.class.getResourceAsStream("/templates/message.txt")) {
    if (input == null) {
        throw new IOException("Không tìm thấy tài nguyên");
    }
    String text = new String(input.readAllBytes(), StandardCharsets.UTF_8);
}
~~~

*Đây là đoạn mã minh họa nằm trong phương thức có khai báo hoặc xử lý IOException; chương trình hoàn chỉnh có ở mục 5.* Dấu **/** đầu đường dẫn nghĩa là bắt đầu từ **gốc classpath**, khác đường dẫn tương đối của hệ thống tệp.

Ưu điểm: nội dung có thể dài mà không làm lớp Java khó bảo trì; file có thể được xem bằng đúng định dạng của nó (.txt, .html, .sql, .json), dùng công cụ kiểm tra riêng và được nhiều chức năng tham chiếu.

**Phân biệt quan trọng:** tài nguyên **đóng gói trong JAR** tuy nằm ngoài tệp .java nhưng **không phải nội dung chỉnh sửa tự do lúc ứng dụng đang chạy**. Muốn thay nó trong bản ứng dụng đã đóng gói, thông thường vẫn phải build/triển khai lại. Nếu vận hành cần thay nội dung độc lập, hãy dùng **tệp cấu hình/nội dung bên ngoài gói triển khai**, cơ sở dữ liệu hoặc hệ thống quản lý nội dung phù hợp.

### C. Xử lý theo luồng: khi nội dung quá lớn để nạp toàn bộ

Nếu tệp có kích thước hàng MB lớn đến GB, hoặc kích thước không dự đoán trước được, việc gọi **readAllBytes()**, **Files.readString()** hay nối toàn bộ dòng vào một String có thể tốn bộ nhớ lớn. Với dữ liệu tuần tự, nên đọc và xử lý dần bằng **BufferedReader** hoặc luồng byte.

~~~java
try (BufferedReader reader = new BufferedReader(
        new InputStreamReader(input, StandardCharsets.UTF_8))) {
    String line;
    while ((line = reader.readLine()) != null) {
        // Xử lý từng dòng, không cộng dồn toàn bộ tệp thành một String.
    }
}
~~~

Đây là đoạn minh họa trong ngữ cảnh đã có biến **input** kiểu InputStream; ví dụ runnable ở mục 5 có hàm hoàn chỉnh tương tự.

Cách đọc theo dòng thường dùng ít bộ nhớ hơn khi xử lý từng dòng xong rồi bỏ đi. Tuy nhiên, **readLine() loại ký tự kết thúc dòng** và vẫn phải giữ **một dòng** trong bộ nhớ. Với một dòng khổng lồ hoặc cần bảo toàn byte, đọc thành các **khối byte có kích thước giới hạn** và xử lý bằng API phù hợp.

## 2. Kích thước dữ liệu ảnh hưởng đến quyết định ra sao?

Không có quy tắc kiểu “trên N dòng phải dùng file”. Các con số sau chỉ là **điểm bắt đầu để cân nhắc**, không phải giới hạn cú pháp:

| Loại nội dung | Lựa chọn thường hợp lý | Lý do |
| --- | --- | --- |
| Vài dòng đến vài chục dòng; ổn định, liên quan trực tiếp tới một hàm | **Text block** | Có thể đọc logic và nội dung tại cùng vị trí. |
| Nhiều đoạn, nhiều trang, hoặc có thể thành hàng trăm dòng | **Tệp tài nguyên** | Dễ chỉnh sửa/soát lỗi định dạng; không làm lớp Java quá dài. |
| Nhiều mẫu email, HTML, SQL hoặc bản dịch cần nhóm nội dung quản lý riêng | **Tài nguyên hoặc giải pháp template/i18n chuyên dụng** | Tách trách nhiệm nội dung khỏi logic; thay đổi dễ kiểm soát. |
| Tệp lớn, log, dữ liệu nhiều MB đến GB hoặc kích thước không giới hạn trước | **Đọc tuần tự/streaming** | Tránh tạo một String/byte[] chứa toàn bộ dữ liệu. |
| Nội dung cần thay đổi lúc chạy mà không biên dịch lại | **Tệp ngoài gói ứng dụng, DB hoặc dịch vụ nội dung** | Classpath resource trong JAR thường không thay đổi độc lập khi runtime. |

Một text block gồm 20 dòng chứa các ký tự Unicode rất dài có thể nặng hơn nhiều so với 200 dòng ngắn. Vì vậy, **đếm số dòng chỉ là dấu hiệu về khả năng đọc**, không thể thay thế việc xem dung lượng và cách sử dụng thực tế.

### Giới hạn kỹ thuật của hằng chuỗi khi biên dịch

Literal chuỗi, bao gồm text block, được biểu diễn trong class file. Trong định dạng class file của JVM, mục **CONSTANT_Utf8_info** có trường **length kiểu u2**; mỗi mục lưu tối đa **65.535 byte theo modified UTF-8**. Một text block quá dài có thể gây lỗi biên dịch như *constant string too long*.

**65.535 byte không đồng nghĩa 65.535 ký tự Java**: chữ có dấu, các ký tự Unicode và modified UTF-8 có thể cần nhiều byte. Đừng thiết kế text block sát giới hạn; với tài liệu dài hoặc nội dung sinh tự động, tách thành tài nguyên riêng sẽ hợp lý hơn. Việc né giới hạn bằng cách chia hoặc nối nhiều literal không tự giải quyết vấn đề bảo trì và bộ nhớ khi sử dụng toàn bộ nội dung.

Mặt khác, việc cho nội dung vào file **không tự bảo đảm ít tốn RAM**: nếu vẫn đọc toàn bộ file bằng **readAllBytes()** rồi tạo String, ứng dụng vẫn giữ nội dung trong bộ nhớ. **Vị trí lưu trữ** (inline hay file) và **cách đọc lúc chạy** (toàn bộ hay theo luồng) là hai quyết định độc lập.

## 3. Phân biệt tài nguyên classpath và tệp ngoài gói ứng dụng

**Tài nguyên classpath** phù hợp với nội dung đi kèm đúng một bản phần mềm: mẫu mặc định, tài liệu trợ giúp, dữ liệu test hoặc cấu hình không đổi theo môi trường. Dùng **Class.getResourceAsStream("/đường/dẫn")** để đọc được cả khi tài nguyên nằm trong JAR. Không giả định URL của tài nguyên luôn chuyển được thành đường dẫn **Path** của hệ thống tệp: tài nguyên trong JAR không phải file độc lập thông thường.

**Tệp ngoài gói triển khai** phù hợp khi cần chỉnh sửa nội dung bằng công cụ vận hành mà không tạo lại JAR. Đọc theo đường dẫn filesystem được cấu hình, ví dụ đoạn sau nằm trong phương thức có xử lý IOException:

~~~java
Path path = Path.of("config", "notice.txt");
String notice = Files.readString(path, StandardCharsets.UTF_8);
~~~

Đường dẫn tương đối ở đây được tính từ **working directory khi chạy chương trình**, không từ package của lớp Java. Trong ứng dụng thật, hãy cấu hình đường dẫn rõ ràng, xét quyền truy cập và báo lỗi khi thiếu tệp. Nếu file có thể rất lớn, thay **Files.readString(...)** bằng phương thức đọc theo luồng.

Đừng nhầm hai cơ chế: **getResourceAsStream** tra cứu **classpath**, còn **Files.readString** mở **tệp trên filesystem**.

## 4. Quy trình chọn nhanh

1. **Nội dung có còn rõ ràng khi nằm trong Java không?** Nếu chỉ vài dòng và là phần cố định của thuật toán, text block thường phù hợp. Nếu phải cuộn qua nhiều trang để tìm logic, cân nhắc tách file.
2. **Ai sửa nội dung và sửa khi nào?** Nếu người viết tài liệu, người quản trị hoặc bộ phận dịch thuật cần sửa độc lập, chọn tài nguyên ngoài code và quy trình triển khai phù hợp.
3. **Dữ liệu phải đóng gói cùng phiên bản phần mềm không?** Nếu có, dùng classpath resource. Nếu phải chỉnh mà không build lại, dùng nguồn ngoài JAR.
4. **Kích thước tối đa khi runtime là bao nhiêu?** Nếu lượng dữ liệu lớn hoặc không bị giới hạn, thiết kế đọc tuần tự, giới hạn độ dài và không tích lũy hết vào một String.
5. **Định dạng có cần bảo toàn byte, dấu xuống dòng, hoặc khoảng trắng?** Text block có xử lý thụt lề và newline lúc biên dịch. Tệp resource thường lưu nội dung theo đúng byte được đóng gói, nhưng bước đọc và xử lý có thể thay đổi dạng dữ liệu.
6. **Định dạng cần parser hay template engine?** JSON, HTML, SQL, YAML và ngôn ngữ khác vẫn cần công cụ xử lý phù hợp. Text block chỉ tạo String; nó không tự kiểm tra hợp lệ hoặc thay thế tham số an toàn.

## 5. Chương trình Java 17+ hoàn chỉnh

Ví dụ dưới đây dùng **ba hình thức trên cùng một cấu trúc dự án**: thông báo nhỏ được đặt trong text block; tài nguyên riêng được đọc toàn bộ vì đang rất nhỏ; cùng tài nguyên đó được đếm dòng bằng cách đọc tuần tự để minh họa đường xử lý cho dữ liệu lớn.

Tạo cấu trúc:

~~~text
demo/
  ContentChoiceDemo.java
  templates/
    message.txt
~~~

Nội dung tệp **templates/message.txt** (mã hóa UTF-8, kết thúc bằng một dấu xuống dòng):

~~~text
Dòng 1: Mẫu lưu ngoài Java.
Dòng 2: Dễ chỉnh sửa nội dung.
~~~

Nội dung **ContentChoiceDemo.java**:

~~~java
import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;

public class ContentChoiceDemo {
    private static final String INLINE = """
            === DEMO ===
            Text block: thông báo ngắn.
            """;
    private static final String RESOURCE = "/templates/message.txt";

    private static InputStream openResource() throws IOException {
        InputStream input = ContentChoiceDemo.class.getResourceAsStream(RESOURCE);
        if (input == null) {
            throw new IOException("Không tìm thấy resource: " + RESOURCE);
        }
        return input;
    }

    private static String loadWholeText() throws IOException {
        try (InputStream input = openResource()) {
            return new String(input.readAllBytes(), StandardCharsets.UTF_8);
        }
    }

    private static long countLinesStreaming() throws IOException {
        try (BufferedReader reader = new BufferedReader(
                new InputStreamReader(openResource(), StandardCharsets.UTF_8))) {
            long count = 0;
            while (reader.readLine() != null) {
                count++;
            }
            return count;
        }
    }

    public static void main(String[] args) throws IOException {
        System.out.print(INLINE);
        System.out.println("Tài nguyên:");
        System.out.print(loadWholeText());
        System.out.println("Số dòng đọc tuần tự: " + countLinesStreaming());
    }
}
~~~

Mở terminal tại thư mục **demo/** rồi chạy trên JDK 17 trở lên:

~~~bash
javac --release 17 -encoding UTF-8 ContentChoiceDemo.java
java -cp . ContentChoiceDemo
~~~

**Stdout chính xác** khi tệp message.txt chứa hai dòng như ở trên:

~~~text
=== DEMO ===
Text block: thông báo ngắn.
Tài nguyên:
Dòng 1: Mẫu lưu ngoài Java.
Dòng 2: Dễ chỉnh sửa nội dung.
Số dòng đọc tuần tự: 2
~~~

**Giải thích:**

- **INLINE** là text block ngắn, cố định và nằm ngay nơi mã sử dụng.
- **RESOURCE** là đường dẫn bắt đầu từ gốc classpath. Vì chạy bằng **java -cp .**, thư mục demo/ là gốc classpath nên tìm thấy templates/message.txt.
- **loadWholeText()** đọc toàn bộ tệp thành byte[] rồi giải mã bằng UTF-8. Cách này phù hợp với tài nguyên nhỏ, đã được kiểm soát kích thước.
- **countLinesStreaming()** dùng BufferedReader, không lưu mọi dòng cùng lúc; số đếm bằng 2. Nó mở riêng một stream vì stream cũ đã được đóng khi loadWholeText() kết thúc.
- **try-with-resources** đóng stream/reader kể cả khi xảy ra lỗi; **openResource()** báo IOException có nội dung cụ thể nếu resource không tồn tại.

Ví dụ đã được **biên dịch với tùy chọn --release 17 và chạy thành công trên JDK 24**; mã không sử dụng API legacy.

Khi đưa dự án vào Maven/Gradle, đặt **message.txt** trong **src/main/resources/templates/** để quy trình build đóng gói vào classpath. Với JAR đã xây dựng, thay file ở thư mục mã nguồn không tự làm bản JAR đang chạy thay đổi.

## 6. Khi file thực sự lớn: tách phần xử lý khỏi nơi lưu

Một tài nguyên hoặc tệp đọc theo luồng có thể được xử lý mà không dựng thành một String lớn. Trong ví dụ ở mục 5, phương thức **countLinesStreaming()** chỉ giữ bộ đệm và dòng đang xử lý. Nếu cần xử lý hàng triệu dòng, áp dụng cùng nguyên tắc: đọc, xử lý, ghi kết quả và giải phóng dữ liệu từng bước.

Tuy nhiên, khi phải **hiển thị toàn bộ** hoặc **phân tích dữ liệu cần xem xét toàn thể**, việc streaming đơn thuần không xóa đi nhu cầu bộ nhớ của thuật toán đầu ra. Lúc đó, cần định nghĩa giới hạn, phân trang, xử lý theo lô, index hoặc lưu kết quả trên đĩa.

Với dữ liệu không phải văn bản (ảnh, âm thanh, tệp nén), hãy lưu dưới dạng **tài nguyên nhị phân** và dùng API đọc byte hoặc stream phù hợp; không biến toàn bộ dữ liệu nhị phân thành text block.

## 7. Lỗi thường gặp

1. **Chọn theo số dòng cứng nhắc.** Số dòng không phản ánh kích thước byte hay khả năng bảo trì. Nội dung dài, ít thay đổi nhưng nhiều trang vẫn có thể nên tách file.
2. **Hiểu text block là String “đọc từ tệp”.** Text block là literal biên dịch từ mã nguồn; muốn lấy nội dung file cần API I/O hoặc resource.
3. **Đặt tài nguyên dưới src/main/resources nhưng chạy java -cp . ở sai thư mục.** Phải bảo đảm tài nguyên đã nằm trên **classpath thực tế** tại thời điểm chạy.
4. **Dùng filesystem Path cho resource trong JAR.** Ưu tiên **getResourceAsStream** cho tài nguyên đóng gói.
5. **Cho rằng tài nguyên trong JAR sửa nóng được.** Muốn thay độc lập, dùng nguồn nội dung runtime bên ngoài.
6. **Nạp file lớn vào RAM bằng readAllBytes/Files.readString.** Chọn stream nếu không cần nắm toàn bộ nội dung cùng lúc; đặt giới hạn kích thước khi đầu vào không đáng tin.
7. **Không chỉ định charset.** Chọn **StandardCharsets.UTF_8** khi giải mã văn bản UTF-8; khớp với charset thực tế của file.
8. **Không đóng stream hoặc bỏ qua lỗi thiếu resource.** Dùng try-with-resources và kiểm tra null khi getResourceAsStream không tìm thấy.
9. **Giả định text block giữ nguyên mọi khoảng trắng.** Việc chuẩn hóa thụt lề và newline của text block có thể làm dữ liệu khác nguồn văn bản thô.
10. **Đưa dữ liệu động/nhạy cảm cố định vào mã hoặc JAR.** Dùng nguồn runtime và cơ chế quản lý dữ liệu phù hợp; không coi việc tách thành resource là biện pháp bảo mật.

## 8. Ghi nhớ

**Text block** phù hợp với văn bản đa dòng **nhỏ, cố định và gắn sát mã**. **Tài nguyên riêng** giúp quản lý văn bản dài, nội dung có định dạng riêng hoặc cần người khác biên tập. **Tệp ngoài bản triển khai** phù hợp nếu nội dung cần thay đổi lúc chạy. Với dữ liệu rất lớn hoặc chưa biết kích thước, **xử lý theo luồng** để tránh nạp tất cả vào String. Hai câu hỏi phải trả lời độc lập là **lưu ở đâu** và **đọc như thế nào**.

## Tài liệu tham khảo chính thức

- Oracle, *Programmer's Guide to Text Blocks* (Java 17): https://docs.oracle.com/en/java/javase/17/text-blocks/index.html
- Oracle, *JVM Specification*, mục 4.4.7 (**CONSTANT_Utf8_info**, Java 25): https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-4.html#jvms-4.4.7
- Oracle, **Class.getResourceAsStream(String)** (Java 17): https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html#getResourceAsStream(java.lang.String)
- Oracle, **InputStream.readAllBytes()** (Java 17): https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/InputStream.html#readAllBytes()
