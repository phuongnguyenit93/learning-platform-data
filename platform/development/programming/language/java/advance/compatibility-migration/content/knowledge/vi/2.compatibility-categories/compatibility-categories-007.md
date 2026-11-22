# Vì sao biên dịch thành công chưa chứng minh ứng dụng chạy đúng

Trong quá trình nâng cấp Java hoặc thay đổi phiên bản thư viện, một lần biên dịch thành công thường tạo cảm giác rằng hệ thống đã tương thích. Tuy nhiên, kết quả đó chỉ xác nhận một phạm vi hẹp: mã nguồn được biên dịch đã vượt qua các kiểm tra của compiler với JDK, tùy chọn biên dịch và tập thư viện có mặt trên compile classpath tại thời điểm build.

Ứng dụng thực tế còn phải nạp lớp, liên kết các lời gọi, khởi tạo framework, đọc cấu hình, kết nối dịch vụ, xử lý dữ liệu và thực hiện đúng nghiệp vụ trong môi trường chạy cụ thể. Những việc này diễn ra sau biên dịch và chịu ảnh hưởng của runtime classpath, JDK/JRE triển khai, cấu hình, dữ liệu, hệ điều hành và các dịch vụ bên ngoài. Vì vậy, **compile success là một bằng chứng cần thiết, nhưng chưa đủ để kết luận ứng dụng chạy đúng hoặc tương thích sau migration**.

## 1. Biên dịch xác nhận điều gì?

Khi biên dịch Java, compiler đọc mã nguồn, phân tích cú pháp, kiểm tra kiểu, kiểm tra quyền truy cập và phân giải các kiểu, trường, phương thức mà mã nguồn tham chiếu. Sau đó compiler tạo bytecode trong các file `.class`.

Ví dụ:

```java
public class GreetingApp {
    public static void main(String[] args) {
        System.out.println("Hello Java");
    }
}
```

Nếu compiler hoàn tất, ta biết đoạn mã này hợp lệ theo ngôn ngữ Java và các kiểu mà compiler nhìn thấy. Nhưng compiler không chạy `main`, không mở kết nối cơ sở dữ liệu, không khởi tạo Spring ApplicationContext, không đọc cấu hình production và cũng không gọi API của hệ thống thanh toán.

Một lệnh như `compileJava` trong Gradle hoặc `mvn compile` trong Maven thường chỉ thực hiện giai đoạn biên dịch tương ứng. Nó không mặc nhiên bao gồm kiểm thử, đóng gói, khởi động ứng dụng hay kiểm tra hành vi trên môi trường đích.

Có thể hình dung chuỗi triển khai như sau:

```text
Mã nguồn
   |
   v
Biên dịch thành công
   |  Kiểm tra cú pháp, kiểu, API trên compile classpath
   v
Bytecode và tài nguyên
   |
   v
Đóng gói artifact
   |
   v
Nạp lớp và liên kết trên runtime classpath
   |
   v
Khởi tạo ứng dụng, framework và cấu hình
   |
   v
Kết nối dịch vụ, đọc/ghi dữ liệu
   |
   v
Thực hiện nghiệp vụ trong môi trường thật
```

Lỗi ở bất kỳ giai đoạn nào phía sau đều có thể xảy ra dù bước biên dịch trước đó đã thành công.

## 2. Tương thích có nhiều lớp khác nhau

Trong một đợt nâng cấp Java, “tương thích” không chỉ có nghĩa mã nguồn vẫn biên dịch được. Cần phân biệt các lớp sau:

| Lớp tương thích | Câu hỏi cần trả lời | Bằng chứng phù hợp |
|---|---|---|
| Tương thích mã nguồn (source compatibility) | Mã nguồn hiện tại có biên dịch với compiler và API mục tiêu không? | Biên dịch sạch bằng đúng JDK và tùy chọn mục tiêu |
| Tương thích nhị phân (binary compatibility) | Bytecode đã biên dịch có liên kết được với các lớp và thư viện khi chạy không? | Chạy artifact với đúng runtime classpath; kiểm tra phụ thuộc và liên kết |
| Tương thích hành vi (behavioral compatibility) | Cùng lời gọi API có còn tạo ra kết quả và tác dụng như ứng dụng mong đợi không? | Unit test, integration test, contract test và kiểm thử hồi quy |
| Tương thích nền tảng/môi trường (platform compatibility) | Ứng dụng có chạy được trên JDK, hệ điều hành, kiến trúc và cấu hình triển khai mục tiêu không? | Chạy trên môi trường gần production, kiểm tra startup và vận hành |
| Tương thích dữ liệu/giao thức (data and protocol compatibility) | Phiên bản mới có đọc, ghi và trao đổi dữ liệu với phiên bản hoặc dịch vụ liên quan không? | Kiểm thử schema, migration dữ liệu và contract giữa các hệ thống |

Biên dịch thành công chủ yếu cung cấp bằng chứng cho lớp đầu tiên. Một số vấn đề ở các lớp khác chỉ xuất hiện khi JVM nạp lớp hoặc khi ứng dụng xử lý tình huống thực tế.

## 3. Compile classpath và runtime classpath có thể khác nhau

Đây là một nguyên nhân thường gặp khiến dự án biên dịch được nhưng không chạy được.

Compiler cần các thư viện để hiểu kiểu và kiểm tra lời gọi trong mã nguồn. Khi chạy, JVM lại cần các lớp thực tế để nạp và liên kết. Hai tập thư viện này có thể khác nhau.

Trong Gradle, `compileClasspath` và `runtimeClasspath` là hai configuration riêng. Một thư viện có thể được khai báo chỉ phục vụ biên dịch, trong khi thư viện cần thiết lúc chạy lại bị thiếu hoặc bị thay bằng phiên bản khác. Các dependency bắc cầu, dependency conflict, `runtimeOnly`, plugin đóng gói hoặc cách triển khai cũng có thể làm runtime classpath khác với điều mà developer hình dung.

### Ví dụ: biên dịch với một phiên bản thư viện, chạy với phiên bản khác

Giả sử thư viện `payment-client` phiên bản 1 có phương thức:

```java
public class PaymentClient {
    public Receipt submit(Order order) {
        // Gửi yêu cầu thanh toán
        return new Receipt();
    }
}
```

Một module hoặc plugin đã được biên dịch khi phương thức `submit(Order)` còn tồn tại. Sau đó môi trường chạy lại nạp phiên bản thư viện không còn phương thức đó. Bytecode của client vẫn chứa tham chiếu đến phương thức cũ; khi JVM phân giải lời gọi, ứng dụng có thể gặp:

```text
java.lang.NoSuchMethodError
```

Một tình huống tương tự xảy ra khi module ứng dụng biên dịch với phiên bản thư viện mới nhưng máy chủ triển khai lại ưu tiên một JAR cũ. Compiler đã nhìn thấy API phù hợp, còn JVM thực tế lại nạp một API khác.

Điểm cần nhớ: **phiên bản thư viện được dùng lúc biên dịch không tự động chứng minh phiên bản thư viện được nạp lúc chạy là giống hệt**.

Với Gradle, có thể xem cây phụ thuộc của từng classpath bằng các lệnh như:

```bash
./gradlew dependencies --configuration compileClasspath
./gradlew dependencies --configuration runtimeClasspath
```

Khi cần tìm lý do một phiên bản được chọn, dùng `dependencyInsight` cho đúng dependency và configuration. Với Maven, `mvn dependency:tree` giúp xem cây phụ thuộc được giải quyết. Hãy kiểm tra artifact cuối cùng và môi trường triển khai nếu ứng dụng chạy trong application server, container hoặc nền tảng có cơ chế cung cấp thư viện riêng.

## 4. Bytecode có thể không phù hợp với JVM đang chạy

JDK dùng để biên dịch và Java runtime dùng để chạy là hai yếu tố có liên quan nhưng không nhất thiết là cùng một bản cài đặt.

Nếu biên dịch bằng JDK mới mà không đặt mức bytecode/API phù hợp, compiler có thể tạo class file mà JVM cũ không đọc được. Khi đó ứng dụng có thể dừng ngay lúc nạp lớp với lỗi:

```text
java.lang.UnsupportedClassVersionError
```

Ví dụ, một class được biên dịch cho Java 21 không thể mặc nhiên chạy trên Java 17. Việc máy developer có JDK 21 và build thành công không chứng minh máy production đang dùng Java 21.

Khi cần nhắm tới một phiên bản Java cụ thể, hãy cấu hình toolchain và mức phát hành phù hợp. Với `javac`, tùy chọn `--release` giúp giới hạn cả phiên bản bytecode và tập API Java SE được phép sử dụng theo release đó. Trong Gradle, nên cấu hình Java toolchain và `options.release` nhất quán với baseline của dự án.

Ví dụ minh họa cho một dự án nhắm Java 17:

```groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 17
}
```

Cấu hình này giúp kiểm soát môi trường biên dịch và API mục tiêu. Dù vậy, vẫn cần chạy artifact bằng Java 17 thực tế hoặc môi trường tương đương để xác nhận runtime, vì cấu hình build không kiểm chứng được toàn bộ máy chủ triển khai.

## 5. Lớp và phương thức có thể không liên kết được lúc chạy

Compiler kiểm tra các tham chiếu dựa trên thư viện mà nó nhìn thấy. Khi chạy, JVM phải tìm được định nghĩa lớp và thành viên tương ứng trong các JAR thực tế. Nếu cấu trúc thư viện thay đổi không tương thích, lỗi có thể chỉ xuất hiện lúc nạp hoặc gọi mã.

Một số lỗi thường gặp:

| Lỗi | Ý nghĩa thường gặp |
|---|---|
| `ClassNotFoundException` | Mã chủ động yêu cầu nạp một lớp, thường qua `Class.forName` hoặc class loader, nhưng không tìm thấy lớp đó |
| `NoClassDefFoundError` | JVM cần định nghĩa một lớp nhưng không thể sử dụng định nghĩa đó; có thể do thiếu lớp ở runtime hoặc do lần khởi tạo lớp trước đó thất bại |
| `NoSuchMethodError` | Bytecode tham chiếu tới phương thức không có trong lớp được nạp lúc chạy |
| `NoSuchFieldError` | Bytecode tham chiếu tới trường không có trong lớp được nạp lúc chạy |
| `AbstractMethodError` | Khi thực thi, một lời gọi cần implementation cụ thể nhưng lớp thực tế không cung cấp implementation tương thích |
| `IncompatibleClassChangeError` | Cấu trúc hoặc cách sử dụng một thành viên/lớp đã thay đổi theo cách không tương thích nhị phân, chẳng hạn khác biệt giữa static và instance hoặc giữa class và interface |

Các lỗi này là tín hiệu cần điều tra dependency graph, thứ tự classpath, JAR thực tế được đóng gói và class loader đang sử dụng. Không nên chỉ thêm một dependency bất kỳ để làm lỗi biến mất, vì việc đó có thể che giấu xung đột phiên bản hoặc tạo thêm xung đột khác.

## 6. Mã biên dịch được nhưng hành vi API đã thay đổi

Một thư viện có thể giữ nguyên tên lớp, tên phương thức và kiểu tham số, vì vậy mã nguồn vẫn biên dịch. Tuy nhiên, hợp đồng hành vi của API có thể đã thay đổi giữa các phiên bản.

Ví dụ, một phiên bản cũ của API nhận timeout theo giây, còn phiên bản mới định nghĩa timeout theo mili giây nhưng vẫn dùng cùng kiểu `long`. Đoạn mã sau vẫn hợp lệ về kiểu:

```java
client.setTimeout(30L);
```

Nhưng nếu ý nghĩa tham số thay đổi, giá trị `30` có thể tương đương 30 giây ở phiên bản cũ và chỉ 30 mili giây ở phiên bản mới. Compiler không thể biết ý định của người viết để cảnh báo sự khác biệt ngữ nghĩa này.

Các thay đổi hành vi khác có thể gồm:

- Giá trị mặc định thay đổi, chẳng hạn retry, timeout, pool size hoặc chế độ xác thực.
- Thứ tự kết quả thay đổi trong khi hợp đồng trước đó không cam kết thứ tự.
- Quy tắc xử lý `null`, dữ liệu rỗng, encoding hoặc timezone thay đổi.
- Ngoại lệ được ném trong một tình huống trước đây trả về giá trị bình thường.
- API vẫn chạy nhưng thay đổi cách đồng bộ, thread-safety hoặc vòng đời tài nguyên.
- Một thao tác trở nên bất đồng bộ hoặc có thêm tác dụng phụ.

Đây là lý do cần đọc release notes và migration guide của thư viện, đồng thời viết kiểm thử dựa trên hành vi mà ứng dụng thực sự phụ thuộc vào. Kiểm thử chỉ xác nhận rằng phương thức được gọi thành công là chưa đủ; cần xác nhận kết quả, tác dụng phụ và các trường hợp biên.

## 7. Framework có thể chỉ phát hiện lỗi khi khởi tạo ứng dụng

Với ứng dụng Java dùng Spring hoặc framework tương tự, compile success không đảm bảo quá trình bootstrap thành công.

Compiler thường không giải quyết toàn bộ quá trình quét component, tạo bean, đánh giá điều kiện auto-configuration, tạo proxy, bind cấu hình hoặc khởi tạo kết nối. Các cơ chế dựa trên reflection và tên lớp được cấu hình dưới dạng chuỗi cũng không nhất thiết được kiểm tra như một lời gọi Java thông thường.

Ví dụ:

```java
@Service
public class OrderService {
    private final PaymentGateway paymentGateway;

    public OrderService(PaymentGateway paymentGateway) {
        this.paymentGateway = paymentGateway;
    }
}
```

Lớp trên có thể biên dịch dù trong runtime application context không có bean nào phù hợp với `PaymentGateway`. Khi Spring tạo `OrderService`, ứng dụng có thể thất bại vì không tìm được dependency cần inject.

Các lỗi khởi động thường xuất phát từ:

- Bean hoặc module không được scan, không được đăng ký hoặc bị điều kiện auto-configuration loại bỏ.
- Phiên bản Spring Boot, Spring Framework và thư viện tích hợp không tương thích.
- Thay đổi constructor, proxy, package hoặc cơ chế reflection làm cấu hình cũ không còn hiệu lực.
- Thiếu property bắt buộc, sai profile hoặc sai tên biến môi trường.
- Resource không được đưa vào artifact hoặc đường dẫn resource thay đổi.
- Service provider metadata hoặc cấu hình plugin bị thiếu trong JAR đóng gói.

Vì vậy, cần chạy ứng dụng đã đóng gói và quan sát toàn bộ quá trình startup. Một bài kiểm thử chỉ khởi tạo một class đơn lẻ không thay thế được kiểm tra application context hoặc bootstrap của ứng dụng thật.

## 8. Cấu hình và môi trường triển khai không được compiler kiểm tra

Ứng dụng thường đọc thông tin quan trọng từ môi trường bên ngoài mã nguồn: biến môi trường, file YAML/properties, secret, tham số JVM, đường dẫn file, cổng mạng, chứng thư TLS và cấu hình của container.

Mã sau vẫn có thể biên dịch bình thường:

```java
String jdbcUrl = System.getenv("DB_URL");
```

Nhưng khi chạy, `DB_URL` có thể không tồn tại, sai định dạng hoặc trỏ tới cơ sở dữ liệu không truy cập được. Tương tự, cấu hình có thể hợp lệ về cú pháp nhưng chứa tên profile, key hoặc giá trị không còn được phiên bản framework hỗ trợ.

Các khác biệt môi trường thường gặp gồm:

- Developer chạy Java 21 nhưng container production chạy Java 17.
- Máy local có file cấu hình hoặc biến môi trường mà CI không có.
- Hệ điều hành khác nhau về đường dẫn, quyền truy cập file, encoding hoặc tên file phân biệt hoa thường.
- Production dùng chứng thư, proxy, DNS, firewall hoặc chính sách TLS khác local.
- Dịch vụ cơ sở dữ liệu hoặc message broker có phiên bản và cấu hình khác môi trường kiểm thử.
- JVM flags, memory limit, timezone, locale hoặc charset mặc định khác nhau.

Một lần chạy thành công trên laptop chỉ chứng minh hành vi trong môi trường đó. Để đánh giá migration, hãy chạy artifact bằng JDK, cấu hình và loại môi trường triển khai mục tiêu, đồng thời kiểm tra các dependency bên ngoài mà ứng dụng cần dùng.

## 9. Dữ liệu cũ và giao thức giữa các dịch vụ vẫn có thể bị phá vỡ

Compiler chủ yếu kiểm tra mã nguồn và kiểu dữ liệu trong chương trình. Nó không xác nhận dữ liệu đang lưu trong database, file đã serialize từ phiên bản trước hoặc payload mà dịch vụ khác gửi đến.

Ví dụ, một bản nâng cấp đổi tên cột, thay đổi kiểu dữ liệu hoặc chuyển một trường từ bắt buộc sang tùy chọn. Java code mới có thể biên dịch, nhưng truy vấn vẫn thất bại khi chạy trên schema cũ. Tương tự, một service có thể biên dịch sau khi nâng thư viện JSON nhưng đọc sai payload vì thay đổi naming strategy, date format hoặc cách xử lý trường thiếu.

Với Java serialization, thay đổi cấu trúc lớp và `serialVersionUID` có thể khiến dữ liệu serialize trước đó không còn đọc được theo cách mong muốn. Với REST, messaging hoặc RPC, việc hai phía cùng biên dịch không đảm bảo hai bên đồng thuận về field, enum, version, encoding, timeout hoặc semantics của message.

Khi migration ảnh hưởng dữ liệu hoặc giao thức, cần kiểm tra:

1. Ứng dụng mới có đọc được dữ liệu do phiên bản cũ tạo ra không?
2. Ứng dụng cũ có còn đọc được dữ liệu do phiên bản mới ghi ra trong giai đoạn rolling deployment không?
3. Migration database có chạy đúng thứ tự và có thể phục hồi khi thất bại không?
4. Các producer/consumer hoặc service gọi nhau có cùng hiểu contract mới không?
5. Có cần chiến lược expand-migrate-contract để nhiều phiên bản cùng tồn tại trong thời gian chuyển đổi không?

Những câu hỏi này phải được trả lời bằng kiểm thử dữ liệu và tích hợp, không thể suy ra từ kết quả compile.

## 10. Reflection, ServiceLoader và class loader tạo ra các phụ thuộc ẩn

Không phải mọi quan hệ giữa các lớp đều xuất hiện dưới dạng import và lời gọi phương thức tĩnh trong mã nguồn.

Ví dụ:

```java
Class<?> type = Class.forName("com.example.plugin.FastExporter");
Object exporter = type.getDeclaredConstructor().newInstance();
```

Compiler không nhất thiết kiểm tra được rằng chuỗi `com.example.plugin.FastExporter` trỏ tới lớp tồn tại trong runtime artifact. Nếu package bị đổi tên, JAR bị loại khỏi runtime classpath hoặc module không mở package cần thiết, lỗi chỉ xuất hiện khi đoạn mã được thực thi.

Các cơ chế dễ bị ảnh hưởng khi migration gồm:

- `Class.forName`, reflection và truy cập thành viên bằng tên chuỗi.
- `ServiceLoader` và file khai báo provider trong `META-INF/services`.
- Annotation scanning và framework tạo proxy lúc chạy.
- Plugin system có class loader riêng.
- Java Platform Module System (JPMS), đặc biệt quan hệ `requires`, `exports` và `opens`.
- Thư viện truy cập JDK internals hoặc dựa vào hành vi không được Java SE cam kết.

Khi nâng cấp JDK, cần rà soát cảnh báo API deprecated/removed, quyền truy cập reflection và các phụ thuộc vào internal API. Mã nguồn biên dịch được vẫn có thể gặp `IllegalAccessException`, `InaccessibleObjectException` hoặc lỗi nạp provider khi chạy với module boundary và JDK mới.

## 11. Một số rủi ro vận hành chỉ xuất hiện dưới tải hoặc theo thời gian

Ngay cả khi ứng dụng khởi động và các luồng chức năng cơ bản đều chạy được, migration vẫn có thể làm thay đổi hiệu năng hoặc đặc tính vận hành.

Ví dụ:

- Garbage collector, memory footprint hoặc thời gian pause khác trước.
- Thread pool, connection pool hoặc cơ chế scheduling làm tăng độ trễ hay gây cạn tài nguyên.
- Một API thay đổi đồng bộ/bất đồng bộ dẫn tới race condition.
- Retry không phù hợp khiến tải lên hệ thống phụ thuộc tăng mạnh.
- Tài nguyên như file, socket, thread hoặc connection không được giải phóng đúng cách.
- Lỗi chỉ xuất hiện khi dữ liệu lớn, số request đồng thời cao hoặc ứng dụng chạy liên tục nhiều giờ.

Các vấn đề này không được phát hiện bằng compile, và thường cũng không xuất hiện trong một smoke test quá ngắn. Cần chọn kiểm thử tải, soak test, quan sát metric/log/trace và kịch bản lỗi theo mức độ rủi ro của ứng dụng.

## 12. Quy trình xác minh sau khi biên dịch thành công

Một quy trình migration đáng tin cậy nên tăng dần phạm vi xác minh. Mỗi bước kiểm tra một loại rủi ro khác nhau.

### Bước 1: Xác nhận đúng JDK và mục tiêu bytecode

- Kiểm tra JDK thực tế được dùng trong CI và local.
- Khai báo Java toolchain và release target rõ ràng.
- Kiểm tra phiên bản Java trên môi trường chạy.
- Bảo đảm mọi module, plugin và thư viện nội bộ đều được build cho baseline tương thích.

### Bước 2: Kiểm tra dependency graph

- So sánh compile classpath và runtime classpath.
- Kiểm tra dependency bị nâng, hạ hoặc loại trừ ngoài dự kiến.
- Kiểm tra dependency bắc cầu và thư viện do container/application server cung cấp.
- Xem nội dung artifact cuối cùng để xác nhận JAR và resource cần thiết đã được đóng gói.

### Bước 3: Build sạch và chạy kiểm thử tự động

- Chạy clean build để giảm nguy cơ dùng output cũ.
- Chạy unit test cho logic và các trường hợp biên.
- Chạy integration test với database, broker hoặc service cần thiết.
- Chạy contract test khi có giao tiếp giữa các module hoặc hệ thống.
- Đọc kỹ các test bị bỏ qua, flaky hoặc chỉ chạy trên một JDK.

### Bước 4: Chạy chính artifact sẽ triển khai

Không chỉ chạy từ IDE hoặc source set của developer. Hãy đóng gói artifact theo cách triển khai thực tế rồi chạy artifact đó bằng runtime mục tiêu. Bước này giúp phát hiện sai khác về manifest, resource, dependency đóng gói, entry point, class loader và JVM version.

### Bước 5: Kiểm tra khởi động và cấu hình thực tế

- Khởi động với profile và cấu hình gần production.
- Xác nhận framework tạo đủ bean, route, scheduler và listener cần thiết.
- Kiểm tra kết nối database, cache, broker và dịch vụ bên ngoài.
- Kiểm tra secret, TLS, quyền truy cập và health endpoint.
- Xác nhận quá trình shutdown giải phóng tài nguyên đúng cách.

### Bước 6: Kiểm thử hồi quy và dữ liệu

- Chạy các luồng nghiệp vụ quan trọng từ đầu đến cuối.
- Dùng dữ liệu đại diện, dữ liệu cũ và dữ liệu biên.
- Kiểm tra schema migration và khả năng tương thích khi triển khai nhiều phiên bản.
- So sánh kết quả nghiệp vụ với baseline trước migration.

### Bước 7: Xác minh vận hành

Với thay đổi có ảnh hưởng lớn, kiểm thử tải và theo dõi metric, log, trace trong thời gian đủ dài. Đặt tiêu chí rõ ràng cho latency, error rate, memory, CPU, connection pool và khả năng phục hồi. Khi triển khai, nên có health check, giám sát và phương án rollback phù hợp.

## 13. Chọn công cụ theo loại rủi ro

Không có một công cụ duy nhất chứng minh mọi loại tương thích. Có thể kết hợp các công cụ sau tùy mục tiêu:

| Công cụ/kỹ thuật | Hữu ích để kiểm tra | Giới hạn |
|---|---|---|
| `javac --release` / Gradle Java toolchain | Phiên bản ngôn ngữ, bytecode và API Java SE mục tiêu | Không xác nhận cấu hình hay hành vi lúc chạy |
| `./gradlew dependencies` / `dependencyInsight` | Dependency graph theo configuration và lý do chọn phiên bản | Cần đối chiếu với artifact và class loader thực tế |
| `mvn dependency:tree` | Cây dependency Maven đã giải quyết | Không chứng minh mọi thư viện bên ngoài runtime đều giống nhau |
| `jar tf app.jar` | Kiểm tra lớp và resource có trong JAR | Không xác nhận lớp có thể khởi tạo hoặc hành vi đúng |
| `javap -verbose` | Xem bytecode, class-file version và thông tin lớp | Không thay thế việc chạy trên JVM mục tiêu |
| `jdeps` | Phân tích phụ thuộc ở mức class/package và phát hiện một số phụ thuộc JDK internals | Không phát hiện đầy đủ reflection, cấu hình chuỗi hoặc lỗi hành vi |
| Unit/integration/contract test | Kiểm tra hành vi và tương tác đã được mô tả trong test | Chỉ bao phủ các tình huống thực sự được kiểm thử |
| Smoke/load/soak test và observability | Kiểm tra khởi động, luồng chính và đặc tính vận hành | Cần thiết kế kịch bản và ngưỡng đánh giá phù hợp |

Các công cụ phân tích tĩnh có thể thu hẹp phạm vi tìm kiếm, nhưng kết luận cuối cùng vẫn cần dựa trên artifact, runtime và kịch bản sử dụng thực tế.

## 14. Ví dụ về một kết luận migration có căn cứ

Giả sử nhóm nâng ứng dụng từ Java 17 lên Java 21. Pipeline chạy `compileJava` thành công. Kết quả đó chỉ cho phép kết luận rằng mã nguồn được compile trong pipeline tương thích với compiler và compile classpath đã chọn.

Để kết luận ứng dụng tương thích với Java 21, nhóm cần có thêm bằng chứng như:

- Các module và plugin đều được build với cấu hình mục tiêu đã thống nhất.
- Runtime classpath không còn phiên bản thư viện xung đột hoặc thiếu dependency.
- Artifact được đóng gói và khởi chạy thành công trên Java 21.
- Application context, cấu hình, resource và kết nối dịch vụ khởi tạo thành công.
- Bộ kiểm thử hồi quy xác nhận các luồng nghiệp vụ quan trọng vẫn đúng.
- Dữ liệu và contract giữa các dịch vụ tương thích với cách triển khai mới.
- Các chỉ số vận hành nằm trong ngưỡng chấp nhận được khi có tải đại diện.

Nếu mới chỉ có log `BUILD SUCCESSFUL` ở task biên dịch, trạng thái chính xác nên là **đã xác nhận biên dịch**, chưa phải **đã xác nhận runtime hoặc behavioral compatibility**. Cách ghi nhận này giúp báo cáo migration phản ánh đúng bằng chứng, tránh biến một bước build xanh thành kết luận tương thích toàn hệ thống.

## 15. Nguyên tắc cần giữ khi đánh giá tương thích

1. **Xác định phạm vi của mỗi bằng chứng.** Compile chứng minh compile; test chứng minh các kịch bản đã test; startup chứng minh ứng dụng khởi động trong cấu hình đã dùng.
2. **Kiểm tra đúng artifact và đúng runtime.** Một lần chạy từ IDE không thay thế việc chạy gói sẽ triển khai trên JDK mục tiêu.
3. **Đối chiếu dependency ở cả hai thời điểm.** API mà compiler nhìn thấy phải phù hợp với lớp JVM thực sự nạp.
4. **Kiểm tra hợp đồng hành vi.** Chữ ký phương thức không đổi không đồng nghĩa ý nghĩa, mặc định và tác dụng phụ không đổi.
5. **Đưa dữ liệu và môi trường vào kiểm thử.** Cấu hình, schema, giao thức và dịch vụ ngoài là một phần của tính tương thích.
6. **Báo cáo kết luận theo mức bằng chứng.** Phân biệt rõ đã compile, đã test, đã chạy trên runtime mục tiêu và đã xác minh vận hành.

Biên dịch thành công là cột mốc đầu tiên trong migration. Chỉ khi bytecode được nạp đúng, ứng dụng khởi tạo được, các tương tác và dữ liệu vẫn đúng, và hệ thống đáp ứng yêu cầu trong môi trường mục tiêu, ta mới có đủ cơ sở để kết luận việc nâng cấp đã đạt yêu cầu tương thích.
