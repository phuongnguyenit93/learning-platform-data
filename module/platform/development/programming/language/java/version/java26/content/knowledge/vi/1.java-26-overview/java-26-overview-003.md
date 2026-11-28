# Bản đồ tính năng Java 26 còn áp dụng trong JDK hiện hành

> **Mốc cập nhật: 27-11-2026.** JDK 27 đã phát hành chính thức ngày 15-09-2026 và là feature release hiện hành; JDK 25 là bản LTS hiện hành theo roadmap Oracle. JDK 26 là bản non-LTS và đã được JDK 27 thay thế trong chu kỳ phát hành của Oracle. Bài này xem xét các cải tiến bắt đầu từ JDK 26 còn dùng được trong JDK 27, đồng thời cập nhật trạng thái API theo JDK 27. Bản vá Oracle JDK được công bố gần nhất tại thời điểm cập nhật là 27.0.1.1 ngày 17-11-2026; với Temurin, Corretto, Azul hoặc bản phân phối khác, hãy kiểm tra lịch cập nhật của chính nhà cung cấp.

## 1. Cách đọc bản đồ tính năng

Ba trạng thái sau quyết định cách một tính năng nên được đưa vào dự án:

| Trạng thái | Ý nghĩa | Cách sử dụng |
|---|---|---|
| **Final / stable** | Đã trở thành API hoặc hành vi chính thức của JDK. | Có thể dùng trong ứng dụng thông thường sau khi kiểm tra phiên bản runtime và tương thích. |
| **Preview** | Thiết kế đang được thử nghiệm công khai; API hoặc cú pháp có thể thay đổi hay bị loại bỏ. | Chỉ bật có chủ đích, khóa phiên bản JDK khi biên dịch và chạy, không xem là hợp đồng API ổn định. |
| **Incubator** | API đang được phát triển trong module incubator; có thể thay đổi hoặc bị loại bỏ. | Thử nghiệm có kiểm soát, khai báo module rõ ràng và chuẩn bị phương án thay thế. |

| Nhóm | Lần xuất hiện ở JDK 26 | Trạng thái tại JDK 27 |
|---|---|---|
| HTTP/3 trong HttpClient | JEP 517 | **Stable**; API HTTP_3 vẫn có trong Java 27. |
| Primitive types trong patterns, instanceof và switch | JEP 530, preview lần 4 | **Preview lần 5**, JEP 532. |
| Structured Concurrency | JEP 525, preview lần 6 | **Preview lần 7**, JEP 533; API đã tiếp tục thay đổi. |
| Vector API | JEP 529, incubator lần 11 | **Incubator lần 12**, JEP 537. |
| Lazy Constants | JEP 526, preview lần 2 | **Preview lần 3**, JEP 531. |
| PEM Encodings | JEP 524, preview lần 2 | **Preview lần 3**, JEP 538; kiểu API đã đổi. |
| G1 và AOT object cache | JEP 522 và JEP 516 | Các cải tiến từ JDK 26 vẫn có; JDK 27 bổ sung G1 mặc định trên mọi môi trường và compact object headers mặc định. |
| Bảo mật | HPKE, ML-DSA cho chữ ký JAR, cảnh báo sửa final field | Các nền tảng này tiếp tục được dùng; JDK 27 bổ sung hybrid key exchange cho TLS 1.3 và JFR redaction. |

Điểm cần nhớ: một tính năng được giới thiệu trong Java 26 không có nghĩa là trạng thái của nó đã ổn định. Primitive patterns, Structured Concurrency, Vector API, Lazy Constants và PEM vẫn chưa phải API ổn định trong JDK 27.

## 2. HTTP/3 với HttpClient

JEP 517 bổ sung HTTP/3 vào HTTP Client API có sẵn trong module **java.net.http**. Từ JDK 26, enum **HttpClient.Version** có giá trị **HTTP_3**; giá trị này vẫn tồn tại trong JDK 27. Ứng dụng có thể dùng HTTP/1.1, HTTP/2 hoặc HTTP/3 qua cùng mô hình HttpClient.

Ví dụ chọn HTTP/3 ở cấp client:

```java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;

public class Http3Example {
    public static void main(String[] args) throws Exception {
        HttpClient client = HttpClient.newBuilder()
                .version(HttpClient.Version.HTTP_3)
                .build();

        HttpRequest request = HttpRequest.newBuilder()
                .uri(URI.create("https://example.com"))
                .GET()
                .build();

        HttpResponse<String> response = client.send(
                request,
                HttpResponse.BodyHandlers.ofString()
        );

        System.out.println("HTTP version: " + response.version());
        System.out.println("Status: " + response.statusCode());
    }
}
```

**HTTP/3 không được chọn mặc định.** Đoạn code trên đặt phiên bản ưu tiên; phiên bản thực tế cần được xác nhận bằng **response.version()**. Khi kiểm thử, cần bảo đảm:

- URI dùng HTTPS. HTTP/3 không được dùng cho URI có scheme HTTP.
- Máy chủ và mạng cho phép kết nối QUIC qua UDP; chỉ bật enum HTTP_3 không thể làm một máy chủ HTTP/1.1 hoặc HTTP/2 trở thành máy chủ HTTP/3.
- Theo implementation mặc định của JDK, HTTP/3 không được sử dụng khi client đi qua proxy.
- SSLContext hoặc SSLParameters tùy chỉnh có thể không tương thích với HTTP/3; trong một số cấu hình, JDK có thể ném UnsupportedProtocolVersionException.

Không nên suy luận rằng mọi request sẽ luôn đi bằng HTTP/3 chỉ vì client đã đặt preferred version. Hãy kiểm thử cả môi trường có proxy, môi trường có firewall và endpoint thật. Nếu ứng dụng cần tương thích với nhiều server, ghi nhận phiên bản giao thức thực tế và xử lý lỗi kết nối theo chính sách của ứng dụng.

## 3. Primitive types trong pattern matching

Pattern matching cho reference types, record patterns và switch patterns đã có các phần ổn định từ những bản Java trước. Phần mới của JDK 26 là mở rộng pattern matching sang **primitive types**. Tính năng này bắt đầu với JEP 530 ở preview lần 4 trong JDK 26 và tiếp tục là preview lần 5, JEP 532, trong JDK 27.

Ví dụ dùng primitive type pattern và guard trong switch:

```java
static String classify(float value) {
    return switch (value) {
        case 0.0f -> "zero";
        case float number when number > 0.0f && number <= 10.0f ->
                "small-positive";
        case float number -> "other";
    };
}
```

Primitive patterns cũng có thể dùng với instanceof và thành phần primitive của record:

```java
float value = 1000.01f;

if (value instanceof double widened) {
    System.out.println("Safe widening: " + widened);
}

record Measurement(double value) {}

Measurement measurement = new Measurement(34.5f);
if (measurement instanceof Measurement(float measured)) {
    System.out.println("Measured value: " + measured);
}
```

JDK 27 mở rộng switch để nhận tất cả primitive types, gồm boolean, long, float và double, cùng các kiểu boxed tương ứng. Với pattern conversion, điều kiện quan trọng là phép chuyển đổi phải an toàn: không làm mất thông tin và không phát sinh ngoại lệ. Ví dụ float có thể được mở rộng thành double, nhưng không thể coi việc chuyển float thành int là phép chuyển đổi an toàn trong pattern.

Đây vẫn là preview. Cú pháp, quy tắc chuyển đổi và kiểm tra dominance trong switch có thể tiếp tục được điều chỉnh. Không bật preview chỉ để dùng switch hoặc pattern matching đã ổn định từ các phiên bản trước; chỉ bật khi mã thực sự dùng primitive patterns mới.

## 4. Structured Concurrency

Structured Concurrency gom các tác vụ con có quan hệ với nhau vào một phạm vi có vòng đời rõ ràng. Tác vụ cha tạo các tác vụ con, chờ kết quả và xử lý lỗi trong cùng một cấu trúc. Khi một tác vụ con thất bại, chính sách join có thể hủy các tác vụ còn lại; phạm vi được đóng khi các tác vụ con đã kết thúc.

JDK 26 có JEP 525, preview lần 6. Trong JDK 27, tính năng tiếp tục ở preview lần 7 với JEP 533. API đã thay đổi qua các lần preview, vì vậy ví dụ dưới đây dùng hình dạng API của JDK 27:

```java
import java.util.concurrent.ExecutionException;
import java.util.concurrent.StructuredTaskScope;

record Dashboard(String profile, String orders) {}

static Dashboard loadDashboard(String customerId)
        throws InterruptedException, ExecutionException {

    try (var scope = StructuredTaskScope.open()) {
        var profile = scope.fork(
                () -> ProfileService.fetch(customerId)
        );
        var orders = scope.fork(
                () -> OrderService.fetchSummary(customerId)
        );

        scope.join();

        return new Dashboard(profile.get(), orders.get());
    }
}
```

Trong ví dụ, hai lời gọi service chạy đồng thời; luồng sở hữu scope chờ kết quả bằng join rồi tổng hợp kết quả. Với joiner mặc định của JDK 27, join hoàn tất khi tất cả tác vụ thành công và ném ExecutionException nếu có tác vụ thất bại. Scope hủy các tác vụ còn lại khi có lỗi. Việc đóng scope vẫn chờ các luồng con kết thúc, nên tác vụ con cần phản hồi interruption đúng cách.

Virtual threads là tính năng ổn định từ Java 21; **StructuredTaskScope vẫn là preview**. Không nhầm trạng thái của hai tính năng này. Trong JDK 27, StructuredTaskScope có ba tham số kiểu và kiểu ngoại lệ của join; mã viết cho preview ở JDK 26 không nên được chép nguyên trạng sang JDK 27. Hãy đọc API docs đúng phiên bản và biên dịch lại.

## 5. Vector API

Vector API biểu diễn phép toán trên nhiều phần tử cùng lúc theo mô hình SIMD (Single Instruction, Multiple Data). Khi phần cứng và JVM hỗ trợ, các phép toán vector có thể được biên dịch thành lệnh SIMD phù hợp. API nằm trong module **jdk.incubator.vector**.

Vector API là incubator lần 11 trong JDK 26 và incubator lần 12 trong JDK 27. Nó chưa phải API Java SE ổn định. Ví dụ sau nhân hai mảng float, xử lý phần tử theo vector rồi xử lý phần dư bằng vòng lặp scalar:

```java
import jdk.incubator.vector.FloatVector;
import jdk.incubator.vector.VectorSpecies;

final class VectorMultiply {
    private static final VectorSpecies<Float> SPECIES =
            FloatVector.SPECIES_PREFERRED;

    static void multiply(float[] a, float[] b, float[] result) {
        if (a.length != b.length || a.length != result.length) {
            throw new IllegalArgumentException(
                    "All arrays must have the same length"
            );
        }

        int i = 0;
        int bound = SPECIES.loopBound(a.length);

        for (; i < bound; i += SPECIES.length()) {
            var left = FloatVector.fromArray(SPECIES, a, i);
            var right = FloatVector.fromArray(SPECIES, b, i);
            left.mul(right).intoArray(result, i);
        }

        for (; i < a.length; i++) {
            result[i] = a[i] * b[i];
        }
    }
}
```

Khi dùng classpath, thêm module trong cả bước compile và chạy:

```text
javac --add-modules jdk.incubator.vector VectorMultiply.java
java --add-modules jdk.incubator.vector Main
```

Nếu ứng dụng dùng module system, khai báo **requires jdk.incubator.vector** trong module-info.java. Vector API không cần cờ **--enable-preview**; cờ cần thiết là **--add-modules jdk.incubator.vector**.

Dùng **SPECIES_PREFERRED** để JVM chọn kích thước vector phù hợp với nền tảng. Luôn có đường xử lý scalar cho phần tử còn dư. Vector API không bảo đảm mọi phép toán đều nhanh hơn: hiệu quả phụ thuộc CPU, kích thước dữ liệu, cách truy cập bộ nhớ và khả năng vector hóa của JIT. Hãy benchmark trên phần cứng triển khai. Vì đây là incubator, không nên để kiểu dữ liệu của module này trở thành hợp đồng công khai khó thay đổi của thư viện hoặc dịch vụ.

## 6. Bảo mật và mã hóa

### 6.1. HPKE, ML-DSA và TLS hậu lượng tử

JDK 26 bổ sung HPKE (Hybrid Public Key Encryption) và hỗ trợ ML-DSA trong chữ ký JAR. HPKE cung cấp cơ chế mã hóa thông điệp dựa trên khóa công khai ở tầng ứng dụng; nó không thay thế TLS. ML-DSA là thuật toán chữ ký hậu lượng tử, có thể dùng trong quy trình ký và xác minh JAR khi toàn bộ công cụ, runtime và hệ thống phân phối hỗ trợ.

JDK 27 bổ sung hybrid key exchange cho TLS 1.3 qua JEP 527. Các nhóm được hỗ trợ gồm **X25519MLKEM768**, **SecP256r1MLKEM768** và **SecP384r1MLKEM1024**. X25519MLKEM768 được bật mặc định và ưu tiên cao nhất. Với ứng dụng sử dụng JSSE qua javax.net.ssl, cơ chế này có thể được thương lượng tự động khi cả hai đầu kết nối hỗ trợ nhóm tương ứng.

Để kiểm tra nhóm đã được thương lượng trong môi trường thử nghiệm, có thể bật JSSE handshake debug:

```text
-Djavax.net.debug=ssl:handshake
```

Sau đó kiểm tra phần key_share trong log ServerHello. Không kết luận kết nối đã dùng hybrid key exchange chỉ từ việc ứng dụng chạy trên JDK 27; cần xác nhận kết quả thương lượng thực tế.

### 6.2. Tương thích định dạng khóa ML-KEM và ML-DSA

JDK 27 cập nhật cách mã hóa private key ML-KEM và ML-DSA trong PKCS #8. Giá trị mặc định chuyển sang định dạng **seed**. Các JDK cũ có thể không đọc được private key được tạo theo định dạng mặc định mới, dù JDK 27 vẫn đọc được các định dạng cũ.

Khi phải trao đổi khóa với runtime cũ, kiểm tra các security properties:

- **jdk.mlkem.pkcs8.encoding**
- **jdk.mldsa.pkcs8.encoding**

Các giá trị được hỗ trợ là **seed**, **expandedKey** và **both**. Có thể chọn expandedKey để tương thích với JDK cũ, sau đó kiểm thử việc import, export và ký/xác minh trên đúng phiên bản triển khai. Không thay đổi định dạng khóa trên hệ thống thật nếu chưa kiểm tra khả năng đọc của toàn bộ bên nhận.

### 6.3. PEM Encoder và Decoder

API PEM trong JDK 26 là preview lần 2 theo JEP 524. Trong JDK 27, API tiếp tục là preview lần 3 theo JEP 538. **PEMEncoder**, **PEMDecoder** và **PEM** hỗ trợ chuyển đổi các đối tượng như certificate, CRL, public key và private key sang hoặc từ định dạng PEM.

Một thay đổi cần lưu ý khi nâng cấp: API JDK 27 dùng **BinaryEncodable**; mã dựa trên kiểu **DEREncodable** của preview JDK 26 không nên được giả định là còn tương thích. Vì API vẫn preview, chỉ dùng sau khi khóa đúng JDK và chấp nhận chi phí cập nhật khi API đổi. Với phần tích hợp bảo mật cốt lõi, ưu tiên API ổn định đã được hỗ trợ trong runtime đang triển khai.

### 6.4. Chính sách thuật toán và final fields

JDK 26 bổ sung security property **jdk.crypto.disabledAlgorithms** để giới hạn thuật toán tại tầng JCE. Đây là điểm cấu hình bảo mật cần phối hợp với chính sách mật mã của tổ chức. Khi thêm hoặc siết danh sách thuật toán, phải kiểm thử các luồng TLS, ký số, mã hóa dữ liệu và tích hợp với provider bên ngoài.

JEP 500 cảnh báo việc dùng deep reflection để sửa trường **final**. Cảnh báo bắt đầu từ JDK 26 và vẫn áp dụng trong JDK 27; mục tiêu là chuẩn bị cho việc siết chặt hành vi này ở các bản JDK tương lai. Mở package bằng **--add-opens** không tự loại bỏ cảnh báo. JDK cung cấp **--enable-final-field-mutation** và **--illegal-final-field-mutation** để hỗ trợ chuyển đổi có kiểm soát, nhưng không nên bật quyền sửa final field trên diện rộng. Hãy xác định thư viện gây cảnh báo, nâng cấp hoặc thay thế thư viện đó và loại bỏ cơ chế sửa final field nếu có thể.

JDK 27 còn bổ sung JFR in-process data redaction theo JEP 536. Các giá trị nhạy cảm trong command-line arguments, environment variables và system properties ban đầu được che trong bản ghi JFR theo mặc định. Khi vận hành hệ thống, kiểm tra cấu hình redaction và bảo đảm dữ liệu nhạy cảm không bị đưa vào log hoặc bản ghi chẩn đoán theo cách ngoài dự kiến.

## 7. Tối ưu JVM và garbage collector

### 7.1. G1 giảm đồng bộ và trở thành collector mặc định rộng hơn

JEP 522 trong JDK 26 giảm đồng bộ giữa application threads và các luồng tối ưu card table của G1. Thay đổi này giảm chi phí write barrier trong một số workload có nhiều cập nhật tham chiếu, từ đó có thể cải thiện throughput và đôi khi cả latency. Mức cải thiện phụ thuộc workload; không dùng một con số benchmark chung để dự đoán hiệu năng của mọi ứng dụng.

JDK 27 tiếp tục với JEP 523: G1 trở thành garbage collector mặc định trong mọi môi trường, thay vì chỉ là mặc định ở môi trường server. Điều này giúp hành vi mặc định nhất quán hơn. Tuy vậy, ứng dụng vẫn cần đo pause time, throughput, heap occupancy và CPU trên dữ liệu tải thực tế trước khi thay đổi cấu hình GC.

### 7.2. Compact object headers

JEP 534 đưa compact object headers thành bố cục mặc định của HotSpot trong JDK 27. Trên kiến trúc 64-bit, object header được rút từ 96 bit xuống 64 bit. Lợi ích kỳ vọng là giảm footprint heap, tăng mật độ triển khai và cải thiện locality khi ứng dụng tạo nhiều object.

Đây là thay đổi ở runtime, không yêu cầu sửa code Java thông thường. Khi nâng cấp, đo lại heap usage và hành vi GC. Đặc biệt kiểm tra các agent, native integration hoặc công cụ chẩn đoán nếu chúng dựa vào chi tiết nội bộ của HotSpot; không nên phụ thuộc vào bố cục object header không thuộc API được hỗ trợ.

### 7.3. Ahead-of-Time object caching với mọi GC

JEP 516 trong JDK 26 mở rộng AOT object cache để hoạt động với mọi garbage collector, bao gồm ZGC. Cache có thể giúp JVM giảm thời gian startup và warmup bằng cách tái sử dụng trạng thái đối tượng đã được chuẩn bị trước. Cải tiến này vẫn có giá trị trong JDK 27.

AOT cache không phải cam kết ứng dụng sẽ khởi động nhanh hơn trong mọi tình huống. Hiệu quả phụ thuộc vào workload dùng để huấn luyện, filesystem cache, GC, heap và tài nguyên CPU. Khi triển khai, so sánh cold start và warm start, kiểm tra cache được tạo từ đúng phiên bản ứng dụng/JDK và đưa việc tái tạo cache vào quy trình phát hành.

### 7.4. Virtual threads và class initialization

JDK 26 cải thiện runtime để virtual thread có thể unmount khỏi carrier thread khi phải chờ một class khác hoàn tất khởi tạo. Trước thay đổi này, việc chờ class initialization trong một số tình huống có thể giữ carrier thread bận và làm giảm số carrier sẵn sàng chạy tác vụ khác. Cải tiến giúp giảm nguy cơ nghẽn scheduler ở ứng dụng dùng nhiều virtual threads.

Đây là cải tiến runtime; không cần chuyển toàn bộ ứng dụng sang một mô hình thread mới để nhận lợi ích. Tuy nhiên, nó không làm mọi thao tác blocking đều trở nên miễn phí. Vẫn cần theo dõi thread dump, JFR và tải thực tế để xác định điểm nghẽn.

## 8. Chọn cờ biên dịch và runtime đúng trạng thái

Với preview features của JDK 27, dùng đúng JDK 27 ở cả bước compile và chạy:

```text
javac --release 27 --enable-preview Example.java
java --enable-preview Example
```

Preview được gắn với major release. Không biên dịch bằng preview của JDK 26 rồi kỳ vọng chạy như preview của JDK 27. Khi đổi JDK, hãy đọc lại preview list, cập nhật code và biên dịch lại.

Với Vector API, khai báo module incubator ở cả compile và runtime:

```text
javac --add-modules jdk.incubator.vector Example.java
java --add-modules jdk.incubator.vector Main
```

Không dùng **--enable-preview** thay cho **--add-modules**. Hai cờ giải quyết hai trạng thái khác nhau. Nếu dự án dùng cả preview API và incubator API, cấu hình riêng hai yêu cầu trong build tool và kiểm tra command line thực tế mà build tool gọi.

## 9. Quy trình đánh giá khi nâng cấp

1. **Xác nhận JDK thực tế.** Kiểm tra java -version và javac -version, đồng thời kiểm tra toolchain của IDE, build tool, CI, container image và môi trường production. Tránh trường hợp compile bằng một JDK nhưng chạy bằng JDK khác.
2. **Chia API theo trạng thái.** Ghi rõ phần nào stable, preview và incubator. Preview/incubator phải có người sở hữu, phiên bản JDK được khóa và kế hoạch xử lý khi API thay đổi.
3. **Kiểm tra HTTP và TLS.** Thử HTTP/3 trên endpoint HTTPS thật, có và không có proxy; kiểm tra response.version(). Với TLS 1.3, xác minh nhóm hybrid đã được thương lượng nếu đó là yêu cầu bảo mật.
4. **Rà soát thư viện và reflection.** Thu thập cảnh báo sửa final field, nâng cấp framework và thư viện liên quan. Kiểm tra các agent hoặc native integration phụ thuộc chi tiết nội bộ của HotSpot.
5. **Kiểm tra định dạng khóa.** Nếu dùng ML-KEM hoặc ML-DSA, xác minh PKCS #8 encoding giữa các JDK và các hệ thống nhận khóa.
6. **Đo hiệu năng trước và sau.** Dùng workload đại diện để so sánh startup, warmup, throughput, latency, heap, GC pause và CPU. Không bật thêm các cờ GC chỉ vì một benchmark tổng quát.
7. **Chọn nhánh JDK theo thời hạn hỗ trợ.** Theo roadmap Oracle cập nhật 20-10-2026, Java 25 là LTS; Java 26 và Java 27 là các bản non-LTS. Nếu cần vòng đời hỗ trợ dài, cân nhắc JDK 25 LTS. Nếu cần tính năng mới của 26/27, dùng bản cập nhật còn được nhà cung cấp hỗ trợ và lên kế hoạch nâng cấp tiếp theo. Lịch hỗ trợ của các vendor có thể khác nhau.

**Không đưa API đã bị loại bỏ vào lộ trình học mới.** Applet API đã bị loại khỏi JDK 26; không xây dựng ứng dụng mới dựa trên Applet hoặc Java Plug-in. Nếu dự án cũ còn phụ thuộc, cần lập kế hoạch thay thế trước khi nâng cấp runtime.

## 10. Tự kiểm tra sau bài học

- Vì sao HTTP_3 có thể được chọn làm preferred version nhưng response vẫn cần được kiểm tra bằng response.version()?
- Primitive patterns trong JDK 27 đang ở trạng thái nào? Cờ nào cần dùng khi compile và chạy?
- Virtual threads đã stable có đồng nghĩa StructuredTaskScope đã stable không?
- Vì sao Vector API cần add-modules nhưng không cần enable-preview?
- Khi nâng cấp từ JDK 26 lên 27, vì sao không nên giữ nguyên mã preview của Structured Concurrency hoặc PEM?
- JDK 27 thay đổi gì về hybrid key exchange TLS 1.3 và định dạng private key ML-KEM/ML-DSA?
- Những thay đổi nào của JDK 26/27 có thể ảnh hưởng đến throughput, heap footprint, startup và warmup?
- Vì sao cần kiểm tra vendor support lifecycle trước khi chọn JDK 26 hoặc 27 cho production?

## Tài liệu chính thức

- [JDK 27 Release Notes](https://www.oracle.com/java/technologies/javase/27-relnote-issues.html)
- [Consolidated JDK 27 Release Notes và các bản cập nhật](https://www.oracle.com/java/technologies/javase/27all-relnotes.html)
- [Oracle Java SE Support Roadmap](https://www.oracle.com/java/technologies/java-se-support-roadmap.html)
- [JDK 26 Release Notes](https://www.oracle.com/java/technologies/javase/26-relnote-issues.html)
- [HttpClient API trong Java 27](https://docs.oracle.com/en/java/javase/27/docs/api/java.net.http/java/net/http/HttpClient.html)
- [Primitive Types in Patterns, instanceof, and switch](https://docs.oracle.com/en/java/javase/27/language/primitive-types-patterns-instanceof-switch.html)
- [StructuredTaskScope API trong Java 27](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/StructuredTaskScope.html)
- [Preview API List của Java 27](https://docs.oracle.com/en/java/javase/27/docs/api/preview-list.html)
- [Vector API trong Java 27](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.incubator.vector/jdk/incubator/vector/package-summary.html)
- [LazyConstant API trong Java 27](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/LazyConstant.html)
- [PEMEncoder API trong Java 27](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/security/PEMEncoder.html)
- [Significant Changes in JDK 27](https://docs.oracle.com/en/java/javase/27/migrate/significant-changes-jdk-27-release.html)
- [Performance Improvements in JDK 26 — Inside Java](https://inside.java/2026/06/09/jdk-26-performance-improvements/)

