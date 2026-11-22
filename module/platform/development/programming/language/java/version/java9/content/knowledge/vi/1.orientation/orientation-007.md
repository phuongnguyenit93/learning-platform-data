# Lựa chọn tính năng theo nhu cầu thay vì áp dụng đồng loạt

Java 9 đưa vào nền tảng nhiều công cụ mới, nhưng mỗi công cụ giải quyết một vấn đề cụ thể. Một dự án tốt không cần sử dụng tất cả tính năng chỉ vì chúng tồn tại. Chọn đúng tính năng giúp mã rõ ràng hơn, giảm lỗi và tiết kiệm chi phí vận hành; chọn sai có thể làm tăng độ phức tạp, gây khó cho build, triển khai hoặc bảo trì.

Cần phân biệt hai việc: **tính năng được giới thiệu trong Java 9** và **tính năng còn được hỗ trợ trong các JDK hiện đại**. Java 9 là bản phát hành ngắn hạn, không phải LTS, nên không nên chọn JDK 9 làm runtime mới. Khi phát triển hoặc triển khai hiện nay, hãy dùng một JDK còn được nhà cung cấp hỗ trợ, thường là bản LTS phù hợp với hệ thống. Những API Java 9 vẫn tồn tại trong JDK hiện đại có thể tiếp tục được sử dụng sau khi kiểm tra phiên bản đích và tương thích thư viện.

## 1. Quy trình quyết định trước khi áp dụng

1. **Nêu rõ vấn đề cần giải quyết.** Ví dụ: danh sách cấu hình bị sửa ngoài ý muốn, pipeline xử lý dữ liệu quá dài, tác vụ gọi dịch vụ bên ngoài không có giới hạn thời gian, hoặc ứng dụng cần ranh giới module rõ ràng.
2. **Xác định runtime thực tế.** Kiểm tra JDK dùng trong máy phát triển, CI, môi trường kiểm thử và production. Tính năng chỉ có ích nếu phiên bản đích hỗ trợ nó.
3. **Kiểm tra trạng thái API.** Đọc Javadoc của JDK mục tiêu và ghi chú migration. Không chọn API đã deprecated for removal, đã bị loại bỏ hoặc từng chỉ là incubator.
4. **So sánh với cách đơn giản hơn.** Nếu vòng lặp, collection thông thường hoặc cấu hình hiện có đã giải quyết tốt vấn đề, không cần thêm abstraction chỉ để dùng API mới.
5. **Đánh giá tác động.** Xem xét khả năng đọc mã, hiệu năng trên dữ liệu thực, tương thích dependency, khả năng debug, build và vận hành.
6. **Thử trong phạm vi nhỏ.** Viết test cho trường hợp biên, đo khi có giả thuyết hiệu năng, chạy trên đúng JDK đích và chỉ mở rộng khi lợi ích được xác nhận.
7. **Ghi lại lý do lựa chọn.** Nêu vấn đề, lợi ích, giới hạn và điều kiện cần xem xét lại. Điều này giúp người bảo trì hiểu vì sao tính năng được dùng.

## 2. Những tính năng Java 9 vẫn có giá trị trong JDK hiện đại

### 2.1. Factory method cho collection bất biến

Các phương thức `List.of(...)`, `Set.of(...)` và `Map.of(...)` tạo collection không cho phép thêm, xóa hoặc thay thế phần tử. Chúng phù hợp với danh sách vai trò mặc định, tập trạng thái cố định, bảng ánh xạ nhỏ hoặc cấu hình được khởi tạo một lần.

Chọn chúng khi dữ liệu cần được công bố dưới dạng chỉ đọc và không chứa `null`. Các collection này từ chối `null`; `Set.of` cũng từ chối phần tử trùng, còn `Map.of` từ chối khóa trùng. Nếu nghiệp vụ cần thay đổi collection, hãy tạo bản sao có thể sửa, chẳng hạn `new ArrayList<>(List.of("READ", "WRITE"))`. Tính không sửa được của collection không đồng nghĩa các object bên trong cũng bất biến sâu.

### 2.2. Các thao tác Stream bổ sung

Java 9 bổ sung `takeWhile`, `dropWhile`, `ofNullable` và overload `iterate` có điều kiện dừng. Chúng hữu ích khi xử lý dữ liệu theo pipeline:

- `takeWhile(predicate)` lấy phần đầu liên tiếp còn thỏa điều kiện trên ordered stream.
- `dropWhile(predicate)` bỏ phần đầu liên tiếp còn thỏa điều kiện.
- `ofNullable(value)` tạo stream một phần tử nếu giá trị khác `null`, hoặc stream rỗng nếu giá trị là `null`.
- `iterate(seed, hasNext, next)` tạo dãy có điều kiện dừng, tránh phải tự ghép vòng lặp vô hạn với thao tác giới hạn.

Không thay `filter` bằng `takeWhile` một cách máy móc: `filter` kiểm tra mọi phần tử, còn `takeWhile` dừng tại phần tử đầu tiên không thỏa điều kiện trên stream có thứ tự. Với ordered parallel stream, `takeWhile` hoặc `dropWhile` có thể tốn kém do phải giữ đúng thứ tự. Stream cũng nên dùng cho phép biến đổi dữ liệu rõ ràng, không dựa vào side effect trong các hàm trung gian.

### 2.3. Timeout và thực thi trễ với CompletableFuture

Các phương thức `orTimeout`, `completeOnTimeout` và `delayedExecutor` giúp mô tả giới hạn thời gian trong luồng xử lý bất đồng bộ:

- Dùng `orTimeout` khi hết hạn phải được xem là lỗi và future hoàn tất ngoại lệ bằng `TimeoutException`.
- Dùng `completeOnTimeout` khi nghiệp vụ có một giá trị mặc định hợp lệ để trả về khi quá hạn.
- Dùng `delayedExecutor` khi cần gửi một tác vụ tới executor sau một khoảng trễ.

Ví dụ minh họa: `callRemoteService().orTimeout(2, TimeUnit.SECONDS)`. Đây là giới hạn thời gian hoàn tất của `CompletableFuture`; nó không tự bảo đảm thao tác I/O bên dưới đã dừng. Hãy cấu hình timeout hoặc cơ chế hủy ở HTTP client, database driver hay API thực thi tương ứng. Không dùng giá trị mặc định để che giấu lỗi nếu nghiệp vụ cần phân biệt timeout với kết quả hợp lệ.

### 2.4. Java Platform Module System (JPMS)

Module system phù hợp khi ứng dụng hoặc thư viện có nhiều thành phần và cần khai báo rõ dependency, package được công khai và service được cung cấp. Tệp `module-info.java` mô tả các quan hệ như `requires`, `exports`, `opens` và `uses/provides`.

Chỉ nên chuyển sang module khi nhóm có nhu cầu thực tế về ranh giới kiến trúc, đóng gói hoặc kiểm soát truy cập. Không thêm module descriptor chỉ để làm dự án trông hiện đại hơn. Ứng dụng đang dùng nhiều thư viện trên classpath, framework dựa vào reflection hoặc plugin động có thể cần cấu hình `opens` và kiểm tra tương thích kỹ hơn. Hãy thử một module nhỏ trước khi chuyển toàn bộ hệ thống.

### 2.5. jlink để tạo runtime image riêng

`jlink` kết hợp các module cần thiết và dependency bắc cầu để tạo một runtime image tùy chỉnh. Chọn nó khi nhóm phân phối ứng dụng kèm runtime, muốn kiểm soát tập module hoặc cần tối ưu image triển khai. Ví dụ dạng lệnh: `jlink --module-path <module-path> --add-modules <module-name> --output <runtime-dir>`.

Không cần dùng `jlink` nếu nền tảng triển khai đã cung cấp JRE/JDK phù hợp hoặc lợi ích về kích thước không đáng kể. Runtime image tùy chỉnh là một artifact phải được cập nhật khi có bản vá JDK; nhóm phát hành phải xây dựng và kiểm thử lại image thay vì xem nó là gói dùng một lần.

### 2.6. Flow API cho luồng dữ liệu có backpressure

`java.util.concurrent.Flow` cung cấp các interface Publisher, Subscriber, Subscription và Processor theo mô hình Reactive Streams. Cơ chế request qua Subscription giúp subscriber kiểm soát lượng phần tử được phát, tránh đẩy dữ liệu không giới hạn vào bên nhận.

Dùng Flow khi cần tích hợp với thành phần đã giao tiếp bằng các interface này hoặc khi backpressure là yêu cầu thật. Nếu ứng dụng chỉ xử lý một danh sách nhỏ hoặc một tác vụ bất đồng bộ đơn giản, collection, iterator hoặc CompletableFuture thường dễ hiểu hơn. Với hệ thống reactive lớn, cân nhắc framework đang được dự án sử dụng để có operator, quản lý lỗi và tích hợp phù hợp; không tự viết một reactive framework nếu không có nhu cầu.

### 2.7. Multi-release JAR cho thư viện hỗ trợ nhiều phiên bản Java

Multi-release JAR cho phép một file JAR chứa implementation chung và các class/resource riêng theo phiên bản trong `META-INF/versions/<N>`, được bật bằng manifest attribute `Multi-Release: true`. Cách này hữu ích cho tác giả thư viện cần giữ một artifact tương thích với nhiều major version nhưng vẫn tận dụng API mới ở runtime mới hơn.

Không nên dùng cho ứng dụng chỉ triển khai trên một phiên bản JDK. Mỗi nhánh phiên bản làm tăng số tổ hợp cần build, test và bảo trì; chỉ áp dụng khi có yêu cầu tương thích nhiều runtime rõ ràng.

### 2.8. JShell và private method trong interface

JShell hữu ích để thử nhanh biểu thức, API, chuyển đổi dữ liệu hoặc một ý tưởng nhỏ trước khi viết thành class và test chính thức. Kết quả thử nghiệm trong JShell không thay thế kiểm thử tự động, review hoặc kiểm tra build.

Private method trong interface hữu ích khi nhiều default method cần dùng chung một đoạn xử lý nhỏ. Dùng nó để loại bỏ lặp mã cục bộ; nếu logic nghiệp vụ lớn, cần state hoặc nhiều dependency, hãy đặt logic trong class/service thích hợp thay vì dồn vào interface.

## 3. Ví dụ: chọn collection bất biến nhưng vẫn cho phép chỉnh sửa khi cần

Chương trình dưới đây dùng Java 9 API còn có trong JDK hiện đại. Danh sách vai trò mặc định được tạo bằng `List.of`; khi cần thêm vai trò, chương trình tạo một `ArrayList` riêng. Pipeline dùng `ofNullable` để bỏ giá trị `null` và `takeWhile` để lấy phần đầu trước mốc dừng.

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.Stream;

public class FeatureChoiceDemo {
    public static void main(String[] args) {
        List<String> defaultRoles = List.of("READER", "EDITOR");
        List<String> editableRoles = new ArrayList<>(defaultRoles);
        editableRoles.add("AUDITOR");

        List<String> usersBeforeBob = Stream.of("alice", null, "bob", "carol")
                .flatMap(Stream::ofNullable)
                .takeWhile(name -> !name.equals("bob"))
                .collect(Collectors.toList());

        System.out.println("Defaults: " + defaultRoles);
        System.out.println("Editable: " + editableRoles);
        System.out.println("Users before bob: " + usersBeforeBob);
    }
}
~~~

Lưu thành `FeatureChoiceDemo.java`, sau đó biên dịch và chạy:

~~~bash
javac -encoding UTF-8 FeatureChoiceDemo.java
java FeatureChoiceDemo
~~~

Kết quả chính xác:

~~~text
Defaults: [READER, EDITOR]
Editable: [READER, EDITOR, AUDITOR]
Users before bob: [alice]
~~~

Ví dụ thể hiện việc chọn theo mục đích: dữ liệu mặc định không cần sửa thì dùng collection không sửa được; dữ liệu cần cập nhật thì dùng collection có thể sửa. Pipeline chỉ lấy phần đầu trước `bob`, nên `carol` không được giữ lại. Nếu yêu cầu là lấy tất cả người dùng khác `bob`, hãy dùng `filter` thay cho `takeWhile`.

## 4. Những thành phần cũ không nên đưa vào thiết kế mới

Một số thành phần từng xuất hiện trong hoặc quanh Java 9 đã bị loại bỏ ở các bản sau. Không đưa chúng vào bài toán mới chỉ vì chúng có mặt trong tài liệu cũ:

- Các module Java EE và CORBA như `java.xml.bind`, `java.xml.ws`, `java.corba` và module tổng hợp `java.se.ee` đã bị loại bỏ khỏi JDK 11. Khi cần chức năng tương ứng, chọn dependency được duy trì và quản lý rõ trong build.
- Java Applet, Java Plug-in và Java Web Start thuộc deployment stack đã bị loại bỏ khỏi JDK 11. Không xây dựng cách phân phối ứng dụng mới dựa trên các công nghệ này.
- Nashorn và công cụ `jjs` đã bị loại bỏ khỏi JDK 15. Không dùng chúng làm JavaScript runtime cho hệ thống mới.
- CMS garbage collector và Pack200 tools/API đã bị loại bỏ khỏi JDK 14. Không cấu hình hoặc xây dựng pipeline phát hành mới dựa trên chúng.
- HTTP Client ở dạng incubator của Java 9 không phải API ổn định để giữ trong thiết kế hiện tại. Dùng API chuẩn `java.net.http.HttpClient` được chuẩn hóa từ Java 11 nếu cần HTTP client tích hợp trong JDK.

Khi bảo trì hệ thống cũ, trước tiên kiểm tra phiên bản JDK, dependency và migration guide để xác định đường chuyển đổi. Không sao chép nguyên cấu hình JVM, công cụ đóng gói hoặc API từ một bài hướng dẫn Java 9 cũ sang môi trường hiện tại.

## 5. Checklist trước khi đưa tính năng vào dự án

- [ ] Vấn đề cụ thể và kết quả mong muốn đã được mô tả.
- [ ] JDK mục tiêu còn được hỗ trợ và có API cần dùng.
- [ ] API không ở trạng thái deprecated for removal, removed hoặc incubator.
- [ ] Dependency, framework, build tool và môi trường triển khai tương thích.
- [ ] Cách đơn giản hơn đã được cân nhắc.
- [ ] Trường hợp biên, lỗi, timeout và khả năng hủy đã được kiểm thử khi liên quan.
- [ ] Hiệu năng chỉ được kết luận sau khi đo trên workload đại diện.
- [ ] Nhóm biết cách vận hành, cập nhật và bảo trì phần mới.
- [ ] Lý do chọn và giới hạn của tính năng được ghi lại.

## 6. Lỗi thường gặp

- **Dùng mọi API mới cùng lúc:** làm thay đổi quá nhiều thứ, khó xác định lợi ích và nguyên nhân lỗi. Chọn từng vấn đề, triển khai từng bước.
- **Nhầm collection không sửa được với bất biến sâu:** object bên trong vẫn có thể thay đổi. Nếu cần snapshot thực sự, phải kiểm soát cả object được chứa.
- **Dùng takeWhile như filter:** có thể làm mất các phần tử hợp lệ nằm sau phần tử đầu tiên không thỏa điều kiện.
- **Cho rằng timeout tự hủy tác vụ:** future có thể đã hoàn tất timeout trong khi thao tác I/O vẫn tiếp tục. Cấu hình timeout và cancellation ở tầng thực thi.
- **Chuyển sang JPMS không kiểm tra dependency:** có thể phát sinh lỗi truy cập reflection hoặc module không được resolve.
- **Tạo jlink image rồi quên cập nhật:** runtime image cần nhận các bản vá bảo mật như mọi runtime khác.
- **Đánh giá hiệu năng bằng cảm giác:** cú pháp ngắn hơn không đồng nghĩa chạy nhanh hơn; hãy đo trước khi tối ưu.

## 7. Tài liệu tham khảo

- [Java SE 25 API — List](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/List.html)
- [Java SE 25 API — Stream](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/Stream.html)
- [Java SE 25 API — CompletableFuture](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/CompletableFuture.html)
- [Java SE 25 API — Flow](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/Flow.html)
- [Java SE 25 — JAR File Specification](https://docs.oracle.com/en/java/javase/25/docs/specs/jar/jar.html)
- [Java SE 25 — jlink command](https://docs.oracle.com/en/java/javase/25/docs/specs/man/jlink.html)
- [Oracle JDK 26 Migration Guide — Removed tools and components](https://docs.oracle.com/en/java/javase/26/migrate/removed-tools-components.html)
- [JEP 261 — Module System](https://openjdk.org/jeps/261)
