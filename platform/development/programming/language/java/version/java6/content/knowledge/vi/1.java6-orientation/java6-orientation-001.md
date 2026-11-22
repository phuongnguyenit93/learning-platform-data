# Những năng lực của Java 6 vẫn dùng trong lập trình Java hiện đại

## 1. Học năng lực còn hữu ích, không đóng băng ứng dụng ở JDK 6

Java 6 bổ sung và chuẩn hóa nhiều công cụ cho việc xây dựng ứng dụng, thư viện và công cụ phát triển: gọi trình biên dịch qua API, xử lý annotation khi biên dịch, tìm nhà cung cấp dịch vụ, tích hợp script, mở rộng truy cập dữ liệu và cấu trúc dữ liệu.

Những năng lực này vẫn có mặt trong Java hiện đại, nhưng cần sử dụng theo hợp đồng và cách đóng gói của JDK đang triển khai.

Ba điều cần tách biệt:

- **Năng lực:** giải quyết được loại bài toán nào?
- **API:** giao diện Java dùng để yêu cầu năng lực đó.
- **Triển khai và môi trường:** provider, driver, module hoặc hệ điều hành có thật sự cung cấp nó không?

Ví dụ, có API chạy script không đồng nghĩa một bộ máy JavaScript đã được cài. Có API trình biên dịch không đồng nghĩa một runtime tối giản có trình biên dịch Java. Có API desktop không đồng nghĩa container có màn hình và ứng dụng mặc định.

Bài định hướng chỉ tập trung vào các hợp đồng còn áp dụng. Các ví dụ chạy trên JDK 17+, kết hợp cú pháp hiện đại khi hữu ích; tên Java 6 mô tả nguồn gốc nhóm năng lực, không phải yêu cầu biên dịch bằng JDK 6.

## 2. Bản đồ năng lực theo vị trí trong ứng dụng

```text
Khi xây dựng ứng dụng
    -> Compiler API, annotation processing

Khi nạp thành phần mở rộng
    -> ServiceLoader và SPI

Khi xử lý dữ liệu
    -> JDBC, StAX, cấu trúc dữ liệu có thứ tự, chuẩn hóa Unicode

Khi tích hợp môi trường
    -> Scripting API, Console, desktop/Swing theo ngữ cảnh
```

Không phải ứng dụng nào cũng cần mọi nhánh. Một dịch vụ web thuần server có thể cần JDBC và ServiceLoader nhưng không có lý do gọi Desktop. Một thư viện tạo mã có thể cần annotation processing mà không cần biên dịch mã trong lúc phục vụ yêu cầu.

Mục tiêu đầu tiên là biết đặt mỗi công cụ vào đúng giai đoạn và đúng ranh giới.

## 3. Java Compiler API: gọi trình biên dịch từ chương trình Java

### Khả năng

`javax.tools.JavaCompiler` cung cấp giao diện chuẩn để yêu cầu biên dịch, nhận chẩn đoán và quản lý đầu vào/đầu ra của trình biên dịch.

Nó hữu ích cho công cụ phát triển, kiểm tra mã sinh, môi trường học tập có kiểm soát hoặc hệ thống cần biên dịch theo một quy trình đã thiết kế. Không cần phụ thuộc trực tiếp vào các lớp compiler nội bộ để có một API biên dịch cơ bản.

Các thành phần cần nhận diện:

| Thành phần | Vai trò |
| --- | --- |
| `ToolProvider` | Tìm công cụ compiler của runtime hiện tại |
| `JavaCompiler` | Tạo yêu cầu biên dịch |
| `DiagnosticCollector` | Thu thông báo lỗi/cảnh báo có cấu trúc |
| `StandardJavaFileManager` | Quản lý tệp theo triển khai compiler |
| `JavaFileObject` | Biểu diễn một đơn vị dữ liệu cho công cụ |

Hợp đồng được mô tả trong [JavaCompiler API](https://docs.oracle.com/en/java/javase/25/docs/api/java.compiler/javax/tools/JavaCompiler.html).

### Điều kiện hiện đại cần kiểm tra

`ToolProvider.getSystemJavaCompiler()` có thể trả null khi không có compiler phù hợp. Kiểm tra kết quả thay vì giả định mọi tiến trình Java đều là một bản JDK đầy đủ.

Phải xác định classpath/module path, phiên bản đích, nơi ghi kết quả, thời hạn và vòng đời file manager. Biên dịch thành công cũng không có nghĩa mã được biên dịch an toàn để chạy.

Nếu xử lý mã không đáng tin, một class loader riêng không tự tạo môi trường cách ly đầy đủ. Việc cấp tài nguyên, giới hạn thời gian và cô lập thực thi là bài toán riêng của hệ thống.

## 4. Annotation processing: chuyển kiểm tra và sinh mã về giai đoạn build

### Khác với đọc annotation bằng reflection

Một annotation có thể được xử lý khi biên dịch để kiểm tra hợp đồng hoặc sinh thêm mã/tài nguyên. Việc này khác với một thư viện đọc annotation khi ứng dụng đang chạy.

Các API `javax.annotation.processing` và `javax.lang.model` cho phép processor làm việc trên mô hình chương trình, thay vì phải nạp mọi lớp ứng dụng để phản chiếu.

Ví dụ nhu cầu:

- Phát hiện một cách khai báo không hợp lệ và báo lỗi tại vị trí nguồn.
- Sinh mã ánh xạ hoặc lớp triển khai theo hợp đồng.
- Tạo metadata cho một công cụ khác ở giai đoạn build.

Các vai trò như `Processor`, `ProcessingEnvironment`, `Messager` và `Filer` nằm trong [Annotation Processing API](https://docs.oracle.com/en/java/javase/25/docs/api/java.compiler/javax/annotation/processing/package-summary.html).

### Áp dụng vào build hiện hành

Processor là mã được thực thi trong quá trình build. Cần chọn dependency và cấu hình processor có chủ đích, không coi mọi JAR trên classpath đều nên được phép tham gia sinh mã.

Trên javac hiện hành, việc xử lý annotation được yêu cầu thông qua cấu hình như processor, processor path/module path hoặc tùy chọn processing phù hợp. Không mặc định một hướng dẫn cũ về tự tìm processor sẽ có cùng hành vi trên mọi JDK. Xem [javac: Annotation Processing](https://docs.oracle.com/en/java/javase/25/docs/specs/man/javac.html#annotation-processing).

Mã sinh cần xác định rõ thư mục đầu ra, khả năng tái tạo và cách tham gia build. Không để processor âm thầm sửa nguồn do người dùng sở hữu nếu hợp đồng công cụ chỉ là sinh đầu ra.

## 5. ServiceLoader: tách giao diện dịch vụ khỏi provider

### Mô hình

```text
Ứng dụng biết interface dịch vụ
               |
         ServiceLoader
               |
  Các provider được triển khai trong môi trường
```

Ứng dụng tham chiếu tới hợp đồng, còn các thư viện cung cấp triển khai có thể được đóng gói độc lập. Đây là một nền tảng để xây điểm mở rộng mà không hard-code mọi lớp triển khai trong mã gọi.

Ở classpath, provider có thể đăng ký qua tài nguyên `META-INF/services`. Trong hệ thống module hiện đại, còn có hợp đồng `uses` và `provides ... with ...`.

Điểm cần nhớ:

- Có thể không tìm thấy provider nào.
- Có thể có nhiều provider; phải có chính sách chọn.
- Nạp provider có thể xảy ra theo nhu cầu.
- Cấu hình/provider sai có thể gây lỗi khi duyệt, không chỉ lúc tạo ServiceLoader.

Hợp đồng hiện hành nằm trong [ServiceLoader API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/ServiceLoader.html).

Không dựa vào “provider đầu tiên” làm ưu tiên nghiệp vụ nếu thứ tự không được ứng dụng quy định. Cũng không coi cơ chế tìm provider là sandbox: provider là mã có thể được nạp và thực thi.

## 6. JDBC 4: nền tảng truy cập dữ liệu vẫn dùng mỗi ngày

JDBC có trước Java 6; Java 6 mang đến JDBC 4 với các khả năng như tích hợp phát hiện driver theo cơ chế provider và mở rộng các hợp đồng liên quan kết nối/dữ liệu.

Trong ứng dụng hiện đại:

- Vẫn cần JDBC driver phù hợp với cơ sở dữ liệu và JDK.
- Driver được đăng ký đúng có thể được phát hiện mà không bắt buộc hard-code việc nạp lớp ở mọi nơi.
- Class loader, classpath hoặc module path vẫn quyết định driver có nhìn thấy được hay không.
- `DataSource` là điểm kết nối phù hợp cho nhiều thiết kế ứng dụng; connection pool là thành phần/cấu hình cụ thể, không phải hệ quả tự có của việc gọi JDBC.

Cách DriverManager tìm driver và vai trò DataSource được mô tả trong [DriverManager API](https://docs.oracle.com/en/java/javase/25/docs/api/java.sql/java/sql/DriverManager.html).

Học khả năng của JDBC 4 không thay các trách nhiệm hiện tại: câu lệnh có tham số, giao dịch, thời hạn, đóng tài nguyên, xử lý lỗi và quản lý thông tin xác thực. Có driver trong JAR chưa chứng minh kết nối, quyền hay schema đã đúng.

Không nhầm “driver tự phát hiện” với “mọi thứ tự cấu hình”.

## 7. Cấu trúc dữ liệu có thứ tự và hàng đợi hai đầu

### NavigableMap và NavigableSet

Khi cần phần tử gần một ngưỡng, thay vì duyệt toàn bộ collection, có thể dùng các phép tìm theo thứ tự:

| Phép tìm | Ý nghĩa |
| --- | --- |
| `lower...` | Nhỏ hơn ngưỡng |
| `floor...` | Nhỏ hơn hoặc bằng ngưỡng |
| `ceiling...` | Lớn hơn hoặc bằng ngưỡng |
| `higher...` | Lớn hơn ngưỡng |

Ví dụ: tìm bậc giá có ngưỡng thấp nhất áp dụng cho một giá trị; tìm mốc thời gian gần trước/sau; lấy một khoảng khóa có quy tắc bao gồm/loại trừ biên.

`NavigableMap` quy định các hợp đồng này trong [API hiện hành](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/NavigableMap.html).

Phải hiểu comparator và tính nhất quán của khóa. `TreeMap` không tự an toàn cho cập nhật đồng thời. Khi cần cấu trúc có thứ tự phục vụ nhiều luồng, xem xét triển khai concurrent phù hợp và hợp đồng thao tác kết hợp.

### Deque và ArrayDeque

Deque biểu diễn hàng đợi hai đầu, hỗ trợ cách thêm/lấy ở đầu hoặc cuối rõ ràng. ArrayDeque phù hợp cho nhiều stack/queue trong một luồng, không chấp nhận null và không tự đồng bộ.

Nếu cần chờ khi rỗng/đầy hoặc trao đổi giữa các luồng, không chỉ thay tên biến thành “queue”; cần dùng cấu trúc có hợp đồng đồng thời/chặn phù hợp. Dữ liệu có thứ tự và cơ chế đồng bộ là hai khía cạnh khác nhau.

## 8. StAX: đọc XML theo dòng sự kiện

Streaming API for XML cho phép ứng dụng chủ động tiến qua dữ liệu XML. Có API con trỏ và API sự kiện, thay vì bắt buộc dựng toàn bộ cây trong bộ nhớ.

Nó có ích khi xử lý dữ liệu XML lớn hoặc chỉ cần đọc một phần tuần tự. StAX không có nghĩa tổng bộ nhớ luôn nhỏ: nếu ứng dụng vẫn gom mọi phần tử vào một danh sách lớn, chính mã ứng dụng lại giữ toàn bộ dữ liệu.

Hai câu hỏi cần đặt:

1. Mô hình đọc theo dòng có phù hợp cách truy cập dữ liệu không?
2. Parser và ứng dụng có giới hạn dữ liệu, xử lý lỗi và chính sách truy cập tài nguyên ngoài phù hợp không?

Không để tài liệu đầu vào tự điều khiển việc truy cập tài nguyên bên ngoài khi chưa có chính sách cho phép. Khả năng streaming không thay thế cấu hình an toàn của XML.

Các nhóm reader/writer/factory được mô tả trong [StAX API](https://docs.oracle.com/en/java/javase/25/docs/api/java.xml/javax/xml/stream/package-summary.html).

## 9. Scripting API còn tồn tại, nhưng engine là một dependency riêng

`javax.script` chuẩn hóa việc tìm và sử dụng script engine, truyền đối tượng qua Bindings và gọi một số khả năng tùy chọn.

Cần phân biệt:

| Thành phần | Điều nó cung cấp |
| --- | --- |
| Scripting API | Giao diện tích hợp trong ứng dụng Java |
| Script engine | Triển khai ngôn ngữ và thực thi script |
| Script | Chương trình được engine xử lý |
| Chính sách thực thi | Quyền, tài nguyên, thời hạn và phạm vi dữ liệu được cấp |

`ScriptEngineManager` có thể không tìm thấy engine nào. `getEngineByName(...)` có thể trả null. Các khả năng `Compilable` hoặc `Invocable` không bắt buộc có ở mọi engine; cần kiểm tra khả năng thật.

Hợp đồng tìm engine và các phần mở rộng nằm trong [javax.script API](https://docs.oracle.com/en/java/javase/25/docs/api/java.scripting/javax/script/package-summary.html).

Không viết ví dụ phụ thuộc một engine ngầm có sẵn trong JDK rồi coi đó là tính chất của API. Cũng không coi eval script là cách an toàn để chạy mọi nội dung người dùng gửi. Môi trường thực thi cần được thiết kế và kiểm soát riêng.

## 10. Tiện ích văn bản và tương tác môi trường

### Normalizer

Hai cách biểu diễn Unicode có thể nhìn giống nhau nhưng có dãy code point khác nhau. Normalizer giúp chuyển về dạng chuẩn như NFC khi hợp đồng dữ liệu cần điều đó.

Chuẩn hóa không đồng nghĩa bỏ dấu, đổi chữ hoa/thường hoặc làm mọi định danh trở nên an toàn. Phải xác định dữ liệu nào được chuẩn hóa và thời điểm nào, nhất là nếu dữ liệu liên quan chữ ký hoặc cần giữ nguyên biểu diễn.

Xem [Normalizer API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/text/Normalizer.html).

### Console

Console cung cấp tương tác với thiết bị console nếu môi trường có. `System.console()` có thể trả null trong IDE, tác vụ nền hoặc CI.

Đọc mật khẩu bằng API phù hợp không thay trách nhiệm quản lý vòng đời mảng ký tự và không ghi bí mật vào log. Không tự giả định một dịch vụ nền có người chờ nhập dữ liệu.

Điều kiện môi trường được mô tả trong [Console API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/io/Console.html).

### Desktop và SwingWorker

Trong ứng dụng desktop, Desktop tích hợp với khả năng hệ điều hành như mở tệp hoặc URI bằng ứng dụng đã đăng ký. Phải kiểm tra khả năng nền tảng và hành động trước khi dùng; không áp dụng như một tiện ích server luôn có sẵn. Xem [Desktop API](https://docs.oracle.com/en/java/javase/25/docs/api/java.desktop/java/awt/Desktop.html).

SwingWorker hỗ trợ việc nền và cập nhật GUI theo mô hình luồng Swing. Tác vụ lâu không nên chạy trên Event Dispatch Thread; cập nhật thành phần Swing phải theo quy tắc EDT. Đây là mô hình cho giao diện Swing, không phải lý do thay mọi executor của dịch vụ bằng SwingWorker. Xem [SwingWorker API](https://docs.oracle.com/en/java/javase/25/docs/api/java.desktop/javax/swing/SwingWorker.html).

## 11. Ví dụ Java 17+: quan sát năng lực và dùng API theo hợp đồng

Chương trình sau:

- Tìm một bậc theo ngưỡng bằng NavigableMap.
- Xử lý hai đầu công việc bằng Deque.
- Kiểm tra một phép chuẩn hóa Unicode.
- Hỏi runtime có compiler và bao nhiêu script engine được tìm thấy.

Nó không biên dịch/chạy mã bên ngoài, không kết nối cơ sở dữ liệu và không mở ứng dụng desktop.

Lưu thành `Java6CapabilitiesDemo.java`:

```java
import java.text.Normalizer;
import java.util.ArrayDeque;
import java.util.Deque;
import java.util.Map;
import java.util.NavigableMap;
import java.util.TreeMap;
import javax.script.ScriptEngineManager;
import javax.tools.ToolProvider;

public class Java6CapabilitiesDemo {
    public static void main(String[] args) {
        NavigableMap<Integer, String> bands = new TreeMap<>();
        bands.put(0, "BASIC");
        bands.put(100, "STANDARD");
        bands.put(1_000, "BULK");
        Map.Entry<Integer, String> selected = bands.floorEntry(750);
        if (selected == null) {
            throw new IllegalStateException("No matching band");
        }
        System.out.println("band=" + selected.getValue());
        System.out.println("descendingKeys=" + bands.descendingKeySet());

        Deque<String> tasks = new ArrayDeque<>();
        tasks.addLast("import");
        tasks.addLast("validate");
        System.out.println("nextTask=" + tasks.removeFirst());
        System.out.println("remaining=" + tasks);

        String composed = Normalizer.normalize(
                "e\u0301", Normalizer.Form.NFC);
        System.out.println("normalizedEquals="
                + composed.equals("\u00E9"));

        System.out.println("compilerAvailable="
                + (ToolProvider.getSystemJavaCompiler() != null));
        System.out.println("scriptFactoryCount="
                + new ScriptEngineManager().getEngineFactories().size());
    }
}
```

Biên dịch và chạy:

```shell
javac -Xlint:all -Werror Java6CapabilitiesDemo.java
java Java6CapabilitiesDemo
```

Stdout trên một JDK 17 đầy đủ không cài script engine bổ sung:

```text
band=STANDARD
descendingKeys=[1000, 100, 0]
nextTask=import
remaining=[validate]
normalizedEquals=true
compilerAvailable=true
scriptFactoryCount=0
```

Năm dòng đầu kiểm chứng dữ liệu được tạo trong chương trình. Hai dòng cuối là kết quả khám phá môi trường; chúng có thể thay đổi khi runtime thiếu compiler hoặc có thêm provider engine.

`scriptFactoryCount=0` không có nghĩa Scripting API bị lỗi. Nó có nghĩa manager không tìm thấy factory trong phạm vi khám phá hiện tại. Tương tự, `compilerAvailable=false` yêu cầu xem lại thành phần runtime, không phải tự gọi một API nội bộ để né kiểm tra.

## 12. Đóng gói hiện đại: có API chưa đủ

Hệ thống module xuất hiện sau Java 6. Khi triển khai trên JDK hiện đại, có thể gặp các module như:

| Nhóm API | Module hiện đại liên quan |
| --- | --- |
| Collections, ServiceLoader, Console, Normalizer | `java.base` |
| Compiler API và annotation processing | `java.compiler` |
| Triển khai javac của JDK | `jdk.compiler` |
| JDBC | `java.sql` |
| StAX | `java.xml` |
| Scripting API | `java.scripting` |
| AWT/Swing/Desktop | `java.desktop` |

Module chứa API và module chứa một triển khai cụ thể có thể khác nhau. Driver/provider bên ngoài vẫn cần được đóng gói đúng.

Không suy ra một API đã bị xóa chỉ vì runtime tối giản không có module của nó. Cũng không suy ra mọi công nghệ từng được một bản JDK đóng gói chung đều còn được JDK hiện tại cung cấp. Hãy đối chiếu tài liệu của chính API và artifact đang dùng.

## 13. Chọn điểm bắt đầu theo nhu cầu thật

| Nhu cầu | Năng lực nên tìm hiểu trước |
| --- | --- |
| Tạo công cụ kiểm tra hoặc biên dịch mã | JavaCompiler và diagnostics |
| Kiểm tra/sinh mã khi build | Annotation processing |
| Nạp nhiều triển khai theo hợp đồng | ServiceLoader |
| Truy cập cơ sở dữ liệu | JDBC/driver/DataSource |
| Tìm phần tử sát ngưỡng hoặc trong khoảng | NavigableMap/NavigableSet |
| Đọc XML tuần tự | StAX |
| Nhúng ngôn ngữ script có chủ đích | Scripting API cùng engine được chọn |
| So sánh văn bản theo dạng chuẩn | Normalizer theo chính sách dữ liệu |
| Ứng dụng dòng lệnh tương tác | Console và xử lý khi không có console |
| Ứng dụng Swing/desktop | EDT, SwingWorker, khả năng Desktop |

Đây là định hướng lựa chọn, không phải yêu cầu mọi ứng dụng phải dùng toàn bộ danh sách.

Với mỗi công cụ, người học nên trả lời được: đầu vào là gì, điều kiện môi trường nào cần có, lỗi nào phải xử lý, ai sở hữu tài nguyên và bằng chứng nào cho thấy hành vi đúng.

## 14. Tự kiểm tra

1. Vì sao học API xuất hiện từ Java 6 vẫn có giá trị? **Nhiều hợp đồng nền tảng vẫn được dùng, nhưng cần áp dụng theo môi trường hiện hành.**
2. Có Scripting API có bảo đảm có một engine ngôn ngữ cụ thể không? **Không.**
3. Annotation processing có giống đọc annotation khi ứng dụng chạy không? **Không; giai đoạn và hợp đồng xử lý khác nhau.**
4. ServiceLoader có luôn tìm được đúng một provider không? **Không; cần xử lý không có/nhiều provider.**
5. Driver tự phát hiện có thay quản lý giao dịch và tài nguyên không? **Không.**
6. Streaming XML có tự bảo đảm bộ nhớ thấp và đầu vào an toàn không? **Không; còn mã giữ dữ liệu và cấu hình parser.**
7. API Desktop có luôn hoạt động trong container không? **Không; phụ thuộc module, nền tảng và khả năng môi trường.**
8. Có thể lấy việc một ví dụ chạy được làm bằng chứng đủ cho triển khai thật không? **Không; còn phải kiểm tra provider, lỗi, tài nguyên và chính sách của hệ thống.**
