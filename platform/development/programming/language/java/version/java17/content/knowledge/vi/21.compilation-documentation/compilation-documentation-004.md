# Cảnh báo javac, -Xlint và xử lý cảnh báo có căn cứ

## 1. Vì sao cần quan tâm đến compiler warnings?

Trình biên dịch Java không chỉ kiểm tra cú pháp và kiểu dữ liệu. Trong quá trình biên dịch, `javac` còn có thể phát hiện những mẫu code đáng ngờ: dùng raw type, ép kiểu không được kiểm chứng, gọi API đã deprecated, bỏ quên `serialVersionUID`, tạo generic varargs không an toàn hoặc dùng tài nguyên mà không tham chiếu trong thân `try`.

Những trường hợp đó có thể vẫn biên dịch thành công, nhưng cảnh báo cho biết code có rủi ro về tính đúng đắn, khả năng tương thích, bảo trì hoặc vận hành. Xử lý cảnh báo có căn cứ nghĩa là:

1. Hiểu chính xác điều kiện khiến compiler phát cảnh báo.
2. Xác định rủi ro thực tế trong ngữ cảnh code.
3. Sửa nguyên nhân nếu có thể.
4. Chỉ suppress khi có invariant hoặc lý do kỹ thuật kiểm chứng được.
5. Giữ quy trình build đủ nghiêm để cảnh báo mới không âm thầm tích lũy.

Trong Java 17, các công cụ chính là:

- `javac`: compiler của JDK.
- `-Xlint`: bật các nhóm cảnh báo chi tiết.
- `-Xlint:<key>`: bật một nhóm cụ thể.
- `-Xlint:all`: bật toàn bộ các nhóm lint được compiler hỗ trợ.
- `-Werror`: coi warning là lỗi biên dịch.
- `@SuppressWarnings`: suppress warning có phạm vi và lý do rõ ràng.
- `--release 17`: biên dịch theo ngôn ngữ, bytecode và API nền tảng của Java 17.

Compiler warning là tín hiệu để điều tra. Không nên bỏ qua tất cả cảnh báo, cũng không nên suppress hàng loạt chỉ để build xanh.

## 2. Cách javac phát ra cảnh báo

### 2.1. Warning khác error

**Error** ngăn compiler tạo class output thành công cho compilation unit liên quan. **Warning** cho biết compiler phát hiện một vấn đề đáng chú ý nhưng vẫn có thể tiếp tục biên dịch.

Ví dụ:

```shell
javac Example.java
```

Compiler có thể hiển thị warning và vẫn tạo file `.class`. Nếu thêm `-Werror`, warning được nâng thành lỗi và build thất bại:

```shell
javac -Werror Example.java
```

`-Werror` không tự bật mọi nhóm lint. Để build nghiêm ngặt với các nhóm lint, thường kết hợp:

```shell
javac -Xlint:all -Werror Example.java
```

### 2.2. Cấu trúc một diagnostic

Một cảnh báo thường có dạng:

```text
Example.java:12: warning: [unchecked] unchecked conversion
    List<String> names = rawNames;
                         ^
  required: List<String>
  found:    List
1 warning
```

Đọc theo thứ tự:

- File và dòng: vị trí compiler phát hiện vấn đề.
- Loại diagnostic: `warning`.
- Lint key trong ngoặc vuông: `unchecked`.
- Thông điệp: điều gì đang không được compiler xác minh.
- Source line và dấu mũ: vị trí liên quan.
- Phần required/found: kiểu mong muốn và kiểu thực tế nếu có.

Lint key rất hữu ích khi cần bật hoặc suppress có mục tiêu. Không nên chỉ tìm cách làm biến mất dòng warning mà bỏ qua thông tin kiểu dữ liệu hoặc API gây ra nó.

### 2.3. Mức cảnh báo mặc định và -Xlint

Không phải mọi nhóm lint đều được bật mặc định trong mọi trường hợp. `-Xlint` hoặc `-Xlint:all` giúp compiler báo thêm các vấn đề mà chế độ mặc định có thể không hiển thị.

Ví dụ:

```shell
# Biên dịch với các cảnh báo mặc định.
javac --release 17 -d out src/com/acme/*.java

# Bật toàn bộ nhóm lint.
javac --release 17 -Xlint:all -d out src/com/acme/*.java
```

Tên và chi tiết của một số lint category có thể phụ thuộc phiên bản javac. Khi dự án chuẩn hóa Java 17, hãy tham khảo tài liệu javac của JDK 17 và dùng cùng toolchain trong CI.

## 3. Chọn nhóm cảnh báo bằng -Xlint

### 3.1. Cú pháp

Các dạng thường dùng:

```shell
javac -Xlint:all Example.java
javac -Xlint:unchecked Example.java
javac -Xlint:deprecation Example.java
javac -Xlint:all,-serial Example.java
```

- `-Xlint:all`: bật tất cả nhóm lint.
- `-Xlint:unchecked`: bật cảnh báo unchecked operation.
- `-Xlint:deprecation`: cảnh báo khi dùng API deprecated.
- `-Xlint:all,-serial`: bật tất cả rồi tắt riêng nhóm `serial`.

Cú pháp danh sách cho phép kết hợp nhiều key, phân cách bằng dấu phẩy. Có thể bật hoặc tắt key bằng dấu `-` trước tên key.

### 3.2. Không dùng disable rộng làm chính sách lâu dài

Ví dụ sau làm giảm khả năng phát hiện vấn đề:

```shell
javac -Xlint:none ...
```

Nếu dự án có một category legacy chưa thể xử lý ngay, có thể tạm thời loại trừ đúng category đó:

```shell
javac -Xlint:all,-deprecation ...
```

Nhưng cần ghi nhận lý do, phạm vi module và kế hoạch loại bỏ ngoại lệ. Không nên tắt `all` chỉ vì một warning cụ thể chưa được xử lý.

### 3.3. Các lint key thường gặp

Bảng dưới đây mô tả các nhóm thường hữu ích khi làm việc với code Java 17. Danh sách không nhằm thay thế tài liệu chính thức của đúng bản javac đang dùng.

| Lint key | Vấn đề compiler cảnh báo | Hướng xử lý thường gặp |
|---|---|---|
| `unchecked` | Thao tác generic không được kiểm chứng đầy đủ | Dùng generic type an toàn, kiểm tra dữ liệu ở boundary |
| `rawtypes` | Dùng generic class mà bỏ type argument | Khai báo `List<String>`, `Map<K,V>` |
| `deprecation` | Dùng API đã deprecated | Chuyển sang API thay thế, kiểm tra tài liệu |
| `removal` | Dùng API được đánh dấu dự kiến loại bỏ | Ưu tiên migration sớm |
| `serial` | Serializable class thiếu khai báo serialization metadata thường dùng | Quyết định serialization contract và khai báo UID khi phù hợp |
| `cast` | Ép kiểu dư thừa hoặc không cần thiết | Xóa cast hoặc sửa kiểu ở nguồn |
| `fallthrough` | Switch case có thể rơi xuống case kế tiếp | Thêm break/return hoặc comment giải thích intentional fall-through |
| `finally` | finally block không thể hoàn tất bình thường | Không return/throw từ finally để ghi đè luồng điều khiển |
| `try` | Vấn đề liên quan try-with-resources | Quản lý resource và vòng đời rõ ràng |
| `static` | Truy cập static member qua instance expression | Dùng tên class |
| `varargs` | Nguy cơ heap pollution với generic varargs | Dùng `@SafeVarargs` khi thật sự chứng minh được an toàn |
| `overloads` | Overload có thể gây nhầm lẫn hoặc mơ hồ | Thiết kế signature dễ phân biệt |
| `path` | Classpath/module path có phần tử không hợp lệ hoặc không tồn tại | Sửa cấu hình dependency/path |
| `options` | Compiler option không phù hợp hoặc dùng sai | Chuẩn hóa JDK và compiler arguments |
| `processing` | Vấn đề liên quan annotation processing | Kiểm tra processor và cấu hình build |
| `auxiliaryclass` | Truy cập auxiliary class từ source file khác | Đưa top-level class vào file riêng |
| `preview` | Sử dụng preview feature/API | Bật preview có chủ đích và đúng JDK |
| `strictfp` | Modifier strictfp không cần thiết trong ngữ cảnh Java 17 | Bỏ modifier dư thừa |

Một số category khác liên quan module declaration, exported API, class file hoặc annotation. Khi cần dùng key cụ thể, hãy tra danh sách của `javac --help-lint` trong JDK 17:

```shell
javac --help-lint
```

## 4. Cảnh báo rawtypes và unchecked

### 4.1. Raw type làm mất kiểm tra kiểu

Raw type là cách dùng generic class mà không chỉ định type argument:

```java
import java.util.ArrayList;
import java.util.List;

List names = new ArrayList();
names.add("An");
names.add(42);
```

Compiler không thể bảo đảm danh sách chỉ chứa String. Lỗi có thể xuất hiện muộn khi code đọc và cast phần tử:

```java
String first = (String) names.get(1); // ClassCastException lúc chạy
```

### 4.2. Sửa bằng generic type

```java
List<String> names = new ArrayList<>();
names.add("An");
names.add("Bình");

String first = names.get(0);
```

Compiler kiểm tra kiểu phần tử tại compile time và code không cần cast khi đọc.

### 4.3. Unchecked conversion

Một ví dụ khác:

```java
List raw = obtainLegacyList();
List<String> names = raw; // unchecked conversion
```

Compiler không biết các phần tử thực tế có phải String hay không. Thêm type argument vào biến đích không làm dữ liệu nguồn trở nên an toàn.

Nếu boundary cũ trả về dữ liệu không có type information, hãy chuyển đổi và kiểm tra từng phần tử:

```java
static List<String> toStrings(List<?> source) {
    List<String> result = new ArrayList<>();
    for (Object item : source) {
        if (!(item instanceof String value)) {
            throw new IllegalArgumentException(
                    "Expected String but got: " +
                    (item == null ? "null" : item.getClass().getName())
            );
        }
        result.add(value);
    }
    return List.copyOf(result);
}
```

Đoạn code trên xác thực dữ liệu runtime thay vì suppress warning. Nếu null được phép, điều chỉnh contract và kiểm tra null riêng; ví dụ hiện tại cố ý từ chối null.

### 4.4. Phân biệt rawtypes và unchecked

- `rawtypes`: cảnh báo về cách khai báo hoặc sử dụng generic type không có type argument.
- `unchecked`: cảnh báo về thao tác mà compiler không thể xác minh an toàn, chẳng hạn unchecked conversion hoặc cast.

Một dòng code có thể tạo cả hai loại cảnh báo. Sửa bằng generic type thường loại bỏ cả hai.

### 4.5. Khi nào unchecked cast có thể chấp nhận?

Đôi khi một API generic cũ không thể biểu diễn đầy đủ type contract. Nếu cast không thể loại bỏ, cần chứng minh invariant bên ngoài compiler bảo đảm kiểu dữ liệu.

Ví dụ một registry nội bộ lưu object theo class token:

```java
import java.util.HashMap;
import java.util.Map;

final class ServiceRegistry {
    private final Map<Class<?>, Object> services = new HashMap<>();

    <T> void register(Class<T> type, T instance) {
        services.put(type, type.cast(instance));
    }

    <T> T lookup(Class<T> type) {
        Object value = services.get(type);
        return value == null ? null : type.cast(value);
    }
}
```

Trong ví dụ này, `Class.cast` giúp kiểm tra kiểu runtime mà không cần unchecked cast. Đây thường là lựa chọn tốt hơn suppress warning.

Nếu dùng một cấu trúc dữ liệu mà generic type không thể kiểm tra bằng class token, có thể cần một cast được bảo vệ bởi invariant mạnh hơn. Khi đó:

- Chứng minh invariant ở nơi dữ liệu được ghi vào cấu trúc.
- Giữ cấu trúc encapsulated, không cho code ngoài thêm dữ liệu sai kiểu.
- Đặt `@SuppressWarnings("unchecked")` đúng tại biến hoặc method nhỏ nhất có thể.
- Viết test cho invariant.
- Ghi chú lý do kỹ thuật, không ghi chú chung chung như “compiler warning”.

## 5. Cảnh báo deprecation và removal

### 5.1. Deprecated có nghĩa API không còn được khuyến nghị

API có thể được đánh dấu:

```java
@Deprecated
public void oldOperation() {
}
```

Điều đó báo cho caller biết API không còn được khuyến nghị. API có thể vẫn tồn tại và hoạt động, nhưng người dùng nên xem tài liệu để biết lựa chọn thay thế và kế hoạch tương thích.

Ví dụ:

```java
class LegacyClient {
    @Deprecated
    void connectOldWay() {
    }

    void connect() {
        connectOldWay(); // deprecation warning
    }
}
```

### 5.2. since và forRemoval

Java hỗ trợ metadata:

```java
@Deprecated(since = "17", forRemoval = true)
public void oldOperation() {
}
```

- `since`: phiên bản mà API được đánh dấu deprecated.
- `forRemoval = true`: cho biết API được dự kiến loại bỏ trong tương lai.

Compiler có thể phát warning thuộc nhóm `deprecation` hoặc `removal` tùy annotation/API. Đây là tín hiệu khác nhau về mức độ ưu tiên migration.

### 5.3. Kiểm tra API thay thế

Khi gặp warning:

1. Mở Javadoc của API.
2. Đọc mô tả `@Deprecated` và `@deprecated`.
3. Tìm API thay thế được khuyến nghị.
4. Kiểm tra khác biệt về semantics, exception, threading và resource lifecycle.
5. Chuyển đổi và chạy test tương ứng.

Không thay thế máy móc chỉ vì tên API mới gần giống tên cũ. API mới có thể thay đổi behavior hoặc yêu cầu cấu hình bổ sung.

### 5.4. Không suppress deprecation chỉ để build xanh

Ví dụ sau chỉ che cảnh báo:

```java
@SuppressWarnings("deprecation")
void load() {
    legacyApi();
}
```

Nếu chưa thể migrate vì dependency hoặc giao thức tương thích, hãy cô lập lời gọi cũ trong adapter, ghi rõ lý do và theo dõi phiên bản dependency. Suppression nên nằm ở boundary nhỏ, không phủ cả package hoặc toàn bộ ứng dụng.

## 6. Cảnh báo serial

### 6.1. Serializable class và serialVersionUID

Một class triển khai `Serializable` nhưng không khai báo `serialVersionUID` có thể phát warning:

```java
import java.io.Serializable;

public class UserSession implements Serializable {
    private String userId;
}
```

Serialization runtime có thể tính một UID mặc định dựa trên cấu trúc class. Thay đổi class có thể làm UID tính được thay đổi, gây lỗi tương thích khi deserialize dữ liệu được serialize từ phiên bản khác.

### 6.2. Khai báo UID khi serialization là contract

```java
import java.io.Serial;
import java.io.Serializable;

public class UserSession implements Serializable {
    @Serial
    private static final long serialVersionUID = 1L;

    private String userId;
}
```

`@Serial` có từ Java 14 và có trong Java 17. Annotation này giúp compiler kiểm tra một số khai báo liên quan serialization. Trường UID thường được khai báo `private static final long`.

Không đặt một UID tùy ý vào mọi class chỉ để suppress warning. Trước tiên xác định class có thực sự cần Java native serialization hay không. Nếu class không cần serialized form, có thể bỏ `implements Serializable`; nếu cần tương thích, quản lý UID và schema migration như một phần của contract.

### 6.3. serialVersionUID không phải schema version tự động

UID giúp kiểm tra compatibility ở mức Java serialization. Nó không thay thế versioning của API, database schema hoặc message format. Thay đổi field vẫn cần xem xét serialization behavior và dữ liệu cũ.

## 7. Cảnh báo cast

### 7.1. Cast dư thừa

Ví dụ:

```java
String name = (String) "An";
```

Cast không cần thiết vì biểu thức đã có kiểu String. Có thể bỏ:

```java
String name = "An";
```

Cast dư thừa làm code nhiễu và đôi khi che khuất việc kiểu nguồn đã được khai báo quá rộng.

### 7.2. Sửa kiểu ở nguồn thay vì cast ở đích

Không nên ép kiểu liên tục nếu biến nguồn có thể được khai báo chính xác:

```java
Object value = "An";
String name = (String) value;
```

Nếu dữ liệu luôn là String, khai báo:

```java
String name = "An";
Object value = name;
```

Nếu dữ liệu thực sự không xác định, cast phải có kiểm tra runtime:

```java
if (value instanceof String name) {
    use(name);
} else {
    handleUnexpectedType(value);
}
```

### 7.3. Không nhầm cast warning với unchecked cast

Cast warning có thể là cast dư thừa; unchecked warning liên quan đến generic type erasure và việc compiler không xác minh được cast. Đọc lint key cụ thể để sửa đúng vấn đề.

## 8. Cảnh báo fallthrough trong switch

### 8.1. Fallthrough ngoài ý muốn

Với switch statement dạng truyền thống, nếu không có `break`, `return` hoặc cơ chế kết thúc tương ứng, luồng điều khiển có thể đi tiếp vào case kế tiếp:

```java
switch (status) {
    case 1:
        start();
    case 2:
        notifyUser();
        break;
    default:
        logUnknown();
}
```

Khi status bằng 1, cả `start()` và `notifyUser()` được gọi. Nếu không chủ ý, đây là lỗi logic.

### 8.2. Kết thúc case rõ ràng

```java
switch (status) {
    case 1:
        start();
        break;
    case 2:
        notifyUser();
        break;
    default:
        logUnknown();
}
```

Nếu có thể dùng switch expression trong Java 17, dạng này cũng làm rõ kết quả của từng nhánh:

```java
String label = switch (status) {
    case 1 -> "STARTED";
    case 2 -> "NOTIFIED";
    default -> "UNKNOWN";
};
```

### 8.3. Fallthrough có chủ đích

Một số switch statement cố ý gom nhiều case:

```java
switch (day) {
    case SATURDAY:
    case SUNDAY:
        return "weekend";
    default:
        return "weekday";
}
```

Đây là nhiều label cùng dùng một body, không phải fallthrough từ một body có câu lệnh sang body khác. Nếu thực sự cần fallthrough giữa các body, dùng comment giải thích rõ lý do và tuân theo quy ước compiler/tooling của dự án.

## 9. Cảnh báo finally

### 9.1. Không return từ finally

```java
static int calculate() {
    try {
        return 10;
    } finally {
        return 0; // ghi đè kết quả return từ try
    }
}
```

Return trong finally có thể ghi đè return trước đó và che exception đang được ném. Đây là mẫu code nguy hiểm và compiler có thể cảnh báo bằng lint key `finally`.

### 9.2. Không throw từ finally để thay exception gốc

Nếu finally ném exception mới, exception ban đầu có thể bị che khuất trong luồng điều khiển thông thường. Với resource, ưu tiên try-with-resources để Java quản lý close và suppressed exception.

### 9.3. Dùng finally cho cleanup không làm thay đổi luồng điều khiển

```java
Lock lock = obtainLock();
lock.lock();
try {
    updateState();
} finally {
    lock.unlock();
}
```

Finally phù hợp cho cleanup như unlock hoặc giải phóng trạng thái, miễn là cleanup không return hoặc ném exception không được quản lý làm che kết quả ban đầu.

## 10. Cảnh báo try và try-with-resources

### 10.1. Tự đóng resource bằng finally dễ sai

Mẫu cũ:

```java
InputStream input = openInput();
try {
    read(input);
} finally {
    input.close();
}
```

Nếu thao tác đọc và close cùng ném exception, code thủ công có thể làm mất thông tin exception gốc hoặc tạo nhiều nhánh cleanup phức tạp.

### 10.2. Dùng try-with-resources

```java
try (InputStream input = openInput()) {
    read(input);
}
```

JVM/compiler tạo cơ chế đóng resource khi rời block, kể cả khi có exception. Exception trong quá trình close được xử lý theo quy tắc suppressed exception.

### 10.3. Resource không được tham chiếu trong body

Lint key `try` có thể cảnh báo resource được khai báo trong try-with-resources nhưng không được tham chiếu trong thân block. Điều này có thể là dấu hiệu code vô tình tạo resource mà không sử dụng.

Ví dụ:

```java
try (var lock = channel.lock()) {
    updateFile();
}
```

Nếu resource cần được kiểm tra, hãy dùng nó một cách có ý nghĩa:

```java
try (var lock = channel.lock()) {
    if (!lock.isValid()) {
        throw new IllegalStateException("File lock is not valid");
    }
    updateFile();
}
```

Không tạo một lời gọi vô nghĩa chỉ để làm compiler im lặng. Nếu resource chỉ được mở để đảm bảo close, hãy cân nhắc API phù hợp hoặc ghi chú lý do và suppress đúng phạm vi nếu compiler vẫn cảnh báo.

### 10.4. AutoCloseable và close exception

Khi tạo resource type riêng, triển khai `AutoCloseable` và định nghĩa rõ hành vi `close()`. Tránh thiết kế close có thể ném exception bất ngờ mà caller không thể xử lý. Nếu resource là một phần của try-with-resources, hiểu quy tắc exception chính và suppressed exception.

## 11. Cảnh báo static

### 11.1. Không gọi static member qua instance

```java
class Config {
    static String environment() {
        return "prod";
    }
}

Config config = new Config();
String env = config.environment();
```

Method `environment()` là static, nhưng được gọi thông qua biến instance. Điều này gây hiểu nhầm rằng kết quả phụ thuộc object.

Sửa:

```java
String env = Config.environment();
```

### 11.2. Dùng static import có chọn lọc

Static import có thể hữu ích cho constant hoặc helper rõ nghĩa:

```java
import static java.lang.Math.max;

int largest = max(a, b);
```

Nhưng không nên static import quá nhiều method có tên chung chung khiến khó biết method đến từ đâu. Cảnh báo `static` thường chỉ ra một trường hợp truy cập member static qua expression; hãy sửa bằng class name để code rõ ràng.

## 12. Cảnh báo varargs và heap pollution

### 12.1. Generic varargs có nguy cơ

Varargs được triển khai qua array. Với kiểu generic không reifiable, compiler không thể bảo đảm array runtime giữ đúng type parameter.

Ví dụ:

```java
static void addToFirst(List<String>... lists) {
    Object[] array = lists;
    array[0] = List.of(42); // có thể gây heap pollution
    String value = lists[0].get(0);
}
```

Generic type bị xóa ở runtime; việc dùng array/object reference có thể làm dữ liệu không đúng type lọt vào cấu trúc.

### 12.2. @SafeVarargs chỉ khi method thật sự an toàn

`@SafeVarargs` có thể suppress warning cho method/constructor varargs có generic element type nếu người viết chứng minh body không gây heap pollution. Trên Java 17, annotation này áp dụng cho static method, final instance method, private instance method và constructor.

Ví dụ method chỉ đọc các list và không lưu/ghi vào varargs array:

```java
@SafeVarargs
static int totalSizes(List<?>... lists) {
    int total = 0;
    for (List<?> list : lists) {
        total += list.size();
    }
    return total;
}
```

Ở đây method chỉ đọc từng list, không thay phần tử array và không để array thoát ra ngoài. Annotation phản ánh một invariant có thể kiểm chứng.

Không dùng `@SafeVarargs` để tắt cảnh báo nếu method ghi vào array, trả array ra ngoài hoặc truyền array tới code có thể thay đổi phần tử. Annotation không biến code không an toàn thành an toàn.

### 12.3. Ưu tiên collection API khi hợp lý

Nếu varargs generic gây phức tạp, có thể nhận `List<T>` hoặc `Collection<T>` thay vì array:

```java
static int totalSizes(List<? extends List<?>> lists) {
    return lists.stream().mapToInt(List::size).sum();
}
```

API collection thể hiện rõ dữ liệu là một tập phần tử và tránh một số rủi ro đặc thù của generic array.

## 13. Cảnh báo overloads và API dễ gây mơ hồ

Overload giúp API tiện dụng, nhưng những method có signature quá gần nhau có thể tạo lời gọi khó hiểu, đặc biệt khi dùng lambda hoặc functional interface.

Ví dụ:

```java
static void process(Runnable action) {
}

static void process(java.util.concurrent.Callable<?> action) {
}

// Một lambda không trả về giá trị có thể phù hợp với Runnable;
// lambda có return value có thể phù hợp với Callable.
process(() -> System.out.println("run"));
```

Trong các trường hợp phức tạp, overload có thể làm lời gọi mơ hồ hoặc thay đổi cách overload resolution hoạt động khi thêm API mới.

Hướng thiết kế:

- Chọn tên method khác nhau nếu semantics khác nhau.
- Tránh overload chỉ khác functional interface mà caller khó phân biệt.
- Cung cấp factory hoặc builder có tên mô tả.
- Kiểm tra source compatibility khi thêm overload vào library public API.

Không phải mọi overload đều sai. Cảnh báo là lời nhắc xem xét khả năng gây nhầm lẫn và compatibility.

## 14. Cảnh báo strictfp trong Java 17

Từ Java 17, các biểu thức floating-point được đánh giá theo ngữ nghĩa strict của Java. Modifier `strictfp` trên class, interface hoặc method vì vậy không còn tạo khác biệt như trong các Java release cũ; compiler có thể cảnh báo modifier không còn cần thiết.

Ví dụ:

```java
public strictfp class Calculator {
    public strictfp double calculate(double a, double b) {
        return a / b;
    }
}
```

Trong code dành cho Java 17, có thể bỏ modifier dư thừa:

```java
public class Calculator {
    public double calculate(double a, double b) {
        return a / b;
    }
}
```

Không cần mang modifier cũ sang code Java 17 chỉ vì nó từng được khuyến nghị để đảm bảo kết quả floating-point nhất quán trên các kiến trúc cũ.

## 15. Cảnh báo path, options và processing

Không phải warning nào cũng đến từ source code. Một số warning phản ánh cấu hình build:

### 15.1. path

`-Xlint:path` có thể giúp phát hiện phần tử classpath/module path không tồn tại hoặc path được cấu hình sai.

Ví dụ:

```shell
javac -Xlint:path -cp "lib/missing.jar" Example.java
```

Nếu dependency không tồn tại, hãy sửa dependency resolution hoặc đường dẫn. Không thêm một JAR rỗng hoặc suppress warning để làm build xanh.

### 15.2. options

`-Xlint:options` giúp phát hiện vấn đề liên quan compiler options, chẳng hạn option không phù hợp với release/source/target đang chọn. Chuẩn hóa JDK và dùng `--release 17` để giảm sai lệch giữa máy developer và CI.

### 15.3. processing

`-Xlint:processing` liên quan annotation processing. Nếu dự án dùng processor sinh source hoặc metadata, cần kiểm tra:

- Processor có được phát hiện đúng không?
- Processor có hỗ trợ JDK 17 không?
- Processor có phát diagnostic hoặc không xử lý annotation nào không?
- Build có cấu hình processor path và version rõ ràng không?

Không tắt annotation processing nếu code phụ thuộc source được sinh ra. Nếu dự án không dùng processor, kiểm tra cấu hình compiler để loại bỏ dependency hoặc option không cần thiết.

## 16. Cảnh báo module và exported API

Trong dự án modular, compiler có thể cảnh báo về module descriptor hoặc API được export. Những cảnh báo này thường liên quan khả năng module khác sử dụng API và dependency được khai báo.

Một số nguyên tắc:

- Chỉ export package thực sự là API public.
- Không export package internal chỉ để giải quyết lỗi truy cập reflection.
- Phân biệt `exports` và `opens`: exports công khai API compile-time; opens cho phép deep reflection runtime.
- Khai báo `requires` và `requires transitive` theo contract API, không thêm transitive dependency tùy tiện.
- Kiểm tra module name của dependency bằng `jar --describe-module`.

Nếu warning đề cập module automatic hoặc dependency không ổn định trong module graph, xác định dependency thực tế và xem xét module descriptor/automatic module name. Không tự tạo tên module giả định từ artifact name.

## 17. @SuppressWarnings: khi nào và cách dùng có căn cứ

### 17.1. Suppress chỉ là annotation, không phải sửa lỗi

`@SuppressWarnings` yêu cầu compiler hoặc tool không phát một nhóm warning trong phạm vi được annotation áp dụng:

```java
@SuppressWarnings("unchecked")
void adaptLegacyApi() {
    // ...
}
```

Annotation không thay đổi runtime behavior, không kiểm tra invariant và không làm một cast trở nên an toàn. Nếu suppress sai, warning biến mất nhưng rủi ro vẫn còn.

### 17.2. Đặt phạm vi nhỏ nhất

Không nên suppress cả class nếu chỉ một dòng cần xử lý. Ưu tiên:

1. Biến cục bộ.
2. Method nhỏ.
3. Constructor hoặc field cụ thể.
4. Class chỉ khi nhiều thao tác trong class cùng chia sẻ một invariant đã được chứng minh.

Ví dụ:

```java
Object legacyValue = legacyApi.read();

// Contract của legacyApi bảo đảm giá trị trả về là List<String>
// khi request được gửi với key "display-names"; producer kiểm tra từng phần tử.
@SuppressWarnings("unchecked")
List<String> displayNames = (List<String>) legacyValue;
```

Ví dụ này chỉ hợp lý nếu contract thực sự bảo đảm kiểu và được kiểm tra ở boundary. Nếu không có bằng chứng đó, hãy kiểm tra kiểu runtime thay vì suppress.

### 17.3. Suppress category cụ thể

Nên viết:

```java
@SuppressWarnings("unchecked")
```

thay vì:

```java
@SuppressWarnings("all")
```

Category cụ thể giúp reviewer biết vấn đề nào được chấp nhận và vẫn để các nhóm warning khác hoạt động.

### 17.4. Ghi chú lý do có thể kiểm chứng

Một suppression có trách nhiệm nên giải thích:

- Vì sao không thể sửa warning tại nguồn.
- Invariant nào bảo đảm thao tác an toàn.
- Invariant được duy trì ở đâu.
- Test nào bảo vệ invariant.

Ví dụ:

```java
@SuppressWarnings("unchecked") // Legacy registry chỉ lưu giá trị sau khi kiểm tra bằng type token.
private <T> T readLegacyEntry(Class<T> type, Object value) {
    // ...
}
```

Chú thích này chỉ có giá trị nếu code thật sự kiểm tra và duy trì type token. Nếu không, hãy sửa code để kiểm tra kiểu.

### 17.5. Suppress deprecation trong adapter có giới hạn

Khi phải gọi API deprecated do một dependency chưa có phiên bản thay thế tương thích, cô lập lời gọi:

```java
final class LegacyAdapter {

    @SuppressWarnings("deprecation")
    void invokeLegacyEndpoint() {
        // Chỉ giữ lời gọi deprecated tại boundary này.
        legacyClient.oldEndpoint();
    }
}
```

Kèm issue/version target để migration. Không suppress deprecation trên toàn bộ module chỉ để tránh thấy warning.

## 18. Dùng -Werror trong quy trình build

### 18.1. Vì sao nên nâng warning thành error?

Nếu CI chỉ in warning mà vẫn thành công, cảnh báo mới có thể bị bỏ qua. Qua nhiều lần merge, số warning tăng và việc phân biệt vấn đề mới với nợ cũ trở nên khó khăn.

`-Werror` giúp build thất bại khi compiler phát warning. Khi codebase đã sạch hoặc có baseline ngoại lệ được kiểm soát, đây là cách giữ chất lượng compiler diagnostics ổn định.

### 18.2. Lộ trình áp dụng

Với codebase hiện có, có thể triển khai theo từng giai đoạn:

1. Chạy `-Xlint:all` và thu thập warning hiện tại.
2. Phân nhóm theo lint key và module.
3. Sửa lỗi có thể sửa trực tiếp.
4. Xử lý API deprecated/removal theo kế hoạch migration.
5. Thêm suppression có căn cứ cho boundary không thể loại bỏ ngay.
6. Bật `-Werror` trong CI.
7. Duy trì cùng JDK/compiler options giữa developer và CI.

Không nên bật `-Werror` ngay trên một codebase có hàng trăm warning chưa phân loại mà không có kế hoạch xử lý; điều đó có thể chặn mọi thay đổi không liên quan. Hãy đưa warning baseline về trạng thái kiểm soát trước.

### 18.3. Lệnh javac đầy đủ

Giả sử source nằm trong `src`:

```shell
javac --release 17 \
  -Xlint:all \
  -Werror \
  -d out \
  src/com/acme/Main.java
```

Với nhiều source file:

```shell
javac --release 17 -Xlint:all -Werror -d out \
  src/com/acme/*.java
```

Trong project modular, dùng `--module-source-path` và `-m` theo cấu trúc module thay vì compile một file độc lập.

### 18.4. Dùng --release 17

`--release 17` cấu hình compiler theo Java 17:

- Ngôn ngữ Java 17.
- Bytecode target Java 17.
- API nền tảng Java SE 17 mà code được phép tham chiếu.

Chỉ dùng `-source 17 -target 17` không đảm bảo compiler giới hạn API nền tảng đúng như `--release`. Khi build bằng JDK mới hơn nhưng cần phát hành ứng dụng chạy Java 17, `--release 17` là lựa chọn phù hợp.

## 19. Cấu hình trong Maven và Gradle

### 19.1. Maven Compiler Plugin

Ví dụ cấu hình compiler:

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-compiler-plugin</artifactId>
    <configuration>
        <release>17</release>
        <showWarnings>true</showWarnings>
        <compilerArgs>
            <arg>-Xlint:all</arg>
            <arg>-Werror</arg>
        </compilerArgs>
    </configuration>
</plugin>
```

Đặt version plugin theo chuẩn dependency/plugin management của dự án. Với multi-module Maven, cấu hình ở parent chỉ áp dụng theo cơ chế inheritance của plugin và module; kiểm tra effective POM để xác nhận module nào thực sự nhận arguments.

### 19.2. Gradle Groovy DSL

```groovy
tasks.withType(JavaCompile).configureEach {
    options.release = 17
    options.compilerArgs += ['-Xlint:all', '-Werror']
}
```

Cấu hình này áp dụng cho các task JavaCompile trong project. Với multi-project build, đặt trong convention plugin hoặc cấu hình dùng chung để các subproject nhận cùng chính sách.

### 19.3. Tránh cấu hình lệch giữa local và CI

Một developer dùng JDK 17, CI dùng JDK 21 nhưng source release khác nhau có thể nhận diagnostics khác nhau. Nên:

- Chốt toolchain JDK.
- Dùng `--release 17`.
- Dùng cùng compiler arguments.
- Ghi lại JDK vendor/version trong CI log.
- Không để IDE tự dùng compiler khác với build chính mà không biết.

## 20. Đọc và xử lý warning trong CI

Một quy trình review hữu ích:

**1. Phân loại theo lint key.**  
Ví dụ `unchecked`, `deprecation`, `serial`, `try` để xác định nhóm công việc.

**2. Xác định warning mới hay đã tồn tại.**  
Nếu codebase có nợ cũ, theo dõi số lượng theo module/package và không cho warning mới tăng.

**3. Tìm nguyên nhân ở source.**  
Đọc dòng cảnh báo, generic type, module descriptor hoặc compiler option liên quan.

**4. Chọn cách xử lý.**  
Sửa source, migrate API, thay dependency, cập nhật build config hoặc suppress có căn cứ.

**5. Chạy lại compiler với cùng flags.**  
Đảm bảo warning cụ thể biến mất vì nguyên nhân được sửa, không phải do lint bị tắt.

**6. Kiểm tra behavior.**  
Chạy test phù hợp vì việc sửa generic, serialization hoặc API deprecated có thể ảnh hưởng runtime behavior.

**7. Giữ -Werror.**  
Khi warning baseline đã được xử lý, bật `-Werror` để cảnh báo mới chặn build.

## 21. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách xử lý |
|---|---|---|
| Bỏ qua toàn bộ warning | Vấn đề generic, API cũ hoặc resource có thể tích lũy | Bật lint và phân loại |
| Dùng `-Werror` nhưng không bật lint | Chỉ nâng những warning đang được bật thành error | Kết hợp `-Xlint:all` khi phù hợp |
| Dùng raw type để tránh generic phức tạp | Mất kiểm tra kiểu và có thể gây ClassCastException | Dùng generic type hoặc kiểm tra dữ liệu ở boundary |
| Ép kiểu unchecked rồi suppress ngay | Che lỗi type contract | Tìm cách kiểm tra runtime hoặc chứng minh invariant |
| Suppress `all` ở class lớn | Che cả warning không liên quan trong tương lai | Suppress key cụ thể, phạm vi nhỏ |
| Suppress deprecation mà không có kế hoạch | Dependency/API cũ tiếp tục tồn tại vô thời hạn | Cô lập adapter và ghi migration target |
| Thêm serialVersionUID vào mọi class | Tạo serialization contract không cần thiết | Chỉ dùng Serializable khi domain cần |
| Thêm break vào mọi case mà không hiểu logic | Có thể làm thay đổi hành vi fallthrough có chủ đích | Xác định semantics trước khi sửa |
| Return từ finally | Có thể che exception hoặc kết quả trước đó | Dùng finally chỉ cho cleanup |
| Tự đóng resource bằng nhiều nhánh | Dễ quên close và che exception | Dùng try-with-resources |
| Gọi static method qua instance | Code gây hiểu nhầm về dispatch | Dùng class name |
| Dùng @SafeVarargs để tắt warning tùy tiện | Heap pollution vẫn có thể xảy ra | Chứng minh method không ghi/escape unsafe array |
| Dùng -source/-target thay --release khi cần API compatibility | Có thể tham chiếu API mới hơn target runtime | Dùng `--release 17` |
| Chỉ chạy lint trên máy developer | CI có thể dùng flags/JDK khác | Chuẩn hóa toolchain và compiler arguments |
| Tắt lint vì một dependency cũ | Mất toàn bộ tín hiệu từ source ứng dụng | Giới hạn ngoại lệ đúng category hoặc nâng dependency |

## 22. Ví dụ tổng hợp: compile warning và cách sửa

Lưu file **LintDemo.java**:

```java
import java.io.Serializable;
import java.util.ArrayList;
import java.util.List;

class LegacyApi {
    @Deprecated(since = "17", forRemoval = true)
    static void oldApi() {
    }
}

class LintDemo {

    static void helper() {
    }

    static void rawTypes() {
        List values = new ArrayList();
        values.add("An");
        values.add(42);
        List<String> names = values;
    }

    static class Session implements Serializable {
        private String userId;
    }

    static void staticCall() {
        LintDemo demo = new LintDemo();
        demo.helper();
        LegacyApi.oldApi();
    }

    public static void main(String[] args) {
        rawTypes();
        staticCall();
    }
}
```

Biên dịch:

```shell
javac --release 17 -Xlint:all LintDemo.java
```

Compiler có thể cảnh báo về deprecation/removal, rawtypes, unchecked và static access (các warning cụ thể tùy code/compiler). Ví dụ này cố ý chứa các mẫu cần xử lý.

Phiên bản sửa:

```java
import java.io.Serial;
import java.io.Serializable;
import java.util.ArrayList;
import java.util.List;

class LintDemo {

    static class Session implements Serializable {
        @Serial
        private static final long serialVersionUID = 1L;

        private final String userId;

        Session(String userId) {
            this.userId = userId;
        }
    }

    static List<String> names() {
        List<String> values = new ArrayList<>();
        values.add("An");
        values.add("Bình");
        return List.copyOf(values);
    }

    public static void main(String[] args) {
        System.out.println(names());
    }
}
```

Trong ví dụ sửa, raw type được thay bằng generic type và serialization metadata được khai báo vì class vẫn giữ contract Serializable. API deprecated không còn được gọi; trong dự án thật, cần thay bằng API mới theo tài liệu của dependency.

Compile nghiêm ngặt:

```shell
javac --release 17 -Xlint:all -Werror LintDemo.java
```

Nếu source vẫn có warning từ các category đang bật, compiler sẽ fail. Ví dụ minh họa không nhằm chứng minh mọi warning của mọi dependency đều được xử lý tự động; hãy đọc output của đúng compiler và source đang build.

## 23. Bài tập thực hành

### Bài 1 — Bật toàn bộ lint

Tạo một file Java có raw type, cast dư thừa, deprecated API và Serializable class không UID. Biên dịch bằng:

```shell
javac --release 17 -Xlint:all Example.java
```

Ghi lại lint key và dòng code tương ứng.

### Bài 2 — Sửa rawtypes và unchecked

Thay raw `List`/`Map` bằng generic types. Nếu dữ liệu đến từ API legacy, chuyển đổi bằng cách kiểm tra từng phần tử. Xác nhận không cần unchecked suppression.

### Bài 3 — Xử lý deprecation và removal

Tạo một API `@Deprecated(since = "17", forRemoval = true)`, gọi từ client class và quan sát warning. Viết adapter sử dụng API thay thế; giải thích khi nào suppression tạm thời có thể chấp nhận.

### Bài 4 — Kiểm tra serial

Tạo Serializable class và quan sát lint. Thêm `@Serial` cùng `serialVersionUID`. Giải thích vì sao chỉ thêm UID không đảm bảo mọi thay đổi class đều tương thích serialization.

### Bài 5 — Tìm fallthrough

Viết switch statement có fallthrough ngoài ý muốn. Bật `-Xlint:fallthrough`, sửa bằng break/return hoặc switch expression và kiểm tra kết quả từng case.

### Bài 6 — Kiểm tra finally và try-with-resources

Viết một method return trong finally và một đoạn tự đóng stream. Quan sát cảnh báo phù hợp, chuyển sang cleanup đúng cách và try-with-resources.

### Bài 7 — Generic varargs

Viết method nhận `List<String>...` và thử thay đổi phần tử qua `Object[]`. Quan sát warning. Sau đó sửa để method chỉ đọc, dùng `@SafeVarargs` nếu có thể chứng minh an toàn, hoặc chuyển sang Collection API.

### Bài 8 — Bật -Werror trong build

Chạy `-Xlint:all` trên project hiện có. Phân loại warning, xử lý hoặc suppress có căn cứ, rồi bật `-Werror`. Xác nhận warning mới làm CI thất bại.

### Bài 9 — Kiểm tra Java 17 API boundary

Biên dịch bằng JDK mới hơn với `--release 17`. Thử tham chiếu API chỉ có trong JDK mới hơn và quan sát compiler từ chối. Giải thích vì sao `--release` phù hợp hơn chỉ đặt source/target.

## 24. Câu hỏi tự kiểm tra

1. Compiler warning khác compile error thế nào?
2. `-Xlint` và `-Xlint:all` có vai trò gì?
3. `-Werror` có tự bật tất cả lint category không?
4. Raw type làm mất lợi ích nào của generics?
5. Khác biệt giữa warning `rawtypes` và `unchecked`?
6. Vì sao unchecked cast có thể gây lỗi runtime?
7. Khi nào nên dùng `Class.cast` thay cast trực tiếp?
8. `@Deprecated` khác `forRemoval = true` thế nào?
9. Vì sao Serializable class có thể cần `serialVersionUID`?
10. `@Serial` giúp compiler kiểm tra điều gì?
11. Fallthrough là gì và khi nào có thể là chủ đích?
12. Vì sao return trong finally nguy hiểm?
13. Try-with-resources xử lý exception khi close thế nào?
14. Heap pollution có thể xuất hiện với generic varargs ra sao?
15. Điều kiện nào cần được chứng minh trước khi dùng `@SafeVarargs`?
16. Vì sao static member nên được gọi bằng class name?
17. `--release 17` khác `-source 17 -target 17` thế nào?
18. Khi nào `-Werror` nên được bật trong CI?
19. Vì sao suppress warning cần phạm vi nhỏ và lý do kiểm chứng được?
20. Khi compiler warning xuất hiện từ annotation processor hoặc build path, cần điều tra phần nào?

## 25. Tài liệu tham khảo

- [Java SE 17 javac Tool Reference](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html): `-Xlint`, `-Werror`, `--release` và compiler options.
- [Java SE 17 javac — lint options](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html#lint): các nhóm cảnh báo và cú pháp bật/tắt lint key.
- [Java Language Specification, Java SE 17](https://docs.oracle.com/javase/specs/jls/se17/html/): quy tắc ngôn ngữ, generics, switch và serialization liên quan.
- [Java SE 17 API — Deprecated](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Deprecated.html): metadata `since` và `forRemoval`.
- [Java SE 17 API — Serial](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/Serial.html): annotation cho khai báo serialization.
- [Java SE 17 API — SuppressWarnings](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/SuppressWarnings.html): phạm vi và ý nghĩa suppression.
- [Java SE 17 API — SafeVarargs](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/SafeVarargs.html): hợp đồng an toàn cho generic varargs.
- [JEP 306 — Restore Always-Strict Floating-Point Semantics](https://openjdk.org/jeps/306): ngữ nghĩa floating-point trong Java 17.

Compiler warnings là thông tin về rủi ro trong source và cấu hình build. Hãy bật `-Xlint` để nhìn rõ vấn đề, sửa nguyên nhân bằng type-safe API và cách quản lý resource phù hợp, migrate khỏi API deprecated/removal, rồi dùng `-Werror` để ngăn warning mới lọt qua CI. Chỉ suppress khi có invariant kỹ thuật được chứng minh, đặt suppression ở phạm vi nhỏ nhất và ghi lại lý do để người bảo trì sau này có thể kiểm tra.
