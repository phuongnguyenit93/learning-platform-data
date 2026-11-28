# Vai trò final trong thiết kế dữ liệu và tối ưu JVM

Từ khóa `final` thể hiện một cam kết quan trọng: sau khi biến hoặc field được gán giá trị hợp lệ, chương trình không tùy ý thay thế giá trị đó. Với field của object, cam kết này giúp mô hình dữ liệu dễ dự đoán, hỗ trợ xây dựng object bất biến và tạo điều kiện cho JVM tối ưu việc đọc field. Java Memory Model còn quy định cách các thread nhìn thấy giá trị của `final` field sau khi constructor kết thúc.

Trong nhiều năm, deep reflection vẫn có thể thay đổi một số `final` instance field sau khi object được tạo. Cách làm này phá vỡ giả định mà code, compiler và JVM dựa vào. JDK 26 triển khai JEP 500 (*Prepare to Make Final Mean Final*): phát cảnh báo khi code dùng deep reflection để sửa `final` field trái phép, chuẩn bị cho các bản JDK tương lai siết chặt quyền đó. Bài này giải thích cả giá trị thiết kế của `final` và cách chuẩn bị ứng dụng cho chính sách mới.

## 1. `final` áp dụng ở những vị trí nào?

Java dùng `final` cho biến, field, phương thức và lớp. Ý nghĩa khác nhau tùy vị trí:

| Vị trí | Ý nghĩa | Ví dụ sử dụng |
|---|---|---|
| Local variable hoặc parameter | Chỉ được gán một lần sau khi đã được khởi tạo | Giữ tham chiếu đầu vào không bị gán lại trong phương thức |
| Instance field | Mỗi object gán field một lần, thường trong khai báo hoặc constructor | Lưu ID, ngày tạo, cấu hình bất biến của object |
| `static final` field | Field cấp lớp được gán một lần khi khai báo hoặc trong static initializer | Hằng số dùng chung hoặc singleton |
| `final` method | Lớp con không thể override phương thức | Bảo vệ một bước xử lý phải giữ nguyên hành vi |
| `final` class | Không thể tạo lớp con | Thiết kế kiểu không cho phép mở rộng bằng kế thừa |

`final` trên field không đồng nghĩa object được tham chiếu là bất biến. Nó chỉ ngăn gán lại field. Ví dụ:

```java
final class UserSession {
    private final List<String> roles = new ArrayList<>();

    void addRole(String role) {
        roles.add(role); // Hợp lệ: không gán lại field roles.
    }
}
```

`roles` luôn tham chiếu cùng một `ArrayList`, nhưng nội dung list vẫn thay đổi. Nếu cần object bất biến, phải kiểm soát cả trạng thái của object được tham chiếu và những object mà nó chứa.

## 2. Dùng final để mô hình hóa dữ liệu bất biến

Một object dễ dự đoán khi trạng thái của nó được xác định đầy đủ lúc khởi tạo và không đổi sau đó. Dùng `private final` cho các field mô tả trạng thái, gán chúng trong constructor và không cung cấp thao tác thay đổi.

```java
import java.util.List;
import java.util.Objects;

public final class UserProfile {
    private final String userId;
    private final String displayName;
    private final List<String> roles;

    public UserProfile(
            String userId,
            String displayName,
            List<String> roles) {
        this.userId = Objects.requireNonNull(userId);
        this.displayName = Objects.requireNonNull(displayName);
        this.roles = List.copyOf(roles);
    }

    public String userId() {
        return userId;
    }

    public String displayName() {
        return displayName;
    }

    public List<String> roles() {
        return roles;
    }
}
```

Lớp này bảo vệ trạng thái theo nhiều lớp:

- Lớp `final` ngăn subclass thay đổi hợp đồng của object.
- Các field `private final` không thể bị gán lại trong code Java thông thường.
- Constructor kiểm tra dữ liệu bắt buộc trước khi object được sử dụng.
- `List.copyOf()` tạo bản sao không thể sửa của danh sách đầu vào, tránh để caller thay đổi list gốc rồi làm thay đổi trạng thái profile.
- Không có setter hoặc phương thức làm thay đổi trạng thái.

`List.copyOf()` chỉ bảo vệ cấu trúc list, không tạo bản sao sâu cho từng phần tử. Nếu phần tử là object mutable, caller vẫn có thể thay đổi object đó. Muốn bất biến sâu, hãy dùng phần tử immutable hoặc sao chép/chuẩn hóa từng phần tử khi nhận dữ liệu.

Với mảng, cần sao chép khi nhận và khi trả về:

```java
public final class Digest {
    private final byte[] bytes;

    public Digest(byte[] bytes) {
        this.bytes = bytes.clone();
    }

    public byte[] bytes() {
        return bytes.clone();
    }
}
```

Nếu chỉ khai báo `private final byte[] bytes` nhưng giữ nguyên mảng caller truyền vào, caller vẫn có thể thay đổi dữ liệu bên trong object. Tương tự, trả trực tiếp mảng nội bộ từ getter sẽ làm lộ trạng thái mutable.

### 2.1. Khi nào không nên dùng final?

Không ép mọi field thành `final`. Nếu nghiệp vụ yêu cầu trạng thái thay đổi theo thời gian, hãy mô hình hóa nó thành state mutable có quyền sở hữu và quy tắc đồng bộ rõ ràng. Ví dụ bộ đếm dùng `AtomicLong`, trạng thái chia sẻ dùng `volatile` hoặc lock khi phù hợp. Không dùng reflection để sửa field `final` nhằm mô phỏng một object mutable.

Với dữ liệu cấu hình có thể reload, tách snapshot bất biến khỏi tham chiếu đang trỏ tới snapshot hiện hành:

```java
record AppConfig(String endpoint, int maxConnections) {}

final class ConfigService {
    private volatile AppConfig current;

    AppConfig current() {
        return current;
    }

    void reload(AppConfig next) {
        current = next;
    }
}
```

Mỗi `AppConfig` là snapshot bất biến; field `current` có thể đổi để chuyển sang snapshot mới và dùng `volatile` để công bố tham chiếu mới cho các thread. Cách này thể hiện đúng yêu cầu thay đổi trạng thái mà không phá vỡ ý nghĩa của `final`.

## 3. Final field semantics trong Java Memory Model

JLS §17.5 quy định một cơ chế đặc biệt cho `final` field. Khi constructor ghi giá trị cho một `final` field và kết thúc, một *freeze action* xảy ra đối với field đó. Nếu object được tạo đúng cách, thread khác chỉ nhìn thấy object sau khi constructor kết thúc sẽ được bảo đảm đọc đúng giá trị `final` đã được gán trong constructor.

Ví dụ:

```java
final class Coordinates {
    final int x;
    final int y;
    int labelCode;

    Coordinates(int x, int y) {
        this.x = x;
        this.y = y;
        this.labelCode = 7;
    }
}
```

Nếu object được tạo xong rồi tham chiếu được chia sẻ cho thread khác, Java Memory Model bảo đảm thread đọc đúng `x` và `y`. Field `labelCode` không có bảo đảm đặc biệt của `final`; nếu chia sẻ object mà không có happens-before thích hợp, thread khác có thể chưa nhìn thấy giá trị `7`.

Điểm này thường bị hiểu nhầm: `final` hỗ trợ tính bất biến và khả năng quan sát giá trị khởi tạo của field đó, nhưng không biến toàn bộ object thành một vùng nhớ được đồng bộ. Các field mutable vẫn cần cơ chế công bố và đồng bộ phù hợp.

### 3.1. Không để `this` thoát khỏi constructor

Để freeze action có ý nghĩa, không công bố tham chiếu `this` cho thread khác trước khi constructor hoàn tất. Ví dụ sau không an toàn:

```java
final class BrokenConfig {
    static volatile BrokenConfig published;
    final int timeoutMillis;

    BrokenConfig(int timeoutMillis) {
        published = this;          // this thoát ra quá sớm
        this.timeoutMillis = timeoutMillis;
    }
}
```

Thread khác có thể đọc `published` sau khi tham chiếu đã được ghi nhưng trước khi constructor gán `timeoutMillis`. Khi đó field có thể mang giá trị mặc định `0`; việc khai báo `final` không cứu được một object bị công bố trước khi khởi tạo hoàn tất.

Hãy gán đầy đủ field trước, và chỉ chia sẻ object sau khi constructor hoàn tất:

```java
final class Config {
    static volatile Config published;
    final int timeoutMillis;

    Config(int timeoutMillis) {
        this.timeoutMillis = timeoutMillis;
        published = this; // Constructor đã gán field trước khi công bố.
    }
}
```

Trong thiết kế thực tế, tốt hơn nên tránh tự công bố `this` trong constructor. Hãy để factory hoặc tầng quản lý object chia sẻ tham chiếu sau khi `new` hoàn tất. Cách công bố chuẩn như `volatile`, `synchronized`, static initialization hoặc collection đồng thời vẫn cần thiết khi object có cả field mutable.

### 3.2. Trạng thái của object được tham chiếu

JLS còn bảo đảm rằng khi thread nhìn thấy một `final` reference đã được khởi tạo đúng cách, nó cũng nhìn thấy trạng thái của object hoặc mảng được tham chiếu ít nhất ở mức cập nhật trước freeze action. Điều này hữu ích cho object graph được xây dựng hoàn chỉnh trong constructor.

Tuy nhiên, các thay đổi diễn ra sau constructor trên object con không tự động được đồng bộ chỉ vì đường dẫn tới object đó bắt đầu bằng một `final` field. Ví dụ, một `final List` chứa các phần tử có thể thêm/xóa sau đó vẫn cần quy tắc đồng bộ riêng.

## 4. Phân biệt compile-time constant và final reference

Một *constant variable* theo JLS là biến `final` có kiểu nguyên thủy hoặc `String`, được khởi tạo bằng constant expression. Compiler có thể thay chỗ sử dụng bằng giá trị hằng ngay khi biên dịch:

```java
public final class Limits {
    public static final int MAX_RETRIES = 3;
    public static final String API_VERSION = "v2";

    public static final java.time.Duration TIMEOUT =
            java.time.Duration.ofSeconds(5);
}
```

`MAX_RETRIES` và `API_VERSION` là constant variables; `TIMEOUT` không phải constant variable dù nó là `static final`. Với constant variable, mã client có thể đã được compiler nhúng giá trị vào bytecode. Nếu thư viện đổi `MAX_RETRIES` từ `3` thành `5`, các client cũ có thể tiếp tục dùng `3` cho đến khi được biên dịch lại.

`static final` trên object reference vẫn hữu ích để bảo đảm tham chiếu không bị gán lại, nhưng không có nghĩa compiler luôn nhúng object vào bytecode. Ví dụ `static final Map` hoặc `static final Duration` là tham chiếu được khởi tạo khi lớp chạy.

Không dùng compile-time constant cho giá trị cần cập nhật động từ cấu hình. Với thông số thay đổi theo môi trường hoặc cần reload, dùng một object cấu hình bất biến và công bố snapshot mới qua tham chiếu mutable được quản lý rõ ràng.

## 5. Final hỗ trợ tối ưu hóa JVM như thế nào?

JLS cho compiler và JVM nhiều tự do hơn khi đọc `final` field so với field mutable. Theo JLS §17.5, compiler có thể:

- Giữ giá trị `final` field trong register và không tải lại từ bộ nhớ khi field thường phải được tải lại.
- Di chuyển thao tác đọc `final` field qua một số synchronization barrier hoặc lời gọi phương thức mà với field mutable phải được xử lý thận trọng hơn.
- Tận dụng việc giá trị field không thay đổi để đơn giản hóa biểu thức và tối ưu mã đã biên dịch.

Ví dụ, nếu một object cấu hình có `final int timeoutMillis`, JVM có thể tối ưu các lần đọc vì giá trị không được phép đổi trong vòng đời object theo quy tắc thông thường. Với field mutable, JVM phải bảo toàn khả năng giá trị thay đổi và có thể cần đọc lại.

Không nên hiểu điều này là mọi `final` field đều được constant-fold hoặc mọi chương trình sẽ nhanh hơn chỉ bằng cách thêm `final`. Mức tối ưu thực tế phụ thuộc vào cách dùng, khả năng inline, profile và quyết định của JIT. Hãy thiết kế dữ liệu đúng trước; benchmark bằng workload đại diện nếu hiệu năng là mục tiêu cần đo.

### 5.1. Vì sao sửa final bằng reflection gây vấn đề?

Giả sử constructor gán `x = 1`, sau đó một thư viện dùng reflection thay `x` thành `2`. Code khác có thể đã được JIT biên dịch với giả định `x` không đổi và giữ giá trị cũ trong register hoặc sắp xếp lại các lần đọc. JLS cho phép một số cách quan sát kết quả không trực quan khi `final` bị sửa ngoài constructor.

Việc sửa `final` sau khi object đã được sử dụng còn gây vấn đề về:

- **Tính đúng đắn:** các phần code khác nhau có thể quan sát giá trị khác nhau.
- **An toàn đa luồng:** thread khác không có một quy tắc đơn giản để biết lúc nào giá trị mới được công bố.
- **Bảo mật:** một object được thiết kế bất biến, ví dụ đối tượng mang dữ liệu định danh hoặc trạng thái bảo mật, có thể bị thay đổi sau khi đã qua kiểm tra.
- **Tối ưu JVM:** compiler phải dè chừng các đường mutation ngoài constructor, làm suy yếu giả định về tính bất biến.

## 6. JEP 500 trong JDK 26: Prepare to Make Final Mean Final

JEP 500 được đưa vào JDK 26. Mục tiêu là chuẩn bị hệ sinh thái cho một bản JDK tương lai trong đó deep reflection không thể sửa `final` field theo mặc định. JDK 26 bắt đầu bằng cảnh báo để nhóm phát triển tìm ra thư viện còn dựa vào hành vi này và cập nhật trước khi chính sách mặc định nghiêm ngặt hơn được áp dụng.

JDK 26 phát cảnh báo khi code dùng các mutation method qua deep reflection để sửa `final` instance field trái phép. Cảnh báo đầu tiên trong mỗi module xác định field bị sửa và module thực hiện mutation. Chương trình vẫn tiếp tục trong chế độ mặc định `warn`, nhưng cần xử lý cảnh báo thay vì xem đó là thông báo vô hại.

Các mutation method được tài liệu JDK 26 nêu gồm:

- `Field.set(Object, Object)` và các biến thể `setBoolean`, `setByte`, `setChar`, `setInt`, `setLong`, `setFloat`, `setDouble`.
- `MethodHandles.Lookup.unreflectSetter(Field)` để tạo MethodHandle có quyền ghi vào reflected final field.

Quy định này nhắm tới `final` instance field không thuộc record class hoặc hidden class. `static final` field, field của record và field của hidden class không trở thành có thể ghi chỉ nhờ các cờ mở quyền này. `setAccessible(true)` chỉ bỏ một số kiểm tra truy cập; nó không tự cấp quyền mutation `final`.

### 6.1. Mở package và cho phép mutation là hai việc khác nhau

Để deep reflection truy cập private member, package của lớp khai báo field có thể phải được mở cho module thực hiện truy cập. Tuy nhiên, `--add-opens` chỉ giải quyết ranh giới truy cập module; nó không cấp quyền sửa `final` field theo JEP 500.

Quyền mutation được cấp riêng bằng `--enable-final-field-mutation` cho module chứa code thực hiện mutation. Ngay cả khi module đã được cấp quyền, việc ghi vẫn phải đáp ứng các điều kiện truy cập của `Field` và giới hạn loại field được phép sửa. Đừng dùng `--add-opens` như cách thay thế cho cờ `--enable-final-field-mutation`.

### 6.2. Các chế độ `--illegal-final-field-mutation`

JDK 26 cung cấp các chế độ để phát hiện hoặc chặn mutation không được cho phép:

| Chế độ | Hành vi |
|---|---|
| `allow` | Cho phép mutation trái phép mà không cảnh báo |
| `warn` | Cho phép mutation nhưng cảnh báo lần đầu trong mỗi module; đây là mặc định của JDK 26 |
| `debug` | Giống `warn`, đồng thời in cảnh báo và stack trace cho từng mutation |
| `deny` | Chặn mutation trái phép; `Field.set()` ném `IllegalAccessException` |

`allow` và `warn` là chế độ tương thích tạm thời. Tài liệu JDK đánh dấu `--illegal-final-field-mutation` sẽ bị loại bỏ trong một bản JDK tương lai; `deny` sẽ trở thành mặc định trong tương lai. Không dựa vào chế độ `allow` như cấu hình dài hạn.

Ví dụ chạy ứng dụng ở chế độ mặc định JDK 26:

```bash
java Application
```

Để tìm chính xác thư viện và call stack đang sửa field:

```bash
java --illegal-final-field-mutation=debug Application
```

Để kiểm tra khả năng tương thích với chính sách nghiêm ngặt trong tương lai:

```bash
java --illegal-final-field-mutation=deny Application
```

Chạy `deny` trong CI hoặc môi trường kiểm thử giúp phát hiện sớm dependency cần cập nhật. Nếu ứng dụng đang có module được bật mutation có chủ đích, hãy xem xét và giới hạn quyền đó theo module cụ thể; không cấp rộng cho toàn bộ classpath nếu không cần.

### 6.3. Cấp quyền có giới hạn bằng `--enable-final-field-mutation`

Nếu một thư viện chưa thể thay thế và thực sự cần mutation trong một giai đoạn chuyển tiếp, JDK 26 cho phép cấp quyền cho module gọi mutation:

```bash
# Code mutation chạy trên classpath (unnamed module)
java --enable-final-field-mutation=ALL-UNNAMED Application

# Code mutation thuộc các named module
java --enable-final-field-mutation=MyApplication,LegacyMapper Application
```

`ALL-UNNAMED` cấp quyền cho code trong unnamed module. Với named module, liệt kê tên module cần quyền, phân tách bằng dấu phẩy. Cờ này không mở package của module đích; điều kiện deep reflection vẫn phải được đáp ứng riêng.

Chỉ dùng cờ này như ngoại lệ có kiểm soát sau khi đã xác định thư viện nào cần quyền và vì sao chưa thể loại bỏ. Hãy ghi nhận module được cấp quyền, dependency liên quan và kế hoạch gỡ cờ sau khi nâng cấp thư viện.

## 7. Theo dõi mutation bằng JFR

Khi JFR được bật, JDK ghi event `jdk.FinalFieldMutation` cho mutation thông qua deep reflection hoặc `Lookup.unreflectSetter`. Event có tên lớp khai báo field, tên field, thread và stack trace để truy ngược thư viện gây mutation.

Ví dụ chạy ứng dụng có JFR recording:

```bash
java -XX:StartFlightRecording:filename=final-field-mutations.jfr \
     Application

jfr print --events jdk.FinalFieldMutation final-field-mutations.jfr
```

Nếu không thấy event trong recording, không nên kết luận rằng toàn bộ hệ thống chắc chắn không có mutation. Hãy kết hợp JFR với chế độ `--illegal-final-field-mutation=debug`, chạy các luồng nghiệp vụ quan trọng và kiểm tra dependency có khả năng dùng deep reflection.

## 8. Cách thay thế việc sửa final sau constructor

Khi cảnh báo chỉ ra thư viện đang sửa `final` field, hãy xử lý ở đúng lớp thiết kế:

| Nhu cầu cũ | Cách thiết kế nên dùng |
|---|---|
| Framework tạo object rỗng rồi gán private final field | Dùng constructor binding, factory hoặc creator/record support của framework |
| Cần đặt nhiều field khi tạo object | Dùng constructor đầy đủ hoặc builder tạo object hoàn chỉnh một lần |
| Cần thay cấu hình trong runtime | Thay snapshot bất biến qua một tham chiếu `volatile` hoặc cơ chế đồng bộ phù hợp |
| Cần cập nhật trạng thái mutable | Dùng field mutable được đóng gói và đồng bộ đúng cách, hoặc atomic/concurrent abstraction |
| Thư viện cũ sửa field của dependency khác | Nâng cấp, thay thế hoặc sửa thư viện để dùng API chính thức của dependency |

Records là lựa chọn phù hợp cho nhiều kiểu dữ liệu chỉ mang giá trị. Với serializable record, quá trình deserialize gọi canonical constructor, cho phép kiểm tra và chuẩn hóa dữ liệu trước khi tạo object. Đây là mô hình tốt hơn việc tạo object ở trạng thái không hợp lệ rồi sửa field sau.

Java serialization có cơ chế xử lý riêng để tiếp tục hỗ trợ các lớp `Serializable`, kể cả lớp có `final` field; JEP 500 không nhằm phá vỡ khả năng tương thích đó. Ngoại lệ này dành cho cơ chế serialization được kiểm soát, không có nghĩa mọi thư viện mapping hoặc deep reflection đều được quyền sửa `final` field. Việc deserialize dữ liệu không tin cậy vẫn có rủi ro bảo mật và cần bộ lọc/kiểm tra dữ liệu thích hợp.

## 9. Checklist nâng cấp ứng dụng lên JDK 26

- [ ] Xác định các lớp dữ liệu có thể được biểu diễn bằng object immutable; dùng `private final` và constructor kiểm tra dữ liệu.
- [ ] Không để `this` thoát khỏi constructor trước khi tất cả final field được gán.
- [ ] Kiểm tra reference field chứa collection, array hoặc object mutable; tạo defensive copy hoặc dùng kiểu immutable khi cần.
- [ ] Phân biệt compile-time constant với `static final` object reference; biên dịch lại client nếu thay đổi constant variable trong thư viện.
- [ ] Chạy toàn bộ test và các luồng serialization, dependency injection, object mapping, mocking trên JDK 26.
- [ ] Dùng mặc định `warn` để nhận cảnh báo; dùng `debug` hoặc JFR để xác định chính xác module và call stack.
- [ ] Thử `--illegal-final-field-mutation=deny` trong CI để phát hiện dependency chưa tương thích.
- [ ] Nâng cấp hoặc thay thư viện đang sửa `final` field; ưu tiên constructor/factory/record binding.
- [ ] Nếu chưa thể bỏ mutation, chỉ cấp `--enable-final-field-mutation` cho module cần thiết và ghi nhận ngoại lệ chuyển tiếp.
- [ ] Không coi `--add-opens` là quyền sửa final field và không giữ `allow` như cấu hình production dài hạn.

`final` vừa là hợp đồng thiết kế dữ liệu vừa là thông tin quan trọng cho Java Memory Model và JVM. JDK 26 bắt đầu làm cho hợp đồng đó có tính toàn vẹn rõ ràng hơn ở runtime. Ứng dụng tận dụng constructor, immutable data và safe publication sẽ ít phụ thuộc vào deep reflection, dễ dự đoán khi chạy đa luồng và sẵn sàng cho các bản JDK siết chặt mutation trong tương lai.

## Tài liệu tham khảo

- [JEP 500: Prepare to Make Final Mean Final](https://openjdk.org/jeps/500)
- [Java SE 26 Migration Guide: Preparing for final Field Mutation Restrictions](https://docs.oracle.com/en/java/javase/26/migrate/preparing-final-field-mutation-restrictions.html)
- [Java SE 26 API: Field](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/reflect/Field.html)
- [Java SE 26 API: Mutation Methods](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/reflect/doc-files/MutationMethods.html)
- [Java SE 26 JLS §17.5: final Field Semantics](https://docs.oracle.com/en/java/javase/26/docs/specs/jls/jls-17.html#jls-17.5)
- [Java SE 26 API: Record](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Record.html)
- [Java SE 26 API: Serializable](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/io/Serializable.html)
