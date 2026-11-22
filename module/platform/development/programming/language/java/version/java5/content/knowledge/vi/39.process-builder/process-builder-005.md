# Đọc và điều chỉnh môi trường tiến trình con

## 1. Môi trường là cấu hình được truyền khi khởi chạy

Một công cụ bên ngoài có thể đọc cấu hình từ biến môi trường: chế độ chạy, ngôn ngữ, thư mục tạm hoặc địa chỉ dịch vụ. Khi Java khởi chạy công cụ bằng `ProcessBuilder`, có thể chuẩn bị riêng các giá trị đó cho tiến trình con.

Cần phân biệt ba nơi:

| Nơi | Cách đọc | Vai trò |
| --- | --- | --- |
| Môi trường của JVM cha | `System.getenv()` | Thông tin JVM hiện tại nhận được khi được khởi chạy |
| Cấu hình môi trường trong builder | `builder.environment()` | Chuẩn bị môi trường cho tiến trình sẽ được tạo |
| Môi trường của tiến trình con | API môi trường của chương trình con | Giá trị thực tế tiến trình con nhận lúc bắt đầu |

Mỗi `ProcessBuilder` ban đầu có bản sao môi trường của tiến trình hiện tại. `environment()` trả về bản đồ có thể điều chỉnh để cấu hình lần `start()` tiếp theo. Việc sửa bản đồ không sửa môi trường JVM cha hay các tiến trình đã được tạo. Đây là hợp đồng của [Java ProcessBuilder API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ProcessBuilder.html#environment()).

Ví dụ khái niệm:

```text
JVM cha: APP_MODE=development
    ↓ tạo builder
Builder: APP_MODE=development
    ↓ sửa builder.environment()
Builder: APP_MODE=test
    ↓ start()
Tiến trình con: APP_MODE=test

JVM cha vẫn giữ APP_MODE=development
```

Tên `APP_MODE` ở đây chỉ là ví dụ. Chương trình đích chỉ sử dụng biến nếu nó có mã hoặc tài liệu quy định đọc tên đó.

## 2. Đọc, thêm, thay và xóa biến

Với một `ProcessBuilder builder` đã có lệnh hợp lệ:

```java
Map<String, String> environment = builder.environment();

String currentMode = environment.get("APP_MODE");
boolean hasMode = environment.containsKey("APP_MODE");

environment.put("APP_MODE", "test");
environment.put("REPORT_LABEL", "monthly report");
environment.remove("UNUSED_OPTION");
```

Đây là đoạn minh họa cần import `java.util.Map` và biến `builder`; chương trình hoàn chỉnh ở phần sau.

Các thao tác có ý nghĩa thông thường của bản đồ:

- `get()` đọc giá trị hiện đang cấu hình; không có tên đó thì trả `null`.
- `containsKey()` phân biệt có tên biến hay không.
- `put()` thêm mới hoặc thay giá trị đã có.
- `remove()` bỏ biến khỏi môi trường dự kiến của tiến trình con.

Bản đồ lấy từ `builder.environment()` gắn với builder. Sửa trực tiếp nó sẽ sửa cấu hình của builder. Nếu tự tạo `new HashMap<>(builder.environment())` rồi chỉ sửa bản sao, builder chưa nhận các thay đổi đó; cần chủ động áp dụng những thay đổi muốn truyền.

Không dùng `null` để thay cho “xóa biến”: dùng `remove()`. Tên và giá trị hợp lệ còn bị ràng buộc bởi hệ điều hành. Không mặc định mọi cặp chuỗi Java đều là biến môi trường hợp lệ; có lỗi có thể xuất hiện lúc chỉnh bản đồ hoặc lúc khởi chạy.

## 3. Không có biến khác với biến có giá trị rỗng

Hai thao tác sau không tương đương:

```java
environment.remove("APP_OPTION");
environment.put("APP_OPTION", "");
```

Dòng thứ nhất bỏ tên biến; dòng thứ hai giữ tên biến với chuỗi rỗng.

Nếu công cụ dùng quy tắc “không có biến thì chọn mặc định, có biến thì dùng đúng giá trị”, sự khác biệt này ảnh hưởng kết quả. Đừng tự thay mọi giá trị thiếu thành chuỗi rỗng khi nhập cấu hình.

Trong tiến trình Java con:

```java
String value = System.getenv("APP_OPTION");
boolean missing = value == null;
boolean empty = "".equals(value);
```

Đoạn minh họa này cho thấy hai phép kiểm tra riêng. `empty` chỉ đúng khi biến tồn tại với giá trị rỗng; với `null`, biểu thức `"".equals(value)` trả `false`.

## 4. Thời điểm thay đổi có hiệu lực

Một builder có thể khởi chạy nhiều tiến trình. Mỗi lần khởi chạy dùng cấu hình tại thời điểm đó:

```text
Builder APP_MODE=first
    ↓ start() lần 1
Con 1 nhận first

Sửa builder APP_MODE=second
    ↓ start() lần 2
Con 2 nhận second
```

Sửa builder sau khi con 1 đã được tạo không gửi một thông điệp cập nhật cấu hình cho con 1. Nếu muốn thay cấu hình của tiến trình đang chạy, cần cơ chế riêng như tệp cấu hình được nạp lại, API hoặc kênh giao tiếp do chương trình con hỗ trợ.

Một builder khác cũng không tự dùng các thay đổi trong builder thứ nhất. Khi mới tạo, nó lấy cấu hình môi trường từ JVM cha, không lấy từ builder đang được tùy chỉnh.

Không chia sẻ rồi chỉnh cùng một builder giữa nhiều luồng mà thiếu đồng bộ. Mỗi tác vụ có cấu hình riêng thường dễ quản lý hơn nếu dùng builder riêng.

## 5. Chương trình Java đầy đủ để kiểm chứng

Chương trình sau dùng cùng một builder tạo hai JVM con. Các tên biến có tiền tố riêng để tránh phụ thuộc vào cấu hình thông thường của máy.

Nó chỉ in ba biến phục vụ bài học và các kết quả kiểm tra, không in toàn bộ môi trường. Lưu thành `ChildEnvironmentDemo.java`, dùng JDK 17 trở lên:

```java
import java.nio.file.Path;
import java.util.Map;
import java.util.Objects;
import java.util.concurrent.TimeUnit;

public class ChildEnvironmentDemo {
    private static final String MODE = "JL_MODE_515";
    private static final String KEEP = "JL_KEEP_515";
    private static final String EMPTY = "JL_EMPTY_515";

    public static void main(String[] args) throws Exception {
        if (args.length > 0 && args[0].equals("--child")) {
            String label = args[1];
            System.out.println(label + ".mode=" + System.getenv(MODE));
            String keep = System.getenv(KEEP);
            System.out.println(label + ".keep="
                    + (keep == null ? "<missing>" : keep));
            System.out.println(label + ".empty="
                    + "".equals(System.getenv(EMPTY)));
            return;
        }

        String originalMode = System.getenv(MODE);
        String originalKeep = System.getenv(KEEP);
        String originalEmpty = System.getenv(EMPTY);
        ProcessBuilder builder = childBuilder("first");
        Map<String, String> environment = builder.environment();
        environment.put(MODE, "first");
        environment.put(KEEP, "present");
        environment.put(EMPTY, "");

        Process first = builder.start();
        environment.put(MODE, "second");
        environment.remove(KEEP);
        await(first, "first");

        builder.command().set(builder.command().size() - 1, "second");
        Process second = builder.start();
        await(second, "second");

        boolean parentUnchanged =
                Objects.equals(originalMode, System.getenv(MODE))
                && Objects.equals(originalKeep, System.getenv(KEEP))
                && Objects.equals(originalEmpty, System.getenv(EMPTY));
        System.out.println("parentUnchanged=" + parentUnchanged);

        ProcessBuilder separate = childBuilder("unused");
        System.out.println("separateBuilderMatchesParent="
                + Objects.equals(separate.environment().get(MODE), originalMode));
    }

    private static ProcessBuilder childBuilder(String label) {
        String executable = System.getProperty("os.name").startsWith("Windows")
                ? "java.exe" : "java";
        String javaPath = Path.of(
                System.getProperty("java.home"), "bin", executable).toString();
        return new ProcessBuilder(
                javaPath, "-cp", System.getProperty("java.class.path"),
                ChildEnvironmentDemo.class.getName(), "--child", label)
                .inheritIO();
    }

    private static void await(Process process, String label)
            throws InterruptedException {
        if (!process.waitFor(10, TimeUnit.SECONDS)) {
            process.destroyForcibly();
            throw new IllegalStateException("Child process timed out");
        }
        System.out.println(label + ".exit=" + process.exitValue());
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 ChildEnvironmentDemo.java
java -cp . ChildEnvironmentDemo
```

Stdout:

```text
first.mode=first
first.keep=present
first.empty=true
first.exit=0
second.mode=second
second.keep=<missing>
second.empty=true
second.exit=0
parentUnchanged=true
separateBuilderMatchesParent=true
```

Cách đọc kết quả:

1. Trước lần `start()` đầu, builder đặt `JL_MODE_515=first`, biến `KEEP` có giá trị `present` và biến `EMPTY` có giá trị rỗng.
2. Ngay sau khi tạo tiến trình đầu, JVM cha sửa builder thành `second` và xóa `KEEP`.
3. Tiến trình đầu vẫn in `first` và `present`: nó đã nhận môi trường của lần khởi chạy đầu.
4. Tiến trình thứ hai in `second` và `<missing>`: nó nhận cấu hình đã sửa.
5. Cả hai đều có biến `EMPTY` với chuỗi rỗng.
6. `parentUnchanged=true` xác nhận ba biến của JVM cha vẫn như trước.
7. Builder mới độc lập khớp môi trường cha ở biến được kiểm tra, không kế thừa giá trị đã chỉnh trong builder trước.

Đường dẫn chương trình Java được lấy từ `java.home`; ví dụ không cần sửa PATH. `inheritIO()` giúp quan sát trực tiếp đầu ra. Việc chờ có thời hạn chỉ hỗ trợ chạy minh chứng, không phải toàn bộ chiến lược quản lý tiến trình cho ứng dụng thực tế.

Các đối số `--child` và nhãn `first/second` nằm trong danh sách lệnh. Chúng là đối số, không phải biến môi trường. Chương trình dùng cả hai kênh riêng để người học thấy rõ ranh giới.

## 6. Biến môi trường không phải Java system property

Đây là hai cơ chế khác nhau:

| Cơ chế | Ví dụ đọc trong JVM | Cách cấu hình điển hình cho JVM con |
| --- | --- | --- |
| Biến môi trường | `System.getenv("APP_MODE")` | `builder.environment().put("APP_MODE", "test")` |
| Java system property | `System.getProperty("app.mode")` | Đối số JVM `-Dapp.mode=test` trước tên lớp |
| Đối số ứng dụng | Phần tử `args` của `main()` | Phần tử danh sách sau tên lớp |

`System.setProperty("app.mode", "test")` trong JVM cha không tự tạo biến môi trường `APP_MODE` cho tiến trình con. Tương tự, đặt `APP_MODE` trong môi trường không tự tạo property `app.mode`, trừ khi chương trình hoặc framework có quy tắc ánh xạ riêng. Các API được mô tả trong [Java System API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/System.html).

`System.getenv()` trả một bản đồ không cho sửa. Đừng cố thay môi trường của JVM đang chạy bằng cách gọi `put()` lên bản đồ đó hoặc dùng thủ thuật truy cập nội bộ JDK. Để cấu hình tiến trình con, `ProcessBuilder.environment()` là điểm cấu hình phù hợp.

Một tệp `.env` cũng không tự được `ProcessBuilder` đọc. Nếu ứng dụng chọn hỗ trợ loại tệp đó, cần bộ đọc với quy tắc rõ ràng rồi áp dụng những biến đã được phép. Không coi việc có tệp trong thư mục là biến đã tồn tại trong tiến trình con.

## 7. Chuỗi giá trị không được shell tự mở rộng

Đặt:

```java
environment.put("REPORT_DIR", "$HOME/reports");
```

sẽ cấu hình một chuỗi có các ký tự `$HOME`. `ProcessBuilder` không tự thay phần ấy bằng thư mục người dùng. Chương trình đích có thể tự hỗ trợ mở rộng biến, nhưng đó là quy tắc riêng của nó.

Nếu muốn tính đường dẫn trong Java, đọc cấu hình đầu vào phù hợp rồi dùng API đường dẫn để tạo giá trị thực tế trước khi `put()`. Tương tự, ký hiệu `%TEMP%` trong một giá trị không tự được Java biến thành thư mục tạm chỉ vì đang chạy trên Windows.

Không cần thêm dấu nháy vào `"monthly report"` chỉ để giữ khoảng trắng trong giá trị môi trường. Bản đồ đã lưu nó như một chuỗi; dấu nháy bổ sung có thể trở thành dữ liệu mà công cụ nhận.

## 8. Những khác biệt nền tảng và giới hạn cần tính đến

### Tên biến và PATH

Quy tắc tên, phân biệt hoa/thường và cách công cụ tìm tệp thực thi có thể khác giữa nền tảng. Nên dùng tên ứng dụng nhất quán, chẳng hạn chữ hoa với dấu gạch dưới; tránh tạo các tên chỉ khác kiểu chữ và mong chúng luôn độc lập.

PATH cũng là một biến môi trường, nhưng cách tìm chương trình đầu tiên của `ProcessBuilder` còn phụ thuộc Java và hệ điều hành. Đừng giả định sửa PATH trong builder sẽ điều khiển mọi bước tìm chương trình giống hệt một terminal. Khi cần chắc chắn chọn đúng công cụ, dùng đường dẫn thực thi cụ thể; PATH trong môi trường con vẫn có thể ảnh hưởng các công cụ mà tiến trình con gọi tiếp.

### Không xóa toàn bộ theo thói quen

`environment.clear()` có thể dùng khi thiết kế một môi trường được giới hạn rõ ràng. Tuy nhiên, xóa tất cả có thể làm mất các biến hệ thống hoặc cấu hình mà công cụ cần để hoạt động.

Nếu dùng cách này, cần biết và cung cấp lại tập biến cần thiết trên từng hệ điều hành, rồi kiểm chứng công cụ thực tế. Một số nền tảng có thể bổ sung biến tối thiểu khi tạo tiến trình; bản đồ rỗng không nên được xem như cam kết một môi trường cách ly hoàn toàn.

### Không phải cơ chế giữ bí mật hoặc cách ly tiến trình

Biến môi trường là kênh cấu hình, không phải một kho bí mật tự động. Tiến trình con có thể đọc những gì nó nhận và có thể truyền tiếp cho tiến trình cháu. Công cụ gỡ lỗi, chẩn đoán hoặc cấu hình log của ứng dụng cũng có thể làm lộ dữ liệu.

Chỉ truyền những giá trị cần thiết, hạn chế kế thừa bí mật không liên quan khi chạy công cụ ngoài và không in toàn bộ `System.getenv()` để gỡ lỗi. Điều chỉnh môi trường không giới hạn quyền truy cập tệp, mạng hoặc tài nguyên hệ thống của tiến trình.

## 9. Tự kiểm tra

1. Sửa `builder.environment()` có đổi kết quả `System.getenv()` của JVM cha không?
2. Sửa biến sau khi `start()` có cập nhật tiến trình đã chạy không?
3. Xóa biến và đặt chuỗi rỗng có luôn tương đương không?
4. `System.setProperty()` có tự tạo biến môi trường cho công cụ ngoài không?
5. Chuỗi `"$HOME/reports"` có tự được `ProcessBuilder` mở rộng không?

Đáp án: (1) không; (2) không, lần khởi chạy sau mới dùng cấu hình sửa; (3) không, phụ thuộc cách chương trình xử lý trạng thái thiếu/rỗng; (4) không; (5) không, đó là chuỗi nguyên văn nếu chương trình đích không tự xử lý.
