# Chẩn đoán lỗi chưa triển khai phương thức và sai phạm vi truy cập trong Java

Khi một lớp implements interface hoặc extends lớp trừu tượng, trình biên dịch kiểm tra xem lớp đó có đáp ứng đầy đủ hợp đồng phương thức hay không. Hai nhóm lỗi thường gặp là **chưa triển khai phương thức trừu tượng** và **ghi đè phương thức với phạm vi truy cập quá hẹp**. Cách chẩn đoán hiệu quả là xác định phương thức nào còn thiếu, so khớp chữ ký phương thức, kiểm tra mức truy cập, rồi biên dịch lại sau mỗi lần sửa.

## 1. Lỗi chưa triển khai phương thức là gì?

Một interface có thể khai báo các phương thức mà lớp triển khai phải cung cấp. Ví dụ:

~~~java
interface Printer {
    void print(String message);
}
~~~

Một lớp concrete triển khai Printer phải cung cấp phương thức print với đúng tên, kiểu tham số và kiểu trả về tương thích. Nếu lớp không có phương thức phù hợp, Java thường báo lỗi dạng:

~~~text
PrinterImpl is not abstract and does not override abstract method print(String) in Printer
~~~

Tên lớp và nội dung thông báo chính xác phụ thuộc mã nguồn, nhưng ý nghĩa là: lớp PrinterImpl được khai báo là lớp cụ thể, trong khi vẫn còn phương thức trừu tượng cần triển khai.

Có hai hướng xử lý hợp lệ:

- **Triển khai phương thức còn thiếu** nếu lớp được thiết kế để tạo đối tượng và thực hiện hành vi đó.
- **Khai báo lớp là abstract** nếu lớp chỉ là lớp nền chưa thể hoàn thành toàn bộ hành vi và dự kiến lớp con sẽ triển khai phần còn lại.

Ví dụ lớp trừu tượng có thể để phương thức chưa triển khai:

~~~java
abstract class BasePrinter implements Printer {
    // Chưa triển khai print(String), nên lớp phải là abstract.
}
~~~

Lớp cụ thể kế thừa BasePrinter vẫn phải hoàn thiện print(String), trừ khi chính lớp con đó cũng được khai báo abstract.

## 2. Kiểm tra chữ ký phương thức trước khi thêm mã

Tên phương thức giống nhau chưa đủ để tạo ra một lần override. Cần so sánh ít nhất tên, danh sách kiểu tham số, kiểu trả về và quan hệ kế thừa. Với phương thức kế thừa, hãy kiểm tra cả generic, kiểu tham số, kiểu trả về tương thích và các quy tắc exception của Java.

Ví dụ dưới đây **cố ý không biên dịch**:

~~~java
interface Printer {
    void print(String message);
}

class ConsolePrinter implements Printer {
    public void print() {
        System.out.println("Hello");
    }
}
~~~

ConsolePrinter định nghĩa print() không có tham số. Đây là một phương thức khác, không triển khai print(String) của Printer. Vì thế lớp vẫn còn thiếu phương thức bắt buộc.

Cách sửa là dùng đúng chữ ký:

~~~java
interface Printer {
    void print(String message);
}

class ConsolePrinter implements Printer {
    @Override
    public void print(String message) {
        System.out.println(message);
    }
}
~~~

**@Override** giúp trình biên dịch xác minh ý định ghi đè. Nếu vô tình viết sai tên hoặc sai tham số, trình biên dịch sẽ báo rằng phương thức không ghi đè hay triển khai phương thức nào từ kiểu cha. Đây là tín hiệu hữu ích để phát hiện lỗi sớm.

### Phân biệt override và overload

- **Override**: lớp con cung cấp cách thực hiện mới cho một phương thức được kế thừa, với chữ ký tương thích.
- **Overload**: cùng tên nhưng có danh sách tham số khác nhau. Overload không thay thế phương thức trừu tượng đang thiếu.

Ví dụ print() và print(String) là hai overload khác nhau. Nếu interface yêu cầu print(String), chỉ có print() thì vẫn chưa đủ.

## 3. Vì sao sai phạm vi truy cập gây lỗi?

Java không cho phép phương thức ghi đè trở nên khó truy cập hơn so với phương thức được ghi đè. Quy tắc này bảo đảm mã gọi qua kiểu cha vẫn có thể gọi phương thức sau khi đối tượng được thay bằng một thể hiện của lớp con.

Xét interface:

~~~java
interface Sender {
    void send(String message);
}
~~~

Các phương thức thông thường được khai báo trong interface mà không có thân đều là public abstract ngầm định. Vì vậy, phương thức triển khai phải là public.

Đoạn dưới đây **cố ý không biên dịch**:

~~~java
class EmailSender implements Sender {
    @Override
    void send(String message) {
        System.out.println(message);
    }
}
~~~

Phương thức send không ghi public, nên mức truy cập mặc định của nó chỉ là package-private. Điều này làm giảm khả năng truy cập so với send(String) công khai của interface. Trình biên dịch thường đưa ra thông báo tương tự:

~~~text
attempting to assign weaker access privileges; was public
~~~

Cách sửa:

~~~java
class EmailSender implements Sender {
    @Override
    public void send(String message) {
        System.out.println(message);
    }
}
~~~

Khi triển khai interface, hãy khai báo public rõ ràng cho các phương thức triển khai, kể cả khi thân phương thức rất ngắn.

## 4. Quy tắc phạm vi khi override lớp thông thường hoặc lớp trừu tượng

Mức truy cập của phương thức ghi đè có thể được giữ nguyên hoặc mở rộng, nhưng không được thu hẹp. Bảng sau tóm tắt các mức truy cập:

| Phương thức ở lớp cha | Mức truy cập tối thiểu ở lớp con | Ghi chú |
|---|---|---|
| public | public | Không được đổi thành protected, package-private hoặc private |
| protected | protected hoặc public | Không được đổi thành package-private hoặc private |
| package-private | package-private hoặc rộng hơn, nếu thật sự override trong cùng package | Quan hệ package ảnh hưởng việc phương thức có được kế thừa và ghi đè hay không |
| private | Không override theo nghĩa đa hình | Phương thức private không được lớp con kế thừa; cùng tên ở lớp con là phương thức riêng |

Ví dụ sau **cố ý không biên dịch** vì lớp con thu hẹp protected thành private:

~~~java
abstract class BaseTask {
    protected abstract void execute();
}

class ReportTask extends BaseTask {
    @Override
    private void execute() {
        System.out.println("Generate report");
    }
}
~~~

Cách sửa là giữ protected hoặc mở rộng thành public:

~~~java
abstract class BaseTask {
    protected abstract void execute();
}

class ReportTask extends BaseTask {
    @Override
    protected void execute() {
        System.out.println("Generate report");
    }
}
~~~

Cũng cần nhớ rằng một phương thức private không thể là phương thức abstract vì lớp con không thể override nó. Phương thức abstract cũng không thể đồng thời là static hoặc final: static thuộc về lớp, final cấm override, còn abstract yêu cầu lớp con cung cấp phần thực hiện.

## 5. Ví dụ hoàn chỉnh chạy được

Ví dụ này kết hợp interface, lớp trừu tượng và lớp cụ thể. BaseChannel triển khai phương thức public send của interface và yêu cầu lớp con cung cấp phương thức format với mức truy cập protected. EmailChannel hoàn thiện phương thức còn thiếu bằng đúng chữ ký và mức truy cập.

Lưu mã vào tệp **AccessDiagnosticsDemo.java**:

~~~java
interface NotificationChannel {
    void send(String message);
}

abstract class BaseChannel implements NotificationChannel {
    protected abstract String format(String message);

    @Override
    public final void send(String message) {
        System.out.println(format(message));
    }
}

final class EmailChannel extends BaseChannel {
    @Override
    protected String format(String message) {
        return "[email] " + message.trim();
    }
}

public class AccessDiagnosticsDemo {
    public static void main(String[] args) {
        NotificationChannel channel = new EmailChannel();
        channel.send("  Xin chào  ");
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~text
javac AccessDiagnosticsDemo.java
java AccessDiagnosticsDemo
~~~

Kết quả stdout chính xác:

~~~text
[email] Xin chào
~~~

Điều gì làm ví dụ này hợp lệ?

1. NotificationChannel yêu cầu send(String) công khai. BaseChannel cung cấp phương thức public send nên đã triển khai hợp đồng interface.
2. BaseChannel khai báo format(String) là protected abstract. Vì BaseChannel là abstract nên có thể để phương thức này cho lớp con thực hiện.
3. EmailChannel triển khai format(String) bằng protected, đúng với mức truy cập ở lớp cha.
4. EmailChannel là lớp concrete và đã cung cấp phần thực hiện cho mọi phương thức abstract còn lại.
5. Biến channel có kiểu NotificationChannel nhưng đối tượng thật là EmailChannel. Lời gọi send vẫn hoạt động nhờ đa hình; mã gọi không cần biết lớp triển khai cụ thể.

## 6. Quy trình chẩn đoán khi javac báo lỗi

Khi gặp lỗi trong một dự án lớn, nên đi theo trình tự sau để tránh sửa sai chỗ:

1. **Đọc tên lớp và phương thức trong thông báo.** Tìm lớp bị báo là not abstract and does not override abstract method, sau đó tìm interface hoặc lớp cha khai báo phương thức đó.
2. **Kiểm tra lớp có phải concrete hay không.** Nếu lớp cần tạo instance, phải triển khai đủ các phương thức abstract. Nếu lớp chỉ là nền tảng chưa hoàn chỉnh, cân nhắc khai báo abstract.
3. **So khớp chữ ký.** So tên, kiểu và thứ tự tham số, kiểu trả về; kiểm tra generic hoặc import nếu hai kiểu có tên giống nhau nhưng thuộc package khác nhau.
4. **Thêm @Override.** Đặt annotation ngay trên phương thức dự định ghi đè để compiler kiểm tra ý định đó.
5. **Kiểm tra phạm vi truy cập.** Phương thức public của interface phải được triển khai public. Phương thức protected ở lớp cha không thể bị thu hẹp xuống private hoặc package-private.
6. **Kiểm tra các ràng buộc override khác.** Kiểu trả về phải tương thích; không thể ném thêm checked exception rộng hơn quy tắc cho phép; không thể override phương thức final. Nếu phương thức cha là private hoặc static, cần xác minh xem đây có thực sự là override hay chỉ là phương thức riêng/che khuất.
7. **Biên dịch lại và đọc lỗi đầu tiên có liên quan.** Một lỗi chữ ký có thể kéo theo nhiều thông báo khác. Sửa nguyên nhân gốc rồi biên dịch lại giúp giảm nhiễu.

Lệnh biên dịch tệp độc lập:

~~~text
javac AccessDiagnosticsDemo.java
~~~

Nếu dự án có nhiều package hoặc phụ thuộc bên ngoài, hãy dùng lệnh build chuẩn của dự án để compiler nhận đúng classpath và source path. Một lỗi “cannot find symbol” do thiếu classpath không giống lỗi chưa triển khai phương thức, nên cần phân loại thông báo trước khi sửa mã.

## 7. Những nhầm lẫn thường gặp

- **Bỏ public khi triển khai interface.** Phương thức trong interface là public theo mặc định nếu khai báo phương thức thông thường không có thân. Lớp triển khai phải giữ mức public.
- **Cho rằng cùng tên phương thức là đủ.** Khác danh sách tham số thường tạo overload, không phải override.
- **Khai báo lớp concrete nhưng để lại phương thức abstract.** Chuyển lớp thành abstract nếu đó là chủ đích; nếu không, hoàn thiện các phương thức còn thiếu.
- **Giảm protected xuống private trong lớp con.** Việc đó vi phạm hợp đồng truy cập của phương thức được override.
- **Xóa @Override để làm biến mất lỗi.** Xóa annotation không sửa chữ ký hoặc phạm vi truy cập; phương thức vẫn có thể không đáp ứng hợp đồng và compiler tiếp tục báo lỗi khác.
- **Sửa phương thức sai lớp.** Nếu lớp cha trừu tượng đã để phương thức cho lớp con thực hiện, hãy tìm đúng lớp concrete bị báo lỗi.
- **Nhầm private với protected.** Private chỉ truy cập trong chính lớp khai báo; protected cho phép truy cập trong package và theo quy tắc kế thừa. Chúng không thể thay thế nhau tùy ý khi override.

## 8. Cách ghi nhớ

Lỗi chưa triển khai phương thức nghĩa là lớp concrete chưa đáp ứng hợp đồng kế thừa. Lỗi sai phạm vi truy cập nghĩa là phương thức ghi đè làm hẹp quyền truy cập so với phương thức cha. Dùng @Override, so khớp chữ ký, kiểm tra lớp có phải abstract và bảo toàn mức truy cập sẽ giải quyết phần lớn trường hợp.

Khi đọc thông báo javac, hãy xác định lớp bị lỗi, tìm phương thức abstract gốc, đối chiếu chữ ký rồi kiểm tra mức truy cập. Sửa đúng nguyên nhân và chạy lại trình biên dịch để xác nhận lớp đã thực hiện đầy đủ hợp đồng.
