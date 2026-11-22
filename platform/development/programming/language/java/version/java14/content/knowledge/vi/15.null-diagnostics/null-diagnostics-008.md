# ShowCodeDetailsInExceptionMessages và cấu hình JVM hiện dùng

## 1. Vì sao cần biết tùy chọn JVM này?

Trong Java, `NullPointerException` (NPE) xảy ra khi chương trình cố sử dụng `null` tại vị trí cần một đối tượng, ví dụ gọi phương thức instance, đọc field, truy cập mảng hoặc lấy độ dài mảng. Stack trace thông thường cho biết **class, method và dòng mã** phát sinh lỗi. Tuy nhiên một dòng có nhiều bước truy cập thì chỉ số dòng có thể chưa đủ để biết chính xác **tham chiếu nào đang null**.

Từ **JDK 14**, JEP 358 (*Helpful NullPointerExceptions*) bổ sung khả năng tạo thông điệp giải thích lỗi chi tiết hơn. HotSpot có thể phân tích bytecode ở vị trí phát sinh NPE để mô tả:

1. **Thao tác nào thất bại**: không thể gọi một phương thức, đọc field, truy cập phần tử mảng…
2. **Vì tham chiếu nào đang null**: ví dụ một field hoặc giá trị trả về của lời gọi trước đó.

Ví dụ thông điệp minh họa:

~~~text
java.lang.NullPointerException:
Cannot invoke "String.length()" because "person.name" is null
~~~

Thông điệp trên chỉ là **minh họa hình dạng**; đường biểu thức `"person.name"`, tên biến cục bộ và dấu vết có thể khác theo bytecode/JDK. Không viết kiểm thử phụ thuộc toàn bộ câu tiếng Anh này.

Cờ cấu hình HotSpot là:

~~~text
-XX:+ShowCodeDetailsInExceptionMessages
~~~

Dấu `+` là **bật**, dấu `-` là **tắt**. Đây là tùy chọn của **JVM khi khởi chạy chương trình**, không phải cú pháp Java source và không phải tham số của `javac`.

**Điểm quan trọng nhất về hiện trạng:** tính năng có mặt từ **Java 14**, nhưng từ **JDK 15**, HotSpot **bật theo mặc định**. Tài liệu lệnh `java` của các JDK hiện đại (ví dụ Java 17/21/25) vẫn mô tả cờ này và cho biết mặc định bật. Vì vậy **không nên yêu cầu mọi dự án Java hiện nay luôn thêm cờ `+` mới có Helpful NPE**. Cần kiểm tra JVM thực tế của ứng dụng trước.

## 2. Phân biệt sự xuất hiện của tính năng với mặc định hiện tại

| JDK | Trạng thái của Helpful NPE trên HotSpot | Cách hiểu đúng |
| --- | --- | --- |
| Java 14 | Tính năng được đưa vào, nhưng **mặc định tắt** | Đây là thông tin lịch sử của bản phát hành; muốn thử trên JDK 14 cần bật `-XX:+ShowCodeDetailsInExceptionMessages` |
| Java 15 | Mặc định được đổi sang **bật** | Không cần thêm cờ `+` cho cấu hình HotSpot thông thường |
| Java 17 / 21 / 25 | Tài liệu HotSpot hiện hành ghi **bật mặc định** | Có thể ghi đè bằng cờ `+` hoặc `-`; đừng suy từ số phiên bản rằng một tiến trình bất kỳ chắc chắn đang bật |
| JVM triển khai khác HotSpot | Phụ thuộc nhà cung cấp và phiên bản | Tùy chọn `-XX` không phải cam kết portable của mọi JVM; đọc tài liệu nhà cung cấp và kiểm tra thực tế |

Như vậy, bài học vẫn có giá trị đối với Java đang dùng hiện nay, nhưng câu “Java 14 phải bật flag” **không được dùng làm kết luận chung cho Java 17+**.

**Từ khóa:** `enabled by default` nghĩa là *giá trị mặc định khi không bị ghi đè*. Nó không khẳng định một tiến trình JVM được deploy trong Docker, IDE, service manager, pipeline CI hay hệ thống production đã dùng giá trị mặc định.

## 3. Cú pháp bật/tắt khi chạy bằng lệnh java

Chạy một class đã được biên dịch:

~~~bash
java -XX:+ShowCodeDetailsInExceptionMessages HelpfulNpeDemo
~~~

Tắt chi tiết của NPE do HotSpot tự sinh:

~~~bash
java -XX:-ShowCodeDetailsInExceptionMessages HelpfulNpeDemo
~~~

Chạy ứng dụng đóng gói dạng JAR:

~~~bash
java -XX:+ShowCodeDetailsInExceptionMessages -jar app.jar
java -XX:-ShowCodeDetailsInExceptionMessages -jar app.jar
~~~

Cần đặt tùy chọn JVM **trước tên main class hoặc trước `-jar`**. Nếu đưa flag sau tên class hoặc sau `app.jar`, nó có thể trở thành **đối số của chương trình** chứ không phải tùy chọn JVM.

- `-XX:+ShowCodeDetailsInExceptionMessages`: bật khả năng bổ sung thông điệp chi tiết cho NPE thích hợp.
- `-XX:-ShowCodeDetailsInExceptionMessages`: vô hiệu hóa phần chi tiết do cơ chế này tạo ra.
- Không có dạng chuẩn `--ShowCodeDetailsInExceptionMessages`; `-XX:+` và `-XX:-` là cú pháp HotSpot.
- Các cờ `-XX` thuộc nhóm **tùy chọn triển khai JVM**. Khi đổi vendor hoặc JVM implementation, phải xem lại khả năng hỗ trợ.

**Lưu ý triển khai:** trên Java 17+ thông thường, thêm `+` là cách **khẳng định rõ** yêu cầu hoặc chẩn đoán một môi trường bị ghi đè, chứ không phải bước bắt buộc để có tính năng. Cờ `-` là một lựa chọn chính sách vận hành, không phải cách sửa nguyên nhân NPE.

## 4. Helpful NPE hoạt động như thế nào?

Giả sử một phương thức có chuỗi truy cập:

~~~java
static class Person {
    Address address;
}

static class Address {
    String city;
}

static void printCityLength(Person person) {
    System.out.println(person.address.city.length());
}
~~~

Đoạn trên là **mảnh mã minh họa**, chưa phải class chạy độc lập. Nếu `person.address` là null, NPE xuất hiện khi Java cố đọc field `city` trên null. Nếu `person.address` khác null nhưng `city` là null, NPE xuất hiện khi gọi `length()` trên null.

Khi tính năng bật và lỗi thuộc trường hợp hỗ trợ, HotSpot phân tích **bytecode tại vị trí NPE** để tìm hành động thất bại và đường truy cập tạo ra null. Ví dụ, nó có thể biểu diễn khác nhau cho:

~~~text
Cannot read field "city" because ... is null
Cannot invoke "String.length()" because ... is null
~~~

Không nên diễn giải rằng JVM “đọc nguyên văn mọi câu lệnh source”. Nó dựa trên bytecode; một số tên hiển thị được lấy từ thông tin class, method, field và bảng debug nếu có.

### Vai trò của thông tin debug

Với các biến cục bộ, JVM có thể không biết **tên nguồn** của biến nếu class file không có bảng `LocalVariableTable`. Khi đó thông điệp có thể dùng tên dạng `"<local1>"` hoặc `"<parameter1>"` thay vì tên bạn viết trong source.

Khi biên dịch phục vụ tái hiện lỗi, có thể dùng:

~~~bash
javac -g HelpfulNpeDemo.java
~~~

`-g` tạo thêm debug information, bao gồm tên biến cục bộ. Với `javac`, mặc định thường chỉ có thông tin **dòng và tên source file**, không có đầy đủ tên biến local. Tuy nhiên:

- `-g` **không tự bật** Helpful NPE nếu JVM đã tắt cờ.
- Cờ Helpful NPE **không tự tạo lại** tên biến đã thiếu trong class file.
- Không nên yêu cầu hệ thống phát hành thêm thông tin debug nếu điều đó mâu thuẫn chính sách bảo mật và kích thước artifact; đánh giá nhu cầu chẩn đoán thực tế.
- Không cam kết mọi thông điệp sẽ chứa tên biến dễ hiểu, kể cả khi có debug metadata.

### Thời điểm tạo message

Với NPE do JVM sinh, phần mô tả hữu ích được xác định khi cần lấy thông điệp (ví dụ `getMessage()` hoặc in stack trace), dựa vào thông tin lỗi JVM còn giữ được. Không nên xem nó là một định dạng dữ liệu ổn định để ứng dụng tự phân tích.

## 5. Khi nào tùy chọn có hiệu lực, khi nào không?

Điểm rất dễ nhầm: **bật flag không làm mọi NullPointerException đều có câu giải thích dài**.

| Cách tạo NPE | Đặc điểm thông điệp |
| --- | --- |
| JVM tự phát sinh NPE do gọi phương thức trên null | Có thể có Helpful NPE detail nếu cờ bật và bytecode đủ thông tin |
| JVM tự phát sinh NPE do đọc field/mảng trên null | Cũng thuộc nhóm có thể được giải thích |
| `throw new NullPointerException("invalid user")` | Thông điệp `"invalid user"` là thông điệp do ứng dụng cung cấp; flag không thay nó bằng mô tả bytecode |
| `throw new NullPointerException()` | Không có message tường minh; không vì thế mà mọi NPE thủ công được VM bổ sung thông tin |
| `Objects.requireNonNull(value, "value required")` | Ném NPE có message chủ động do code truyền; message này không phụ thuộc Helpful NPE flag |
| NPE được deserialize từ byte | Thông tin nội bộ để dựng Helpful NPE detail có thể không tồn tại; Javadoc cảnh báo không bảo đảm có message |
| NPE từ JVM khác hoặc trường hợp đặc thù | Tùy khả năng hỗ trợ/triển khai; không dựa vào nội dung message như một hợp đồng API |

Ví dụ:

~~~java
Object object = null;
object.toString();  // JVM sinh NPE, có thể có detail.

throw new NullPointerException("missing object"); // Có message do người viết.
~~~

Hai dòng trên chỉ là **ví dụ riêng biệt**, không đặt liên tiếp thành mã chạy vì dòng đầu sẽ ném lỗi trước dòng sau.

**Không nhầm:** NPE sinh bởi `Objects.requireNonNull` không có Helpful NPE detail kiểu “Cannot invoke…” vì helper chủ động ném exception có message riêng. Đây là một chiến lược kiểm tra điều kiện đầu vào có chủ đích, không phải lỗi của JVM.

## 6. Chương trình Java 17+ hoàn chỉnh để thử flag

Ví dụ sau tránh phụ thuộc **toàn bộ câu message** hoặc số dòng stack trace. Nó phân biệt NPE do JVM sinh với NPE tự tạo và một NPE có thông điệp từ `Objects.requireNonNull`.

Lưu thành **`HelpfulNpeDemo.java`**:

~~~java
import java.util.Objects;

public class HelpfulNpeDemo {

    static final class Profile {
        String name;
    }

    static Profile profile = new Profile();

    static void triggerVmNpe() {
        // profile tồn tại nhưng field name đang là null.
        System.out.println(profile.name.length());
    }

    static void checkVmGenerated() {
        try {
            triggerVmNpe();
        } catch (NullPointerException error) {
            String message = error.getMessage();
            System.out.println(
                    "vm-message-present=" + (message != null)
            );
            System.out.println(
                    "vm-has-helpful-action="
                        + (message != null
                           && message.startsWith("Cannot invoke "))
            );
        }
    }

    static void checkManualMessages() {
        try {
            throw new NullPointerException("manual reason");
        } catch (NullPointerException error) {
            System.out.println(
                    "manual-message=" + error.getMessage()
            );
        }

        try {
            throw new NullPointerException();
        } catch (NullPointerException error) {
            System.out.println(
                    "manual-empty-message=" + (error.getMessage() == null)
            );
        }

        try {
            Objects.requireNonNull(null, "required value");
        } catch (NullPointerException error) {
            System.out.println(
                    "require-non-null=" + error.getMessage()
            );
        }
    }

    public static void main(String[] args) {
        checkVmGenerated();
        checkManualMessages();
    }
}
~~~

Biên dịch:

~~~bash
javac -encoding UTF-8 HelpfulNpeDemo.java
~~~

### 6.1. Chạy với cờ bật

~~~bash
java -XX:+ShowCodeDetailsInExceptionMessages HelpfulNpeDemo
~~~

Đầu ra dự kiến trên **HotSpot Java 17+**, với ví dụ này:

~~~text
vm-message-present=true
vm-has-helpful-action=true
manual-message=manual reason
manual-empty-message=true
require-non-null=required value
~~~

### 6.2. Chạy với cờ tắt

~~~bash
java -XX:-ShowCodeDetailsInExceptionMessages HelpfulNpeDemo
~~~

Đầu ra dự kiến trên **HotSpot Java 17+**:

~~~text
vm-message-present=false
vm-has-helpful-action=false
manual-message=manual reason
manual-empty-message=true
require-non-null=required value
~~~

### 6.3. Phân tích kết quả

- `profile.name.length()` tạo ra **NPE bởi JVM**: field `name` của đối tượng `profile` là null, nên không thể gọi `String.length()`. Khi bật flag, HotSpot dựng message bắt đầu bằng một hành động như `Cannot invoke ...`. Khi tắt, NPE do JVM phát sinh trong ví dụ không có thông điệp chi tiết.
- `new NullPointerException("manual reason")` luôn mang message tường minh; flag không thay nội dung này.
- `new NullPointerException()` được tạo bằng code, không đi qua cơ chế null-dereference tại điểm tạo. `getMessage()` trong ví dụ là null.
- `Objects.requireNonNull(null, "required value")` chủ động tạo message `required value`; kết quả không đổi giữa hai chế độ.

Các dòng đầu ra trên nhằm kiểm tra **tác động của flag** chứ không kiểm tra chính xác câu tiếng Anh của JVM. Vào JVM khác hoặc bản triển khai có chi tiết khác, hãy kiểm tra tài liệu và quan sát hành vi trước khi suy ra nguyên nhân.

**Chú ý:** mã mẫu không nhằm khuyên bắt và nuốt NPE trong ứng dụng thật. Bắt NPE ở đây chỉ để đo message của hai chế độ. Trong sản phẩm thực, nên sửa nguyên nhân null, xây dựng hợp đồng đầu vào và xử lý exception ở ranh giới phù hợp.

## 7. Kiểm tra cấu hình JVM hiện dùng

Một ứng dụng có thể chạy JDK 17/21/25 nhưng đã được cấu hình bằng flag `-`, biến môi trường, thiết lập IDE, Docker, script khởi động hoặc cấu hình máy chủ. Vì vậy phải phân biệt **mặc định của JDK** và **giá trị thực tế tại tiến trình**.

### 7.1. Kiểm tra một JVM mới chạy với bộ options hiện tại

Trên Linux/macOS:

~~~bash
java -XX:+PrintFlagsFinal -version 2>&1 | grep ShowCodeDetailsInExceptionMessages
~~~

Trên Windows PowerShell:

~~~powershell
java -XX:+PrintFlagsFinal -version 2>&1 |
    Select-String "ShowCodeDetailsInExceptionMessages"
~~~

Ở một bản HotSpot hiện đại, đầu ra có một mục tương tự:

~~~text
bool ShowCodeDetailsInExceptionMessages = true {product} {default}
~~~

**Không chép nguyên mẫu trên để đoán trạng thái:** định dạng, nhãn nguồn giá trị và trạng thái thực tế có thể khác tùy bản JDK, lệnh chạy và options đã được đưa vào. Cột quan trọng là giá trị cuối **`true` hoặc `false`**.

Lệnh này khởi chạy **một JVM mới** để in cấu hình của chính JVM đó. Nó **không chứng minh** tiến trình web/service đang chạy khác đã dùng cùng flags.

Nếu muốn đo tác động của một override cụ thể, có thể gọi:

~~~bash
java -XX:-ShowCodeDetailsInExceptionMessages \
     -XX:+PrintFlagsFinal -version
~~~

Kiểm tra dòng `ShowCodeDetailsInExceptionMessages`. Chạy lệnh trên là kiểm tra **JVM mới với cờ `-`**, không phải thay đổi JVM đang chạy.

### 7.2. Kiểm tra một tiến trình JVM đang chạy bằng jcmd

Với HotSpot/JDK có `jcmd` và quyền attach phù hợp, có thể tìm tiến trình:

~~~bash
jcmd -l
~~~

Sau đó thay `12345` bằng PID thực (không tự giả định PID của người dùng):

~~~bash
jcmd 12345 VM.flags -all
~~~

Kết quả rất dài; có thể lọc riêng flag:

~~~bash
jcmd 12345 VM.flags -all | grep ShowCodeDetailsInExceptionMessages
~~~

Trên PowerShell:

~~~powershell
jcmd 12345 VM.flags -all |
    Select-String "ShowCodeDetailsInExceptionMessages"
~~~

Khác với `PrintFlagsFinal -version`, lệnh `jcmd PID VM.flags -all` yêu cầu **tiến trình Java đang chạy** xuất các giá trị flags được JVM của chính nó sử dụng. Đây là hướng kiểm tra phù hợp khi điều tra một dịch vụ cụ thể.

Giới hạn cần nhớ:

- `jcmd` có thể yêu cầu cùng máy, người dùng/quyền truy cập thích hợp và khả năng attach. Trong container hoặc môi trường bị cô lập PID, cần xác định đúng PID và namespace.
- Tiến trình dùng runtime tối giản không đi kèm `jcmd` thì có thể chạy công cụ từ một JDK tương thích bên ngoài container, nếu chính sách vận hành cho phép.
- Cú pháp và danh sách diagnostic commands tùy JVM. Hãy dùng `jcmd PID help` để xem có `VM.flags` hay không, thay vì suy đoán.
- Việc đọc flags không yêu cầu sửa JVM. Đừng vô tình gọi diagnostic commands có tác dụng thay đổi trạng thái trong môi trường production.

### 7.3. Kiểm tra dòng lệnh và nguồn cờ

Có thể tham khảo:

~~~bash
jcmd 12345 VM.command_line
~~~

Lệnh này cho biết cách tiến trình JVM được khởi chạy, giúp phát hiện cờ được truyền qua launcher hoặc một số nguồn cấu hình. Cần rà soát cả:

- Script khởi động và lệnh `java -XX:...`.
- Biến môi trường `JAVA_TOOL_OPTIONS` hoặc `JDK_JAVA_OPTIONS` khi môi trường có dùng chúng.
- Thiết lập **VM options** trong IDE, test runner, Gradle/Maven hoặc application server.
- `Dockerfile`, Kubernetes Deployment, Helm values, service manager hoặc launcher do đơn vị vận hành cấu hình.

**Không thể suy ra đầy đủ cấu hình chỉ từ `java -version`.** Lệnh đó cho biết phiên bản của JVM đang được gọi, nhưng một ứng dụng đang chạy có thể dùng binary JDK hoặc biến môi trường khác.

### 7.4. Phân biệt VM options với program arguments

Đúng:

~~~bash
java -XX:+ShowCodeDetailsInExceptionMessages -jar service.jar
~~~

Không có tác dụng thiết lập VM option cho JVM khởi chạy:

~~~bash
java -jar service.jar -XX:+ShowCodeDetailsInExceptionMessages
~~~

Trong lệnh thứ hai, phần cuối được chuyển thành **đối số sau JAR**, có thể được chương trình nhận tại `String[] args`. Nó không bật tùy chọn HotSpot cho JVM đã được tạo trước đó.

## 8. Bảng xử lý khi message không xuất hiện

| Hiện tượng | Nguyên nhân cần kiểm tra | Bước tiếp theo |
| --- | --- | --- |
| NPE của code mình nhưng `getMessage() == null` | JVM đang tắt flag; NPE được tạo thủ công; thông tin nội bộ không còn | Kiểm tra cách NPE được tạo, chạy ví dụ ở mục 6, kiểm tra VM.flags trên PID |
| Dùng JDK 17 nhưng không thấy Helpful NPE | Cờ `-` bị truyền qua launcher/IDE/service; không phải HotSpot; logger không in message | Xem Java runtime thực tế, JVM vendor, flags, cách logger format exception |
| Có stack trace nhưng không có câu “because … is null” | Message có thể thiếu/không thể dựng đầy đủ hoặc NPE không do JVM tạo | Đọc stack trace, kiểm tra type/call site và mã tại dòng lỗi |
| Thông điệp có `<local1>` thay vì tên biến | Thiếu thông tin debug về biến cục bộ | Xem tùy chọn `javac -g` và cấu hình build; không coi là lỗi của flag |
| `new NullPointerException("x")` in `x` ngay cả khi tắt flag | Message do code cung cấp | Đây là hành vi đúng, không chứng minh flag vẫn bật |
| `Objects.requireNonNull(null, "x")` vẫn có `x` | Helper tự cung cấp message | Phân biệt NPE thủ công và NPE do VM phát sinh |
| Nhìn log thấy `null` nhưng IDE trình diễn tooltip chi tiết | Logger, IDE và runtime có thể diễn đạt khác nhau | Kiểm tra trực tiếp `e.getMessage()` trong chương trình thử nghiệm |
| Tiến trình khác có giá trị flag khác | Không chạy cùng options/JDK/vendor | Kiểm tra đúng PID, JVM và môi trường riêng của từng tiến trình |
| Sau khi đổi flag mà service vẫn như cũ | Chưa restart hoặc đã đặt flag ở program arguments | Xác nhận lệnh khởi chạy thực tế, kiểm tra flags của tiến trình mới |

**Không tạo ra “bộ bắt NPE toàn cục” chỉ để sinh helpful messages.** Mục tiêu của tính năng là hỗ trợ chẩn đoán. Với lỗi null bất thường, cần sửa dữ liệu, invariant, hợp đồng API hoặc kiểm tra biên thích hợp.

## 9. Chi tiết hơn không đồng nghĩa an toàn hơn

JDK 15 release notes đã cảnh báo: thông điệp Helpful NPE có thể cho biết **field, phương thức và cấu trúc đường truy cập**, tức cung cấp nhiều chi tiết nội bộ hơn cho người đọc lỗi.

Ví dụ, một thông điệp có thể vô tình tiết lộ tên field mô tả dữ liệu nội bộ hoặc một chuỗi thao tác mà API công khai không nên bộc lộ. Do đó:

1. **Đừng trả thẳng `exception.getMessage()` hoặc stack trace cho người dùng bên ngoài** qua JSON/HTML API chỉ vì message hữu ích cho developer.
2. **Tách thông điệp công khai và log nội bộ:** API trả mã lỗi/phản hồi phù hợp, trong khi log có thể giữ stack trace với quyền xem hạn chế.
3. **Giảm dữ liệu nhạy cảm trong logs:** chú ý field names, metadata, request IDs, dữ liệu đầu vào và chính sách retention; không gửi thông tin bí mật vào logger một cách tùy tiện.
4. **Không tin tắt flag sẽ giải quyết mọi rò rỉ:** stack trace và các message do ứng dụng tự tạo vẫn có thể tiết lộ nội dung; chính sách xử lý lỗi ở API vẫn cần đúng.
5. **Chỉ thay đổi flag theo quyết định vận hành đã xét tác động:** việc tắt Helpful NPE có thể làm mất thông tin chẩn đoán đáng giá và không ngăn NPE xảy ra.

Mặc định hiện hành bật vì hỗ trợ debug; nhưng cách dùng log và quyền truy cập mới quyết định phần lớn rủi ro lộ thông tin.

## 10. Giới hạn của Helpful NPE khi điều tra lỗi thật

### 10.1. Không thay thế stack trace

Một message dạng “Cannot invoke … because … is null” cho biết biểu thức null gần vị trí xảy ra lỗi. Bạn vẫn cần:

- **Dòng stack trace** để tìm class/method và luồng gọi.
- **Giá trị đầu vào** được thu thập hợp pháp, an toàn và phù hợp bảo mật.
- **Invariant của chương trình**: vì sao trường đó được phép null hoặc ai đã cung cấp nó.
- **Bản phát hành/build đúng**: tên source và line number có thể không còn khớp nếu dùng sai artifact.

Thông điệp bổ sung giúp khoanh vùng vị trí, không giải thích chắc chắn **nguyên nhân nghiệp vụ** tạo ra null.

### 10.2. Không phải lời hứa về nội dung message ổn định

Nội dung có thể khác giữa HotSpot versions, compiler, bytecode shape và thông tin debug. Vì vậy **không** nên:

~~~java
// Ví dụ không nên dựa vào trong production test:
assert error.getMessage().equals(
    "Cannot invoke ... because \"local\" is null");
~~~

Nếu cần kiểm thử mã ứng dụng, kiểm tra **loại exception và hành vi**; nếu muốn kiểm tra flag, dùng chương trình nhỏ riêng (như mục 6), không biến câu tiếng Anh của HotSpot thành public API.

### 10.3. Những NPE không được VM tạo tự động

NPE có thể được tạo bởi code ứng dụng hoặc thư viện. Một error message do người lập trình cung cấp vẫn có thể hữu ích và rõ ràng hơn, nhưng đó là một cơ chế **khác**.

Ví dụ kiểm tra đầu vào:

~~~java
static String normalizeName(String name) {
    Objects.requireNonNull(name, "name must not be null");
    return name.strip();
}
~~~

Đây là **mảnh phương thức**, cần import `java.util.Objects` hoặc dùng tên đầy đủ. Khi `name == null`, message `"name must not be null"` được xác định bởi chính chương trình; việc bật/tắt Helpful NPE không làm đổi message đó.

**Chọn thông điệp tường minh tại biên API** nếu cần giải thích hợp đồng đầu vào cho caller; dùng Helpful NPE để chẩn đoán lỗi dereference bất ngờ ở bên trong.

### 10.4. Bảo toàn thông tin khi truyền lỗi giữa hệ thống

Javadoc `NullPointerException.getMessage()` cho biết thông tin nội bộ để dựng mô tả có thể không có, đặc biệt với **NPE được deserialize**. Vì vậy truyền một object NPE qua serialization không đồng nghĩa rằng hệ thống nhận sẽ tự tái dựng được Helpful NPE message giống hệt.

Không dùng serialization của `Throwable` như phương án mặc định để truyền lỗi giữa microservices. Thường nên truyền **mã lỗi và các trường được lựa chọn an toàn** theo hợp đồng API; giữ thông tin nội bộ trong log/trace của hệ thống phát sinh lỗi.

## 11. Chọn chế độ cấu hình cho từng môi trường

| Môi trường | Gợi ý | Lý do |
| --- | --- | --- |
| Máy developer / unit test | Thường **giữ mặc định bật** trên JDK hiện đại | Giúp xác định dereference null và đọc log |
| CI | Thường giữ bật; capture stack trace trong artifact có kiểm soát | Hữu ích khi test thất bại không tái hiện dễ dàng |
| Staging | Bật theo chính sách logging của đội ngũ | Có thông tin chẩn đoán mà vẫn cần giới hạn quyền truy cập |
| Production | Đánh giá chính sách bảo mật/logging; thường có thể giữ bật nếu log được bảo vệ | Thông tin có giá trị, nhưng không được trả trực tiếp cho client |
| Hệ thống yêu cầu tránh tiết lộ tối đa chi tiết lỗi | Có thể cân nhắc `-XX:-ShowCodeDetailsInExceptionMessages` | Phải cân bằng khả năng debug và vẫn kiểm soát mọi error response khác |

Không có một cờ nào thay thế được quy tắc **không expose stack trace/message nội bộ cho client**. Nếu muốn dùng cấu hình khác nhau, ghi nhận lý do và có test chẩn đoán sau deploy.

## 12. Những lỗi cấu hình phổ biến

| Hiểu nhầm | Cách hiểu đúng |
| --- | --- |
| “Java 17 muốn Helpful NPE luôn phải bật `+`.” | HotSpot đã bật theo mặc định từ JDK 15; chỉ cần override khi có lý do. |
| “Java 14 và Java 21 có cùng default.” | Không: JDK 14 mặc định tắt; JDK 15+ HotSpot mặc định bật. |
| “Thêm flag sau `-jar app.jar` cũng là VM option.” | Không: thường là đối số của ứng dụng. |
| “`javac -g` sẽ bật Helpful NPE.” | Không: nó thêm debug metadata, không thay JVM flag. |
| “Flag `-` ngăn mọi NPE.” | Không: chỉ tắt chi tiết message của cơ chế này, NPE vẫn phát sinh. |
| “Tắt flag sẽ xóa message do app tự tạo.” | Không: `new NullPointerException("x")` vẫn có message `x`. |
| “Có JDK 21 là biết service đang bật.” | Không: service có thể dùng JDK, options và vendor khác với terminal. |
| “Mọi NPE đều có đường truy cập chi tiết.” | Không: phụ thuộc cách NPE được tạo và metadata còn tồn tại. |
| “Message luôn có đúng tên biến local.” | Không: có thể thấy `<local1>` khi thiếu `LocalVariableTable`. |
| “Chỉ cần ghi log đầy đủ message ra ngoài HTTP response.” | Không: Helpful NPE có thể tiết lộ chi tiết triển khai. |
| “`PrintFlagsFinal -version` đo được flag của mọi process trên máy.” | Không: chỉ đo JVM mới chạy bằng chính lệnh đó. |
| “`-XX` là cờ portable của mọi JVM.” | Không: phụ thuộc implementation, dù một số JVM khác có hỗ trợ tương thích. |

## 13. Quy trình chẩn đoán có thể áp dụng trong dự án

1. **Xác định sự cố:** có phải `NullPointerException`? Có stack trace đầy đủ? Có đang bắt NPE và chỉ log mỗi class name?
2. **Xác định JVM đang chạy:** dùng công cụ runtime, PID và phiên bản/vendor thật, không dựa duy nhất vào JDK cài trên máy developer.
3. **Kiểm tra flag thực tế:** ưu tiên `jcmd PID VM.flags -all` nếu hỗ trợ; phân biệt với kiểm tra JVM mới qua `-XX:+PrintFlagsFinal -version`.
4. **Tìm cách NPE được tạo:** VM tự dereference null, hay code ném NPE tường minh/`Objects.requireNonNull`?
5. **Tái hiện bằng chương trình nhỏ:** đối chiếu hai lần chạy có `-XX:+` và `-XX:-`, không thay đổi nhiều cấu hình cùng lúc.
6. **Đọc thêm stack trace và dữ liệu hợp lệ:** hiểu vì sao đường truy cập chứa null; không dừng ở câu message.
7. **Sửa hợp đồng dữ liệu:** kiểm tra null ở biên, khởi tạo đúng đối tượng, xử lý dữ liệu tùy chọn bằng API phù hợp; không chỉ bật cờ và đóng issue.
8. **Kiểm tra chính sách log:** debug logs được giới hạn quyền, không lộ đường truy cập nội bộ trong error response công khai.
9. **Bổ sung test hồi quy:** chứng minh đường xử lý thực tế không còn NPE ngoài dự kiến; chỉ assert loại exception/message cụ thể khi message đó do code của mình chủ động định nghĩa.

## 14. Bài tập và đáp án

### Bài 1 — Mặc định hiện hành

**Câu hỏi:** Dự án đang dùng HotSpot Java 21, không truyền cờ liên quan. Có cần thêm `-XX:+ShowCodeDetailsInExceptionMessages` mới xem được Helpful NPE?

**Đáp án:** thông thường **không**. Trên HotSpot hiện đại, mặc định bật. Nếu không thấy message, trước hết kiểm tra cờ thực của tiến trình, cách NPE được tạo và cách logging hiển thị exception.

### Bài 2 — Nhận diện flag đúng

**Câu hỏi:** Hai lệnh khác nhau thế nào?

~~~bash
java -XX:-ShowCodeDetailsInExceptionMessages -jar app.jar
java -jar app.jar -XX:-ShowCodeDetailsInExceptionMessages
~~~

**Đáp án:** lệnh đầu tắt chi tiết Helpful NPE trong JVM dùng để chạy JAR; lệnh sau đặt chuỗi đó trong program arguments sau JAR, **không phải VM option** của launcher.

### Bài 3 — Vì sao tắt flag mà NPE vẫn có message?

~~~java
try {
    throw new NullPointerException("Missing user");
} catch (NullPointerException error) {
    System.out.println(error.getMessage());
}
~~~

**Đáp án:** in `Missing user` trên cả hai chế độ vì message đến từ constructor, không phải do JVM phân tích bytecode null-dereference.

### Bài 4 — Tên biến bị thay bằng local slot

**Câu hỏi:** Vì sao log có `"<local1>"` thay vì `user`?

**Đáp án:** class file có thể thiếu thông tin debug về tên biến cục bộ. Có thể dùng `javac -g` khi cần debug; vẫn phải bật flag nếu runtime đang tắt. Không khẳng định mọi tên biến sẽ khôi phục được.

### Bài 5 — Đo cấu hình của service

**Bài tập:** người dùng chạy `java -XX:+PrintFlagsFinal -version` trên máy và thấy `true`, nhưng service khác chạy trong container không hiển thị message. Hãy nêu ba bước điều tra.

**Gợi ý:** (1) xác định JDK/vendor và PID thật của service; (2) dùng `jcmd PID VM.flags -all` trong đúng môi trường nếu có quyền hoặc xem command line; (3) xác nhận đó là NPE do VM sinh và kiểm tra logger/error handler có giữ message không. Kết quả JVM mới trên host **không** đại diện tự động cho service trong container.

### Bài 6 — Có thể thay hoàn toàn kiểm tra null không?

**Câu hỏi:** Vì có helpful message, có nên bỏ mọi `Objects.requireNonNull` và validation của API?

**Đáp án:** không. Helpful NPE là công cụ **chẩn đoán lỗi phát sinh**; `Objects.requireNonNull(value, "value required")` và validation giúp làm rõ hợp đồng ở biên đầu vào, tạo thông điệp ổn định do ứng dụng kiểm soát.

## 15. Tài liệu chính thức còn áp dụng

- [OpenJDK JEP 358 — Helpful NullPointerExceptions](https://openjdk.org/jeps/358): cơ chế diễn giải null-dereference dựa trên bytecode, phạm vi và giới hạn.
- [Oracle JDK 15 Release Notes — Enable ShowCodeDetailsInExceptionMessages by default](https://www.oracle.com/java/technologies/javase/15-relnote-issues.html): xác nhận mặc định được chuyển thành bật từ JDK 15 và cảnh báo khả năng lộ thông tin trong thông điệp.
- [Oracle Java 25 — The java Command](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html): cú pháp `-XX:+ShowCodeDetailsInExceptionMessages` và mặc định bật của HotSpot hiện đại.
- [Oracle Java 17 — The jcmd Command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html): công cụ kiểm tra flags trên JVM thực tế qua `VM.flags -all` và yêu cầu quyền truy cập.
- [Oracle Java 26 API — NullPointerException](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/NullPointerException.html): `getMessage()`, mô tả chi tiết nếu có metadata và giới hạn với NPE được deserialize.
- [Oracle javac — Debugging Information](https://docs.oracle.com/en/java/javase/26/docs/specs/man/javac.html): `-g` tạo thông tin debug bao gồm biến cục bộ, khác với tùy chọn của JVM.
