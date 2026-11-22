# System.getenv và môi trường của tiến trình hiện tại

## 1. Biến môi trường là dữ liệu tiến trình nhận khi được khởi chạy

Một ứng dụng thường cần biết chế độ chạy, địa chỉ dịch vụ hoặc một số tùy chọn triển khai. Thay vì gán tất cả trong mã nguồn, nơi khởi chạy có thể cung cấp các cặp tên–giá trị qua **biến môi trường (environment variables)**.

Trong Java, `System.getenv` đọc môi trường mà **tiến trình JVM hiện tại** nhìn thấy. Nó không phải một bảng cấu hình chung luôn được đồng bộ giữa mọi chương trình trên máy.

Có thể hình dung:

```text
Terminal / IDE / trình quản lý dịch vụ / môi trường chạy
        |
        | khởi chạy JVM với một môi trường
        v
JVM hiện tại
        |
        | System.getenv(...)
        v
Các giá trị môi trường JVM đó nhìn thấy
```

Hai JVM trên cùng máy có thể nhận môi trường khác nhau. Một JVM chạy từ terminal không nhất thiết thấy đúng các biến mà JVM được IDE hoặc dịch vụ khởi chạy nhận được.

## 2. Hai cách đọc của System.getenv

| Cách gọi | Kiểu kết quả | Khi nào dùng |
|---|---|---|
| `System.getenv("APP_MODE")` | `String` hoặc `null` | Đọc một tên cụ thể |
| `System.getenv()` | `Map<String, String>` không cho sửa | Cần truy cập nhiều tên theo giao diện map |

Ví dụ nhỏ, đặt trong một phương thức Java:

```java
String mode = System.getenv("APP_MODE");
if (mode == null) {
    mode = "development";
}
```

Ở đây, mặc định chỉ được dùng khi biến **không tồn tại**. Nó không tự áp dụng cho chuỗi rỗng.

Map do `System.getenv()` trả về không phải giao diện sửa môi trường. Gọi `put`, `remove` hoặc `clear` qua map đó để thay đổi dữ liệu sẽ không được hỗ trợ. Java không có phương thức `System.setenv` tiêu chuẩn tương ứng để sửa môi trường tiến trình hiện tại. Xem [API System.getenv](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/System.html#getenv()).

Đừng nhầm map này với map của `ProcessBuilder.environment()`: map của builder dùng để cấu hình môi trường cho **tiến trình con sẽ khởi chạy**, không sửa môi trường mà `System.getenv` của cha đọc được.

## 3. Thiếu biến, giá trị rỗng và giá trị sai là ba trạng thái

Giả sử ứng dụng cần biến `APP_PORT`:

| Trạng thái | Giá trị Java điển hình | Cần quyết định |
|---|---|---|
| Không định nghĩa | `null` | Dùng mặc định hay báo thiếu cấu hình? |
| Có tên nhưng không có nội dung | `""` | Có cho phép rỗng không? |
| Chỉ có khoảng trắng | Ví dụ `"   "` | Có chuẩn hóa khoảng trắng hay từ chối? |
| Có nội dung nhưng sai kiểu | Ví dụ `"eighty"` | Báo lỗi cấu hình |
| Đúng kiểu nhưng ngoài miền | Ví dụ `"70000"` nếu yêu cầu cổng 1–65535 | Báo sai miền giá trị |
| Hợp lệ | Ví dụ `"8080"` | Chuyển sang kiểu mà ứng dụng sử dụng |

`System.getenv` trả chuỗi, không tự chuyển thành số, boolean hoặc đường dẫn. Việc phân tích và kiểm tra miền là trách nhiệm của lớp đọc cấu hình.

Những lỗi cần tránh:

- Gọi `System.getenv("APP_MODE").equals("production")` khi biến có thể thiếu.
- Dùng mặc định cho mọi trường hợp sai, làm cấu hình gõ nhầm bị che khuất.
- Cho rằng `getOrDefault` trên map sẽ thay cả giá trị rỗng bằng mặc định; nó chỉ xử lý trường hợp không có ánh xạ.
- Tự `trim` mọi giá trị dù loại dữ liệu đó có thể coi khoảng trắng là một phần nội dung.

Với từng biến, hãy ghi rõ quy tắc: bắt buộc hay tùy chọn, mặc định nào, có chấp nhận rỗng không, có bỏ khoảng trắng không và miền giá trị hợp lệ. Việc này giúp cùng một cấu hình được hiểu thống nhất ở nhiều môi trường.

## 4. Biến môi trường khác Java system properties

Cùng một tên có thể xuất hiện ở hai nơi với hai giá trị độc lập:

| Nguồn | Đọc bằng | Cách cấp điển hình |
|---|---|---|
| Môi trường tiến trình | `System.getenv(name)` | Nơi khởi chạy cấp môi trường |
| Thuộc tính hệ thống của JVM | `System.getProperty(name)` | Tùy chọn `-Dname=value` khi gọi Java |
| Thuộc tính được đặt trong JVM | `System.getProperty(name)` | Mã Java gọi `System.setProperty` |

Nếu chạy Java với `-DAPP_MODE=production`, điều đó đặt một **system property**; nó không tự tạo biến môi trường `APP_MODE`. Tương tự, gọi `System.setProperty("APP_MODE", "production")` không làm `System.getenv("APP_MODE")` trả giá trị mới.

Nếu ứng dụng muốn hỗ trợ cả hai nguồn, phải tự định nghĩa thứ tự ưu tiên. Ví dụ “property ghi đè môi trường, môi trường ghi đè mặc định” là chính sách của ứng dụng hoặc framework, không phải quy tắc tự động của `System.getenv`.

Các API property và môi trường là hai nhóm riêng trong [lớp System](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/System.html).

### Tệp .env không tự trở thành môi trường JVM

Chỉ đặt một tệp tên `.env` trong thư mục dự án không khiến `System.getenv` tự đọc nó. Muốn dùng tệp đó, công cụ khởi chạy hoặc một thành phần cấu hình phải xử lý tệp theo cơ chế đã chọn.

Tương tự, chuỗi `"${APP_MODE}"` hay `"$APP_MODE"` trong Java không tự được `System.getenv` thay thế thành giá trị biến. Muốn tra cứu phải gọi API hoặc dùng cơ chế cấu hình có quy tắc thay thế riêng.

## 5. Ví dụ kiểm chứng bằng một JVM con có môi trường đã biết

Chỉ đọc môi trường thật của máy thì stdout khó xác định vì mỗi nơi cấu hình khác nhau. Ví dụ này chủ động cấp ba tên minh họa cho một JVM con:

- Một biến có nội dung `training`.
- Một biến được định nghĩa với chuỗi rỗng.
- Một biến bị loại khỏi môi trường của con.

Đồng thời, JVM con nhận một system property trùng tên với biến thứ nhất nhưng có giá trị `property-only`. Nhờ vậy có thể kiểm chứng hai nguồn độc lập.

Lưu mã sau vào `CurrentEnvironmentDemo.java`:

```java
import java.nio.file.Path;
import java.util.Map;
import java.util.Locale;
import java.util.Objects;
import java.util.concurrent.TimeUnit;

public class CurrentEnvironmentDemo {
    private static final String VALUE_KEY = "JAVA_LEARNING_ENV_DEMO";
    private static final String EMPTY_KEY = "JAVA_LEARNING_ENV_EMPTY";
    private static final String MISSING_KEY = "JAVA_LEARNING_ENV_MISSING";

    public static void main(String[] args) throws Exception {
        if (args.length == 1 && args[0].equals("--child")) {
            Map<String, String> environment = System.getenv();
            System.out.println("env value=" + System.getenv(VALUE_KEY));
            System.out.println("map agrees=" + Objects.equals(
                    environment.get(VALUE_KEY), System.getenv(VALUE_KEY)));

            String empty = System.getenv(EMPTY_KEY);
            System.out.println("empty defined="
                    + (empty != null && empty.isEmpty()));
            System.out.println("missing="
                    + (System.getenv(MISSING_KEY) == null));
            System.out.println("property value="
                    + System.getProperty(VALUE_KEY));
            return;
        }

        String parentValueBefore = System.getenv(VALUE_KEY);
        boolean windows = System.getProperty("os.name")
                .toLowerCase(Locale.ROOT).startsWith("windows");
        Path javaExecutable = Path.of(
                System.getProperty("java.home"),
                "bin", windows ? "java.exe" : "java");

        ProcessBuilder builder = new ProcessBuilder(
                javaExecutable.toString(),
                "-D" + VALUE_KEY + "=property-only",
                "-cp", System.getProperty("java.class.path"),
                CurrentEnvironmentDemo.class.getName(),
                "--child");
        builder.environment().put(VALUE_KEY, "training");
        builder.environment().put(EMPTY_KEY, "");
        builder.environment().remove(MISSING_KEY);
        builder.redirectErrorStream(true);
        builder.redirectOutput(ProcessBuilder.Redirect.INHERIT);

        Process child = builder.start();
        try {
            child.getOutputStream().close();
            if (!child.waitFor(10, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Child process timed out");
            }
            int exitCode = child.exitValue();
            if (exitCode != 0) {
                throw new IllegalStateException("Child failed: " + exitCode);
            }
            System.out.println("child exit=" + exitCode);
            System.out.println("parent env unchanged=" + Objects.equals(
                    parentValueBefore, System.getenv(VALUE_KEY)));
        } finally {
            if (child.isAlive()) {
                child.destroyForcibly();
                child.waitFor(5, TimeUnit.SECONDS);
            }
        }
    }
}
```

Biên dịch và chạy với JDK 17 trở lên:

```shell
javac -encoding UTF-8 --release 17 CurrentEnvironmentDemo.java
java CurrentEnvironmentDemo
```

Stdout khi JVM con khởi chạy và hoàn thành trong thời hạn:

```text
env value=training
map agrees=true
empty defined=true
missing=true
property value=property-only
child exit=0
parent env unchanged=true
```

### Kết quả cho biết điều gì?

Dòng đầu cho thấy `System.getenv(VALUE_KEY)` đọc giá trị môi trường đã cấp cho JVM con. Dòng `map agrees=true` xác nhận việc tra cùng tên qua map cho cùng kết quả.

`empty defined=true` chỉ đạt khi giá trị khác `null` nhưng rỗng. `missing=true` cho thấy biến bị loại bỏ trả về `null`. Hai trường hợp có thể cần chính sách xử lý khác nhau.

Dòng `property value=property-only` chứng minh rằng tên giống nhau không làm hai nguồn nhập lại thành một. Con nhìn thấy môi trường `training` và property `property-only` cùng lúc.

Cha chỉ so sánh giá trị của tên minh họa trước và sau khi chạy, không in giá trị môi trường sẵn có của cha. `parent env unchanged=true` xác nhận việc sửa map của builder không sửa nguồn mà cha đọc qua `System.getenv`.

### Vì sao có ProcessBuilder trong bài về môi trường hiện tại?

Mỗi lần JVM con bắt đầu chạy, môi trường được cấp cho nó trở thành môi trường **hiện tại của chính nó**. Ở nhánh `--child`, việc đọc vẫn là `System.getenv` bình thường.

Map của builder khởi đầu từ bản sao môi trường của cha, rồi được sửa trước `start()`. Việc này chỉ ảnh hưởng tiến trình con được tạo từ cấu hình đó. Xem [API ProcessBuilder.environment](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ProcessBuilder.html#environment()).

Ví dụ giữ nguyên thư mục làm việc, dùng cùng classpath hiện tại và chuyển tiếp đầu ra. Mã còn chờ có thời hạn, kiểm tra mã thoát và yêu cầu dừng nếu con vẫn sống khi rời khối xử lý. Nó là một chương trình minh họa đồng bộ, không phải bộ quản lý tiến trình cho mọi tình huống.

## 6. Vì sao đổi biến ở terminal khác mà ứng dụng chưa thấy?

Môi trường tiến trình thường được truyền khi tiến trình được tạo. Nếu một terminal khác thay biến của riêng nó, JVM đang chạy không được cập nhật tự động chỉ vì tên biến trên cùng máy đã thay đổi.

Khi điều tra cấu hình:

1. Xác định ai khởi chạy JVM: terminal nào, IDE, dịch vụ hay nền tảng triển khai.
2. Kiểm tra biến được cấp ở đúng nơi khởi chạy đó.
3. Khởi chạy một JVM mới từ môi trường đã có cấu hình mới.
4. Nếu IDE hoặc dịch vụ giữ cấu hình cũ, cập nhật đúng launcher hoặc cấu hình chạy của nó; chỉ mở một terminal mới chưa chắc thay được môi trường mà launcher đang dùng.

Với môi trường triển khai, thông tin cấu hình có thể nằm trong thiết lập của tiến trình hoặc nền tảng. Không dựa vào việc một lệnh trong terminal tương tác đọc được biến để kết luận mọi ứng dụng khác cũng nhìn thấy nó.

Việc có nhiều nơi lưu cấu hình cũng làm dễ nhầm “đã sửa giá trị” với “đã cấp giá trị cho đúng tiến trình”. Khi ghi hướng dẫn chạy, hãy nêu rõ nguồn nào cấp biến và tiến trình nào cần khởi chạy lại.

## 7. Tên biến và khác biệt hệ điều hành

Quy tắc tên và cách đối chiếu chữ hoa/thường phụ thuộc môi trường hệ điều hành. Không nên viết mã dựa vào giả định rằng `APP_MODE` và `app_mode` luôn tương đương trên mọi nền tảng.

Đặt một tên thống nhất, dùng chính xác tên đó ở nơi cấp cấu hình và nơi đọc. Quy ước chữ hoa ASCII kèm dấu gạch dưới như `APP_MODE` giúp dễ nhận diện, nhưng đó là lựa chọn quy ước, không phải cơ chế tự đổi tên của Java.

Không truyền `null` làm tên biến để diễn đạt “không có tên”; hãy kiểm tra đầu vào trước khi tra cứu. Tên của một cấu hình cụ thể nên là hằng rõ ràng thay vì được ghép tùy tiện từ dữ liệu đầu vào.

## 8. Thiết kế lớp đọc cấu hình dễ kiểm thử

Một cách tổ chức hữu ích là chỉ đọc môi trường ở ranh giới ứng dụng, sau đó truyền các giá trị đã kiểm tra vào phần xử lý nghiệp vụ.

Ví dụ luồng trách nhiệm:

```text
System.getenv()
      → chọn những tên ứng dụng cần
      → xử lý thiếu/rỗng
      → phân tích kiểu và kiểm tra miền
      → đối tượng cấu hình
      → các thành phần nghiệp vụ
```

Khi kiểm thử phần phân tích, có thể cho hàm nhận một `Map<String, String>` do bài kiểm thử tạo. Như vậy kiểm tra được biến thiếu, rỗng và sai kiểu mà không cố sửa môi trường thật của JVM. Cần nhớ rằng một map giả thông thường không mô phỏng mọi quy tắc hệ điều hành, nên các giả định phụ thuộc nền tảng vẫn cần được kiểm tra ở môi trường phù hợp.

Chỉ đọc những biến thực sự cần. Khi chẩn đoán, ưu tiên thông tin như “biến X có tồn tại không” hoặc lỗi định dạng, tránh in toàn bộ `System.getenv()` vào log vì môi trường có thể chứa thông tin nhạy cảm. Ví dụ của bài chỉ in các giá trị minh họa do chính nó cấp.

## 9. Bài thực hành

1. Thêm một tên minh họa có giá trị chỉ chứa khoảng trắng. Viết điều kiện phân biệt nó với biến thiếu và chuỗi rỗng.
2. Bỏ tùy chọn `-D...` trong một bản thử. Dự đoán dòng property, rồi chạy để kiểm chứng rằng biến môi trường vẫn tồn tại.
3. Viết hàm nhận map và đọc một cổng với chính sách: thiếu dùng 8080, rỗng hoặc sai kiểu thì báo lỗi, số hợp lệ phải trong 1–65535. Kiểm thử bằng map tự tạo.
4. Vẽ đường khởi chạy JVM trong IDE và trong terminal của bạn. Xác định nơi phải cấp cùng một biến để hai JVM nhận cùng cấu hình.

Khi dùng `System.getenv`, luôn xác định rõ đang đọc môi trường của tiến trình nào, giá trị có tồn tại hay không và lớp nào chịu trách nhiệm diễn giải chuỗi thành cấu hình hợp lệ.
