# Kiểm thử thứ tự bước và hook của Template Method

## Mục tiêu

Template Method định nghĩa khung của một thuật toán trong lớp cha, còn các phương thức được ghi đè hoặc hook cho phép lớp con tùy biến một số bước. Khi kiểm thử, cần xác nhận cả kết quả lẫn thứ tự gọi bước, hành vi mặc định của hook và điều gì xảy ra khi một bước thất bại. Bài này dùng Java 17, một bộ kiểm thử nhỏ không cần thư viện ngoài, và các sự kiện được ghi lại để quan sát luồng chạy.

## 1. Vì sao cần kiểm thử thứ tự?

Giả sử một quy trình xử lý dữ liệu phải thực hiện các bước theo thứ tự:

1. Chạy hook trước khi xử lý.
2. Đọc dữ liệu.
3. Biến đổi dữ liệu.
4. Lưu kết quả.
5. Chạy hook sau khi hoàn tất.

Nếu chỉ kiểm tra kết quả cuối cùng, bài kiểm thử có thể bỏ sót việc lưu dữ liệu trước khi biến đổi, gọi hook sai thời điểm hoặc chạy bước sau dù bước trước đã thất bại. Với Template Method, thứ tự là một phần của hợp đồng mà lớp cha cung cấp.

Một cách kiểm tra trực tiếp là cho lớp thử nghiệm ghi tên từng bước vào một danh sách. Sau khi gọi phương thức template, so sánh toàn bộ danh sách thực tế với danh sách sự kiện mong đợi. Cách này giúp phát hiện cả bước bị thiếu, bước bị lặp và thứ tự bị đảo.

## 2. Thiết kế điểm mở rộng có thể kiểm thử

Lớp cha dưới đây định nghĩa phương thức `execute()` là `final`. Lớp con không thể thay thế quy trình tổng thể, nhưng có thể triển khai bước `load()` và `persist()`, đồng thời tùy biến các hook `before()`, `transform()` và `after()`.

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;

abstract class DataPipeline {
    public final String execute(String source) {
        if (source == null || source.isBlank()) {
            throw new IllegalArgumentException("source must not be blank");
        }

        before(source);

        String loaded = load(source);
        if (loaded == null) {
            throw new IllegalStateException("load returned null");
        }

        String transformed = transform(loaded);
        if (transformed == null) {
            throw new IllegalStateException("transform returned null");
        }

        persist(transformed);
        after(transformed);
        return transformed;
    }

    protected void before(String source) {
        // Hook tùy chọn: mặc định không làm gì.
    }

    protected abstract String load(String source);

    protected String transform(String loaded) {
        return loaded.trim();
    }

    protected abstract void persist(String transformed);

    protected void after(String transformed) {
        // Hook tùy chọn: mặc định không làm gì.
    }
}
~~~

Các phương thức `before()` và `after()` là hook tùy chọn có hành vi mặc định rỗng. `transform()` có hành vi mặc định là loại bỏ khoảng trắng ở hai đầu. `load()` và `persist()` là các bước bắt buộc do lớp con triển khai. Các bước kiểm tra dữ liệu nằm trong phương thức template nên mọi lớp con đều phải đi qua chúng khi gọi `execute()`.

Việc khai báo `execute()` là `final` có nghĩa trình biên dịch sẽ từ chối lớp con nếu lớp đó cố ghi đè phương thức này. Kiểm thử thứ tự vẫn cần thiết vì các phương thức template có thể gọi những hook có thể ghi đè; chính các lời gọi đó tạo ra hành vi đa hình ở thời gian chạy.

## 3. Ghi lại sự kiện để xác nhận thứ tự

Tạo một lớp thử nghiệm ghi lại từng bước. Phương thức `load()` trả về chuỗi có khoảng trắng, còn `transform()` ghi nhận dữ liệu đầu vào rồi chuẩn hóa thành chữ hoa. Nhờ vậy, kiểm thử có thể xác nhận không chỉ thứ tự mà còn dữ liệu được truyền giữa các bước.

~~~java
final class RecordingPipeline extends DataPipeline {
    final List<String> events = new ArrayList<>();

    @Override
    protected void before(String source) {
        events.add("before:" + source);
    }

    @Override
    protected String load(String source) {
        events.add("load:" + source);
        return "  hello  ";
    }

    @Override
    protected String transform(String loaded) {
        events.add("transform:" + loaded);
        return loaded.trim().toUpperCase(Locale.ROOT);
    }

    @Override
    protected void persist(String transformed) {
        events.add("persist:" + transformed);
    }

    @Override
    protected void after(String transformed) {
        events.add("after:" + transformed);
    }
}
~~~

Danh sách sự kiện mong đợi khi gọi `execute("source")` là:

~~~text
before:source
load:source
transform:  hello  
persist:HELLO
after:HELLO
~~~

Có thể thấy hook `before()` chạy trước khi đọc, dữ liệu có khoảng trắng được truyền vào `transform()`, kết quả đã chuẩn hóa được lưu, và hook `after()` chỉ chạy sau bước lưu thành công. Nếu danh sách thực tế khác danh sách mong đợi, bài kiểm thử sẽ chỉ ra hợp đồng nào đã bị vi phạm.

## 4. Kiểm tra đường đi thất bại

Ngoài đường đi thành công, hãy xác nhận các bước phía sau không chạy khi một bước trả về dữ liệu không hợp lệ. Lớp dưới đây mô phỏng lỗi đọc dữ liệu bằng cách trả về `null`. Cờ `persisted` giúp kiểm tra rằng bước lưu không được gọi.

~~~java
final class NullLoadPipeline extends DataPipeline {
    boolean persisted;

    @Override
    protected String load(String source) {
        return null;
    }

    @Override
    protected void persist(String transformed) {
        persisted = true;
    }
}
~~~

Theo hợp đồng của `DataPipeline`, `execute()` phải ném `IllegalStateException` với thông báo `load returned null` ngay sau bước đọc. Phương thức `transform()`, `persist()` và `after()` không được chạy. Kiểm thử đường đi thất bại rất quan trọng khi thứ tự bước liên quan đến tác dụng phụ, chẳng hạn ghi dữ liệu ra cơ sở dữ liệu hoặc phát sự kiện.

## 5. Chương trình kiểm thử hoàn chỉnh

Lưu tất cả mã trong cùng một tệp `TemplateMethodOrderTest.java`: đặt ba dòng `import` của mục 2 ở **đầu tệp**, sau đó ghép lần lượt `DataPipeline` (mục 2), `RecordingPipeline` (mục 3), `NullLoadPipeline` (mục 4) và `TemplateMethodOrderTest` (mục 5). Các dòng `import` phải đứng trước mọi khai báo lớp; khi ghép, không lặp thêm `import` ở giữa tệp.

~~~java
public class TemplateMethodOrderTest {
    public static void main(String[] args) {
        RecordingPipeline pipeline = new RecordingPipeline();

        String result = pipeline.execute("source");
        check("HELLO".equals(result), "unexpected result: " + result);

        List<String> expectedEvents = List.of(
            "before:source",
            "load:source",
            "transform:  hello  ",
            "persist:HELLO",
            "after:HELLO"
        );
        check(
            pipeline.events.equals(expectedEvents),
            "unexpected order: " + pipeline.events
        );

        System.out.println("success trace: " + String.join(" -> ", pipeline.events));

        NullLoadPipeline failing = new NullLoadPipeline();
        try {
            failing.execute("source");
            throw new AssertionError("Expected load failure");
        } catch (IllegalStateException expectedFailure) {
            check(
                "load returned null".equals(expectedFailure.getMessage()),
                "unexpected error: " + expectedFailure.getMessage()
            );
        }

        check(!failing.persisted, "persist must not run after invalid load");
        System.out.println("failure path: load returned null; persist skipped");
    }

    private static void check(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }
}
~~~

Biên dịch và chạy bằng Java 17 trở lên:

~~~text
javac TemplateMethodOrderTest.java
java TemplateMethodOrderTest
~~~

Kết quả stdout chính xác:

~~~text
success trace: before:source -> load:source -> transform:  hello   -> persist:HELLO -> after:HELLO
failure path: load returned null; persist skipped
~~~

Nếu bất kỳ điều kiện nào không đúng, phương thức `check()` ném `AssertionError`, khiến chương trình kết thúc với lỗi thay vì in ra kết quả thành công. Vì vậy, stdout trên chỉ xuất hiện khi cả kết quả, thứ tự sự kiện, thông báo lỗi và việc bỏ qua bước lưu đều đúng.

## 6. Kiểm thử hook mặc định và hook được ghi đè

Một hook có hành vi mặc định cần được kiểm thử theo mục đích của nó. Nếu mặc định là không làm gì, có thể tạo một lớp con chỉ triển khai các bước bắt buộc và xác nhận kết quả vẫn đúng khi không ghi đè hook. Nếu hook mặc định chuẩn hóa dữ liệu, hãy xác nhận việc chuẩn hóa diễn ra khi lớp con không cung cấp phiên bản riêng.

Với hook được ghi đè, hãy kiểm tra:

- Hook chạy đúng một lần và ở đúng vị trí trong luồng.
- Hook nhận đúng dữ liệu đầu vào và kết quả được truyền tiếp đúng bước.
- Hành vi tùy biến không bỏ qua điều kiện bắt buộc của lớp cha.
- Nếu hook ném ngoại lệ, các bước sau nó không được chạy ngoài hợp đồng đã định.
- Nếu hook trả về dữ liệu, lớp cha kiểm tra dữ liệu đó trước khi dùng tiếp.

Không nên kiểm tra bằng cách chỉ xác nhận rằng hook đã được gọi. Một hook có thể được gọi đúng số lần nhưng sai thứ tự hoặc nhận dữ liệu sai. Danh sách sự kiện cùng giá trị đối số giúp kiểm tra hợp đồng rõ ràng hơn.

## 7. Phạm vi kiểm thử và giới hạn của final

Phương thức `final` bảo vệ điểm điều phối khỏi bị ghi đè, nhưng không tự bảo đảm mọi hook đều an toàn. Lớp con vẫn có thể thực hiện tác dụng phụ trong `load()`, `transform()`, `persist()` hoặc hook. Bởi vậy, cần kiểm tra kết quả và lỗi ở ranh giới giữa các bước, đồng thời giới hạn trạng thái mà lớp con có thể sửa.

Trong hệ thống lớn, có thể chuyển các phụ thuộc như kho dữ liệu hoặc bộ đọc vào đối tượng riêng rồi dùng fake/mock để xác minh thứ tự tương tác. Khi dùng JUnit, mỗi đường đi nên là một bài kiểm thử độc lập: đường đi thành công, đầu vào không hợp lệ, dữ liệu đọc không hợp lệ, hook phát sinh ngoại lệ và hành vi hook mặc định. Ví dụ trên dùng `main` và các kiểm tra đơn giản để có thể chạy trực tiếp mà không cần cài thư viện.

Tránh viết kiểm thử phụ thuộc vào chi tiết nội bộ không thuộc hợp đồng. Nếu thứ tự `before → load → transform → persist → after` là hành vi được cam kết, hãy kiểm tra thứ tự đó. Nếu thứ tự giữa hai thao tác không được quy định, đừng làm bài kiểm thử thất bại chỉ vì một triển khai hợp lệ chọn thứ tự khác.

## 8. Checklist rà soát

1. Xác định rõ thứ tự các bước mà Template Method cam kết.
2. Dùng fake hoặc lớp ghi sự kiện để quan sát lời gọi hook và thao tác bắt buộc.
3. So sánh toàn bộ danh sách sự kiện mong đợi với thực tế, bao gồm dữ liệu truyền vào từng bước.
4. Kiểm tra đường đi lỗi và xác nhận các bước phía sau không chạy khi điều kiện tiên quyết thất bại.
5. Kiểm thử hook mặc định và hook được ghi đè.
6. Dùng `final` cho phương thức điều phối khi lớp con không được phép thay đổi thuật toán tổng thể.
7. Chạy ví dụ bằng đúng phiên bản Java mục tiêu và xác nhận stdout khớp với kết quả dự kiến.

## Kết luận

Kiểm thử Template Method cần xác minh hợp đồng của cả quy trình: bước nào chạy, chạy theo thứ tự nào, dữ liệu nào được truyền giữa các bước và các bước sau phản ứng ra sao khi có lỗi. Ghi lại sự kiện bằng fake hoặc spy là cách trực tiếp để kiểm tra các yêu cầu này. Kết hợp phương thức điều phối `final`, hook có phạm vi rõ ràng và kiểm thử cả thành công lẫn thất bại giúp lớp cha giữ được quy trình ổn định mà vẫn cho phép lớp con tùy biến an toàn.