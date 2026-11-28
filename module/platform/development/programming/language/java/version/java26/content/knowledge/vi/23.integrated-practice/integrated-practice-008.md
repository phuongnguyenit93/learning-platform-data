# Phát hiện sửa final và sửa thiết kế hoặc dependency

Field khai báo final được thiết kế để nhận giá trị khi khởi tạo object và giữ nguyên giá trị đó sau khi constructor hoàn tất. Tuy nhiên, một số thư viện từng dùng deep reflection để ghi vào private final field sau khi object đã được tạo, thường để deserialize dữ liệu, inject dependency, dựng fixture kiểm thử hoặc ánh xạ dữ liệu database. Cách làm này phá vỡ giả định bất biến của Java và có thể khiến JVM tối ưu hóa dựa trên giá trị ban đầu trong khi code phản chiếu lại ghi giá trị khác.

JEP 500 — Prepare to Make Final Mean Final — bắt đầu siết hành vi này trong JDK 26. Khi code dùng deep reflection để sửa final instance field, JDK 26 phát warning ở lần đầu tiên của module thực hiện thao tác đó. JDK 27 vẫn giữ chế độ cảnh báo mặc định. Một bản JDK tương lai dự kiến sẽ từ chối thao tác trái phép bằng IllegalAccessException. Vì vậy, khi nâng cấp, cần tìm ra thư viện đang sửa field, chuyển việc tạo object sang constructor/factory hoặc thay dependency có hỗ trợ cách khởi tạo phù hợp.

Đây là thay đổi hành vi runtime chính thức của JDK 26, không phải preview hay incubator API. Các tùy chọn --illegal-final-field-mutation và --enable-final-field-mutation là cơ chế kiểm soát tương thích trong giai đoạn chuyển tiếp; chúng không biến việc sửa final sau khởi tạo thành thiết kế bền vững.

## 1. Vì sao sửa final sau khi tạo object là vấn đề

Ví dụ một object cấu hình:

```java
public final class EndpointConfig {
    private final URI endpoint;
    private final Duration timeout;

    public EndpointConfig(URI endpoint, Duration timeout) {
        this.endpoint = Objects.requireNonNull(endpoint);
        this.timeout = Objects.requireNonNull(timeout);
    }

    public URI endpoint() {
        return endpoint;
    }

    public Duration timeout() {
        return timeout;
    }
}
```

Constructor thiết lập toàn bộ trạng thái cần thiết trước khi object được công bố cho phần còn lại của ứng dụng. Các field final giúp người đọc và JVM dựa vào giả định rằng giá trị field không đổi sau khi constructor hoàn tất.

final trên một reference không làm object được tham chiếu trở thành immutable. Ví dụ, một final List ngăn gán một list khác vào field, nhưng không ngăn gọi add hoặc remove trên list đó. Nếu cần dữ liệu bất biến, còn phải kiểm soát trạng thái của object bên trong, chẳng hạn dùng List.copyOf để tạo bản sao không thể sửa.

Sửa final sau constructor gây ra các vấn đề:

- Code khác có thể đã đọc giá trị cũ hoặc đã công bố object cho thread khác.
- JVM có thể tối ưu hóa việc đọc final field dựa trên ngữ nghĩa final; thay đổi phản chiếu không phải một cơ chế cập nhật trạng thái thông thường mà ứng dụng có thể dựa vào.
- Object có thể tạm thời tồn tại ở trạng thái không hợp lệ, ví dụ thiếu dependency hoặc cấu hình chỉ được điền sau khi đã chạy một method.
- Hành vi có thể khác nhau giữa runtime, JDK vendor, cách biên dịch và loại field.

Nếu một giá trị cần thay đổi trong vòng đời object, hãy biểu diễn nó bằng trạng thái mutable có API và quy tắc đồng bộ rõ ràng. Nếu giá trị phải bất biến, hãy đưa nó vào constructor hoặc factory trước khi công bố object.

## 2. Nhận diện đúng phạm vi của JEP 500

JEP 500 tập trung vào việc sửa final instance field bằng deep reflection. Trường hợp thường gặp là thư viện lấy Field, gọi setAccessible(true) hoặc trySetAccessible(), rồi gọi Field.set(...) hay một trong các method Field.setInt(), setLong(), setBoolean()... để ghi giá trị.

Các method sau được gọi là mutation methods trong Java SE:

- Field.set(Object, Object) và các biến thể setBoolean, setByte, setChar, setInt, setLong, setFloat, setDouble.
- MethodHandles.Lookup.unreflectSetter(Field) khi tạo MethodHandle có quyền ghi vào final field.

Các tình huống cần phân biệt:

| Field/hoạt động | Khả năng ghi qua reflection |
|---|---|
| Field thường, không phải final | Theo quy tắc truy cập Java/module thông thường |
| Non-static final field của class thông thường | Được kiểm soát bởi khả năng truy cập, module thực hiện mutation và chế độ illegal-final-field-mutation |
| static final field | Không thể ghi bằng các mutation methods của Field |
| Final field trong record | Không thể ghi bằng các mutation methods của Field |
| Final field trong hidden class | Không thể ghi bằng các mutation methods của Field |
| Đọc final field | Không phải mutation; việc đọc không bị JEP 500 cấm |
| Gán final field trong constructor/initializer theo Java language rules | Hợp lệ, không phải deep-reflection mutation |

setAccessible(true) chỉ yêu cầu bỏ kiểm tra truy cập Java thông thường khi điều kiện module cho phép. Nó không tự cấp quyền sửa final field. Với final instance field, quyền ghi còn phụ thuộc việc module của code gọi đã được cho phép mutation hay chưa và package khai báo field có mở cho module đó hay không.

--add-opens một mình không cho phép sửa final field. Nó chỉ có thể giải quyết điều kiện package openness cho deep reflection. --enable-final-field-mutation kiểm soát module của code thực hiện thao tác mutation; đây là hai điều kiện khác nhau.

VarHandle cũng không phải cách thay thế để ghi final field. Nếu VarHandle tham chiếu một final field, các access mode ghi và cập nhật nguyên tử không được hỗ trợ. unreflectSetter(Field) tuân theo cùng quy tắc mutation của Field.set.

## 3. Tái hiện một trường hợp sửa final bằng reflection

Đây là kiểu code có thể xuất hiện trong một thư viện mapping hoặc injection cũ:

```java
import java.lang.reflect.Field;
import java.net.URI;

EndpointConfig config = new EndpointConfig(
        URI.create("https://api.example.test"),
        Duration.ofSeconds(2));

Field endpointField =
        EndpointConfig.class.getDeclaredField("endpoint");

if (!endpointField.trySetAccessible()) {
    throw new IllegalStateException("Cannot access endpoint field");
}

// JDK 26/27: thao tác này có thể phát warning.
endpointField.set(config, URI.create("https://other.example.test"));
```

Với classpath, package của class đích thường nằm trong unnamed module; với named modules, package phải được mở cho module gọi thì trySetAccessible() mới có thể thành công. Sau đó, việc ghi final instance field còn chịu quy tắc final-field mutation riêng.

Trong JDK 26 và JDK 27, chế độ mặc định warn vẫn cho phép thao tác trái phép tiếp tục nhưng phát warning ở lần đầu tiên của module thực hiện mutation. Đây là giai đoạn chuyển tiếp để tìm dependency. Không dùng việc chương trình vẫn chạy được làm bằng chứng rằng code đã tương thích với chính sách tương lai.

## 4. Phát hiện nơi thực hiện mutation bằng warning và stack trace

### Warning mặc định trên JDK 26/27

Warning thường chỉ rõ:

- Tên final field.
- Class khai báo field.
- Class thực hiện mutation.
- Module và vị trí JAR của code gọi.

Ví dụ dạng thông báo:

```text
WARNING: Final field endpoint in class com.example.EndpointConfig
has been mutated reflectively by class com.vendor.mapper.FieldWriter
in unnamed module (file:/app/lib/legacy-mapper.jar)
WARNING: Use --enable-final-field-mutation=ALL-UNNAMED to avoid a warning
WARNING: Mutating final fields will be blocked in a future release
unless final field mutation is enabled
```

Mặc định chỉ có warning đầu tiên cho mỗi module thực hiện mutation. Một thư viện có thể sửa nhiều field hoặc sửa cùng field nhiều lần nhưng log không nhất thiết phát warning cho từng lần. Nếu cần tìm toàn bộ call site, chạy ở chế độ debug.

### Chạy với --illegal-final-field-mutation=debug

```powershell
java --illegal-final-field-mutation=debug -jar application.jar
```

Chế độ debug phát warning và stack trace cho từng final-field mutation trái phép qua deep reflection. Stack trace giúp xác định method cụ thể của thư viện, class ứng dụng đã gọi thư viện và JAR chứa code đó.

Đưa cấu hình này vào môi trường kiểm thử hoặc staging với workload đại diện. Chạy các luồng khởi động, deserialization, request, xử lý nền, plugin, ORM và các chức năng ít được gọi. Nếu chỉ chạy smoke test khởi động, có thể bỏ sót mutation chỉ xảy ra khi đọc một loại dữ liệu hoặc xử lý một endpoint cụ thể.

### Dùng JFR event jdk.FinalFieldMutation

Khi bật Java Flight Recorder, JVM có event jdk.FinalFieldMutation cho các lần sửa final instance field qua deep reflection và trường hợp dùng Lookup.unreflectSetter(Field) để lấy MethodHandle có quyền ghi.

Ghi recording:

```powershell
java -XX:StartFlightRecording=filename=final-field-mutations.jfr -jar application.jar
```

Sau khi ứng dụng chạy qua workload cần khảo sát:

```powershell
jfr print --events jdk.FinalFieldMutation final-field-mutations.jfr
```

Event chứa class khai báo field, tên field, thread thực hiện và stack trace. JFR phù hợp khi cần lưu dấu vết theo thời gian, ghép sự kiện mutation với request hoặc luồng xử lý và phân tích recording sau khi workload kết thúc.

Không chỉ xem tên field. Hãy xác định thư viện và phiên bản JAR trong stack trace, tìm lý do thư viện cần ghi field, rồi kiểm tra phiên bản mới có constructor binding, creator, record support hoặc cơ chế khởi tạo khác hay không.

## 5. Kiểm tra bằng chế độ deny

JDK 26/27 hỗ trợ các chế độ:

| Tùy chọn | Hành vi |
|---|---|
| --illegal-final-field-mutation=allow | Cho phép mutation trái phép, không phát warning |
| --illegal-final-field-mutation=warn | Cho phép mutation trái phép, warning ở lần đầu của mỗi module; đây là mặc định hiện tại |
| --illegal-final-field-mutation=debug | Cho phép mutation trái phép, warning và stack trace cho mỗi lần |
| --illegal-final-field-mutation=deny | Từ chối mutation trái phép; Field.set ném IllegalAccessException |

Để tìm lỗi tương thích trước khi một JDK tương lai chuyển sang deny mặc định, chạy test:

```powershell
java --illegal-final-field-mutation=deny -jar application.jar
```

Trong đợt migration, nên chạy deny mà không bật --enable-final-field-mutation cho tất cả module. Khi đó, các đường chạy vẫn phụ thuộc vào deep-reflection mutation sẽ bộc lộ lỗi trong kiểm thử.

Nếu có một dependency cũ chưa thể thay ngay, có thể tạm cho phép đúng module thực hiện mutation bằng --enable-final-field-mutation. Ví dụ, code trên classpath:

```powershell
java --enable-final-field-mutation=ALL-UNNAMED -jar application.jar
```

Với code trên module path, truyền danh sách tên module thực hiện mutation:

```powershell
java --enable-final-field-mutation=com.vendor.legacy.mapper,com.example.compat -m com.example.app/com.example.Main
```

Tùy chọn này cho phép code trong các module được chỉ định thực hiện final-field mutation qua reflection khi package khai báo field có thể truy cập theo quy tắc module. Nó không tự mở package của module chứa class đích.

Nếu cần mở package đích cho thư viện cũ, --add-opens có thể cần thiết để setAccessible thành công, nhưng nó không thay thế --enable-final-field-mutation. Ví dụ dưới đây là cấu hình tương thích tạm thời cho code trên classpath:

```powershell
java --enable-final-field-mutation=ALL-UNNAMED --add-opens=com.example.domain/com.example.model=ALL-UNNAMED -jar application.jar
```

Chỉ dùng cấu hình rộng như ALL-UNNAMED khi đã xác định code thực hiện mutation nằm trên classpath và chưa thể chuyển ngay. Với named modules, ưu tiên chỉ định đúng module. Ghi nhận dependency, lý do cần giữ, chủ sở hữu và điều kiện loại bỏ cờ trong kế hoạch nâng cấp.

--illegal-final-field-mutation là tùy chọn chuyển tiếp và dự kiến bị loại bỏ trong tương lai. allow chỉ nên dùng tạm trong lúc điều tra; không dùng nó để che warning trong production. --enable-final-field-mutation là opt-in tương thích cho module được chỉ định; mục tiêu cuối cùng vẫn là loại bỏ dependency vào mutation.

## 6. Tìm call site trong source và dependency

Static search hữu ích để tìm code do nhóm ứng dụng sở hữu:

```powershell
rg -n "setAccessible|trySetAccessible|unreflectSetter|Field\.set|setInt\(|setLong\(|setBoolean\(" src
```

Tìm kiếm này tạo danh sách điểm cần xem xét, không phải kết luận rằng mọi chỗ đều sửa final field. setAccessible có thể chỉ dùng để đọc field; Field.set có thể ghi field không final; wrapper/helper có thể che lời gọi thật.

Khi rà soát dependency:

1. Dùng stack trace từ debug hoặc JFR để xác định JAR, class và method.
2. Đọc release notes của thư viện và kiểm tra phiên bản mới có còn dùng deep reflection để gán final field không.
3. Kiểm tra cấu hình của thư viện: constructor binding, creator/factory, record support, custom deserializer hoặc immutable mapping.
4. Kiểm thử đúng phiên bản thư viện trên JDK 26/27 với --illegal-final-field-mutation=deny.
5. Nếu dependency không còn được duy trì, đánh giá thay thế hoặc viết adapter/factory do ứng dụng quản lý.

jdeps không thể chứng minh ứng dụng không sửa final field vì thao tác có thể được tạo qua reflection, method handle, cấu hình hoặc dependency tải động. jdeprscan cũng không phải công cụ phát hiện final-field mutation. Runtime warning, debug, JFR và kiểm thử deny mới là các tín hiệu trực tiếp cho hành vi này.

## 7. Sửa thiết kế bằng constructor hoặc factory

### Thay field injection bằng constructor injection

Thiết kế cũ thường tạo object thiếu trạng thái rồi nhờ reflection điền field:

```java
final class PaymentService {
    private final PaymentGateway gateway;

    // Framework cũ tạo instance trước rồi sửa field bằng reflection.
}
```

Chuyển sang constructor injection:

```java
final class PaymentService {
    private final PaymentGateway gateway;

    PaymentService(PaymentGateway gateway) {
        this.gateway = Objects.requireNonNull(gateway);
    }
}
```

Container dependency injection nên chọn constructor và truyền dependency khi tạo object. Nếu framework hiện tại chỉ hỗ trợ field injection cho trường hợp này, nâng cấp hoặc thay framework/binding strategy để hỗ trợ constructor injection.

### Dùng factory cho cấu hình phức tạp

Đưa việc đọc, parse và kiểm tra cấu hình vào một factory. Object miền nghiệp vụ chỉ nhận giá trị đã hợp lệ:

```java
record EndpointConfig(URI endpoint, Duration timeout) {
    EndpointConfig {
        Objects.requireNonNull(endpoint);
        Objects.requireNonNull(timeout);

        if (!endpoint.isAbsolute()) {
            throw new IllegalArgumentException("Endpoint must be absolute");
        }
        if (timeout.isNegative() || timeout.isZero()) {
            throw new IllegalArgumentException("Timeout must be positive");
        }
    }

    static EndpointConfig from(Properties properties) {
        URI endpoint = URI.create(
                properties.getProperty("service.endpoint"));
        Duration timeout = Duration.ofMillis(
                Long.parseLong(properties.getProperty("service.timeout-ms")));
        return new EndpointConfig(endpoint, timeout);
    }
}
```

Với record, canonical constructor là nơi khởi tạo component. Record final fields không thể được ghi bằng các mutation methods của Field; thư viện mapping cần gọi constructor hoặc creator phù hợp.

### Dùng builder để thu thập dữ liệu, constructor để chốt trạng thái

Builder không cần sửa field của object đích. Builder có thể mutable trong giai đoạn thu thập đầu vào, sau đó tạo một object hoàn chỉnh:

```java
final class ClientOptions {
    private final URI baseUri;
    private final Duration timeout;
    private final int maxAttempts;

    private ClientOptions(Builder builder) {
        this.baseUri = Objects.requireNonNull(builder.baseUri);
        this.timeout = Objects.requireNonNull(builder.timeout);
        this.maxAttempts = builder.maxAttempts;
    }

    static final class Builder {
        private URI baseUri;
        private Duration timeout = Duration.ofSeconds(3);
        private int maxAttempts = 2;

        Builder baseUri(URI value) {
            this.baseUri = value;
            return this;
        }

        Builder timeout(Duration value) {
            this.timeout = value;
            return this;
        }

        Builder maxAttempts(int value) {
            this.maxAttempts = value;
            return this;
        }

        ClientOptions build() {
            if (maxAttempts < 1) {
                throw new IllegalArgumentException("maxAttempts must be positive");
            }
            return new ClientOptions(this);
        }
    }
}
```

Builder có thể thay đổi giá trị của chính nó trước khi gọi build(). Object ClientOptions nhận snapshot của các giá trị trong constructor và không cần được chỉnh sửa sau khi tạo.

## 8. Chọn cách sửa theo loại dependency

| Nơi phát sinh mutation | Cách xử lý ưu tiên |
|---|---|
| Dependency injection | Chuyển sang constructor injection hoặc factory do container gọi |
| JSON/XML binder | Chọn constructor/creator binding, custom deserializer tạo object hoàn chỉnh hoặc phiên bản thư viện đã hỗ trợ immutable object |
| ORM/data mapper | Dùng constructor mapping/immutable mapping nếu framework hỗ trợ; nếu không, ánh xạ row sang persistence DTO rồi tạo domain object qua constructor |
| Mocking/test fixture | Inject interface/collaborator qua constructor; dùng factory hoặc fixture builder thay vì sửa field của object đã tạo |
| Configuration framework | Parse và validate cấu hình trước, sau đó tạo immutable config object |
| Plugin/serialization library | Nâng cấp thư viện, chọn serialization creator/proxy hoặc định dạng có constructor binding; kiểm thử dữ liệu cũ và mới |
| Thư viện không còn duy trì | Thay dependency hoặc bọc bằng adapter/factory được kiểm soát; chỉ giữ opt-in mutation trong giai đoạn chuyển tiếp nếu thật sự bắt buộc |

Đối với ORM, không giả định mọi framework hỗ trợ cùng mô hình immutable entity. Kiểm tra yêu cầu constructor, proxy, lazy loading, dirty checking và mapping của đúng framework/version. Nếu framework cần một persistence model mutable, có thể giữ model đó ở ranh giới persistence rồi chuyển sang domain object immutable sau khi đọc dữ liệu.

Đối với JSON/XML mapping, kiểm tra binder thực sự gọi constructor/creator. Chỉ thêm annotation hoặc bật một cấu hình tên là immutable chưa đủ; xác minh bằng integration test trên JDK đích và quan sát rằng không còn warning/event mutation.

## 9. Nếu trạng thái thật sự cần thay đổi

Không phải mọi field đều nên là final. Nếu giá trị là trạng thái thay đổi hợp lệ trong vòng đời object, hãy biểu diễn điều đó bằng API tường minh:

```java
final class RefreshableToken {
    private volatile Token currentToken;

    RefreshableToken(Token initialToken) {
        this.currentToken = Objects.requireNonNull(initialToken);
    }

    Token current() {
        return currentToken;
    }

    void refresh(Token newToken) {
        currentToken = Objects.requireNonNull(newToken);
    }
}
```

Ví dụ này cho phép thay giá trị qua method refresh() với visibility semantics của volatile. Nếu cập nhật cần compare-and-set, nhiều bước nguyên tử hoặc phối hợp giữa nhiều thread, cân nhắc AtomicReference và xác định rõ invariant đồng thời.

Không xóa final chỉ để làm warning biến mất. Trước khi đổi field thành mutable, trả lời được:

- Thành phần nào được phép cập nhật?
- Thời điểm nào được phép cập nhật?
- Thread nào có thể đọc/ghi đồng thời?
- Cần volatile, lock hay atomic operation nào?
- Giá trị mới được validate và công bố như thế nào?

Nếu không có câu trả lời rõ ràng, nhiều khả năng field nên được khởi tạo đúng một lần qua constructor/factory.

## 10. Không dùng API khác để né giới hạn

Các cách sau không phải giải pháp migration:

- Dùng VarHandle để ghi final field. Các write/update access mode không được hỗ trợ cho final field.
- Dùng MethodHandles.Lookup.unreflectSetter(Field) để lách quy tắc. Đây cũng là mutation method và chịu giới hạn tương ứng.
- Chuyển sang sun.misc.Unsafe, JNI hoặc bytecode manipulation chỉ để giữ hành vi cũ. Chúng không tạo ra hợp đồng Java SE công khai, ổn định cho việc sửa final field.
- Thêm --add-opens với hy vọng nó tự cấp quyền mutation. Package openness và final-field-mutation permission là hai điều kiện riêng.
- Chuyển mọi field sang non-final mà không xem xét invariant và thread-safety.
- Dùng --illegal-final-field-mutation=allow hoặc bật --enable-final-field-mutation trên toàn bộ ứng dụng để che warning lâu dài.

Mục tiêu của JEP 500 là giữ cho ý nghĩa final đáng tin cậy hơn. Một đường vòng khác để tiếp tục ghi vào field sẽ giữ lại chính dependency mà migration cần loại bỏ.

## 11. Bài thực hành migration theo từng bước

Giả sử ứng dụng có một dependency mapping cũ dùng reflection để gán field private final trong EndpointConfig. Thực hiện theo quy trình:

1. Chạy toàn bộ test hiện có trên JDK 26 hoặc 27 và thu warning final-field mutation.
2. Chạy lại với --illegal-final-field-mutation=debug để lấy stack trace của mọi mutation trái phép.
3. Ghi nhận field, class thực hiện mutation, tên module và JAR chứa thư viện.
4. Tìm phiên bản thư viện mới có constructor/creator binding; nếu không có, đánh giá custom mapper hoặc dependency thay thế.
5. Chuyển EndpointConfig sang constructor/record/factory và đưa validation vào lúc tạo.
6. Chạy integration test cho dữ liệu hợp lệ, dữ liệu thiếu field, giá trị null, dữ liệu cũ và trường hợp parse lỗi.
7. Bỏ --add-opens hoặc --enable-final-field-mutation đã thêm chỉ để hỗ trợ dependency đó.
8. Chạy toàn bộ workload với --illegal-final-field-mutation=deny; xác nhận không còn IllegalAccessException do mutation, warning hoặc JFR event ngoài danh sách đã được giải quyết.

Kết quả migration nên lưu được bằng chứng: dependency/version đã thay, constructor hoặc creator được gọi, test dữ liệu cũ đã pass, và ứng dụng chạy được ở chế độ deny mà không cần quyền mutation ngoài dự kiến.

## 12. Ma trận kiểm thử sau refactor

| Nhóm | Kiểm tra | Kết quả mong đợi |
|---|---|---|
| Khởi tạo | Tạo object qua constructor/factory | Mọi final field có giá trị hợp lệ trước khi object được công bố |
| Validation | Null, giá trị ngoài miền, thiếu cấu hình | Constructor/factory từ chối với lỗi rõ ràng |
| Reflection | Chạy --illegal-final-field-mutation=debug | Không còn mutation trái phép trong luồng ứng dụng |
| Deny mode | Chạy --illegal-final-field-mutation=deny | Các chức năng chính không dựa vào final-field mutation trái phép |
| Dependency | Chạy đúng JAR/framework production | Không có thư viện cũ âm thầm ghi final field |
| Serialization/mapping | Round-trip hoặc đọc dữ liệu cũ và mới | Giá trị được khôi phục qua constructor/creator được hỗ trợ |
| Concurrency | Công bố object cho thread khác sau khởi tạo | Không có trạng thái một phần hoặc mutation sau publication |
| Regression | So sánh hành vi trước/sau thay dependency | API nghiệp vụ và dữ liệu đầu ra giữ đúng hợp đồng |
| JFR | In jdk.FinalFieldMutation từ recording | Không còn event ngoài trường hợp chuyển tiếp được phê duyệt |

Với test serialization, chỉ xác nhận object đọc lại có giá trị mong đợi là chưa đủ nếu thư viện bên thứ ba đang được thay. Hãy kiểm tra cả implementation path hoặc JFR/runtime diagnostics để biết nó có còn deep-reflection mutation không. Java Serialization tích hợp có cơ chế khôi phục object riêng; không suy rộng cơ chế đó cho mọi JSON/XML binder hoặc ORM.

## 13. Trạng thái và điều kiện áp dụng trên JDK 26/27

| Nội dung | JDK 26 | JDK 27 |
|---|---|---|
| JEP 500 | Bắt đầu phát warning khi deep reflection sửa final instance field | Tiếp tục phát warning |
| --illegal-final-field-mutation=warn | Mặc định; cho phép mutation trái phép và warning tối đa một lần mỗi module | Vẫn là mặc định |
| --illegal-final-field-mutation=debug | Warning và stack trace cho từng mutation trái phép | Có thể dùng để chẩn đoán tương tự |
| --illegal-final-field-mutation=deny | Field.set từ chối mutation trái phép bằng IllegalAccessException | Dùng để kiểm tra sẵn sàng cho thay đổi tương lai |
| --enable-final-field-mutation | Cho phép module được chỉ định thực hiện mutation khi các điều kiện truy cập khác cũng thỏa | Vẫn có trong launcher |
| Mặc định deny | Chưa áp dụng | Chưa áp dụng; được dự kiến cho JDK tương lai |

JEP 500 không yêu cầu bật --enable-preview và không thêm một API preview để thay thế field mutation. Các tùy chọn kiểm soát mutation là cờ launcher; không dùng chúng như API trong code ứng dụng.

## 14. Những điểm cần nhớ

- JDK 26 bắt đầu warning khi deep reflection sửa final instance field; JDK 27 vẫn mặc định warn.
- Warning mặc định chỉ phát lần đầu cho mỗi module; dùng --illegal-final-field-mutation=debug để có stack trace cho mọi mutation trái phép.
- JFR event jdk.FinalFieldMutation ghi nhận field, class khai báo, thread và stack trace.
- Chạy --illegal-final-field-mutation=deny trong kiểm thử để phát hiện dependency không còn tương thích với chính sách tương lai.
- --enable-final-field-mutation cho phép module gọi được chỉ định; package đích vẫn phải có quyền truy cập phù hợp. --add-opens riêng lẻ không cho phép mutation.
- static final, final field trong record và hidden class không thể ghi bằng mutation methods của Field.
- VarHandle không cung cấp write access cho final field; Lookup.unreflectSetter(Field) chịu cùng quy tắc mutation.
- Ưu tiên constructor injection, factory, builder, record canonical constructor và constructor/creator binding của thư viện.
- Nếu trạng thái thực sự cần thay đổi, dùng field mutable cùng API cập nhật và quy tắc đồng bộ tường minh.
- Không dùng cờ allow, Unsafe hoặc reflection workaround để che dependency; loại bỏ, thay thế hoặc sửa thư viện gây mutation.

## Tài liệu tham khảo

- [Oracle JDK 26 Migration Guide: Preparing for final Field Mutation Restrictions](https://docs.oracle.com/en/java/javase/26/migrate/preparing-final-field-mutation-restrictions.html)
- [Oracle JDK 27 Migration Guide: Preparing for final Field Mutation Restrictions](https://docs.oracle.com/en/java/javase/27/migrate/preparing-final-field-mutation-restrictions.html)
- [JDK 26 Release Notes: JEP 500 — Prepare to Make Final Mean Final](https://www.oracle.com/java/technologies/javase/26-relnote-issues.html)
- [JDK 27 Migration Guide: Significant Changes in JDK 27](https://docs.oracle.com/en/java/javase/27/migrate/significant-changes-jdk-27-release.html)
- [Java SE 26 API: Field](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/reflect/Field.html)
- [Java SE 26 API: Mutation methods](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/reflect/doc-files/MutationMethods.html)
- [Java SE 26 API: MethodHandles.Lookup](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html)
- [Java SE 26 API: VarHandle](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/invoke/VarHandle.html)
- [Java SE 26 API: ObjectInputStream](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/io/ObjectInputStream.html)
- [Java SE 27 java command: final-field mutation options](https://docs.oracle.com/en/java/javase/27/docs/specs/man/java.html)
