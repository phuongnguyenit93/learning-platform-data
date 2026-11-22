# Hook method, phương thức final và bảo vệ bất biến

## Mục tiêu

Sau bài này, bạn có thể phân biệt hook method với phương thức trừu tượng, giải thích cách Template Method giữ cố định thứ tự xử lý, dùng `final` để ngăn lớp con thay đổi quy trình quan trọng, và nhận biết vì sao `final` một mình chưa đủ để bảo vệ mọi bất biến của đối tượng.

## 1. Hook method là gì?

**Hook method** là phương thức trong lớp cha cung cấp một điểm mở rộng cho lớp con. Lớp cha thường định nghĩa sẵn hành vi mặc định; lớp con có thể ghi đè khi cần thay đổi một bước tùy chọn. Nếu lớp con không ghi đè, quy trình vẫn chạy bằng hành vi mặc định.

Ví dụ đơn giản:

~~~java
abstract class Report {
    public final void print() {
        String content = createContent();
        String decorated = decorate(content);
        System.out.println(decorated);
    }

    protected abstract String createContent();

    protected String decorate(String content) {
        return content;
    }
}
~~~

Trong ví dụ này, `createContent()` là một thao tác trừu tượng mà lớp con bắt buộc phải triển khai để lớp cụ thể có thể được tạo. `decorate()` là hook có hành vi mặc định: nếu không ghi đè, nội dung được giữ nguyên. Lớp con có thể tùy chọn thêm tiêu đề, dấu phân cách hoặc phần trang trí.

Hook nên thể hiện một điểm mở rộng có chủ đích. Tránh tạo quá nhiều hook khiến người triển khai khó hiểu thứ tự chạy, hoặc cho phép lớp con thay đổi những bước phải luôn đúng để duy trì trạng thái hợp lệ.

## 2. Template Method và phương thức final

**Template Method** là mẫu thiết kế trong đó lớp cha định nghĩa khung thuật toán và thứ tự các bước; một số bước được lớp con cung cấp hoặc tùy biến. Một cách phổ biến để giữ cố định khung đó là khai báo phương thức điều phối bằng `final`.

~~~java
abstract class Importer {
    public final void importData(String source) {
        validateSource(source);
        String data = read(source);
        String normalized = normalize(data);
        save(normalized);
        afterImport(normalized);
    }

    private void validateSource(String source) {
        if (source == null || source.isBlank()) {
            throw new IllegalArgumentException("source must not be blank");
        }
    }

    protected abstract String read(String source);

    protected String normalize(String data) {
        return data.trim();
    }

    protected abstract void save(String data);

    protected void afterImport(String data) {
        // Hook tùy chọn: mặc định không làm gì.
    }
}
~~~

Phương thức `importData()` là Template Method. Nó luôn thực hiện kiểm tra nguồn, đọc dữ liệu, chuẩn hóa, lưu dữ liệu rồi mới gọi hook sau khi nhập. Lớp con có thể cung cấp cách đọc và lưu phù hợp với định dạng hoặc hệ thống cụ thể; lớp con cũng có thể ghi đè `normalize()` hoặc `afterImport()` khi cần.

Từ khóa `final` ngăn lớp con ghi đè `importData()`, vì vậy lớp con không thể thay thế toàn bộ thứ tự điều phối bằng một thuật toán khác. Tuy nhiên, các phương thức có thể ghi đè mà Template Method gọi bên trong vẫn dùng cơ chế dispatch động. Khi chạy `importData()` trên đối tượng lớp con, Java sẽ gọi phiên bản `read()`, `normalize()`, `save()` hoặc `afterImport()` tương ứng với đối tượng đó.

Đây là sự kết hợp có chủ đích: **quy trình tổng thể được giữ cố định, còn các bước mở rộng được tùy biến trong giới hạn đã thiết kế**.

## 3. Ví dụ Java 17 chạy được

Ví dụ sau tạo một bộ xuất báo cáo. Phương thức `export()` là Template Method và được khai báo `final`. Các hook có thể tùy biến bước chuẩn bị và phần chân trang; bước định dạng là thao tác trừu tượng bắt buộc. Phương thức điều phối kiểm tra dữ liệu trước và sau mỗi điểm mở rộng có thể trả về kết quả.

Lưu toàn bộ mã trong tệp `TemplateMethodInvariantDemo.java`:

~~~java
import java.util.Locale;

abstract class ReportExporter {
    public final String export(String raw) {
        String input = requireNonBlank(raw, "raw input");
        String prepared = requireNonBlank(prepare(input), "prepared text");
        String body = requireNonBlank(format(prepared), "formatted body");
        return requireNonBlank(addFooter(body), "final output");
    }

    private static String requireNonBlank(String value, String name) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(name + " must not be blank");
        }
        return value;
    }

    protected String prepare(String input) {
        return input.trim();
    }

    protected abstract String format(String prepared);

    protected String addFooter(String body) {
        return body;
    }
}

final class PlainTextExporter extends ReportExporter {
    @Override
    protected String format(String prepared) {
        return "REPORT: " + prepared.toUpperCase(Locale.ROOT);
    }

    @Override
    protected String addFooter(String body) {
        return body + "\n-- end --";
    }
}

public class TemplateMethodInvariantDemo {
    public static void main(String[] args) {
        ReportExporter exporter = new PlainTextExporter();
        System.out.println(exporter.export("  hello Java  "));

        try {
            exporter.export("   ");
        } catch (IllegalArgumentException ex) {
            System.out.println(ex.getMessage());
        }
    }
}
~~~

Biên dịch và chạy bằng Java 17 trở lên:

~~~text
javac TemplateMethodInvariantDemo.java
java TemplateMethodInvariantDemo
~~~

Kết quả stdout chính xác:

~~~text
REPORT: HELLO JAVA
-- end --
raw input must not be blank
~~~

Luồng xử lý của lần gọi đầu tiên là:

1. Kiểm tra đầu vào ban đầu.
2. Gọi hook `prepare()`; hành vi mặc định loại bỏ khoảng trắng ở hai đầu.
3. Gọi thao tác `format()` do lớp con triển khai.
4. Gọi hook `addFooter()`; lớp con thêm dòng kết thúc.
5. Trả về chuỗi đã được kiểm tra.

Lần gọi thứ hai bị từ chối ngay ở bước kiểm tra đầu vào. Nếu một lớp con ghi đè `prepare()`, `format()` hoặc `addFooter()` để trả về `null` hay chuỗi chỉ có khoảng trắng, bước kiểm tra kế tiếp sẽ từ chối kết quả đó. Lớp con vẫn tùy biến được hành vi, nhưng không thể bỏ qua chuỗi kiểm tra bằng cách ghi đè `export()`.

## 4. `final` bảo vệ được gì?

Trong Java, `final` có ý nghĩa tùy theo vị trí khai báo:

| Cách dùng | Ý nghĩa |
|---|---|
| `final class A` | Không thể tạo lớp con kế thừa `A`. |
| `final void run()` | Lớp con không thể ghi đè phương thức instance `run()`. |
| `final int limit = 10` | Biến chỉ có thể được gán một lần. Với biến tham chiếu, `final` khóa việc gán lại tham chiếu, không tự làm đối tượng được tham chiếu trở nên bất biến. |

Phương thức `final` hữu ích khi lớp cha phải duy trì một giao thức ổn định, chẳng hạn kiểm tra đầu vào trước khi xử lý, thực hiện bước cập nhật trạng thái, rồi kiểm tra kết quả trước khi trả về. Lớp con không thể ghi đè phương thức đó để đảo thứ tự hoặc bỏ qua các kiểm tra được đặt trực tiếp trong phương thức.

Tuy nhiên, `final` **không tự động làm mọi hành vi bên trong phương thức bất biến**. Nếu phương thức `final` gọi một hook có thể ghi đè, hook vẫn có thể thực hiện hành vi riêng, phát sinh ngoại lệ hoặc gây tác dụng phụ. Vì vậy, hãy đặt các kiểm tra quan trọng trong mã không thể bị ghi đè, giới hạn trạng thái có thể truy cập từ lớp con và xác thực kết quả sau các điểm mở rộng.

Không thể khai báo cùng một phương thức vừa `abstract` vừa `final`: `abstract` yêu cầu lớp con cung cấp phần triển khai, trong khi `final` cấm ghi đè. Nếu cần bắt buộc lớp con triển khai một bước, dùng phương thức trừu tượng; nếu cần giữ nguyên bước điều phối, dùng phương thức `final` gọi thao tác trừu tượng đó.

## 5. Bảo vệ bất biến của đối tượng

**Bất biến (invariant)** là điều kiện phải luôn đúng đối với trạng thái hợp lệ của một đối tượng, tại những thời điểm đối tượng được xem là ổn định và có thể được sử dụng. Ví dụ, một tài khoản có thể yêu cầu số dư không âm; một bộ đếm có thể yêu cầu giá trị không nhỏ hơn 0; một đối tượng cấu hình có thể yêu cầu tên không được để trống.

Để bảo vệ bất biến trong thiết kế có kế thừa:

- **Ẩn trạng thái:** ưu tiên trường `private`; không cho lớp con sửa trực tiếp các trường đại diện cho bất biến.
- **Kiểm tra tại ranh giới:** xác thực dữ liệu đầu vào trước khi cập nhật và xác thực kết quả trước khi công bố.
- **Giữ thao tác quan trọng ổn định:** cân nhắc dùng phương thức `final` cho thao tác công khai nếu lớp con không được phép thay đổi giao thức của nó.
- **Thiết kế hook hẹp:** chỉ mở rộng những bước thực sự cần tùy biến. Tránh truyền cho hook quyền sửa trực tiếp trạng thái nội bộ.
- **Không trả về trạng thái có thể bị sửa ngoài ý muốn:** dùng kiểu bất biến hoặc bản sao phòng vệ khi cần; khai báo một tham chiếu là `final` không làm đối tượng phía sau tham chiếu tự động bất biến.
- **Xác thực sau khi gọi mã mở rộng:** nếu hook trả về dữ liệu, hãy kiểm tra dữ liệu đó trước khi dùng hoặc trả cho caller.

Một phương thức `final` không thể tự bảo vệ trường `public` bị thay đổi trực tiếp, một đối tượng mutable được trả ra ngoài hoặc trạng thái bị làm sai bởi tác dụng phụ của hook. Bất biến được bảo vệ tốt nhất bằng nhiều lớp: đóng gói trạng thái, kiểm tra dữ liệu, hạn chế điểm mở rộng và điều phối thao tác theo thứ tự rõ ràng.

## 6. Constructor và lời gọi phương thức có thể ghi đè

Một cạm bẫy quan trọng là gọi phương thức có thể ghi đè từ constructor của lớp cha. Java có thể dispatch đến phiên bản ghi đè trong lớp con ngay cả khi constructor của lớp con chưa chạy xong. Khi đó, phương thức ghi đè có thể đọc trường lớp con chưa được khởi tạo đầy đủ và quan sát trạng thái chưa hợp lệ.

Ví dụ minh họa lỗi thiết kế:

~~~java
class BaseConfig {
    BaseConfig() {
        initialize(); // Không nên gọi hook có thể ghi đè ở đây.
    }

    protected void initialize() {
    }
}

class AppConfig extends BaseConfig {
    private String endpoint = "https://example.invalid";

    @Override
    protected void initialize() {
        System.out.println(endpoint.length());
    }
}
~~~

Trong lúc constructor của `BaseConfig` gọi `initialize()`, phiên bản ghi đè trong `AppConfig` có thể được gọi trước khi phần khởi tạo trường `endpoint` của lớp con hoàn tất. Trường có thể vẫn là `null`, dẫn đến `NullPointerException`. Vì vậy, tránh gọi các phương thức có thể ghi đè từ constructor; hãy hoàn tất việc khởi tạo trước rồi mới gọi các điểm mở rộng.

Đoạn mã trên chỉ là ví dụ minh họa lỗi và không phải chương trình chạy thành công. Việc đặt phương thức điều phối là `final` cũng không làm cho mọi lời gọi bên trong trở nên tĩnh: nếu phương thức đó gọi một hook có thể ghi đè trong constructor, nguy cơ vẫn tồn tại.

## 7. Khi nào nên dùng hook và final?

Dùng hook khi lớp cha cần một điểm tùy biến có kiểm soát, như thêm phần mở rộng sau khi xử lý, cung cấp quy tắc định dạng hoặc cho phép lớp con tùy chỉnh một bước phụ. Hook nên có tên và hợp đồng rõ ràng, đồng thời có hành vi mặc định hợp lý nếu là tùy chọn.

Dùng phương thức `final` khi lớp cha cần bảo đảm thứ tự của một quy trình hoặc không cho phép lớp con thay đổi một thao tác cốt lõi. Không nên đánh dấu mọi phương thức là `final` theo thói quen: làm vậy có thể hạn chế khả năng mở rộng mà thiết kế thực sự cần. Nếu không cần kế thừa, một lớp `final` hoặc một thiết kế composition có thể đơn giản hơn.

Trước khi thêm hook, hãy tự hỏi: lớp con có thật sự cần thay đổi bước này không? Nếu hook trả về kết quả, lớp cha sẽ xác minh kết quả ra sao? Hook có thể làm lộ hoặc làm sai trạng thái nội bộ không? Nếu không có câu trả lời rõ, hãy thu hẹp API mở rộng.

## 8. Checklist rà soát

1. Phương thức nào xác định thứ tự thuật toán? Nếu thứ tự phải cố định, cân nhắc đặt phương thức điều phối là `final`.
2. Bước nào bắt buộc lớp con cung cấp? Dùng phương thức `abstract` với hợp đồng cụ thể.
3. Bước nào là tùy chọn? Dùng hook có hành vi mặc định rõ ràng.
4. Bất biến nào phải luôn đúng? Giữ trường liên quan ở phạm vi `private`, kiểm tra đầu vào và xác thực kết quả.
5. Hook có thể trả về `null`, dữ liệu rỗng, phát sinh ngoại lệ hoặc gây tác dụng phụ không? Quyết định cách xử lý trước khi công bố kết quả.
6. Constructor có gọi phương thức có thể ghi đè không? Nếu có, xem lại cách khởi tạo để tránh sử dụng trạng thái chưa hoàn chỉnh.
7. Ví dụ có biên dịch được và stdout có khớp với lệnh chạy không? Giữ riêng ví dụ runnable và đoạn mã chỉ nhằm minh họa lỗi thiết kế.

## Kết luận

Hook method mở ra điểm tùy biến có kiểm soát; phương thức `final` giữ nguyên khung điều phối; và các kiểm tra cùng đóng gói trạng thái giúp bảo vệ bất biến. Ba kỹ thuật này bổ trợ nhau. Một thiết kế tốt xác định rõ bước nào được phép tùy biến, giữ các điều kiện cốt lõi trong mã không thể bị ghi đè, và kiểm tra dữ liệu tại ranh giới giữa lớp cha với lớp con.