# Thêm abstract method và tác động tới các lớp triển khai cũ

## Mục tiêu

Khi thư viện thêm phương thức trừu tượng (`abstract method`) vào interface đã công bố, lớp triển khai cũ có thể không biên dịch lại được nếu không có implementation tương ứng. Bài học này tập trung vào cách tái hiện lỗi, điều kiện khiến bytecode cũ tiếp tục chạy hoặc phát sinh `AbstractMethodError`, và cách chọn phương án mở rộng hợp đồng phù hợp. Cần thử riêng khả năng biên dịch lại source, liên kết bytecode cũ và hành vi thực tế.

## 1. Ví dụ về thay đổi gây lỗi biên dịch

Giả sử phiên bản đầu của thư viện cung cấp interface sau:

```java
public interface ReportSink {
    void write(String text);
}
```

Một ứng dụng triển khai interface:

```java
public final class FileReportSink implements ReportSink {
    @Override
    public void write(String text) {
        System.out.println(text);
    }
}
```

Cả hai đoạn mã đều biên dịch. Sau đó, tác giả thư viện quyết định thêm thao tác `flush()` vào `ReportSink`:

```java
public interface ReportSink {
    void write(String text);
    void flush();
}
```

Khi biên dịch lại `FileReportSink` với interface mới, trình biên dịch báo lỗi vì lớp cụ thể chưa triển khai `flush()`. Cách sửa trực tiếp là bổ sung phương thức:

```java
@Override
public void flush() {
    // Đẩy dữ liệu đang đệm xuống đích lưu trữ.
}
```

Phần thân trên chỉ minh họa hình dạng của phương thức; trong một triển khai thực tế, nội dung phải thực hiện đúng hợp đồng lưu trữ. Nếu lớp không thể cung cấp hành vi đó, việc thêm một phương thức trừu tượng bắt buộc có thể là dấu hiệu API cần một thiết kế khác.

Một lớp trừu tượng triển khai `ReportSink` có thể chưa cài đặt `flush()` và vẫn biên dịch, vì lớp đó không hứa sẽ tạo được đối tượng trực tiếp. Tuy nhiên, các lớp cụ thể ở dưới nó vẫn cần có một triển khai phù hợp trước khi tạo đối tượng.

## 2. Source compatibility và binary compatibility

Việc thêm phương thức trừu tượng vào interface có hai tác động cần phân biệt.

| Tình huống | Kết quả thường gặp |
|---|---|
| Biên dịch lại một lớp cụ thể cũ với interface mới | Lỗi biên dịch nếu lớp không có phương thức mới và không kế thừa được một triển khai thích hợp |
| Chạy bytecode cũ, không gọi phương thức mới | Thường vẫn chạy; phương thức mới chưa được sử dụng |
| Gọi phương thức mới trên đối tượng của lớp cũ không có triển khai | Có thể phát sinh `AbstractMethodError` lúc chạy |
| Một lớp con đã có phương thức công khai tương thích với chữ ký mới | Phương thức đó có thể đáp ứng hợp đồng theo quy tắc của Java; vẫn cần kiểm tra ngữ nghĩa |
| Dùng một triển khai mặc định (`default method`) mới | Thường giữ khả năng tương thích nguồn và nhị phân tốt hơn, nhưng phải xét xung đột và thay đổi hành vi |

Theo quy tắc tương thích nhị phân của Java, thêm một phương thức trừu tượng vào interface không nhất thiết khiến mọi bytecode đã biên dịch trước đó ngừng chạy ngay lập tức. Một chương trình cũ có thể tiếp tục chạy nếu đường thực thi không cần phương thức mới. Nhưng nếu mã mới gọi phương thức ấy trên một lớp triển khai cũ không có phần cài đặt phù hợp, JVM có thể ném `AbstractMethodError`.

Vì vậy, **“bytecode cũ vẫn khởi chạy được” không có nghĩa “API thay đổi an toàn trong mọi trường hợp”**. Một thư viện có nhiều bên thứ ba triển khai interface nên xem việc thêm phương thức trừu tượng là thay đổi có rủi ro tương thích nguồn và rủi ro lỗi lúc chạy.

## 3. Thêm default method để có hành vi mặc định

Từ Java 8, interface có thể khai báo phương thức mặc định bằng từ khóa `default`. Phương thức này có phần thân, vì vậy lớp triển khai cũ có thể kế thừa hành vi đó mà không bắt buộc phải viết lại ngay.

Ví dụ hoàn chỉnh dưới đây mô phỏng API đã phát triển thêm một khả năng tùy chọn. Phiên bản cũ của `LegacyNotifier` chỉ cài đặt `send()`; interface mới cung cấp hành vi mặc định cho `supportsScheduling()`.

Lưu nội dung vào tệp `InterfaceEvolutionDemo.java`:

```java
public class InterfaceEvolutionDemo {
    public static void main(String[] args) {
        Notifier notifier = new LegacyNotifier();

        notifier.send("deploy complete");
        System.out.println("supports scheduling: "
                + notifier.supportsScheduling());
    }
}

interface Notifier {
    void send(String message);

    default boolean supportsScheduling() {
        return false;
    }
}

final class LegacyNotifier implements Notifier {
    @Override
    public void send(String message) {
        System.out.println("sent: " + message);
    }
}
```

Biên dịch và chạy bằng Java 17 trở lên:

```text
javac -encoding UTF-8 InterfaceEvolutionDemo.java
java InterfaceEvolutionDemo
```

Kết quả chuẩn:

```text
sent: deploy complete
supports scheduling: false
```

Lớp `LegacyNotifier` không khai báo `supportsScheduling()`, nhưng vẫn là một triển khai cụ thể hợp lệ vì interface đã cung cấp phần thân mặc định. Khi một loại notifier thực sự hỗ trợ lập lịch, lớp đó có thể ghi đè phương thức và trả về `true`.

Chỉ nên thêm `default` khi thư viện xác định được hành vi chung hợp lý cho mọi triển khai chưa ghi đè. Không nên tạo một phần thân giả chỉ để mã biên dịch, chẳng hạn luôn trả về thành công khi thao tác thực tế không được hỗ trợ. Một mặc định sai có thể giữ source compatibility nhưng phá behavioral compatibility.

## 4. Rủi ro khi thay abstract bằng default

Một default method có phần thân vẫn có thể xung đột với phương thức cùng chữ ký từ interface độc lập. Chẳng hạn, nếu `Printable` và `Exportable` cùng cung cấp `default String format()`, lớp `Document implements Printable, Exportable` phải ghi đè `format()` để xác định hành vi; compiler không chọn theo thứ tự liệt kê interface. Phương thức instance tương thích đã có ở lớp hoặc lớp cha có thể được ưu tiên, nhưng ý nghĩa của nó chưa chắc trùng hợp đồng mới.

Hãy kiểm tra những interface và lớp mà client thường kết hợp, kể cả implementation ở ngoài repository. Khi không có hành vi mặc định đúng cho mọi implementation, một interface năng lực riêng sẽ trung thực hơn việc cung cấp phần thân giả. Các quy tắc phân giải chi tiết và thí nghiệm về xung đột được triển khai trong bài chuyên về default method.

## 5. Khi nào nên chọn từng cách tiến hóa API?

| Nhu cầu | Lựa chọn thường phù hợp | Lý do |
|---|---|---|
| Mọi triển khai bắt buộc phải cung cấp một khả năng cốt lõi mới | Thêm abstract method, kèm kế hoạch chuyển đổi rõ ràng | Hợp đồng mới thật sự yêu cầu mọi triển khai hỗ trợ hành vi đó |
| Có hành vi mặc định đúng cho hầu hết triển khai | Thêm default method | Các lớp cũ có thể tiếp tục hoạt động mà không phải lập tức ghi đè |
| Chỉ một số loại triển khai có khả năng mới | Tạo interface năng lực riêng, ví dụ `SchedulableNotifier` | Không ép tất cả triển khai cũ giả vờ có khả năng mới |
| Muốn cung cấp một tiện ích không cần trạng thái đa hình mới | Cân nhắc phương thức `static` hoặc lớp tiện ích | Không bắt mọi lớp triển khai phải thay đổi |
| Có một hợp đồng mới khác đáng kể với hợp đồng cũ | Tạo abstraction mới hoặc adapter chuyển đổi | Làm rõ ranh giới tương thích và giúp khách hàng di chuyển có chủ đích |

Ví dụ, thay vì bắt tất cả notifier hỗ trợ lịch chạy, có thể khai báo:

```java
interface SchedulableNotifier extends Notifier {
    void schedule(String message, java.time.Instant when);
}
```

Chỉ những notifier thực sự hỗ trợ lịch chạy mới triển khai `SchedulableNotifier`. Khách hàng có thể kiểm tra năng lực đó bằng kiểu interface hoặc yêu cầu trực tiếp loại dịch vụ phù hợp. Cách này giữ interface cơ bản ổn định khi tính năng mới chỉ có ý nghĩa với một phần triển khai.

Phương thức `static` của interface thuộc về chính interface và không phải phương thức instance mà lớp triển khai cần cài đặt. Phương thức `private` của interface (có từ Java 9) hỗ trợ chia sẻ logic bên trong các default method; nó không tạo ra một yêu cầu mới cho lớp triển khai.

## 6. Quy trình thay đổi interface an toàn hơn

1. **Xác định hợp đồng mới:** ghi rõ phương thức dùng để làm gì, đầu vào hợp lệ, kết quả, lỗi và ảnh hưởng lên trạng thái.
2. **Kiểm kê bên triển khai:** tìm tất cả lớp trong cùng repository, module, plugin và các triển khai bên ngoài đã biết.
3. **Chọn loại phương thức:** dùng abstract method khi mọi triển khai bắt buộc phải đáp ứng; dùng default khi có hành vi mặc định đúng; dùng interface năng lực riêng khi chỉ một số triển khai hỗ trợ.
4. **Đánh giá ba loại tương thích:** thử biên dịch lại mã nguồn cũ, thử chạy bytecode đã biên dịch trước đó và kiểm tra xem hành vi cũ có bị đổi hay không.
5. **Kiểm thử các trường hợp thiếu triển khai:** đặc biệt nếu khách hàng có thể nâng thư viện độc lập với việc nâng ứng dụng.
6. **Ghi hướng dẫn di chuyển:** nếu không thể tránh việc bắt buộc cài đặt phương thức mới, công bố ví dụ triển khai, thời điểm thay đổi và lỗi có thể gặp.
7. **Kiểm tra xung đột default method:** thử các lớp kết hợp nhiều interface và xác nhận hành vi được chọn đúng như hợp đồng.

Không nên chỉ chạy test trong repository của thư viện rồi kết luận thay đổi an toàn. Bộ test nội bộ có thể đã cập nhật tất cả lớp triển khai cùng lúc, trong khi người dùng thư viện vẫn có những lớp cũ ở bên ngoài.

## Ghi nhớ

- Thêm abstract method vào interface thường làm mã nguồn của lớp cụ thể cũ không biên dịch khi biên dịch lại cho đến khi có triển khai phù hợp.
- Bytecode cũ có thể vẫn chạy nếu không gọi phương thức mới; lời gọi phương thức chưa có phần triển khai có thể dẫn đến `AbstractMethodError`.
- Default method là công cụ hữu ích khi có hành vi mặc định đúng, nhưng cần kiểm tra xung đột chữ ký và thay đổi hành vi.
- Nếu khả năng mới chỉ áp dụng cho một số triển khai, interface năng lực riêng thường biểu đạt hợp đồng tốt hơn việc bắt mọi lớp triển khai một phương thức trừu tượng mới.
- Đánh giá source, binary và behavioral compatibility riêng biệt trước khi phát hành phiên bản API mới.