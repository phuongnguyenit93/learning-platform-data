# Java 26 và các nhóm thay đổi ngôn ngữ, API, JVM, công cụ

## 1. Phạm vi và bối cảnh phiên bản

Java SE 26 được phát hành chính thức ngày 17/03/2026. Đây là một feature release trong chu kỳ phát hành sáu tháng của OpenJDK. Những thay đổi đáng chú ý tập trung vào HTTP/3, pattern matching cho kiểu nguyên thủy, đồng thời có cấu trúc, xử lý vector, API PEM, tính toàn vẹn của trường `final` và tối ưu HotSpot.

Cần đặt kiến thức Java 26 vào đúng bối cảnh hiện tại:

- JDK 27 đã phát hành ngày 15/09/2026 và là feature release mới hơn.
- Bản cập nhật Oracle JDK 27.0.1.1 phát hành ngày 17/11/2026.
- Theo bảng vòng đời hỗ trợ Java của Oracle, JDK 26 kết thúc vòng đời hỗ trợ vào tháng 09/2026; JDK 27 có mốc kết thúc dự kiến tháng 03/2027.
- JDK 25 được đánh dấu LTS trong lộ trình Oracle, với mốc hỗ trợ đến tháng 09/2033. Chính sách hỗ trợ thực tế còn tùy nhà cung cấp JDK và hợp đồng của tổ chức.

JDK 26 và JDK 27 là các feature release ngắn hạn, không được đánh dấu LTS trong lộ trình trên.

Vì vậy, bài này dùng JDK 26 làm mốc để hiểu các thay đổi được đưa vào phiên bản đó, đồng thời ghi rõ những gì đã tiếp tục thay đổi ở JDK 27. Không nên chọn JDK 26 làm runtime triển khai mới chỉ vì muốn sử dụng một tính năng của phiên bản này. Hãy chọn bản JDK còn được nhà cung cấp hỗ trợ; ưu tiên JDK 25 LTS khi cần chu kỳ hỗ trợ dài, hoặc JDK 27 khi tổ chức chủ động theo feature release mới.

## 2. Phân biệt tính năng chính thức, preview và incubator

Một thay đổi được đưa vào JDK không có nghĩa là API của nó đã ổn định. Khi đọc JEP hoặc release notes, cần xác định trạng thái trước khi quyết định sử dụng.

| Trạng thái | Ý nghĩa | Cách sử dụng |
|---|---|---|
| Final / Standard | Đã trở thành một phần chính thức của nền tảng Java SE hoặc JDK | Có thể dùng trong ứng dụng sản xuất sau khi kiểm tra tương thích và điều kiện vận hành |
| Preview | Đã có thiết kế và triển khai để dùng thử, nhưng chưa cam kết là API cuối cùng | Phải bật preview khi biên dịch và chạy; API hoặc hành vi có thể thay đổi hoặc bị loại bỏ ở bản sau |
| Incubator | API thử nghiệm được cung cấp trong module riêng để thu thập phản hồi và tiếp tục phát triển | Phải thêm module khi biên dịch và chạy; không nên tạo phụ thuộc lâu dài vào API này |
| Removed / Deprecated | API đã bị loại bỏ hoặc đang được cảnh báo sẽ loại bỏ | Kiểm tra mã nguồn và thư viện phụ thuộc khi nâng cấp |

Các JEP trọng tâm của JDK 26 có trạng thái như sau:

| JEP | Nội dung | Trạng thái trong JDK 26 |
|---|---|---|
| 517 | HTTP/3 cho HTTP Client API | Chính thức |
| 530 | Primitive Types in Patterns, instanceof, and switch | Preview lần thứ tư |
| 525 | Structured Concurrency | Preview lần thứ sáu |
| 526 | Lazy Constants | Preview lần thứ hai |
| 524 | PEM Encodings of Cryptographic Objects | Preview lần thứ hai |
| 529 | Vector API | Incubator lần thứ mười một |
| 522 | G1 GC giảm đồng bộ hóa để tăng throughput | Chính thức |
| 516 | Ahead-of-Time Object Caching with Any GC | Chính thức |
| 500 | Prepare to Make Final Mean Final | Thay đổi chính thức, phát cảnh báo khi sửa trường final bằng deep reflection |

Tình trạng tiếp tục phát triển trên JDK 27 cũng cần được lưu ý: primitive patterns chuyển sang preview lần thứ năm (JEP 532), Structured Concurrency sang preview lần thứ bảy (JEP 533), Lazy Constants sang preview lần thứ ba (JEP 531), PEM sang preview lần thứ ba (JEP 538) và Vector API sang incubator lần thứ mười hai (JEP 537). Điều này cho thấy các API thử nghiệm vẫn chưa trở thành hợp đồng ổn định dù đã xuất hiện qua nhiều phiên bản.

## 3. Ngôn ngữ: pattern matching với kiểu nguyên thủy

JEP 530 mở rộng pattern matching để hỗ trợ kiểu nguyên thủy trong các ngữ cảnh pattern. Toán tử `instanceof` và `switch` cũng được mở rộng để làm việc với các kiểu như `byte`, `short`, `int`, `long`, `float`, `double`, `char` và `boolean`.

Trước thay đổi này, pattern matching chủ yếu xử lý kiểu tham chiếu. Khi làm việc với số nguyên thủy, lập trình viên thường phải kiểm tra, chuyển kiểu và xử lý điều kiện riêng. JEP 530 giúp biểu diễn việc kiểm tra và lấy giá trị theo cùng một cấu trúc pattern.

Ví dụ dùng `instanceof` với kiểu nguyên thủy:

~~~java
public class PrimitivePatternDemo {
    public static void main(String[] args) {
        float value = 1000.01f;

        if (value instanceof float f) {
            System.out.println("Giá trị float: " + f);
        }

        if (value instanceof double d) {
            System.out.println("Giá trị double: " + d);
        }

        if (value instanceof int i) {
            System.out.println("Giá trị int: " + i);
        }

    }
}
~~~

Trong ví dụ này, phép chuyển từ `float` sang `double` là chính xác nên pattern tương ứng khớp. Phép chuyển từ `float` sang `int` có thể làm mất phần thập phân nên pattern không khớp. Đây là điểm quan trọng: pattern kiểm tra khả năng chuyển đổi an toàn, không đơn giản chấp nhận mọi phép ép kiểu có thể viết được.

`switch` cũng có thể nhận các giá trị nguyên thủy như `long`, `float`, `double` và `boolean`. Ví dụ:

~~~java
static String classify(float value) {
    return switch (value) {
        case 0f -> "Bằng không";
        case float n when n > 0f -> "Số dương";
        case float n -> "Số âm hoặc giá trị NaN";
    };
}
~~~

Pattern có biến `n` cho phép sử dụng giá trị đã khớp ngay trong nhánh. Mệnh đề `when` bổ sung điều kiện cho pattern. Các quy tắc về độ chính xác của phép chuyển đổi và thứ tự nhánh vẫn được trình biên dịch kiểm tra; nhánh tổng quát đặt sai vị trí có thể làm các nhánh sau bị xem là không thể đạt tới.

Primitive patterns còn dùng được bên trong record pattern. Ví dụ:

~~~java
record Cup(double volume) {}

Cup cup = new Cup(34.567f);

if (cup instanceof Cup(float volume)) {
    System.out.println("Thể tích có thể biểu diễn chính xác dưới dạng float: "
            + volume);
}
~~~

Trong trường hợp này, pattern vừa kiểm tra record vừa lấy thành phần của record. Phép chuyển từ thành phần `double` sang `float` chỉ khớp nếu giá trị có thể chuyển đổi mà không mất thông tin.

**Trạng thái và điều kiện sử dụng:** đây là preview lần thứ tư trong JDK 26 và vẫn là preview lần thứ năm trong JDK 27. Không được xem cú pháp này là nền tảng ổn định cho thư viện công khai hoặc mã cần tương thích dài hạn. Khi thử nghiệm trên JDK 26, cần bật preview ở cả bước biên dịch và chạy:

~~~bash
javac --release 26 --enable-preview -d out PrimitivePatternDemo.java
java --enable-preview -cp out PrimitivePatternDemo
~~~

Preview gắn với phiên bản phát hành cụ thể. Khi chuyển sang JDK 27, phải biên dịch và chạy bằng preview của JDK 27, sau khi kiểm tra JEP và API tương ứng; không thể giả định bytecode dùng preview của JDK 26 sẽ chạy như một tính năng preview của JDK 27.

## 4. HTTP Client: hỗ trợ HTTP/3

JEP 517 bổ sung HTTP/3 cho `java.net.http.HttpClient`. Ứng dụng có thể yêu cầu giao thức HTTP/3 bằng API chuẩn mà không phải tự triển khai tầng giao thức. HTTP/3 sử dụng QUIC trên UDP và TLS, trong khi HTTP/2 sử dụng TCP.

Ví dụ yêu cầu HTTP/3:

~~~java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;

public class Http3Demo {
    public static void main(String[] args) throws Exception {
        HttpClient client = HttpClient.newBuilder()
                .version(HttpClient.Version.HTTP_3)
                .build();

        HttpRequest request = HttpRequest.newBuilder()
                .uri(URI.create("https://example.com/api/items"))
                .GET()
                .build();

        HttpResponse<String> response = client.send(
                request,
                HttpResponse.BodyHandlers.ofString()
        );

        System.out.println("HTTP version thực tế: " + response.version());
        System.out.println(response.body());
    }
}
~~~

Có một số điều kiện vận hành cần hiểu rõ:

- HTTP/2 vẫn là phiên bản được ưu tiên mặc định. Ứng dụng phải chủ động đặt phiên bản ưu tiên thành `HTTP_3` ở `HttpClient` hoặc `HttpRequest`.
- Việc đặt `HTTP_3` là yêu cầu ưu tiên, không phải cam kết rằng mọi request đều sẽ được truyền bằng HTTP/3. Phiên bản thực tế phụ thuộc khả năng kết nối, server, cấu hình TLS và cách phát hiện endpoint.
- Request phải dùng URI `https`. Request HTTP không mã hóa sẽ không được gửi bằng HTTP/3.
- Trong triển khai `HttpClient` tích hợp của JDK 26, HTTP/3 không được hỗ trợ khi request đi qua proxy. Tùy chế độ phát hiện, client có thể hạ xuống HTTP/2 hoặc HTTP/1.1; chế độ chỉ cho phép HTTP/3 có thể khiến request thất bại.
- Có thể kiểm tra giao thức thực tế qua `HttpResponse.version()` thay vì suy luận từ cấu hình client.

API có tùy chọn `HttpOption.H3_DISCOVERY` để định hướng cách tìm kết nối HTTP/3. Các chế độ đáng chú ý gồm:

- `ANY`: để client chọn cách tìm hoặc thiết lập kết nối phù hợp; có thể thử HTTP/3 qua QUIC và kết nối TLS/TCP.
- `ALT_SVC`: dựa vào thông tin HTTP Alternative Services do server quảng bá.
- `HTTP_3_URI_ONLY`: chỉ thử HTTP/3 tại host và port trong URI; nếu không thiết lập được kết nối phù hợp thì request thất bại.

JDK 26 cũng bổ sung `HttpRequest.BodyPublishers.ofFileChannel(FileChannel, long, long)` để gửi một vùng byte của file qua HTTP request mà không cần đọc toàn bộ file vào bộ nhớ. Điều này hữu ích cho upload theo phần hoặc upload một vùng dữ liệu xác định.

Một thay đổi liên quan đến HTTP server tích hợp cũng cần chú ý khi nâng cấp: từ JDK 26, map thuộc tính của mỗi `HttpExchange` không còn được chia sẻ mặc định với `HttpContext`. Mỗi exchange có map riêng. Ứng dụng đang dựa vào hành vi chia sẻ cũ cần kiểm tra lại cách truyền dữ liệu giữa context và exchange.

## 5. Đồng thời có cấu trúc

JEP 525 tiếp tục phát triển Structured Concurrency, API giúp quản lý một nhóm tác vụ đồng thời như một đơn vị công việc. Thay vì tạo nhiều tác vụ rồi tự quản lý vòng đời, lỗi và hủy tác vụ ở nhiều vị trí, chương trình mở một scope, tạo các tác vụ con, chờ kết quả và đóng scope trong cùng một cấu trúc.

Ví dụ một request cần tải thông tin người dùng và danh sách đơn hàng song song:

~~~java
import java.util.List;
import java.util.concurrent.StructuredTaskScope;

record Dashboard(User user, List<Order> orders) {}

static Dashboard loadDashboard() throws Exception {
    try (var scope = StructuredTaskScope.open()) {
        var userTask = scope.fork(() -> loadUser());
        var ordersTask = scope.fork(() -> loadOrders());

        scope.join();

        return new Dashboard(userTask.get(), ordersTask.get());
    }
}
~~~

Với cấu hình mặc định của JDK 26:

1. `StructuredTaskScope.open()` mở scope do thread hiện tại sở hữu.
2. Mỗi lời gọi `fork()` tạo một thread để chạy tác vụ con; mặc định các thread này là virtual thread.
3. `join()` chờ các tác vụ hoàn thành như một đơn vị. Với joiner mặc định, nếu một tác vụ thất bại thì các tác vụ còn lại bị yêu cầu hủy và lỗi được báo về scope.
4. `close()` được gọi tự động bởi `try-with-resources`. Scope đợi các thread con kết thúc trước khi luồng điều khiển đi ra ngoài khối.

Lợi ích chính là vòng đời tác vụ được giới hạn theo cấu trúc của request cha. Lỗi, hủy tác vụ và việc chờ hoàn tất được quản lý tập trung hơn. API cũng hỗ trợ các chính sách join khác nhau, chẳng hạn lấy kết quả thành công đầu tiên hoặc yêu cầu tất cả tác vụ thành công.

Cần thiết kế tác vụ con có khả năng phản hồi interruption. Nếu một tác vụ chặn ở thao tác không thể ngắt hoặc bỏ qua tín hiệu ngắt, việc đóng scope có thể phải chờ rất lâu. Các thao tác `fork()`, `join()` và `close()` phải được gọi bởi thread sở hữu scope; không chia sẻ scope để nhiều thread tùy ý thao tác.

**Trạng thái và điều kiện sử dụng:** Structured Concurrency là preview lần thứ sáu trong JDK 26 và preview lần thứ bảy trong JDK 27. API và cách cấu hình đã thay đổi qua các vòng preview, vì vậy chỉ nên thử nghiệm trong môi trường kiểm soát, không xây dựng hợp đồng thư viện lâu dài dựa trên chữ ký hiện tại.

## 6. Vector API và SIMD

JEP 529 tiếp tục phát triển Vector API ở trạng thái incubator lần thứ mười một. API nằm trong module `jdk.incubator.vector` và biểu diễn phép toán trên nhiều phần tử cùng lúc. Đây là cách khai thác SIMD (Single Instruction, Multiple Data): một lệnh vector có thể thực hiện cùng phép toán trên nhiều lane dữ liệu.

Ví dụ nhân hai mảng số thực:

~~~java
import java.util.Arrays;
import jdk.incubator.vector.FloatVector;
import jdk.incubator.vector.VectorMask;
import jdk.incubator.vector.VectorSpecies;

public class VectorMultiply {
    private static final VectorSpecies<Float> SPECIES =
            FloatVector.SPECIES_PREFERRED;

    static void multiply(float[] a, float[] b, float[] result) {
        if (a.length != b.length || a.length != result.length) {
            throw new IllegalArgumentException("Các mảng phải cùng kích thước");
        }

        for (int i = 0; i < a.length; i += SPECIES.length()) {
            VectorMask<Float> mask = SPECIES.indexInRange(i, a.length);

            FloatVector va = FloatVector.fromArray(SPECIES, a, i, mask);
            FloatVector vb = FloatVector.fromArray(SPECIES, b, i, mask);

            va.mul(vb).intoArray(result, i, mask);
        }
    }

    public static void main(String[] args) {
        float[] a = {1f, 2f, 3f, 4f, 5f};
        float[] b = {2f, 3f, 4f, 5f, 6f};
        float[] result = new float[a.length];

        multiply(a, b, result);
        System.out.println(Arrays.toString(result));
    }
}
~~~

`SPECIES_PREFERRED` chọn độ rộng vector phù hợp với nền tảng đang chạy. Mask xử lý phần tử cuối khi độ dài mảng không chia hết cho số lane của vector, tránh đọc hoặc ghi vượt giới hạn mảng.

Để biên dịch và chạy trên JDK 26, thêm module incubator:

~~~bash
javac --release 26 --add-modules jdk.incubator.vector \
      -d out VectorMultiply.java

java --add-modules jdk.incubator.vector \
     -cp out VectorMultiply
~~~

Vector API không phải lúc nào cũng nhanh hơn vòng lặp scalar. Khả năng sinh lệnh vector phụ thuộc CPU, kiến trúc, JIT, dạng dữ liệu và cách viết phép toán. Nếu phần cứng không hỗ trợ phép toán hoặc vector shape được chọn, runtime có thể dùng triển khai scalar. Nên ưu tiên species phù hợp nền tảng, xử lý phần tử dư bằng mask và benchmark trên workload thực tế.

API này tiếp tục ở trạng thái incubator lần thứ mười hai trong JDK 27. Module, kiểu dữ liệu và phương thức có thể thay đổi hoặc bị loại bỏ. Tránh để API incubator trở thành kiểu dữ liệu trong interface công khai, định dạng trao đổi dữ liệu hoặc hợp đồng phụ thuộc giữa nhiều service.

## 7. Bảo mật: PEM và tính toàn vẹn của trường final

### 7.1. Mã hóa và giải mã PEM

JEP 524 bổ sung API chuẩn để chuyển đổi các đối tượng mật mã sang và từ định dạng PEM. PEM thường dùng để lưu trữ hoặc trao đổi chứng chỉ, khóa công khai, khóa riêng và danh sách thu hồi chứng chỉ.

API chính nằm trong `java.security`:

- `PEMEncoder` chuyển đối tượng triển khai `DEREncodable` thành dữ liệu PEM.
- `PEMDecoder` đọc dữ liệu PEM và trả về đối tượng mật mã tương ứng.
- Có thể cấu hình mã hóa khóa riêng khi encode hoặc giải mã khóa riêng đã được mã hóa bằng mật khẩu.

Ví dụ chuyển đổi chứng chỉ X.509:

~~~java
import java.security.PEMDecoder;
import java.security.PEMEncoder;
import java.security.cert.X509Certificate;

static String encodeCertificate(X509Certificate certificate) {
    return PEMEncoder.of().encodeToString(certificate);
}

static X509Certificate decodeCertificate(String pem) {
    return PEMDecoder.of().decode(pem, X509Certificate.class);
}
~~~

PEM chỉ là định dạng biểu diễn và trao đổi dữ liệu. Việc encode thành PEM không tự biến khóa riêng thành dữ liệu được bảo vệ. Nếu cần mã hóa khóa riêng, phải cấu hình encoder với mật khẩu và quản lý mật khẩu an toàn; không ghi khóa hoặc mật khẩu vào log, repository hay file cấu hình công khai.

**Trạng thái:** JEP 524 là preview lần thứ hai trong JDK 26 và tiếp tục là preview lần thứ ba trong JDK 27. Chữ ký và kiểu đối tượng hỗ trợ có thể thay đổi. Khi cần API ổn định cho sản phẩm, kiểm tra API chuẩn của JDK đang được hỗ trợ và cân nhắc giải pháp mật mã đã ổn định trong hệ sinh thái hiện tại.

### 7.2. Chuẩn bị cho việc hạn chế sửa trường final bằng reflection

JEP 500 chuẩn bị để trường `final` thực sự giữ được ý nghĩa bất biến. Một số thư viện trước đây dùng deep reflection để sửa trường private hoặc trường final sau khi đối tượng đã khởi tạo. Cách làm này có thể phá vỡ giả định của JVM về tính bất biến, gây khó khăn cho tối ưu hóa và làm suy yếu tính toàn vẹn của nền tảng.

Từ JDK 26, lần đầu một module thực hiện sửa trường final bằng deep reflection, JVM phát cảnh báo. Mặc định của `--illegal-final-field-mutation` trong JDK 26 là `warn`. Các tùy chọn điều khiển gồm:

| Tùy chọn | Hành vi |
|---|---|
| `--illegal-final-field-mutation=allow` | Cho phép và không cảnh báo |
| `--illegal-final-field-mutation=warn` | Cho phép nhưng phát cảnh báo; đây là chế độ mặc định của JDK 26 |
| `--illegal-final-field-mutation=debug` | Cảnh báo kèm stack trace |
| `--illegal-final-field-mutation=deny` | Từ chối thao tác sửa trường final bằng deep reflection |

`--enable-final-field-mutation` cho phép chỉ định module được phép thực hiện thao tác cần thiết. Ví dụ cho mã trên classpath:

~~~bash
java --enable-final-field-mutation=ALL-UNNAMED -jar app.jar
~~~

Không nên dùng tùy chọn cho phép toàn cục như cách xử lý mặc định. Trước tiên, hãy cập nhật framework và thư viện để chúng không cần sửa trường final. Có thể chạy kiểm thử với `--illegal-final-field-mutation=deny` để tìm những đường đi còn phụ thuộc vào hành vi này. `--add-opens` chỉ điều chỉnh quyền truy cập sâu vào package; tự nó không cấp quyền sửa trường final.

Oracle định hướng các bản JDK tương lai sẽ từ cảnh báo chuyển sang từ chối mặc định. Vì vậy, xử lý cảnh báo ngay trong quá trình nâng cấp sẽ giảm rủi ro khi chuyển sang phiên bản JDK tiếp theo.

### 7.3. Bổ sung bảo mật trong JDK 27

Một thay đổi bảo mật thuộc JDK 27, không phải JDK 26, là JEP 527: Post-Quantum Hybrid Key Exchange for TLS 1.3. JDK 27 bổ sung cơ chế trao đổi khóa lai kết hợp thuật toán chống lượng tử với thuật toán truyền thống cho TLS 1.3. Ứng dụng dùng API `javax.net.ssl` có thể hưởng lợi khi cấu hình, provider và phía đối tác hỗ trợ cơ chế tương ứng.

Khi nâng cấp, vẫn cần kiểm thử handshake với các server, proxy, load balancer và thiết bị TLS trong hệ thống. Không suy luận rằng mọi kết nối đều đã dùng thuật toán lai chỉ từ việc nâng JDK.

## 8. Tối ưu JVM và garbage collector

### 8.1. G1 GC giảm đồng bộ hóa

JEP 522 cải thiện throughput của G1 bằng cách giảm đồng bộ hóa giữa thread ứng dụng và thread nền tối ưu card table. G1 dùng card table để theo dõi các thay đổi tham chiếu giữa các vùng heap. Việc cập nhật và tối ưu cấu trúc này có thể tạo chi phí đồng bộ hóa trong workload thay đổi nhiều tham chiếu đối tượng.

JDK 26 bổ sung cơ chế card table thứ hai để thread ứng dụng và thread tối ưu hoạt động độc lập hơn. Thay đổi nằm trong HotSpot và không yêu cầu sửa mã ứng dụng. Một số workload có thể tăng throughput và giảm chi phí write barrier; mức cải thiện phụ thuộc vào đặc điểm cấp phát, cập nhật tham chiếu, heap và CPU.

Không nên thay đổi cấu hình GC chỉ dựa trên mô tả tính năng. Hãy đo throughput, thời gian pause, CPU tiêu thụ, heap và độ trễ p95/p99 trước và sau nâng cấp. G1 được cải thiện không có nghĩa là G1 luôn là lựa chọn tốt nhất cho mọi workload.

### 8.2. AOT Object Caching với mọi garbage collector

JEP 516 mở rộng AOT cache để lưu trạng thái đối tượng theo định dạng trung lập với garbage collector. Trước thay đổi này, một số tối ưu AOT từ JEP 483 bị giới hạn khi dùng ZGC do cách biểu diễn và ánh xạ trạng thái đối tượng phụ thuộc GC. JDK 26 cho phép cơ chế cache đối tượng AOT hoạt động với các collector khác nhau, bao gồm ZGC.

Mục tiêu là giảm thời gian khởi động và warmup bằng cách tái sử dụng dữ liệu đã được thu thập trong lần chạy huấn luyện. Một quy trình điển hình gồm:

1. Chạy ứng dụng với workload đại diện để thu thập cấu hình AOT.
2. Tạo cache từ dữ liệu đã thu thập.
3. Khởi động ứng dụng trong môi trường triển khai với cache tương ứng.
4. Theo dõi log AOT và đo thời gian khởi động, warmup, throughput.

JDK cung cấp các tùy chọn như `-XX:AOTCacheOutput` để tạo cache và `-XX:AOTCache` để nạp cache. Cache có ràng buộc tương thích với phiên bản JDK, hệ điều hành, CPU, ứng dụng và một số tùy chọn JVM. Không xem file cache là artifact có thể chia sẻ tùy ý giữa mọi môi trường. Nếu cache không tương thích, cần xác định nguyên nhân và tạo lại cache phù hợp.

AOT cache là một cơ chế tối ưu của HotSpot, không đồng nghĩa với biên dịch ứng dụng thành native executable. JIT vẫn có vai trò trong quá trình thực thi và tối ưu theo hành vi thực tế.

### 8.3. Cải thiện hành vi của virtual thread khi chờ khởi tạo class

JDK 26 cải thiện một trường hợp runtime liên quan đến virtual thread: khi một virtual thread phải chờ thread khác hoàn tất khởi tạo class, trong phần lớn trường hợp nó có thể unmount khỏi carrier thread trong lúc chờ. Carrier thread được giải phóng để scheduler chạy virtual thread khác.

Thay đổi này giúp giảm nguy cơ giữ platform thread trong thời gian chờ khởi tạo class, đặc biệt ở hệ thống có nhiều virtual thread và có đường khởi tạo class chậm. Đây là cải thiện runtime; ứng dụng không cần thay đổi cú pháp tạo virtual thread. Tuy vậy, vẫn cần theo dõi thread dump và hành vi chờ thực tế để xác định bottleneck.

### 8.4. Lazy Constants

JEP 526 giới thiệu `java.lang.LazyConstant` ở trạng thái preview lần thứ hai trong JDK 26. Lazy constant giữ một giá trị được tính toán khi cần và chỉ khởi tạo thành công một lần. Sau khi khởi tạo, nội dung của nó không thể được thay thế; JVM có thể tối ưu việc đọc giá trị tương tự cách tối ưu trường final.

Ví dụ:

~~~java
import java.lang.LazyConstant;
import java.util.regex.Pattern;

static final LazyConstant<Pattern> EMAIL_PATTERN =
        LazyConstant.of(() -> Pattern.compile("^[^@]+@[^@]+\\.[^@]+$"));

static boolean isValidEmail(String value) {
    return EMAIL_PATTERN.get().matcher(value).matches();
}
~~~

Khởi tạo bị trì hoãn đến lần gọi `get()` đầu tiên. Sau đó, giá trị được giữ lại cho các lần truy cập tiếp theo. Cần phân biệt tính bất biến của tham chiếu với tính bất biến sâu của đối tượng: nếu lazy constant giữ một collection có thể sửa đổi, nội dung collection vẫn có thể thay đổi.

Lazy Constants tiếp tục là preview lần thứ ba trong JDK 27. Không nên dùng API này làm nền tảng ổn định cho thư viện hoặc hợp đồng lâu dài khi chưa chấp nhận rủi ro thay đổi API.

## 9. Một số API chuẩn khác đáng chú ý

Ngoài các JEP lớn, JDK 26 có những thay đổi API nhỏ hơn nhưng có thể hữu ích khi phát triển hoặc nâng cấp:

| API / thay đổi | Giá trị sử dụng |
|---|---|
| `Process` triển khai `AutoCloseable` | Có thể quản lý vòng đời process và stream bằng `try-with-resources` |
| `Instant.plusSaturating(Duration)` | Cộng thời lượng theo kiểu bão hòa, trả về giới hạn gần nhất thay vì tràn phạm vi thời gian |
| `Duration.MIN` và `Duration.MAX` | Biểu diễn giới hạn nhỏ nhất và lớn nhất của `Duration` |
| `UUID.ofEpochMillis(long)` | Tạo UUID phiên bản 7 từ Unix epoch milliseconds |
| `Comparator.min()` và `Comparator.max()` | Lấy phần tử nhỏ hơn hoặc lớn hơn theo thứ tự của comparator |
| Hỗ trợ Unicode 17.0 | Cập nhật dữ liệu ký tự, chuẩn hóa, xử lý hai chiều và biểu thức chính quy |

Đây là API chuẩn của JDK 26, không phải preview hoặc incubator. Khi áp dụng, vẫn cần kiểm tra mức Java tối thiểu mà ứng dụng hỗ trợ và cấu hình biên dịch của dự án. Ví dụ, dùng một phương thức mới trong mã nguồn sẽ khiến ứng dụng không thể chạy trên runtime cũ không có phương thức đó.

## 10. Công cụ biên dịch, chạy và chẩn đoán

Cần phân biệt ba trường hợp khi cấu hình công cụ:

**Mã chỉ dùng API chính thức**

Biên dịch với mức release mục tiêu để giới hạn API và cú pháp được phép sử dụng:

~~~bash
javac --release 26 -d out Main.java
java -cp out Main
~~~

**Mã dùng preview**

Bật preview khi biên dịch và chạy bằng cùng feature release:

~~~bash
javac --release 26 --enable-preview -d out Main.java
java --enable-preview -cp out Main
~~~

**Mã dùng incubator module**

Thêm module ở cả bước biên dịch và chạy. Ví dụ Vector API:

~~~bash
javac --release 26 --add-modules jdk.incubator.vector -d out Main.java
java --add-modules jdk.incubator.vector -cp out Main
~~~

`--enable-preview` và `--add-modules` giải quyết hai vấn đề khác nhau. Preview bật tính năng preview của phiên bản JDK đang dùng; add-modules đưa module incubator vào graph module của ứng dụng. Một chương trình dùng cả hai nhóm tính năng cần khai báo đủ các tùy chọn tương ứng.

Một số bước kiểm tra hữu ích khi nâng cấp:

- Dùng `java --version` và `javac --version` để xác nhận JDK thực tế được dùng trong terminal, IDE, CI và container.
- Dùng `jdeps --jdk-internals` để phát hiện phụ thuộc vào API nội bộ của JDK.
- Kiểm tra dependency, annotation processor, agent và framework có dùng reflection để sửa trường final hay không.
- Dùng `jcmd` và thread dump để phân tích trạng thái thread. JDK 26 bổ sung thông tin owner của park blocker trong một số thread dump được tạo bằng `HotSpotDiagnosticMXBean.dumpThreads` và `jcmd Thread.dump_to_file`.
- Dùng JFR để thu thập dữ liệu runtime, sau đó đối chiếu CPU, allocation, GC, lock contention và latency trước/sau nâng cấp.
- Với AOT cache, xác nhận cache được tạo từ workload đại diện và tương thích với môi trường chạy thực tế.

Không dùng cờ preview hoặc incubator trong cấu hình sản xuất chỉ để làm cho quá trình biên dịch thành công. Cần ghi nhận rõ tính năng nào đang được thử nghiệm, ai sở hữu rủi ro nâng cấp và kế hoạch thay thế khi API đổi.

## 11. Quy trình đánh giá khi nâng cấp JDK

Có thể áp dụng quy trình sau cho một service hoặc ứng dụng Java:

1. **Kiểm kê runtime và build.** Ghi nhận JDK của máy phát triển, CI, image container, môi trường staging và production. Xác nhận mức source, target và release của dự án.
2. **Kiểm tra phụ thuộc.** Rà soát framework, thư viện, plugin, agent, native library, annotation processor và các API nội bộ. Đặc biệt tìm deep reflection sửa trường final.
3. **Phân loại tính năng dự định dùng.** Ghi rõ API là final, preview hay incubator. Chỉ dùng preview/incubator khi mục tiêu thử nghiệm đã được xác định.
4. **Kiểm thử tương thích.** Biên dịch bằng JDK mục tiêu, chạy unit test, integration test và kiểm thử tải. Kiểm tra cả hành vi HTTP, TLS, proxy, GC, thread và serialization.
5. **Đo hiệu năng.** So sánh startup, warmup, throughput, p95/p99 latency, allocation rate, GC pause và mức dùng CPU. Với Vector API, dùng dữ liệu có kích thước đại diện và chạy trên phần cứng đích.
6. **Chọn bản JDK có hỗ trợ.** Đối chiếu lịch cập nhật bảo mật và thời hạn hỗ trợ của nhà cung cấp. Nếu cần LTS, đánh giá JDK 25; nếu cần feature release mới hơn, đánh giá JDK 27 và duy trì lịch cập nhật.
7. **Triển khai có quan sát.** Canary hoặc rollout theo từng nhóm instance; theo dõi lỗi kết nối, cảnh báo reflection, GC, thread và latency trước khi mở rộng.

Đối với HTTP/3, cần kiểm tra server đích có hỗ trợ HTTP/3, mạng có cho phép QUIC/UDP, cấu hình proxy có tương thích và client có thực sự dùng HTTP/3 qua `response.version()`. Đối với Structured Concurrency, kiểm tra khả năng hủy tác vụ và phản hồi interruption. Đối với Vector API, kiểm tra fallback và hiệu năng trên CPU triển khai. Đối với AOT, xác nhận cache không bị tạo từ môi trường khác biệt đáng kể.

## 12. Kết luận định hướng

Java 26 có một số cải tiến đã chính thức như HTTP/3 trong HTTP Client, tối ưu G1 và AOT object caching với nhiều GC. Những thay đổi khác như primitive pattern matching, Structured Concurrency, Lazy Constants và PEM API vẫn ở trạng thái preview; Vector API vẫn là incubator. JEP 500 bắt đầu phát cảnh báo khi deep reflection sửa trường final, giúp ứng dụng chuẩn bị cho các hạn chế mạnh hơn trong tương lai.

Khi học Java 26, điều quan trọng là đọc đúng trạng thái của từng JEP, biết cờ biên dịch/chạy cần thiết và hiểu giới hạn runtime. Khi áp dụng vào hệ thống hiện tại, hãy đối chiếu JDK 27 và chính sách hỗ trợ của nhà cung cấp. JDK 26 hiện đã hết vòng đời hỗ trợ theo lộ trình Oracle, do đó phù hợp làm mốc nghiên cứu hoặc kiểm tra tương thích hơn là lựa chọn triển khai mới.

## Tài liệu tham khảo chính thức

- [JDK 26 Release Notes](https://www.oracle.com/java/technologies/javase/26-relnote-issues.html)
- [Significant Changes in JDK 26](https://docs.oracle.com/en/java/javase/26/migrate/significant-changes-jdk-26-release.html)
- [Primitive Types in Patterns, instanceof, and switch](https://docs.oracle.com/en/java/javase/26/language/primitive-types-patterns-instanceof-switch.html)
- [HttpClient API for Java 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.net.http/java/net/http/HttpClient.html)
- [StructuredTaskScope API for Java 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/StructuredTaskScope.html)
- [Vector API package documentation](https://docs.oracle.com/en/java/javase/26/docs/api/jdk.incubator.vector/jdk/incubator/vector/package-summary.html)
- [PEMEncoder API for Java 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/security/PEMEncoder.html)
- [Preparing for final Field Mutation Restrictions](https://docs.oracle.com/en/java/javase/26/migrate/preparing-final-field-mutation-restrictions.html)
- [JDK 27 Release Notes](https://www.oracle.com/java/technologies/javase/27-relnote-issues.html)
- [Consolidated JDK 27 Release Notes](https://www.oracle.com/java/technologies/javase/27all-relnotes.html)
- [Java Release Support Timeline](https://ops.java/releases/?lang=en)

