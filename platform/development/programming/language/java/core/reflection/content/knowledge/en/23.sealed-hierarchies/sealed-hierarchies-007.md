# Giới hạn dùng danh sách permits để quyết định toàn bộ cách khởi tạo

## 1. Permits trả lời về quan hệ kiểu, không phải công thức tạo đối tượng

Một kiểu sealed khai báo những lớp hoặc interface được phép làm kiểu con trực tiếp. Reflection có thể đọc các nhánh đó bằng:

~~~java
Class<?>[] direct = root.getPermittedSubclasses();
~~~

Thông tin này rất hữu ích khi vẽ sơ đồ phân cấp, khảo sát một mô hình miền dữ liệu hoặc kiểm tra quan hệ giữa các kiểu.

Nhưng từ danh sách đó chưa thể trả lời đầy đủ:

- Cần chọn nhánh nào cho một dữ liệu đầu vào?
- Nhánh đó có phải một lớp cụ thể có thể tạo instance không?
- Cần constructor, factory, builder hay một đối tượng đã tồn tại?
- Các đối số khởi tạo lấy từ đâu và phải qua kiểm tra gì?
- Có đủ quyền truy cập và các phụ thuộc cần thiết không?
- Một nhánh `non-sealed` còn có những cách triển khai nào ngoài danh sách trực tiếp?

**Được phép làm kiểu con** không đồng nghĩa với **được chọn cho dữ liệu này**, và cũng không đồng nghĩa với **có thể gọi constructor không tham số để tạo ngay**.

Cách thiết kế rõ ràng là tách ba việc:

~~~text
Khảo sát phân cấp
    -> hiểu các quan hệ kiểu

Chọn biến thể
    -> xác định kiểu hoặc ý nghĩa cần có từ dữ liệu/ngữ cảnh

Tạo hoặc lấy đối tượng
    -> thực thi chiến lược phù hợp với biến thể đã chọn
~~~

Không gộp cả ba việc vào một vòng lặp trên mảng permitted.

## 2. Chính xác thì API cung cấp những gì?

`Class.getPermittedSubclasses()` trả về các lớp hoặc interface con **trực tiếp** được một kiểu sealed cho phép mà API thu được.

Những thuộc tính quan trọng của kết quả:

- Chỉ là các đối tượng `Class<?>`, không phải các instance.
- Có thể chứa interface hoặc lớp trừu tượng.
- Không tự mở rộng thành toàn bộ hậu duệ gián tiếp.
- Không cam kết thứ tự phần tử.
- Với kiểu không sealed, kết quả là `null`.
- Nếu một kiểu ghi trong metadata không lấy được đối tượng `Class` phù hợp, nó có thể bị bỏ qua theo hợp đồng API.

Tài liệu [Class.getPermittedSubclasses](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Class.html#getPermittedSubclasses()) mô tả phạm vi này.

Vì vậy, danh sách permitted không phải:

~~~text
Danh sách mọi lớp cụ thể có thể tạo
    +
Constructor nên dùng
    +
Dữ liệu đối số
    +
Thứ tự ưu tiên chọn nhánh
~~~

Một kiểu sealed có thể có nhiều kiểu con hợp lệ về mặt ngôn ngữ nhưng ứng dụng chỉ công bố một số biến thể trong giao thức của nó. Phân cấp Java và danh mục biến thể ứng dụng có quan hệ, nhưng không tự là một danh sách duy nhất.

## 3. Những điều không suy ra được chỉ từ một Class trong permits

| Kiểu nhánh hoặc thiết kế | Vì sao danh sách permits chưa đủ? |
| --- | --- |
| Interface | Không thể tạo instance trực tiếp bằng constructor |
| Lớp trừu tượng | Có thể có constructor nhưng không tạo trực tiếp instance của chính lớp đó |
| Lớp final | Chỉ cấm tạo lớp con; không bảo đảm có constructor không tham số |
| Record | Cần constructor phù hợp với các thành phần, thường kèm kiểm tra dữ liệu |
| Lớp dùng factory | API tạo có thể là một phương thức tĩnh; constructor riêng tư không phải hợp đồng dành cho người gọi |
| Enum | Cần chọn một hằng hiện có; `Constructor.newInstance()` không cho tạo thêm instance enum |
| Nhánh non-sealed | Tập triển khai tiếp theo mở rộng; permitted của chính nhánh đó không liệt kê toàn bộ hậu duệ |
| Lớp thành viên không static | Khi gọi constructor bằng Reflection có thể cần đối tượng bao quanh |
| Kiểu cần phụ thuộc bên ngoài | Metadata không tự cung cấp cấu hình, dịch vụ, tài nguyên hoặc ngữ cảnh cần thiết |

Ngay cả khi một lớp cụ thể có một constructor gọi được, việc chọn constructor đó còn phải theo ý nghĩa mô hình. Một constructor “không ném lỗi ở lần thử này” không tự là constructor đúng cho ánh xạ dữ liệu.

Hợp đồng [Constructor.newInstance](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/Constructor.html#newInstance(java.lang.Object...)) phân biệt các điều kiện như lớp trừu tượng, enum, quyền truy cập, kiểu đối số và ngoại lệ trong thân constructor.

## 4. Chương trình đầy đủ: cùng một phân cấp, nhiều cách tạo

Ví dụ dưới đây có năm nhánh trực tiếp của `Message`:

- `Ping`: record có một thành phần.
- `Data`: lớp có constructor riêng tư và factory tĩnh.
- `Failure`: lớp trừu tượng sealed, dù có constructor công khai không tham số.
- `Provider`: interface non-sealed.
- `Mode`: enum có các hằng sẵn có.

Hai kiểu `NotFound` và `PluginMessage` là hậu duệ gián tiếp của `Message`.

Lưu mã vào `PermitsAndCreationDemo.java`:

~~~java
import java.lang.reflect.Modifier;
import java.util.Arrays;
import java.util.Comparator;
import java.util.Map;
import java.util.Objects;
import java.util.function.Function;

public class PermitsAndCreationDemo {
    public sealed interface Message
            permits Ping, Data, Failure, Provider, Mode {
        String describe();
    }

    public record Ping(String trace) implements Message {
        public Ping {
            trace = Objects.requireNonNull(trace, "trace").strip();
            if (trace.isEmpty()) {
                throw new IllegalArgumentException("Empty trace");
            }
        }

        @Override
        public String describe() {
            return "ping:" + trace;
        }
    }

    public static final class Data implements Message {
        private final String payload;

        private Data(String payload) {
            this.payload = payload;
        }

        public static Data of(String payload) {
            String normalized = Objects.requireNonNull(payload).strip();
            if (normalized.isEmpty()) {
                throw new IllegalArgumentException("Empty payload");
            }
            return new Data(normalized);
        }

        @Override
        public String describe() {
            return "data:" + payload;
        }
    }

    public static abstract sealed class Failure
            implements Message permits NotFound {
        public Failure() {
        }
    }

    public static final class NotFound extends Failure {
        private final String resource;

        public NotFound(String resource) {
            this.resource = Objects.requireNonNull(resource);
        }

        @Override
        public String describe() {
            return "missing:" + resource;
        }
    }

    public non-sealed interface Provider extends Message {
    }

    public static final class PluginMessage implements Provider {
        private final String payload;

        public PluginMessage(String payload) {
            this.payload = Objects.requireNonNull(payload);
        }

        @Override
        public String describe() {
            return "plugin:" + payload;
        }
    }

    public enum Mode implements Message {
        ON, OFF;

        @Override
        public String describe() {
            return "mode:" + name();
        }
    }

    static final Map<String, Function<Map<String, String>, Message>>
            FACTORIES = Map.of(
                    "ping", fields -> new Ping(required(fields, "trace")),
                    "data", fields -> Data.of(required(fields, "payload")),
                    "missing", fields ->
                            new NotFound(required(fields, "resource")),
                    "plugin", fields ->
                            new PluginMessage(required(fields, "payload")),
                    "mode", fields ->
                            Enum.valueOf(Mode.class, required(fields, "name")));

    static String required(Map<String, String> fields, String key) {
        String value = fields.get(key);
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("Missing field: " + key);
        }
        return value;
    }

    static Message create(String kind, Map<String, String> fields) {
        Objects.requireNonNull(kind, "kind");
        Objects.requireNonNull(fields, "fields");
        Function<Map<String, String>, Message> factory = FACTORIES.get(kind);
        if (factory == null) {
            throw new IllegalArgumentException("Unknown kind: " + kind);
        }
        return Objects.requireNonNull(
                factory.apply(Map.copyOf(fields)), "factory result");
    }

    static String kind(Class<?> type) {
        if (type.isInterface()) {
            return "interface";
        }
        if (type.isEnum()) {
            return "enum";
        }
        if (type.isRecord()) {
            return "record";
        }
        if (Modifier.isAbstract(type.getModifiers())) {
            return "abstract class";
        }
        return "class";
    }

    static boolean hasPublicNoArg(Class<?> type) {
        try {
            type.getConstructor();
            return true;
        } catch (NoSuchMethodException expected) {
            return false;
        }
    }

    static void showFailure(String label, Runnable action) {
        try {
            action.run();
            throw new AssertionError("Expected failure");
        } catch (IllegalArgumentException expected) {
            System.out.println(label + ": " + expected.getMessage());
        }
    }

    public static void main(String[] args)
            throws ReflectiveOperationException {
        Class<?>[] direct = Message.class.getPermittedSubclasses();
        Arrays.sort(direct, Comparator.comparing(Class::getSimpleName));
        for (Class<?> type : direct) {
            System.out.println(type.getSimpleName()
                    + " -> " + kind(type)
                    + "; publicNoArg=" + hasPublicNoArg(type));
        }

        System.out.println("Failure direct: "
                + Arrays.stream(Failure.class.getPermittedSubclasses())
                        .map(Class::getSimpleName)
                        .sorted()
                        .toList());
        System.out.println("Provider permitted is null: "
                + (Provider.class.getPermittedSubclasses() == null));
        System.out.println("PluginMessage is a Message: "
                + Message.class.isAssignableFrom(PluginMessage.class));
        System.out.println("PluginMessage directly permitted: "
                + Arrays.asList(direct).contains(PluginMessage.class));

        try {
            Failure.class.getConstructor().newInstance();
            throw new AssertionError("Abstract class instantiated");
        } catch (InstantiationException expected) {
            System.out.println("abstract newInstance: InstantiationException");
        }

        System.out.println("factory ping: "
                + create("ping", Map.of("trace", "T-1")).describe());
        System.out.println("factory data: "
                + create("data", Map.of("payload", " hello ")).describe());
        System.out.println("factory missing: "
                + create("missing", Map.of("resource", "/docs")).describe());
        System.out.println("factory plugin: "
                + create("plugin", Map.of("payload", "custom")).describe());
        Message mode = create("mode", Map.of("name", "ON"));
        System.out.println("factory mode: " + mode.describe());
        System.out.println("mode uses existing constant: " + (mode == Mode.ON));

        showFailure("unknown", () -> create("other", Map.of()));
        showFailure("missing input", () -> create("ping", Map.of()));
    }
}
~~~

Biên dịch và chạy với JDK 17 trở lên:

~~~bash
javac --release 17 -encoding UTF-8 PermitsAndCreationDemo.java
java PermitsAndCreationDemo
~~~

Kết quả chính xác:

~~~text
Data -> class; publicNoArg=false
Failure -> abstract class; publicNoArg=true
Mode -> enum; publicNoArg=false
Ping -> record; publicNoArg=false
Provider -> interface; publicNoArg=false
Failure direct: [NotFound]
Provider permitted is null: true
PluginMessage is a Message: true
PluginMessage directly permitted: false
abstract newInstance: InstantiationException
factory ping: ping:T-1
factory data: data:hello
factory missing: missing:/docs
factory plugin: plugin:custom
factory mode: mode:ON
mode uses existing constant: true
unknown: Unknown kind: other
missing input: Missing field: trace
~~~

Khi in thông tin nhánh trực tiếp, chương trình chủ động sắp xếp tên. Nó không dùng thứ tự mảng permitted làm thứ tự ưu tiên tạo đối tượng.

## 5. Đọc các giới hạn qua thí nghiệm

### 5.1. Có constructor công khai không tham số vẫn chưa đủ

Dòng:

~~~text
Failure -> abstract class; publicNoArg=true
~~~

cho biết `Failure` có một constructor công khai không tham số.

Tuy nhiên:

~~~java
Failure.class.getConstructor().newInstance();
~~~

ném `InstantiationException`, vì `Failure` là lớp trừu tượng. Constructor tồn tại để phục vụ việc khởi tạo phần lớp cha trong các đối tượng lớp con; nó không làm bản thân lớp trừu tượng trở thành lớp cụ thể.

Vì thế, kiểm tra “có constructor không tham số” không thể thay thế kiểm tra bản chất của kiểu và lựa chọn một lớp cụ thể.

### 5.2. Record cần dữ liệu thành phần

`Ping` không có constructor không tham số trong ví dụ. Nó cần `trace`.

Compact constructor còn chuẩn hóa và kiểm tra giá trị:

~~~java
public Ping {
    trace = Objects.requireNonNull(trace, "trace").strip();
    if (trace.isEmpty()) {
        throw new IllegalArgumentException("Empty trace");
    }
}
~~~

Đây là phần trích từ chương trình đầy đủ.

Permitted cho biết `Ping` là một nhánh trực tiếp hợp lệ. Nó không tự cho biết chuỗi `trace` trong yêu cầu lấy từ đâu hoặc chính sách khi chuỗi bị thiếu.

Nếu công cụ tạo record qua Reflection, nó cần xác định canonical constructor từ các thành phần, chuẩn bị đúng thứ tự và chuyển đổi đối số, rồi giữ logic kiểm tra của constructor. Quy tắc constructor record được mô tả tại [JLS §8.10.4](https://docs.oracle.com/javase/specs/jls/se21/html/jls-8.html#jls-8.10.4).

### 5.3. Lớp có thể công bố factory thay vì constructor

`Data` có constructor riêng tư và factory `Data.of(...)`. Factory chuẩn hóa payload bằng `strip()` và từ chối payload rỗng.

Danh sách permitted không đánh dấu rằng `of` là phương thức tạo cần dùng. Cũng không xác định được một factory chỉ bằng cách tìm phương thức tĩnh đầu tiên trả về kiểu phù hợp: một lớp có thể có nhiều phương thức tĩnh với vai trò khác nhau.

Trong ví dụ, chiến lược `data` đăng ký tường minh việc gọi `Data.of(...)`. Kết quả:

~~~text
factory data: data:hello
~~~

cho thấy chuỗi `" hello "` đã được xử lý qua factory.

Việc có thể tìm thấy một constructor riêng tư bằng Reflection không tự làm constructor đó thành hợp đồng khởi tạo mà công cụ nên chọn. Quyền truy cập và ý nghĩa API của mô hình cần được xem riêng.

### 5.4. Enum cần chọn hằng, không tạo một hằng mới

`Mode` là một kiểu con trực tiếp của `Message`, nhưng không phải một lớp để tạo instance mới theo cách thông thường.

Factory `mode` dùng:

~~~java
Enum.valueOf(Mode.class, required(fields, "name"))
~~~

để chọn hằng có tên khai báo tương ứng. Dòng kiểm tra:

~~~text
mode uses existing constant: true
~~~

xác nhận kết quả là chính `Mode.ON`, không phải một đối tượng enum mới.

Tài liệu [Enum.valueOf](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Enum.html#valueOf(java.lang.Class,java.lang.String)) quy định việc tra cứu hằng hiện có theo tên. Nếu không có hằng mang tên đó, đây là lỗi tra cứu; không nên dùng constructor Reflection làm nhánh “tạo bù”.

### 5.5. Nhánh gián tiếp vẫn thuộc họ kiểu

`Message` cho phép trực tiếp `Provider`; `Provider` là non-sealed. `PluginMessage` triển khai `Provider`, nên là một `Message` hợp lệ.

Kết quả:

~~~text
PluginMessage is a Message: true
PluginMessage directly permitted: false
~~~

không mâu thuẫn. Hai phép kiểm tra hỏi hai quan hệ khác nhau:

- `Message.class.isAssignableFrom(PluginMessage.class)` xét khả năng dùng một đối tượng kiểu đó như `Message`.
- Kiểm tra thành viên trong permitted của `Message` chỉ xét các nhánh trực tiếp được liệt kê.

Nếu một công cụ yêu cầu mọi kiểu tạo được phải nằm **trực tiếp** trong permitted của gốc, nó sẽ từ chối nhầm những hậu duệ gián tiếp như `NotFound` hoặc `PluginMessage`.

Ngược lại, chỉ có quan hệ assignable cũng chưa có nghĩa ứng dụng muốn công bố mọi hậu duệ đó cho người dùng. Chính sách đăng ký biến thể vẫn cần tồn tại.

## 6. Vì sao không chọn nhánh bằng thứ tự hoặc hình dạng dữ liệu?

Một cách làm dễ sai là duyệt permitted rồi thử tạo lần lượt:

~~~java
// Minh họa thuật toán không đủ điều kiện, không phải factory hoàn chỉnh.
for (Class<?> candidate : Message.class.getPermittedSubclasses()) {
    Object value = candidate.getDeclaredConstructor().newInstance();
}
~~~

Các vấn đề không chỉ là cần thêm một khối `try/catch`:

- Mảng permitted không có thứ tự ưu tiên được API cam kết.
- Interface và lớp trừu tượng không phải đích tạo trực tiếp.
- Một số lớp không có constructor không tham số.
- Enum không được tạo theo cách đó.
- Lớp dùng factory có quy tắc khởi tạo riêng.
- Thử chạy nhiều constructor có thể gây tác động phụ trước khi có kết quả cuối cùng.

Ngay cả khi dựa vào tên trường để đoán, dữ liệu vẫn có thể mơ hồ. Trong chương trình, cả biến thể `data` và `plugin` đều nhận khóa `payload`, nhưng có ý nghĩa và cách tạo khác nhau.

Không có đủ thông tin để quyết định chỉ từ:

~~~text
{payload: "..."}
~~~

Nếu chọn `Data` chỉ vì tên lớp được sắp trước `PluginMessage`, kết quả là một quy tắc tình cờ, không phải ý nghĩa mà dữ liệu yêu cầu.

Một giao thức có thể dùng **nhãn phân biệt biến thể (discriminator)**, chẳng hạn `kind = "data"` hoặc `kind = "plugin"`. Một hệ thống khác có thể chọn bằng ngữ cảnh hoặc cấu hình tường minh. Dù chọn cách nào, đó là một phần hợp đồng ứng dụng, không được suy ra đầy đủ từ `permits`.

## 7. Danh mục factory tường minh giải quyết phần còn thiếu

`FACTORIES` trong chương trình ánh xạ:

~~~text
nhãn biến thể -> chiến lược đọc đầu vào và trả về Message
~~~

| Nhãn | Chiến lược |
| --- | --- |
| `ping` | Đọc `trace`, gọi constructor record |
| `data` | Đọc `payload`, gọi factory tĩnh |
| `missing` | Đọc `resource`, tạo lớp cụ thể dưới nhánh trừu tượng |
| `plugin` | Đọc `payload`, tạo triển khai dưới nhánh non-sealed |
| `mode` | Đọc `name`, trả về hằng enum có sẵn |

Mỗi hàm được khai báo trả về `Message`, nên việc lắp ghép trong ví dụ đã được compiler kiểm tra về họ kiểu.

Lợi ích của cách tách này:

1. Nhãn có ý nghĩa đối với giao thức, không phụ thuộc tên nhị phân lớp Java.
2. Một biến thể có một chiến lược rõ ràng.
3. Dữ liệu thiếu được báo tại factory liên quan.
4. Biến thể không đăng ký bị từ chối rõ ràng.
5. Các hậu duệ gián tiếp có thể được hỗ trợ khi ứng dụng chủ động đăng ký.
6. Một chiến lược có thể tạo mới, gọi factory hoặc trả về đối tượng đã có.

Ví dụ không lấy một tên lớp tùy ý từ đầu vào rồi tự gọi `Class.forName` và thử mọi constructor. Danh mục trong mã xác định những biến thể mà ứng dụng hỗ trợ.

Ở công cụ có cơ chế đăng ký động, cần kiểm tra quan hệ kiểu khi đăng ký, chẳng hạn bằng `root.isAssignableFrom(candidate)` hoặc `candidate.asSubclass(root)`. Sau đó vẫn cần một chiến lược tạo cụ thể; quan hệ kiểu không thay thế chiến lược đó.

## 8. Permits vẫn có vai trò hữu ích

Không nên bỏ metadata sealed chỉ vì nó không giải quyết toàn bộ khởi tạo. Nó có thể hỗ trợ:

- Tạo tài liệu về các nhánh trực tiếp.
- Phát hiện một kiểu được đăng ký có quan hệ phân cấp ngoài dự kiến.
- Tổ chức các nhóm biến thể trong giao diện chọn.
- Kiểm tra độ bao phủ của một danh mục theo một chính sách đã được xác định.
- Phát hiện rằng một nhánh là sealed tiếp, final hoặc đã mở bằng non-sealed.

Tuy nhiên, khi nói “đã hỗ trợ đủ mọi biến thể”, phải xác định rõ phạm vi:

- Chỉ các nhánh trực tiếp hay các lớp cụ thể ở sâu hơn?
- Có tính một lớp trừu tượng là một biến thể tạo được không?
- Có đi tiếp vào nhánh sealed con không?
- Với nhánh non-sealed, danh mục là cố định theo cấu hình hay cho phép đăng ký thêm?
- Enum được tính theo kiểu enum hay theo các hằng của nó?
- Một lớp có nhiều factory hoặc nhiều chế độ cấu hình được tính thế nào?

Ngay cả khi mọi nhánh đều đóng và có thể duyệt hết một phân cấp hữu hạn, danh sách lớp vẫn không chứa đầy đủ dữ liệu đối số hoặc hợp đồng chọn factory.

Trong môi trường đóng gói hoặc class loader không cung cấp đủ các kiểu ghi trong metadata, cũng không nên xem một mảng Reflection ngắn hơn là bằng chứng rằng các nhánh còn lại không tồn tại trong bản thiết kế. Phải tách kết quả quan sát lúc chạy với hợp đồng phân cấp và cấu hình mà ứng dụng kỳ vọng.

## 9. Thiết kế quy trình tạo đối tượng theo từng trách nhiệm

Một quy trình cho công cụ ánh xạ hoặc đọc dữ liệu đa hình có thể là:

~~~text
1. Nhận kiểu gốc và dữ liệu
2. Đọc nhãn biến thể hoặc ngữ cảnh lựa chọn
3. Tìm chiến lược đã đăng ký
4. Kiểm tra schema và chuyển đổi dữ liệu
5. Chuẩn bị phụ thuộc hoặc đối số
6. Gọi constructor/factory hoặc lấy đối tượng hiện có
7. Kiểm tra kết quả và trả về theo kiểu gốc
~~~

Metadata sealed có thể được dùng khi lập kế hoạch hoặc kiểm tra quan hệ ở các bước trên. Nó không tự thực hiện những bước còn thiếu.

Trong ví dụ, `required(...)` kiểm tra các trường bắt buộc mà từng factory đọc. Những chính sách như từ chối trường dư, xử lý giá trị `null`, chuyển chuỗi thành số hoặc xác minh cấu trúc lồng nhau cần được bổ sung vào hợp đồng schema khi ứng dụng cần chúng.

Nếu lời gọi được thực hiện qua Reflection:

- Lấy đúng chữ ký constructor hoặc phương thức factory.
- Xem đúng quy tắc truy cập của lớp, package và module.
- Không coi `setAccessible(true)` là cách thay thế toàn bộ thiết kế tạo đối tượng.
- Giữ nguyên nhân khi constructor hoặc factory ném lỗi, thay vì thử nhánh khác một cách âm thầm.
- Không công bố đối tượng hợp lệ giả tạo khi dữ liệu chưa đáp ứng điều kiện của mô hình.

Lỗi thiếu dữ liệu và lỗi chọn biến thể nên được phát hiện trước khi chạy mã khởi tạo. Lỗi do mã khởi tạo thực thi vẫn có thể xảy ra; metadata không chứng minh rằng một constructor hoặc factory sẽ luôn thành công.

## 10. Tự kiểm tra

1. Một lớp có mặt trong permitted và có constructor công khai không tham số. Điều đó đủ để khẳng định tạo instance thành công chưa?
2. Vì sao `Failure` trong chương trình có `publicNoArg=true` nhưng `newInstance()` thất bại?
3. Vì sao `Ping` không có constructor không tham số vẫn là một biến thể hợp lệ?
4. Nếu `Data` công bố `Data.of(...)`, permitted có tự chỉ ra phương thức đó không?
5. `PluginMessage` không nằm trực tiếp trong permitted của `Message`. Vì sao nó vẫn là một `Message`?
6. Với enum `Mode`, chiến lược `mode` tạo một đối tượng mới hay chọn hằng hiện có?
7. Nếu hai biến thể cùng nhận khóa `payload`, có thể chọn đúng chỉ bằng cách sắp xếp tên lớp không?
8. Nếu mọi nhánh của phân cấp đều đóng, có thể bỏ hoàn toàn schema đối số và chính sách factory không?
9. Vì sao không nên bắt mọi lỗi khởi tạo rồi tự thử nhánh tiếp theo?
10. Kiểm tra assignable có tự có nghĩa là ứng dụng phải cho phép công bố kiểu đó qua giao thức không?

Đáp án:

1. Chưa. Còn bản chất kiểu, quyền truy cập, điều kiện khởi tạo và hành vi constructor.
2. Nó là lớp trừu tượng; constructor tồn tại không cho phép tạo trực tiếp instance của chính lớp đó.
3. Nó được khai báo là nhánh hợp lệ; việc tạo cần đối số `trace` cho constructor record.
4. Không. Factory cần được xác định bằng cấu hình, đăng ký hoặc hợp đồng rõ ràng.
5. Nó triển khai `Provider`, là một nhánh non-sealed trực tiếp của `Message`.
6. Chọn hằng hiện có; chương trình xác nhận kết quả là chính `Mode.ON`.
7. Không. Cần nhãn phân biệt hoặc một quy tắc chọn có ý nghĩa.
8. Không. Đóng phân cấp không cung cấp đầy đủ dữ liệu hay ý nghĩa khởi tạo.
9. Có thể chọn sai biến thể, che mất lỗi dữ liệu và gây tác động phụ từ các lần thử trước.
10. Không. Quan hệ kiểu và danh mục biến thể được ứng dụng hỗ trợ là hai quyết định khác nhau.
