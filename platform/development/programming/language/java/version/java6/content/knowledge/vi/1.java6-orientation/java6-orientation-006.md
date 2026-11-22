# Lựa chọn API theo nhu cầu và kiểm chứng giới hạn sử dụng

## 1. Bắt đầu từ việc cần làm, không bắt đầu từ tên phiên bản

Khi học các API xuất hiện trong Java 6, mục tiêu không phải đưa càng nhiều lớp mới vào chương trình càng tốt. Một API hữu ích khi nó diễn đạt đúng yêu cầu, có hợp đồng phù hợp và hoạt động trong môi trường sẽ triển khai.

Ví dụ, yêu cầu “tìm mức thưởng có ngưỡng lớn nhất không vượt quá điểm hiện tại” khác với “tìm phần tử bằng khóa”. Cả hai đều liên quan bảng khóa–giá trị, nhưng phép toán cần thiết khác nhau. Chọn đúng API giúp giảm mã tự viết và làm quy tắc rõ hơn.

Một chuỗi suy luận nên dùng:

```text
nhu cầu
  -> phép toán và dữ liệu
    -> hợp đồng API
      -> thành phần triển khai cần có
        -> điều kiện môi trường
          -> thử đúng, thử biên và thử lỗi
```

Bài tập trung phương pháp lựa chọn các API còn hữu ích trên Java hiện đại. Ví dụ dùng Java 17+; tên nhóm “Java 6” chỉ ngữ cảnh học các khả năng được giới thiệu từ giai đoạn đó, không phải yêu cầu triển khai bằng JDK 6.

## 2. Viết yêu cầu đủ cụ thể để chọn được API

Trước khi tra cứu lớp, trả lời những câu sau:

| Câu hỏi | Ví dụ |
| --- | --- |
| Đầu vào/đầu ra là gì? | Điểm nguyên và tên mức thưởng |
| Phép toán chính là gì? | Tìm ngưỡng gần nhất ở phía nhỏ hơn hoặc bằng |
| Có yêu cầu thứ tự không? | Các ngưỡng phải có thứ tự theo số |
| Khi không có kết quả thì sao? | Báo không hỗ trợ, không tự lấy mức đầu tiên |
| Có dùng đồng thời không? | Một luồng cấu hình hay nhiều luồng vừa đọc vừa cập nhật |
| Có phụ thuộc môi trường không? | Cần driver cơ sở dữ liệu, trình biên dịch, script engine hay giao diện đồ họa |
| Có giới hạn tài nguyên không? | Kích thước dữ liệu, số kết nối, thời gian chờ, bộ nhớ |
| Ai đóng tài nguyên và xử lý lỗi? | Phạm vi sử dụng phải quản lý kết nối/luồng/tệp tương ứng |

Nếu yêu cầu chỉ là tìm theo khóa chính xác, một `Map` thông thường có thể đủ. Nếu cần tìm khóa lân cận theo thứ tự, `NavigableMap` mới diễn đạt đúng vấn đề. Không chọn cấu trúc phức tạp hơn chỉ vì nó nằm trong danh sách cần học.

Yêu cầu cũng có thể cho thấy không cần một API nào đó: tính một biểu thức cố định không nhất thiết cần nhúng cả ngôn ngữ script; đọc cấu hình đơn giản không nhất thiết cần biên dịch mã Java khi chạy.

## 3. Tách hợp đồng API khỏi thành phần triển khai

Có thể hiểu một khả năng qua ba lớp:

1. **Hợp đồng API:** kiểu, phương thức, tham số và hành vi được tài liệu cam kết.
2. **Thành phần triển khai (provider):** mã thực hiện khả năng đó.
3. **Môi trường chạy:** module, thư viện, hệ điều hành, bộ nạp lớp, cấu hình và quyền truy cập.

Một lời gọi biên dịch được mới chứng minh API có mặt trên đường biên dịch. Nó chưa chứng minh provider có mặt, kết nối thành công hoặc dữ liệu đầu vào được hỗ trợ.

Ví dụ:

- Có `java.sql` không đồng nghĩa JDK có sẵn driver cho mọi hệ quản trị cơ sở dữ liệu.
- Có `javax.script` không đồng nghĩa có engine cho tên ngôn ngữ bạn yêu cầu.
- Có `javax.tools.JavaCompiler` không đồng nghĩa mọi runtime image đều chứa trình biên dịch.
- Có `Desktop` không đồng nghĩa máy chủ có giao diện đồ họa và ứng dụng liên kết với mọi loại tệp.

Vì vậy, cần xác định provider và môi trường như một phần của thiết kế, thay vì chỉ xử lý chúng khi gặp lỗi lúc triển khai.

## 4. Bản đồ lựa chọn một số nhóm API

| Nhu cầu thực tế | API/khả năng phù hợp để khảo sát | Giới hạn phải kiểm chứng |
| --- | --- | --- |
| Tìm khóa lân cận hoặc khoảng theo thứ tự | `NavigableMap`, `NavigableSet` | Bao gồm/loại trừ biên, không có kết quả, comparator, truy cập đồng thời |
| Phát hiện nhiều bản triển khai của một dịch vụ | `ServiceLoader` | Provider được đóng gói và nhìn thấy đúng chưa; khi không có/nhiều provider thì chọn thế nào |
| Biên dịch mã Java từ công cụ Java | `JavaCompiler`, `ToolProvider` | Runtime có trình biên dịch không; phiên bản nguồn, phụ thuộc và chẩn đoán lỗi |
| Nhúng một ngôn ngữ script | `ScriptEngineManager`, `ScriptEngine` | Engine nào được cài, tên tra cứu, tính đồng thời và quyền truy cập của mã script |
| Làm việc với cơ sở dữ liệu quan hệ | JDBC và driver tương ứng | Driver, kết nối, giao dịch, SQL và từng khả năng thực sự được hỗ trợ |
| Mở trình duyệt/tệp bằng ứng dụng trên máy người dùng | `Desktop` | Nền tảng, phiên làm việc đồ họa, hành động và ứng dụng liên kết |

Đây là bản đồ định hướng, không thay thế hợp đồng chi tiết của từng API. Một bài học không cần dùng hết bảng. Chọn nhánh tương ứng nhu cầu rồi kiểm chứng nhánh đó.

### Ví dụ: NavigableMap thay vòng lặp tự tìm ngưỡng

Với các ngưỡng `0`, `100`, `500`, nếu quy tắc là “mức cao nhất không vượt quá điểm”:

- `floorEntry(120)` chọn ngưỡng `100`.
- `floorEntry(100)` vẫn chọn `100`, vì có bao gồm biên bằng.
- `lowerEntry(100)` chọn phía nhỏ hơn hẳn, nên cho kết quả khác.
- Khi không có ngưỡng phù hợp, `floorEntry` trả `null`.

Lựa chọn giữa `floor` và `lower` là quyết định nghiệp vụ, không phải chi tiết tên phương thức. Hợp đồng quan hệ thứ tự xem [NavigableMap](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/NavigableMap.html).

## 5. Đọc tài liệu theo các câu hỏi có thể kiểm chứng

Đừng chỉ đọc phần mô tả ngắn và ví dụ thành công. Với phương thức quan trọng, kiểm tra:

- **Điều kiện đầu vào:** có chấp nhận `null`, giá trị rỗng, số âm hoặc kiểu không so sánh được không?
- **Kết quả khi không có dữ liệu:** trả `null`, tập rỗng, giá trị mặc định hay ném ngoại lệ?
- **Tác dụng phụ:** có sửa dữ liệu, mở tài nguyên, khởi tạo provider hoặc chạy mã bên ngoài không?
- **Quan hệ sở hữu:** kết quả là bản sao, ảnh chụp một thời điểm hay một khung nhìn gắn với dữ liệu gốc?
- **Tính đồng thời:** đối tượng có dùng chung an toàn được không, thao tác nhiều bước có nguyên tử không?
- **Ngoại lệ:** loại nào biểu diễn dữ liệu sai, thiếu khả năng, lỗi cấu hình hoặc lỗi môi trường?
- **Phiên bản và module:** API có mặt từ đâu, có bị ngừng khuyến nghị dùng không, runtime thực tế có module cần thiết không?

Ví dụ, một khung nhìn khoảng của map không mặc nhiên là bản sao độc lập. Một thư viện nêu “an toàn khi dùng đồng thời” cũng không tự làm chuỗi “kiểm tra rồi cập nhật” thành một giao dịch nguyên tử.

Dùng tài liệu của JDK/driver/provider thực sự triển khai. Không lấy kết quả thử ở một JDK làm hợp đồng chung cho tất cả JDK.

## 6. Kiểm tra khả năng trước khi sử dụng

### Trình biên dịch Java

`ToolProvider.getSystemJavaCompiler()` có thể trả `null` nếu môi trường không cung cấp trình biên dịch. Trên bản triển khai JDK được mô tả, nó liên quan sự có mặt của `jdk.compiler`.

Do đó, công cụ cần biên dịch khi chạy phải kiểm tra giá trị này và có thông báo/cách xử lý phù hợp. Máy phát triển có `javac` không chứng minh runtime image dùng để triển khai cũng có khả năng tương tự. Xem [ToolProvider](https://docs.oracle.com/en/java/javase/25/docs/api/java.compiler/javax/tools/ToolProvider.html).

Biên dịch thành công cũng chưa có nghĩa chạy mã đó an toàn. Nếu đầu vào là mã không đáng tin, phải có thiết kế cách ly/quyền hạn riêng; Compiler API không tự cung cấp một sandbox.

### Script engine

`ScriptEngineManager` phát hiện các `ScriptEngineFactory` nhìn thấy theo cơ chế provider. `getEngineByName(...)` có thể không tìm được engine; không được nối ngay `.eval(...)` mà bỏ qua kết quả không có engine.

Không giả định JavaScript engine luôn được đóng gói cùng mọi JDK hiện đại. Nếu ứng dụng cần một ngôn ngữ cụ thể, chọn và đóng gói provider còn được duy trì, kiểm chứng đúng phiên bản và kiểm tra cách provider giới hạn truy cập mã Java/tài nguyên.

Một danh sách engine không rỗng cũng chưa chứng minh có đúng engine bạn cần. Xem [ScriptEngineManager](https://docs.oracle.com/en/java/javase/25/docs/api/java.scripting/javax/script/ScriptEngineManager.html).

### ServiceLoader

`ServiceLoader` giúp ứng dụng tìm các bản triển khai của một dịch vụ; nó không tự tải một thư viện còn thiếu từ Internet.

Cần xử lý cả không có provider, có nhiều provider hoặc cấu hình provider lỗi. Nếu dùng module có tên, kiểm tra khai báo `uses`/`provides` liên quan. Không chọn “provider đầu tiên” nếu yêu cầu thực sự cần một khả năng hoặc phiên bản cụ thể. Xem [ServiceLoader](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/ServiceLoader.html).

### JDBC

Cơ chế tự phát hiện driver giảm nhu cầu gọi tên lớp driver thủ công trong trường hợp cấu hình đúng; nó không loại bỏ nhu cầu cung cấp JAR driver.

Kết nối thành công chưa chứng minh mọi kiểu dữ liệu, mức cô lập giao dịch hoặc tính năng JDBC đều dùng được. Đọc metadata thích hợp và thử trên đúng driver/cơ sở dữ liệu; xử lý `SQLException` và các trường hợp tính năng không được hỗ trợ theo hợp đồng. Trong ứng dụng, còn phải xác định cách lấy kết nối, thời gian chờ, giao dịch và đóng tài nguyên. Xem [DriverManager](https://docs.oracle.com/en/java/javase/25/docs/api/java.sql/java/sql/DriverManager.html).

### Desktop

Kiểm tra hỗ trợ Desktop và hành động cụ thể trước khi gọi. Dù hành động được hỗ trợ, thao tác vẫn có thể thất bại khi không có ứng dụng liên kết hoặc môi trường không cho phép.

Lệnh mở trình duyệt/tệp chạy trên **máy đang chạy ứng dụng Java**. Một backend gọi `Desktop.browse` không mở trình duyệt của người dùng từ xa. Xem [Desktop](https://docs.oracle.com/en/java/javase/25/docs/api/java.desktop/java/awt/Desktop.html).

## 7. Ví dụ chạy được: lựa chọn phép toán và thăm dò môi trường

Tệp `ApiSelectionDemo.java`:

```java
import java.util.Map;
import java.util.NavigableMap;
import java.util.TreeMap;
import javax.script.ScriptEngineManager;
import javax.tools.ToolProvider;

public final class ApiSelectionDemo {
    public static void main(String[] args) {
        NavigableMap<Integer, String> levels = new TreeMap<>();
        levels.put(0, "BASIC");
        levels.put(100, "SILVER");
        levels.put(500, "GOLD");

        System.out.println("score=120 -> " + findLevel(levels, 120));
        System.out.println("score=100 -> " + findLevel(levels, 100));
        System.out.println("score=-1 -> " + findLevel(levels, -1));

        System.out.println(
                "compilerAvailable=" + (ToolProvider.getSystemJavaCompiler() != null));
        System.out.println(
                "scriptFactories=" + new ScriptEngineManager().getEngineFactories().size());
    }

    private static String findLevel(
            NavigableMap<Integer, String> levels, int score) {
        Map.Entry<Integer, String> selected = levels.floorEntry(score);
        return selected == null ? "UNSUPPORTED" : selected.getValue();
    }
}
```

Biên dịch và chạy với JDK 17 trở lên:

```shell
javac --release 17 ApiSelectionDemo.java
java ApiSelectionDemo
```

Stdout trên Zulu OpenJDK 24.0.2, không bổ sung thư viện script engine:

```text
score=120 -> SILVER
score=100 -> SILVER
score=-1 -> UNSUPPORTED
compilerAvailable=true
scriptFactories=0
```

Ba dòng đầu kiểm chứng hợp đồng của quy tắc tìm ngưỡng:

- Điểm nằm giữa hai ngưỡng dùng ngưỡng phía dưới.
- Điểm đúng ngưỡng được tính vào mức tương ứng.
- Điểm thấp hơn mọi ngưỡng được xử lý rõ ràng, không gây `NullPointerException`.

Hai dòng cuối là kết quả **của môi trường thử**, không phải stdout cố định trên mọi máy. Nếu runtime không có compiler thì giá trị có thể là `false`; nếu bổ sung provider script nhìn thấy được thì số factory có thể tăng.

Thăm dò khả năng không đồng nghĩa đã kiểm thử chức năng hoàn chỉnh: `compilerAvailable=true` chưa chứng minh biên dịch được một dự án có phụ thuộc cụ thể, và `scriptFactories>0` chưa chứng minh engine hỗ trợ cú pháp/cấu hình bạn cần.

Ví dụ không dùng cơ sở dữ liệu hoặc mở ứng dụng desktop để giữ phép kiểm chứng độc lập, không cần dịch vụ ngoài.

## 8. Thử giới hạn theo bốn nhóm

Sau khi một ví dụ thành công, tiếp tục các phép thử có ý nghĩa:

| Nhóm thử | Câu hỏi | Ví dụ |
| --- | --- | --- |
| Đúng nhu cầu | API có tạo kết quả nghiệp vụ mong muốn không? | Điểm `120` chọn mức `100` |
| Biên dữ liệu | Khi chạm hoặc vượt giới hạn thì sao? | Đúng ngưỡng, dưới ngưỡng thấp nhất, map rỗng |
| Thiếu điều kiện | Khi provider/tài nguyên không có thì sao? | Không có engine, không có compiler, không có driver phù hợp |
| Điều kiện vận hành | Có còn đúng trong môi trường thật không? | Nhiều luồng, mạng chậm, runtime image khác, hệ điều hành không có desktop |

Không tự động chuyển mọi lỗi thành một giá trị mặc định. Ví dụ, “không có mức thưởng cho điểm âm” có thể là dữ liệu đầu vào không hợp lệ; còn “không có script engine bắt buộc” là lỗi cấu hình triển khai. Hai trường hợp cần thông báo và phản ứng khác nhau.

Đối với ví dụ map, `TreeMap` không phải một lựa chọn cho cập nhật đồng thời không đồng bộ hóa. Nếu nhu cầu thay đổi, xem xét thiết kế truy cập và bản triển khai phù hợp thay vì chỉ thêm nhiều luồng vào đoạn mã mẫu.

Đối với API giữ tài nguyên, chứng minh cả đường thành công và đường lỗi đều giải phóng đúng. Với Java hiện đại, dùng `try-with-resources` khi đối tượng thực sự có hợp đồng `AutoCloseable`; đừng suy ra mọi interface đều có thể đưa vào khối đó.

## 9. Ghi lại quyết định để có thể thay đổi đúng lúc

Một quyết định chọn API nên đủ ngắn để đọc nhưng đủ cụ thể để kiểm tra lại:

```text
Nhu cầu: chọn mức theo ngưỡng lớn nhất không vượt quá điểm.
Lựa chọn: NavigableMap.floorEntry trên TreeMap.
Lý do: diễn đạt trực tiếp quan hệ <= theo thứ tự khóa.
Giới hạn: không tìm thấy trả null; truy cập đồng thời cần thiết kế riêng.
Bằng chứng: thử giữa ngưỡng, đúng ngưỡng, dưới ngưỡng thấp nhất và map rỗng.
```

Đây là ví dụ bản ghi kỹ thuật, không phải cấu hình chương trình.

Nếu lựa chọn phụ thuộc provider, bổ sung phiên bản provider, module/thư viện cần có và cách kiểm tra khi thiếu. Nếu phụ thuộc hệ điều hành, ghi rõ phạm vi nền tảng đã thử.

Không ghi “chọn vì có từ Java 6” như lý do thiết kế chính. Năm xuất hiện giúp định hướng lịch sử; nhu cầu và hợp đồng mới giải thích vì sao API phù hợp.

## 10. Các lỗi lựa chọn cần tránh

| Lỗi | Cách sửa |
| --- | --- |
| Chọn API theo tên nghe mạnh hơn | Viết phép toán và yêu cầu trước, rồi đối chiếu hợp đồng |
| Có thể import thì chắc chắn chạy được | Kiểm tra provider, module và môi trường thực tế |
| Chạy thành công một lần là đã hiểu giới hạn | Thử biên, thiếu điều kiện và lỗi vận hành |
| Dùng ví dụ cũ như cấu hình triển khai mặc định | Đối chiếu tài liệu và provider còn được hỗ trợ trên JDK đang dùng |
| Gặp lỗi thì bắt mọi ngoại lệ và trả kết quả rỗng | Phân biệt lỗi dữ liệu, thiếu khả năng và lỗi hệ thống |
| API có cơ chế mở rộng nên tin mọi plugin/script | Kiểm chứng nguồn, quyền hạn và phạm vi thực thi của thành phần mở rộng |

Tự thực hành:

1. Đổi `floorEntry` thành `lowerEntry` trong ví dụ; giải thích vì sao kết quả ở điểm `100` thay đổi.
2. Xóa toàn bộ ngưỡng rồi chạy; xác định vì sao đoạn mã vẫn xử lý được trường hợp không có kết quả.
3. Viết bản ghi lựa chọn cho một công cụ cần biên dịch Java khi chạy: điều kiện môi trường và lỗi nào phải được kiểm chứng?
4. Phân biệt “không phát hiện script factory nào” với “có factory nhưng engine không đáp ứng ngôn ngữ/cấu hình cần dùng”.
5. Với một API dự định dùng, liệt kê một điều kiện đầu vào, một giới hạn môi trường và một phép thử lỗi trước khi tích hợp.
