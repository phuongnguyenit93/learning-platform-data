# Kết thúc phiên, EOF và đóng ApplicationContext

Một ứng dụng Spring Shell có thể dừng theo nhiều cách: người dùng gõ `quit`, terminal báo hết dữ liệu đầu vào (EOF), runner được yêu cầu dừng hoặc Spring `ApplicationContext` được đóng. Những sự kiện này có liên quan nhưng không đồng nghĩa.

Phân biệt đúng từng tầng giúp ứng dụng giải phóng kết nối, file, terminal và các tài nguyên khác một cách có kiểm soát. Đặc biệt, việc vòng lặp shell kết thúc chưa chắc đồng nghĩa tiến trình JVM đã thoát; các thread nền vẫn có thể giữ ứng dụng hoạt động.

Bài này sử dụng mô hình runner và cấu hình Spring Shell 4.x, với ví dụ theo tài liệu 4.0.4.

## 1. Bốn khái niệm cần phân biệt

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| Shell loop kết thúc | Runner không tiếp tục đọc và thực thi command | Người dùng gõ `quit`, hoặc input provider trả EOF |
| Runner dừng | Vòng thực thi do `ShellRunner` điều khiển nhận yêu cầu dừng | Gọi `InteractiveShellRunner.stop()` |
| ApplicationContext đóng | Spring ngừng quản lý bean, phát sự kiện đóng và chạy destruction callbacks | `quit`, `spring.shell.context.close=true`, hoặc Spring Boot shutdown hook |
| JVM/process kết thúc | Tiến trình Java dừng; hệ điều hành thu hồi tài nguyên tiến trình | Không còn non-daemon thread hoặc ứng dụng chủ động kết thúc |

Có thể hình dung quan hệ như sau:

```text
Người dùng gõ quit / input provider gặp EOF
                    |
                    v
             Shell loop kết thúc
                    |
                    v
         Shell execution hoàn tất
                    |
          +---------+----------+
          |                    |
          v                    v
 context được yêu cầu       JVM còn thread
 đóng (nếu cấu hình)        non-daemon khác?
          |                    |
          v                    v
 destruction callbacks     tiến trình tiếp tục
          |                hoặc kết thúc khi hết thread
          v                    |
          +---------+----------+
                    v
              Process kết thúc
```

Sơ đồ thể hiện các mốc thường gặp trong ứng dụng Spring Boot. Một ứng dụng tùy biến runner, lifecycle hoặc thread có thể có luồng kết thúc khác; hãy kiểm tra cấu hình thực tế của dự án.

## 2. Kết thúc phiên bằng `quit` hoặc `exit`

Spring Shell cung cấp built-in command `quit`; `exit` là alias của command này. Trong interactive shell, người dùng có thể nhập:

```text
shell:>quit
```

Hoặc:

```text
shell:>exit
```

Theo tài liệu Spring Shell, `quit` yêu cầu shell thoát và đóng Spring application context một cách graceful. Khi context đóng, Spring thực hiện quy trình hủy bean để các thành phần quản lý tài nguyên có cơ hội dọn dẹp.

Nếu ứng dụng dùng JLine và không tùy chỉnh history, bean `History` có thể ghi lịch sử command xuống đĩa để dùng ở lần khởi động tiếp theo. Đây là một phần hành vi liên quan đến lifecycle của cấu hình JLine; không nên giả định mọi ứng dụng đều bật history hoặc ghi cùng một vị trí.

`quit` là cách thoát rõ ràng dành cho người dùng interactive. Trong non-interactive mode, ứng dụng thường chạy command hoặc script rồi hoàn tất runner; một command thoát tương tác không có cùng ý nghĩa trong chế độ này.

## 3. EOF là gì?

EOF là viết tắt của *End Of File* hoặc *end of input*. Nó báo cho chương trình rằng nguồn input hiện tại không còn dữ liệu để đọc. EOF không phải một chuỗi command và cũng không phải một dòng trống.

Trong Spring Shell 4, `InputProvider.readInput()` trả về `null` khi đã đến cuối input. API mô tả rõ rằng `null` biểu thị end of input. Vòng lặp interactive shell coi tín hiệu này là yêu cầu kết thúc shell.

Có ba trường hợp khác nhau:

| Tình huống | Dữ liệu/ý nghĩa | Kết quả |
|---|---|---|
| Người dùng nhấn Enter trên dòng trống | Một dòng input rỗng | Không phải EOF; shell vẫn tiếp tục phiên |
| Người dùng nhập `quit` | Một command hợp lệ | Built-in command yêu cầu shell thoát và đóng context |
| Input provider trả `null` | Không còn dữ liệu đầu vào | Shell loop dừng vì EOF |

Không xử lý chuỗi rỗng như EOF. Nếu tự triển khai `InputProvider`, chỉ trả `null` khi nguồn input thực sự kết thúc; không trả `null` cho dòng trống hoặc dòng chỉ chứa khoảng trắng.

## 4. EOF trong terminal tương tác

Phím tạo EOF phụ thuộc terminal, hệ điều hành và cách input được kết nối. Trên nhiều terminal kiểu Unix, `Ctrl+D` tại đầu dòng gửi EOF. Với Windows console, tổ hợp thường gặp là `Ctrl+Z` rồi Enter. Một số terminal IDE, terminal nhúng hoặc môi trường remote có thể xử lý khác.

Điểm quan trọng là Spring Shell nhận kết quả từ input provider. Khi provider báo hết input bằng `null`, runner kết thúc vòng đọc lệnh. Spring Shell không cần nhận một command tên là `EOF`.

Nếu nhấn tổ hợp EOF khi dòng đang có nội dung, hành vi có thể phụ thuộc line editor và terminal. Hãy thử ở một dòng trống trong terminal đích và xác nhận hành vi của JLine hoặc system console mà ứng dụng đang dùng.

### EOF không giống Ctrl+C

`Ctrl+C` thường gửi tín hiệu ngắt (interrupt) tới tiến trình hoặc terminal foreground process. Nó không phải quy ước `InputProvider.readInput() == null`. Cách JVM, terminal và ứng dụng xử lý interrupt phụ thuộc môi trường và signal handler.

Nếu cần kết thúc bình thường, ưu tiên `quit` hoặc gửi EOF theo đúng cách terminal hỗ trợ. Không dựa vào `Ctrl+C` như một thay thế cho quy trình cleanup đã thiết kế.

## 5. EOF từ pipe, file hoặc input provider tùy chỉnh

EOF không chỉ xuất hiện khi người dùng nhấn phím. Một input provider có thể đọc từ file, pipe, socket hoặc nguồn dữ liệu khác. Khi nguồn đọc không còn dữ liệu, provider trả `null` và shell loop kết thúc.

Trong Spring Shell 4, `InputProvider.readInput()` trả về `String` và có thể ném exception. Một implementation đọc dòng từ `BufferedReader` có thể trả trực tiếp kết quả của `readLine()`:

```java
import java.io.BufferedReader;
import java.io.IOException;

import org.springframework.shell.core.InputProvider;

class ReaderInputProvider implements InputProvider {

    private final BufferedReader reader;

    ReaderInputProvider(BufferedReader reader) {
        this.reader = reader;
    }

    @Override
    public String readInput() throws IOException {
        // readLine() trả null khi nguồn đã hết dữ liệu.
        return reader.readLine();
    }
}
```

Ví dụ trên minh họa hợp đồng EOF. Trong ứng dụng thực tế, cần quyết định rõ ai sở hữu và đóng `BufferedReader`; không đóng một stream do thành phần khác quản lý.

Với nguồn input dạng file, khi đọc hết file, provider phải báo EOF để runner dừng. Với nguồn có thể tiếp tục nhận dữ liệu như socket hoặc stream lâu dài, việc đóng kết nối và báo EOF cần theo giao thức của nguồn đó.

## 6. EOF kết thúc shell loop, không tự quyết định mọi thứ về JVM

Khi input provider trả `null`, shell loop kết thúc. Nhưng việc JVM có kết thúc ngay hay không còn phụ thuộc vòng đời ứng dụng.

Trong ứng dụng Spring Boot, Spring Shell chạy logic command thông qua bean `ApplicationRunner`. Khi runner hoàn tất, JVM có thể thoát nếu không còn non-daemon thread giữ tiến trình sống. Khi JVM shutdown, Spring Boot shutdown hook đóng application context.

Nếu ứng dụng có thread nền, scheduler, executor hoặc một thành phần khác giữ non-daemon thread hoạt động, tiến trình có thể vẫn tồn tại sau khi shell loop kết thúc. Trong tình huống này, người dùng có thể không còn prompt nhưng ứng dụng vẫn chưa dừng.

Ví dụ các nguồn có thể giữ ứng dụng hoạt động:

- `@EnableScheduling` với scheduler thread còn chạy.
- `ExecutorService` chưa shutdown.
- Thread nền do thư viện kết nối hoặc tác vụ định kỳ tạo ra.
- Một server hoặc listener khác được khởi động trong cùng application context.

Hãy xác định thread nào cần tồn tại sau khi shell kết thúc. Nếu ứng dụng chỉ là CLI chạy một lần, các executor và kết nối cần có lifecycle rõ ràng để không giữ JVM sống ngoài ý muốn.

## 7. Cấu hình `spring.shell.context.close`

Spring Shell cung cấp thuộc tính:

```yaml
spring:
  shell:
    context:
      close: true
```

Thuộc tính `spring.shell.context.close` mặc định là `false`. Khi bật, Spring Shell đăng ký listener cho `ApplicationReadyEvent` và yêu cầu đóng `ApplicationContext` sau khi shell hoàn tất logic thực thi.

Thiết lập này hữu ích khi runner đã hoàn tất nhưng các thread nền hoặc bean khác có thể khiến JVM tiếp tục chạy. Đóng context sẽ bắt đầu quy trình shutdown của các bean do context quản lý.

Ví dụ file `application.yml` cho một CLI chạy tác vụ rồi kết thúc:

```yaml
spring:
  shell:
    interactive:
      enabled: false
    context:
      close: true
```

Trong ví dụ này:

- `interactive.enabled: false` chọn `NonInteractiveShellRunner`.
- Runner thực thi command được truyền khi khởi động.
- Khi shell execution hoàn tất, `context.close: true` yêu cầu Spring đóng application context.

Không bật thuộc tính này một cách máy móc cho ứng dụng có chủ đích chạy lâu dài sau khi shell kết thúc, ví dụ ứng dụng CLI đồng thời cung cấp một server hoặc listener. Đóng context sẽ hủy các bean và tài nguyên thuộc context đó.

## 8. Đóng ApplicationContext có nghĩa gì?

`ApplicationContext` là container quản lý bean, dependency và lifecycle của ứng dụng Spring. Khi context đóng, Spring phát sự kiện đóng và thực hiện các destruction callbacks đã đăng ký cho bean singleton.

Các cơ chế cleanup thường dùng:

- `@PreDestroy` trên method cần chạy khi bean bị hủy.
- `DisposableBean.destroy()` nếu bean triển khai interface này.
- `destroyMethod` của `@Bean` để chỉ định method đóng tài nguyên.
- Callback hủy được framework hoặc thư viện đăng ký khi tạo bean.

Ví dụ:

```java
import jakarta.annotation.PreDestroy;
import org.springframework.stereotype.Component;

@Component
class ConnectionManager {

    private RemoteConnection connection;

    @PreDestroy
    void closeConnection() {
        if (connection != null) {
            connection.close();
            connection = null;
        }
    }
}
```

`RemoteConnection` là kiểu minh họa cho tài nguyên kết nối của ứng dụng. Trong code thực tế, hãy dùng API close tương ứng và xử lý exception theo hợp đồng của thư viện.

Nếu tài nguyên được tạo bởi một `@Bean`, có thể chỉ định destroy method:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class ClientConfiguration {

    @Bean(destroyMethod = "close")
    RemoteClient remoteClient() {
        return new RemoteClient();
    }
}
```

Spring gọi callback hủy khi context quản lý bean được đóng. Hãy để container sở hữu lifecycle của tài nguyên; tránh đóng cùng một tài nguyên ở nhiều nơi nếu không có quy ước ownership rõ ràng.

## 9. Runner dừng không đồng nghĩa context đóng

`InteractiveShellRunner` có phương thức `stop()` để báo runner dừng và chờ trong thời gian ngắn cho thread của runner kết thúc. API cũng có cơ chế đánh thức thao tác `InputProvider.readInput()` đang chờ.

Đây là thao tác điều khiển runner. Bản thân việc gọi `stop()` không phải một lệnh đóng `ApplicationContext`. Nếu ứng dụng quản lý runner theo cách tùy chỉnh, cần thiết kế riêng trình tự dừng runner, đóng input provider và đóng context.

Thông thường, ứng dụng Spring Boot để `springShellApplicationRunner` điều phối runner và dùng built-in `quit` cho thao tác thoát của người dùng. Chỉ tùy biến `stop()` khi ứng dụng thực sự cần điều khiển runner từ một thành phần khác.

## 10. Trình tự shutdown nên được thiết kế rõ

Một ứng dụng CLI có thể sở hữu nhiều loại tài nguyên: kết nối mạng, file, executor, terminal, temporary directory và state trong bộ nhớ. Khi kết thúc, hãy xác định ai chịu trách nhiệm đóng từng tài nguyên.

Một trình tự thường dùng:

1. Ngừng nhận command hoặc yêu cầu runner kết thúc.
2. Ngừng nhận công việc mới từ các thành phần nền.
3. Chờ tác vụ đang chạy hoàn tất trong thời gian cho phép.
4. Đóng kết nối, stream, executor và tài nguyên do bean quản lý.
5. Để Spring đóng `ApplicationContext` và chạy destruction callbacks.
6. Xác nhận tiến trình kết thúc và trả mã thoát phù hợp.

Không phải ứng dụng nào cũng cần tự viết toàn bộ các bước này. Với CLI đơn giản, `quit` và lifecycle mặc định của Spring Boot thường đủ. Với ứng dụng có thread nền hoặc tài nguyên dài hạn, hãy cấu hình shutdown rõ ràng và kiểm thử.

## 11. Tránh kết thúc tiến trình bằng cách bỏ qua lifecycle

Không gọi `Runtime.getRuntime().halt(...)` trong command thông thường. `halt` dừng JVM ngay lập tức và bỏ qua shutdown hooks, vì vậy Spring có thể không có cơ hội chạy cleanup.

Tránh gọi `System.exit(...)` từ method command như một cách thay thế cho `quit`. `System.exit` khởi động JVM shutdown sequence, nhưng việc đặt lệnh thoát sâu trong nghiệp vụ làm command khó kiểm thử và khó tái sử dụng. Hãy để runner và application lifecycle điều phối việc kết thúc; nếu cần mã thoát, dùng cơ chế exit code phù hợp với Spring Boot và kiểm thử ở cấp tiến trình.

Không đóng trực tiếp `ApplicationContext` từ một command thông thường nếu command đó chỉ cần yêu cầu shell thoát. Dùng `quit` cho interactive shell hoặc cấu hình lifecycle phù hợp cho non-interactive execution.

## 12. Lịch sử command và tài nguyên terminal

Nếu ứng dụng dùng JLine, terminal và history có lifecycle riêng. Spring Shell auto-configuration có thể đăng ký các bean liên quan để giải phóng terminal khi context đóng. Không nên tự tạo một terminal thứ hai hoặc đóng terminal do Spring quản lý từ code command.

History cũng là dữ liệu cần được xử lý đúng. Built-in `quit` mô tả việc ghi lịch sử command qua JLine `History` bean nếu bean này được cấu hình và không bị thay thế. Không ghi token, mật khẩu hoặc dữ liệu nhạy cảm vào command history; nếu command nhận bí mật qua option, hãy cân nhắc cách nhập an toàn và cấu hình history phù hợp.

## 13. Kiểm thử kết thúc phiên và cleanup

Kiểm thử một command trả kết quả thành công chưa đủ để xác nhận lifecycle. Hãy kiểm tra cả shell loop, context và process.

| Kịch bản | Điều cần xác nhận |
|---|---|
| Gõ `quit` | Interactive shell thoát và context được yêu cầu đóng graceful |
| Gõ `exit` | Alias có cùng hành vi với `quit` |
| Nhấn Enter trên dòng trống | Shell không nhầm dòng trống với EOF |
| Input provider trả `null` | Shell loop dừng vì EOF |
| Dùng `spring.shell.context.close=true` | Context đóng sau khi shell hoàn tất execution logic |
| Có scheduler hoặc executor nền | Xác định tiến trình có còn sống sau khi runner kết thúc không |
| Context đóng | `@PreDestroy`/destroy method giải phóng tài nguyên |
| Dùng JLine | Terminal và history được xử lý theo cấu hình thực tế |
| Lỗi khi cleanup | Có log/chẩn đoán đủ để tìm tài nguyên không được đóng |

Ví dụ bean dùng để kiểm tra callback trong integration test:

```java
import jakarta.annotation.PreDestroy;
import org.springframework.stereotype.Component;

@Component
class LifecycleProbe {

    private boolean destroyed;

    @PreDestroy
    void onDestroy() {
        destroyed = true;
    }

    boolean isDestroyed() {
        return destroyed;
    }
}
```

Trong test, lấy bean trước khi đóng context, gọi `context.close()`, rồi xác nhận callback đã chạy. Nếu kiểm tra process exit hoặc shutdown hook, dùng integration test chạy ứng dụng trong process riêng; không gọi `System.exit` bên trong test JVM.

## 14. Bài tập thực hành

Xây dựng CLI quản lý kết nối tới một máy chủ từ xa. Ứng dụng có command `remote connect`, `remote status`, `remote disconnect` và built-in `quit`.

Hãy thực hiện:

1. Tạo `ConnectionManager` singleton giữ kết nối và đóng kết nối trong `@PreDestroy`.
2. Chạy ứng dụng ở interactive mode; gọi `connect`, `status`, `disconnect` rồi `quit`.
3. Gọi `exit` để xác nhận alias của `quit`.
4. Thử EOF trong terminal đích khi dòng nhập trống; ghi lại shell loop kết thúc như thế nào.
5. Tạo một `InputProvider` đọc từ `BufferedReader`; xác nhận `readLine()` trả `null` làm shell kết thúc.
6. Thêm một executor nền có thread non-daemon và quan sát tiến trình sau khi shell loop kết thúc.
7. Thử `spring.shell.context.close=true`; xác nhận `@PreDestroy` được gọi sau khi shell hoàn tất.
8. So sánh trường hợp context close mặc định với trường hợp bật thuộc tính.
9. Kiểm tra terminal/history khi dùng JLine và bảo đảm không ghi dữ liệu bí mật vào history.

**Kết quả cần nộp:** sơ đồ lifecycle, log của `quit`/EOF/context close, kết quả callback cleanup và giải thích vì sao runner kết thúc không luôn đồng nghĩa JVM đã thoát.

## 15. Checklist trước khi phát hành CLI

- [ ] Đã phân biệt `quit`/`exit`, EOF, runner stop, context close và process exit.
- [ ] Built-in `quit`/`exit` hoạt động đúng trong interactive mode.
- [ ] Input provider trả `null` chỉ khi nguồn input kết thúc.
- [ ] Dòng trống không bị xem nhầm là EOF.
- [ ] Đã thử EOF trên terminal và môi trường triển khai thực tế.
- [ ] Đã xác định hành vi của `spring.shell.context.close` và giá trị mặc định `false`.
- [ ] Đã xác định thread nền nào có thể giữ JVM sống sau khi runner kết thúc.
- [ ] Các singleton bean giải phóng tài nguyên bằng destruction callback phù hợp.
- [ ] Không đóng tài nguyên do Spring quản lý từ nhiều nơi không có ownership rõ ràng.
- [ ] Không dùng `Runtime.halt` hoặc `System.exit` trong command nghiệp vụ.
- [ ] Đã kiểm thử cleanup khi thoát bình thường, EOF và lỗi.
- [ ] Không lưu bí mật trong history hoặc thông báo shutdown.

## Tài liệu tham khảo

- [Spring Shell Reference — Exit](https://docs.spring.io/spring-shell/reference/commands/builtin/exit.html)
- [Spring Shell Reference — Context Close](https://docs.spring.io/spring-shell/reference/customization/contextclose.html)
- [Spring Shell Reference — Execution](https://docs.spring.io/spring-shell/reference/execution.html)
- [Spring Shell API — `InputProvider`](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/InputProvider.html)
- [Spring Shell API — `InteractiveShellRunner`](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/InteractiveShellRunner.html)
- [Spring Shell API — `ShellRunner`](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/ShellRunner.html)
- [Spring Framework Reference — Bean Scopes and Lifecycle](https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html)
- [Spring Framework Reference — Lifecycle Callbacks](https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html#beans-factory-lifecycle)
