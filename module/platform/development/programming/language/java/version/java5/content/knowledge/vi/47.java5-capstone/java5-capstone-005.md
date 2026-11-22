# Kiểm tra cấu hình bằng annotation lúc chạy

## 1. Annotation mô tả quy tắc, bộ kiểm tra mới thực thi quy tắc

Giả sử ứng dụng cần một endpoint không được rỗng, cổng nằm trong khoảng cho phép và timeout có giới hạn. Nếu rải các điều kiện kiểm tra ở nhiều nơi sử dụng, lỗi cấu hình có thể chỉ xuất hiện khi hệ thống bắt đầu xử lý yêu cầu.

Một cách tổ chức là đặt metadata quy tắc gần trường cấu hình:

```java
@Required
public final String endpoint;

@IntRange(min = 1, max = 65535)
public final int port;
```

Đây là đoạn khai báo minh họa, chưa phải chương trình độc lập. `@Required` và `@IntRange` là annotation tự định nghĩa trong bài, không phải annotation có sẵn của JDK hoặc thư viện khác.

Annotation không tự chạy một lệnh `if`. Ứng dụng cần một bộ kiểm tra đọc metadata, đọc giá trị trên đối tượng và tạo kết quả. Luồng hợp lý là:

```text
Đọc nguồn cấu hình
  -> phân tích/chuyển đổi sang kiểu dữ liệu
  -> tạo đối tượng cấu hình ứng viên
  -> kiểm tra quy tắc
  -> chỉ công bố/sử dụng nếu hợp lệ
```

Mục tiêu của bài là thực hành cơ chế runtime annotation và reflection trên Java 17+, không xây dựng toàn bộ một framework kiểm tra cấu hình.

## 2. Retention và Target quyết định khả năng đọc metadata

Muốn đọc annotation bằng reflection lúc chạy, khai báo `@Retention(RetentionPolicy.RUNTIME)`. Nếu không khai báo retention, mặc định là `CLASS`; annotation có thể có trong class file nhưng không có hợp đồng để phản chiếu đọc nó lúc chạy. `SOURCE` không giữ annotation trong class file. [API Retention](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/annotation/Retention.html), [RetentionPolicy](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/annotation/RetentionPolicy.html).

`@Target(ElementType.FIELD)` giới hạn chỗ được đặt annotation vào trường. Trình biên dịch kiểm tra giới hạn ngữ cảnh này. Nhưng nó không tự biết `@IntRange` của bài chỉ hỗ trợ `int`, hoặc `min` không được lớn hơn `max`; đó là hợp đồng do bộ kiểm tra thực thi. [API Target](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/annotation/Target.html).

Ví dụ khai báo:

```java
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.FIELD)
public @interface IntRange {
    int min();
    int max();
}
```

Các phần tử annotation chứa metadata quy tắc. Giá trị cổng hay timeout của từng môi trường vẫn nằm trong đối tượng cấu hình. Không đặt mật khẩu hoặc token của môi trường vào annotation trong mã nguồn.

## 3. Định nghĩa rõ phạm vi trước khi viết reflection

Bài thực hành chọn hợp đồng nhỏ, có thể kiểm tra được:

| Thành phần | Quy tắc |
| --- | --- |
| `@Required` | Chỉ dùng cho trường `String`; từ chối `null`, rỗng và toàn khoảng trắng theo `String.isBlank()` |
| `@IntRange` | Chỉ dùng cho trường `int`; kiểm tra khoảng đóng từ `min` tới `max` |
| Trường được kiểm tra | Các trường khai báo trực tiếp trong `AppConfig` |
| Cách truy cập | Trường instance `public`, chỉ đọc, không sửa giá trị |
| Kết quả lỗi dữ liệu | Danh sách mô tả trường và quy tắc vi phạm, không in giá trị cấu hình |
| Lỗi định nghĩa quy tắc | Dừng bằng lỗi rõ ràng, không bỏ qua |

`endpoint` trong ví dụ chỉ được kiểm tra không rỗng, chưa kiểm tra cú pháp URI, scheme hoặc khả năng kết nối. Khoảng cổng và timeout là yêu cầu minh họa của ứng dụng này; không phải giới hạn chung cho mọi ứng dụng Java.

Giới hạn tường minh tốt hơn một bộ kiểm tra có vẻ tổng quát nhưng âm thầm bỏ qua kiểu dữ liệu hoặc trường mà nó chưa hiểu.

## 4. Chương trình Java 17+ chạy độc lập

Lưu thành `RuntimeConfigDemo.java`:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.Field;
import java.lang.reflect.Modifier;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Comparator;
import java.util.List;
import java.util.Objects;

public class RuntimeConfigDemo {
    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.FIELD)
    public @interface Required {}

    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.FIELD)
    public @interface IntRange {
        int min();
        int max();
    }

    public static final class AppConfig {
        @Required
        public final String endpoint;
        @IntRange(min = 1, max = 65535)
        public final int port;
        @IntRange(min = 100, max = 30000)
        public final int timeoutMillis;

        public AppConfig(String endpoint, int port, int timeoutMillis) {
            this.endpoint = endpoint;
            this.port = port;
            this.timeoutMillis = timeoutMillis;
        }
    }

    static List<String> validate(AppConfig config) {
        Objects.requireNonNull(config, "config");
        List<String> errors = new ArrayList<>();
        Field[] fields = AppConfig.class.getDeclaredFields();
        Arrays.sort(fields, Comparator.comparing(Field::getName));
        for (Field field : fields) {
            Required required = field.getAnnotation(Required.class);
            IntRange range = field.getAnnotation(IntRange.class);
            if (required == null && range == null) continue;
            if (Modifier.isStatic(field.getModifiers())
                    || !Modifier.isPublic(field.getModifiers())) {
                throw new IllegalStateException("Unsupported field: " + field.getName());
            }
            if (required != null && field.getType() != String.class) {
                throw new IllegalStateException("Required needs String: " + field.getName());
            }
            if (range != null && (field.getType() != int.class || range.min() > range.max())) {
                throw new IllegalStateException("Invalid range rule: " + field.getName());
            }
            try {
                if (required != null) {
                    String value = (String) field.get(config);
                    if (value == null || value.isBlank()) {
                        errors.add(field.getName() + ": must not be blank");
                    }
                }
                if (range != null) {
                    int value = field.getInt(config);
                    if (value < range.min() || value > range.max()) {
                        errors.add(field.getName() + ": must be between "
                                + range.min() + " and " + range.max());
                    }
                }
            } catch (IllegalAccessException accessFailure) {
                throw new IllegalStateException("Cannot inspect " + field.getName(), accessFailure);
            }
        }
        return List.copyOf(errors);
    }

    public static void main(String[] args) {
        AppConfig valid = new AppConfig("https://example.com", 443, 3000);
        System.out.println("valid=" + validate(valid));
        AppConfig invalid = new AppConfig(" ", 70000, 0);
        validate(invalid).forEach(System.out::println);
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 RuntimeConfigDemo.java
java RuntimeConfigDemo
```

Stdout:

```text
valid=[]
endpoint: must not be blank
port: must be between 1 and 65535
timeoutMillis: must be between 100 and 30000
```

Chương trình không đọc file môi trường, không mở kết nối và không thay đổi cấu hình. Nó tạo hai đối tượng trong bộ nhớ để quan sát bộ kiểm tra. Danh sách rỗng cho biết không vi phạm những quy tắc đã được triển khai, không có nghĩa đối tượng đáp ứng mọi yêu cầu vận hành có thể có.

## 5. Bộ kiểm tra đọc gì và theo thứ tự nào?

`AppConfig.class.getDeclaredFields()` lấy các trường được khai báo trực tiếp trên lớp đã chọn. `Field.getAnnotation(...)` trả annotation tương ứng hoặc `null` nếu không có. `Field.get(...)` và `getInt(...)` đọc giá trị trên đối tượng được truyền vào. Đây là bước nối metadata của lớp với dữ liệu của một instance. [API Field](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/reflect/Field.html).

Không nên phụ thuộc thứ tự trường mà reflection trả về. Ví dụ sắp xếp theo tên trước khi tạo lỗi để stdout và kết quả kiểm tra có thứ tự ổn định. Đây là lựa chọn trình bày của bộ kiểm tra, không phải thứ tự khai báo được API bảo đảm. [Class.getDeclaredFields](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Class.html#getDeclaredFields()).

Các bước chính trong vòng lặp:

1. Đọc hai annotation mà bộ kiểm tra hiểu.
2. Bỏ qua trường không có các quy tắc đó theo hợp đồng bài học.
3. Kiểm tra metadata quy tắc: phạm vi truy cập, static/instance, kiểu dữ liệu và khoảng hợp lệ.
4. Đọc giá trị và áp dụng điều kiện.
5. Thu thập lỗi dữ liệu, sau đó trả danh sách không sửa được qua API danh sách trả về.

`List.copyOf(errors)` không làm các đối tượng cấu hình tự bất biến. Trong chương trình, cấu hình có lớp `final`, các trường `final` và giá trị chỉ là `String`/`int`; đây là cách thiết kế snapshot đơn giản, không phải hiệu ứng do annotation tạo ra.

## 6. Phân biệt lỗi dữ liệu với lỗi quy tắc

Hai loại lỗi cần cách xử lý khác nhau:

| Loại | Ví dụ | Cách xử lý trong bài |
| --- | --- | --- |
| Dữ liệu môi trường không hợp lệ | Endpoint trống, cổng 70000, timeout 0 | Thu thập lỗi để người vận hành sửa cùng một lượt |
| Metadata quy tắc sai | `@IntRange(min = 100, max = 1)` | Dừng vì định nghĩa bộ quy tắc không hợp lệ |
| Quy tắc gắn sai kiểu | `@Required` trên `int` hoặc `@IntRange` trên `String` | Dừng với thông báo nêu tên trường |
| Không có quyền đọc theo hợp đồng | Không thể truy cập trường cấu hình | Báo lỗi truy cập, không coi là hợp lệ |

Nếu bắt mọi ngoại lệ rồi trả danh sách rỗng, một lỗi reflection có thể làm ứng dụng hiểu nhầm cấu hình đã qua kiểm tra. Nếu đổi sai kiểu thành “không cần kiểm tra”, lỗi khai báo quy tắc có thể bị giấu đi.

Ngược lại, lỗi giá trị của nhiều trường có thể được gom để giảm vòng sửa–khởi động lại. Danh sách lỗi chỉ chứa tên trường và điều kiện, tránh vô tình ghi endpoint có thông tin nhạy cảm hoặc một trường bí mật mở rộng sau này.

## 7. Kiểm tra trước khi công bố cấu hình

Đoạn tích hợp định hướng:

```java
List<String> errors = validate(candidate);
if (!errors.isEmpty()) {
    throw new IllegalStateException("Invalid configuration: " + String.join("; ", errors));
}
// Chỉ từ đây mới cung cấp candidate cho các thành phần sử dụng.
```

Đây là đoạn minh họa trong phạm vi có `candidate` là `AppConfig` và có phương thức `validate` của chương trình. Trong ví dụ đầy đủ, `main` chỉ in lỗi để học cơ chế; ứng dụng thật phải quyết định dừng khởi động hoặc từ chối bản cấu hình mới khi có lỗi.

Phân tích chuỗi nguồn và kiểm tra ràng buộc là hai bước khác nhau. Nếu nguồn chứa `port=abc`, bước chuyển sang `int` đã thất bại trước khi kiểm tra khoảng. Đừng mô tả lỗi ấy là “cổng ngoài khoảng” nếu thực tế chưa có giá trị số hợp lệ.

Với cơ chế tải lại cấu hình, tạo snapshot ứng viên, kiểm tra toàn bộ, rồi thay thế snapshot đang dùng theo cách đồng bộ phù hợp. Nếu ứng viên không hợp lệ, giữ bản đang hoạt động theo chính sách. Không lần lượt ghi một nửa số trường của cấu hình mới vào đối tượng dùng chung rồi mới phát hiện lỗi ở trường cuối.

## 8. Quyền truy cập reflection và module hiện đại

Bài dùng trường `public` để tập trung vào đọc annotation và giá trị, không yêu cầu tắt kiểm tra truy cập. Đây là lựa chọn tối giản cho bài học, không phải yêu cầu mọi mô hình cấu hình trong sản phẩm phải có public field.

Nếu chuyển bộ kiểm tra sang đọc trường `private`, phải xác định hợp đồng truy cập. `setAccessible(true)` không bảo đảm luôn thành công, đặc biệt khi lớp nằm trong module khác và package không mở cho phía đọc. `trySetAccessible()` có thể báo không thể mở quyền; không được bỏ qua tình huống đó rồi coi dữ liệu đã được kiểm tra. [AccessibleObject](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/reflect/AccessibleObject.html).

Một phương án khác là bộ kiểm tra dùng accessor công khai hoặc điểm tích hợp mà lớp cấu hình cung cấp. Với ứng dụng có nhiều module, lựa chọn điểm truy cập cần được thiết kế phù hợp thay vì mở quyền toàn cục chỉ để tránh một lỗi reflection.

Bộ kiểm tra trong bài chỉ đọc. Không dùng reflection để thay đổi trường `final`, ép một giá trị sai về mặc định rồi gọi đó là “kiểm tra thành công”. Nếu có bước chuẩn hóa hoặc áp dụng mặc định, thực hiện rõ ràng trước kiểm tra và giữ nguyên ý nghĩa nghiệp vụ.

## 9. Kế thừa, đối tượng lồng nhau và annotation ở vị trí khác

Ví dụ chủ động giới hạn `AppConfig` là lớp `final` và quét đúng lớp đó. Nó không phải bộ quét mọi lớp con hoặc cây cấu hình bất kỳ.

Nếu mở rộng, phải quyết định rõ:

| Phạm vi mới | Quy tắc cần bổ sung |
| --- | --- |
| Trường ở lớp cha | Có duyệt chuỗi superclass không? Xử lý trường trùng tên thế nào? |
| Đối tượng cấu hình lồng nhau | Có kiểm tra đệ quy không? Đường dẫn lỗi và chu trình được xử lý ra sao? |
| Getter hoặc record component | Annotation được đặt và đọc ở đâu? Có trùng kiểm tra qua nhiều vị trí không? |
| Kiểu wrapper như `Integer` | `null` nghĩa là thiếu bắt buộc hay giá trị tùy chọn? |
| Nhiều quy tắc trên một trường | Thứ tự, số lỗi và cách xử lý quy tắc không tương thích là gì? |

`@Inherited` không tự làm annotation trên field được kế thừa theo mọi cách quét; meta-annotation ấy có phạm vi đối với annotation trên khai báo lớp. Không thêm nó rồi cho rằng `getDeclaredFields()` sẽ trả trường lớp cha. [API Inherited](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/annotation/Inherited.html).

Một annotation có `@Target(FIELD)` cũng không tự xuất hiện trên getter hay record component bất kể cách đọc. Mở rộng vị trí đích cần đi kèm thay đổi bộ kiểm tra và ca kiểm chứng tương ứng.

## 10. Ràng buộc giữa các trường cần điểm kiểm tra phù hợp

Quy tắc `timeoutMillis` nằm trong khoảng là quy tắc của một trường. Quy tắc “khi bật kết nối từ xa thì endpoint phải là HTTPS và phải có thông tin xác thực phù hợp” phụ thuộc nhiều trường và ngữ cảnh.

Không cố nhét mọi quan hệ vào một annotation đơn giản chỉ đọc giá trị riêng lẻ. Có thể thêm một bước kiểm tra toàn đối tượng hoặc một kiểu quy tắc cấp lớp, miễn là điểm chạy và nguồn dữ liệu rõ ràng. Giữ kiểm tra khả năng kết nối mạng tách khỏi kiểm tra hình dạng cấu hình nếu ứng dụng cần phân biệt sai dữ liệu với phụ thuộc tạm thời không sẵn sàng.

Tương tự, annotation kiểm tra chuỗi không thay cho xác minh quyền sử dụng một bí mật hoặc danh tính của dịch vụ từ xa. Phạm vi kiểm tra phải được nói đúng để kết quả “hợp lệ” không bị hiểu rộng hơn điều đã thực hiện.

## 11. Hiệu năng và vòng đời metadata

Cấu hình thường được kiểm tra khi khởi động hoặc tải lại, nên tính đúng đắn và thông báo lỗi thường quan trọng hơn tối ưu từng lần đọc reflection. Đừng quét toàn bộ classpath hoặc mọi đối tượng ứng dụng chỉ để kiểm tra một lớp cấu hình đã biết.

Nếu có nhu cầu kiểm tra lặp lại ở tần suất cao, có thể tách bước đọc/kiểm tra metadata của lớp khỏi bước áp dụng lên từng instance. Khi lưu metadata để dùng lại, phải xét vòng đời class/classloader và cách công bố an toàn. Không lưu giá trị cấu hình cũ trong cache metadata rồi áp nhầm sang đối tượng mới.

Bài thực hành không cần một cache hoặc cơ chế plugin validator tổng quát. Khi dự án đã có cơ chế kiểm tra chuẩn hóa, nên tích hợp theo kiến trúc sẵn có; ví dụ tự viết ở đây phục vụ hiểu cách annotation lúc chạy được đọc và thực thi.

## 12. Ca tự kiểm tra có ý nghĩa

| Tình huống | Kỳ vọng theo bộ kiểm tra của bài |
| --- | --- |
| Endpoint hợp lệ theo quy tắc không rỗng, port 443, timeout 3000 | Không có lỗi dữ liệu |
| Endpoint `null`, rỗng hoặc toàn khoảng trắng | Báo lỗi bắt buộc |
| Port đúng 1 hoặc 65535 | Hợp lệ theo khoảng đóng |
| Port 0 hoặc 65536 | Báo ngoài khoảng |
| Timeout đúng 100 hoặc 30000 | Hợp lệ theo khoảng đóng |
| `min > max` trong annotation | Lỗi định nghĩa quy tắc, không báo cấu hình hợp lệ |
| Đặt annotation trên kiểu không được hỗ trợ | Lỗi định nghĩa rõ ràng |
| Bỏ `Retention(RUNTIME)` khỏi annotation | Kiểm tra khả năng đọc metadata; không coi việc annotation biến mất là dữ liệu đã được xác nhận |

Bài tập mở rộng: thêm quy tắc kiểm tra endpoint có scheme được phép mà không thực hiện kết nối mạng. Ghi rõ kiểu dữ liệu được hỗ trợ, cách xử lý `null`, thông báo lỗi và điểm thực thi. Sau đó kiểm tra rằng lỗi không in nguyên giá trị endpoint hoặc thông tin bí mật có thể đi kèm.

Điểm cốt lõi của mô hình là sự phối hợp giữa metadata, một bộ thực thi có hợp đồng rõ ràng và thời điểm kiểm tra trước khi dùng cấu hình. Chỉ thêm annotation vào trường mà không có bước thực thi chưa tạo ra cơ chế kiểm tra lúc chạy.
