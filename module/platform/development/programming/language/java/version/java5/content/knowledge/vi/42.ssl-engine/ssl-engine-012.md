# Lựa chọn giao thức, thuật toán theo chính sách bảo mật hiện hành

## 1. Từ khả năng của SSLEngine đến chính sách cho phép

`SSLEngine` cho phép ứng dụng cấu hình giao thức và bộ mã dùng trong bắt tay TLS. Tuy nhiên, “JDK hỗ trợ” không đồng nghĩa “hệ thống cho phép dùng”. Chính sách bảo mật là quyết định về mức bảo vệ cần đạt, đối tác phải tương thích và bằng chứng cần kiểm tra khi kết nối được thiết lập.

Một mô hình dễ áp dụng là tách ba tập:

| Tập cấu hình | Ý nghĩa |
| --- | --- |
| Được hỗ trợ (supported) | Bộ cung cấp JSSE có khả năng triển khai |
| Được bật (enabled) | Những giá trị engine đang được cấu hình để đưa vào thương lượng |
| Được phép theo chính sách | Những giá trị tổ chức chấp nhận cho loại kết nối này |

Kết nối thực tế còn bị ràng buộc bởi đối tác, chứng chỉ, thuật toán chữ ký, nhóm trao đổi khóa và các hạn chế của môi trường chạy. Việc đặt thành công một danh sách cấu hình chưa chứng minh bắt tay sẽ thành công. Xem [API SSLEngine](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/javax/net/ssl/SSLEngine.html).

Bài này tập trung TLS trên TCP với JDK hiện đại. Tên module Java 5 không phải yêu cầu chọn các giao thức hay thuật toán có từ thời Java 5.

## 2. Chính sách hiện hành phải có phiên bản và nguồn

Một chính sách có thể được ghi thành nội dung có thể kiểm tra:

```text
Đối tượng: máy khách gọi API nội bộ mới
Giao thức được phép: TLS 1.3
Bộ mã: giao của danh sách phê duyệt với cấu hình được bật của runtime
Danh tính: kiểm tra chuỗi tin cậy và tên máy chủ
Tương thích TLS 1.2: chỉ theo ngoại lệ có chủ sở hữu và thời hạn
Kiểm chứng: bắt tay thật với đối tác, đọc giao thức/bộ mã đã thương lượng
Bảo trì: đánh giá lại khi cập nhật JDK, provider, chứng chỉ hoặc chính sách
```

Đây là ví dụ thiết kế chính sách cho một môi trường cụ thể, không phải một chuẩn bắt buộc cho mọi hệ thống. Điều quan trọng là có thể giải thích vì sao một giá trị được bật và ai có quyền thay đổi nó.

Nguồn tham chiếu cũng cần được kiểm tra cập nhật. Tại thời điểm biên soạn tháng 10/2026, không nên chỉ sao chép một bảng cấu hình dựa trên RFC 9325 rồi coi nó bất biến: RFC 9852 và RFC 10015, công bố tháng 7/2026, đã cập nhật các khuyến nghị liên quan. [RFC 9325](https://www.rfc-editor.org/rfc/rfc9325.html), [RFC 9852](https://www.rfc-editor.org/rfc/rfc9852.html), [RFC 10015](https://www.rfc-editor.org/rfc/rfc10015.html).

## 3. Chọn phiên bản giao thức trước khi chọn bộ mã

Với một giao thức ứng dụng mới dùng TLS, RFC 9852 yêu cầu hỗ trợ và mặc định dùng TLS 1.3. TLS 1.2 có thể được quy định thêm như lựa chọn không mặc định khi có nhu cầu triển khai; điều này không biến TLS 1.2 thành lựa chọn bắt buộc cho mọi giao thức mới. Cũng không có nghĩa mọi dịch vụ đang hoạt động phải lập tức loại TLS 1.2 mà không đánh giá đối tác và chính sách. [RFC 9852, mục 4–5](https://www.rfc-editor.org/rfc/rfc9852.html#section-4).

Một cách ra quyết định cho ứng dụng:

- Hai đầu mới, kiểm soát được khả năng tương thích: chọn chính sách TLS 1.3.
- Phải giao tiếp với một đối tác chỉ có TLS 1.2 và được phê duyệt: xây dựng hồ sơ tương thích riêng, giới hạn bộ mã và có kế hoạch cập nhật.
- Đối tác không đáp ứng mức tối thiểu: từ chối có thông tin chẩn đoán; không tự mở rộng cấu hình xuống dưới mức cho phép.

Trong API, tên chuẩn để cấu hình là `TLSv1.3` hoặc `TLSv1.2`. Chuỗi `TLS` dùng trong `SSLContext.getInstance("TLS")` là tên thuật toán tạo context; nó không tự biểu diễn chính sách “chỉ TLS 1.3”. Phải cấu hình engine/`SSLParameters` phù hợp và kiểm chứng sau bắt tay.

Không lấy toàn bộ kết quả `getSupportedProtocols()` rồi đưa vào `setEnabledProtocols()`. Cách làm ấy biến danh sách khả năng của thư viện thành chính sách của ứng dụng và có thể đưa vào những lựa chọn mà hệ thống không chủ định chấp nhận.

## 4. Bộ mã không đại diện cho mọi thuật toán của TLS

Bộ mã (cipher suite) xác định một tập thuật toán, nhưng ý nghĩa tên khác nhau theo phiên bản TLS.

| Ví dụ tên | Cách đọc cần biết |
| --- | --- |
| `TLS_AES_128_GCM_SHA256` | Bộ mã TLS 1.3: AES-GCM để bảo vệ bản ghi; SHA-256 liên quan hàm băm/HKDF của bộ mã |
| `TLS_AES_256_GCM_SHA384` | Bộ mã TLS 1.3 với AES-256-GCM và SHA-384 |
| `TLS_CHACHA20_POLY1305_SHA256` | Bộ mã TLS 1.3 dùng ChaCha20-Poly1305 |
| `TLS_ECDHE_RSA_WITH_AES_128_GCM_SHA256` | Ví dụ TLS 1.2: ECDHE cho trao đổi khóa, RSA cho xác thực bằng chữ ký, AES-GCM để bảo vệ dữ liệu |

Đặc biệt, bộ mã TLS 1.3 không chứa tên thuật toán trao đổi khóa hay chữ ký xác thực. Các lựa chọn ấy được thương lượng riêng. Vì vậy, thấy `TLS_AES_128_GCM_SHA256` không đủ để kết luận kết nối dùng chứng chỉ RSA, ECDSA, nhóm đường cong nào hay cơ chế hậu lượng tử nào. [RFC 8446, mục 4.1.2](https://www.rfc-editor.org/rfc/rfc8446.html#section-4.1.2).

Không sửa danh sách bộ mã TLS 1.3 bằng một danh sách chỉ gồm tên dành cho TLS 1.2. Nếu chính sách cho phép cả hai phiên bản, danh sách bộ mã phải có lựa chọn phù hợp với mỗi phiên bản muốn duy trì. Nếu không, một phiên bản có thể đã được bật nhưng không còn bộ mã dùng được.

### Độ dài khóa lớn hơn không giải quyết mọi rủi ro

Đổi AES-128 thành AES-256 không thay cho kiểm tra danh tính máy chủ, bảo vệ khóa riêng hoặc chọn phương thức trao đổi khóa phù hợp. Hiệu năng cũng phụ thuộc phần cứng và provider. Chính sách nên xem xét đồng thời độ an toàn, tuân thủ, khả năng tương thích và hiệu năng đo được, thay vì chọn theo số lớn nhất trong tên.

## 5. Nếu cần TLS 1.2, chọn phương thức trao đổi khóa theo hướng dẫn đã cập nhật

ECDHE là trao đổi khóa Diffie-Hellman tạm thời trên đường cong elliptic. Khi triển khai đúng, nó cung cấp tính bí mật chuyển tiếp (forward secrecy): việc khóa xác thực dài hạn bị lộ về sau không tự động cho phép giải mã các phiên trước chỉ từ lưu lượng đã ghi lại.

RFC 10015 cập nhật hướng dẫn TLS 1.2: không sử dụng trao đổi khóa RSA tĩnh và DH trên trường hữu hạn, kể cả dạng tạm thời được đề cập trong tài liệu; ECDH tĩnh cũng không được khuyến nghị. Phạm vi cập nhật này là TLS/DTLS 1.2, không phải một lệnh cấm mọi nhóm DH của TLS 1.3. [RFC 10015, mục 2–6](https://www.rfc-editor.org/rfc/rfc10015.html#section-2).

Điểm dễ nhầm là `RSA` trong tên chứng chỉ hoặc trong `ECDHE_RSA` không đồng nghĩa với trao đổi khóa RSA tĩnh. Ví dụ `TLS_ECDHE_RSA_WITH_AES_128_GCM_SHA256` dùng ECDHE để trao đổi khóa; RSA phục vụ xác thực bằng chữ ký. Không loại mọi chứng chỉ RSA chỉ vì đọc một khuyến nghị cấm RSA key exchange.

Một hồ sơ tương thích TLS 1.2 có thể xét các bộ mã ECDHE kết hợp cơ chế mã hóa có xác thực AEAD như AES-GCM hoặc ChaCha20-Poly1305, theo chính sách và khả năng hai bên. Danh sách cụ thể còn phải phù hợp loại chứng chỉ của máy chủ, thuật toán chữ ký, provider và ràng buộc runtime. Không coi một ví dụ bộ mã là bảo đảm bắt tay thành công.

## 6. Dùng mặc định của runtime hay danh sách cho phép rõ ràng?

Có hai cách tổ chức cấu hình có giá trị, tùy trách nhiệm của ứng dụng:

| Cách tổ chức | Khi phù hợp | Việc phải kiểm tra |
| --- | --- | --- |
| Giữ bộ mã mặc định của runtime đã cập nhật | Chính sách chấp nhận bộ cấu hình do runtime quản lý, ứng dụng không có yêu cầu thu hẹp riêng | Kiểm tra mặc định thực tế của JDK/provider, theo dõi cập nhật và kiểm thử đối tác |
| Giới hạn bằng danh sách được phê duyệt | Chính sách yêu cầu tập rõ ràng hoặc hồ sơ riêng cho một kết nối | Kiểm tra tập không rỗng, có bộ mã đúng phiên bản, có cơ chế cập nhật danh sách |

Mặc định không phải hợp đồng cố định giữa mọi JDK. Danh sách viết cứng cũng có chi phí bảo trì: nó có thể ngăn sử dụng một lựa chọn an toàn mới nếu không được rà soát. Đưa cấu hình chính sách ra một nơi có chủ sở hữu, phiên bản và quy trình cập nhật sẽ giúp tránh các chuỗi bộ mã rải rác trong nhiều lớp.

Đặc biệt, không lọc bằng quy tắc mơ hồ như “tên chứa AES thì cho phép”. Một bộ mã có thể chứa AES nhưng dùng phương thức trao đổi khóa không được chính sách chấp nhận. Ưu tiên tên chuẩn đầy đủ hoặc hồ sơ được đánh giá rõ ràng.

## 7. Chương trình Java 17+: áp dụng một hồ sơ TLS 1.3

Ví dụ sau cấu hình máy khách cho HTTPS, không mở mạng và không thực hiện bắt tay. Nó kiểm tra các tên cần thiết có trong khả năng runtime, lấy giao giữa bộ mã đang bật và danh sách đã phê duyệt, rồi áp dụng chính sách. Không có mã bỏ qua kiểm tra chứng chỉ.

Lưu thành `TlsPolicyDemo.java`:

```java
import java.util.Arrays;
import java.util.Set;
import javax.net.ssl.SSLContext;
import javax.net.ssl.SSLEngine;
import javax.net.ssl.SSLParameters;

public class TlsPolicyDemo {
    private static final Set<String> APPROVED_SUITES = Set.of(
            "TLS_AES_128_GCM_SHA256",
            "TLS_AES_256_GCM_SHA384",
            "TLS_CHACHA20_POLY1305_SHA256");

    static SSLEngine createHttpsClient(SSLContext context,
                                      String host, int port) {
        SSLEngine engine = context.createSSLEngine(host, port);
        engine.setUseClientMode(true);

        boolean supportsTls13 = Arrays.asList(engine.getSupportedProtocols())
                .contains("TLSv1.3");
        if (!supportsTls13) {
            throw new IllegalStateException("Policy requires TLS 1.3");
        }

        String[] selected = Arrays.stream(engine.getEnabledCipherSuites())
                .filter(APPROVED_SUITES::contains)
                .toArray(String[]::new);
        if (selected.length == 0) {
            throw new IllegalStateException("No enabled approved cipher suite");
        }

        SSLParameters parameters = engine.getSSLParameters();
        parameters.setProtocols(new String[] {"TLSv1.3"});
        parameters.setCipherSuites(selected);
        parameters.setEndpointIdentificationAlgorithm("HTTPS");
        engine.setSSLParameters(parameters);
        return engine;
    }

    public static void main(String[] args) throws Exception {
        SSLContext context = SSLContext.getInstance("TLS");
        context.init(null, null, null);
        SSLEngine engine = createHttpsClient(context, "example.com", 443);

        boolean onlyApproved = engine.getEnabledCipherSuites().length > 0
                && Arrays.stream(engine.getEnabledCipherSuites())
                         .allMatch(APPROVED_SUITES::contains);
        System.out.println("protocols="
                + String.join(",", engine.getEnabledProtocols()));
        System.out.println("onlyApprovedSuites=" + onlyApproved);
        System.out.println("endpointIdentification="
                + engine.getSSLParameters().getEndpointIdentificationAlgorithm());
        System.out.println("clientMode=" + engine.getUseClientMode());
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 TlsPolicyDemo.java
java TlsPolicyDemo
```

Stdout với SunJSSE trên JDK 21 có TLS 1.3 và bộ mã phù hợp đang bật:

```text
protocols=TLSv1.3
onlyApprovedSuites=true
endpointIdentification=HTTPS
clientMode=true
```

Nếu runtime không đáp ứng chính sách, chương trình dừng bằng lỗi nêu rõ thay vì tự chọn giao thức/bộ mã ngoài danh sách. Thứ tự `selected` kế thừa danh sách đang bật của runtime; ví dụ không tuyên bố một thứ tự ưu tiên bộ mã giống nhau trên mọi máy.

Đây mới là kiểm tra cấu hình cục bộ. Chưa có bằng chứng chứng chỉ đối tác hợp lệ hay TLS đã được thương lượng. Một hệ thống thật phải tiếp tục điều khiển `wrap()`/`unwrap()`, tác vụ bắt tay và vận chuyển mạng; chỉ đưa dữ liệu nghiệp vụ vào kết nối đã đạt các điều kiện bảo mật yêu cầu.

## 8. Giới hạn thuật toán của JDK và của kết nối

Chính sách TLS còn chịu tác động của các thuộc tính bảo mật như `jdk.tls.disabledAlgorithms` và `jdk.certpath.disabledAlgorithms`. Nhóm đầu liên quan hạn chế thuật toán TLS; nhóm sau liên quan kiểm tra đường dẫn chứng chỉ. Với SunJSSE, việc gọi setter để bật lại một bộ mã bị thuộc tính bảo mật cấm không khiến nó được phép thương lượng. [JSSE Reference Guide](https://docs.oracle.com/en/java/javase/25/security/java-secure-socket-extension-jsse-reference-guide.html).

Các giá trị này là security properties, có thể đọc qua `Security.getProperty(...)`; không đồng nhất với system properties đọc bằng `System.getProperty(...)`. Không xóa hạn chế toàn JVM chỉ để một kết nối thử nghiệm bắt tay được. Cách xử lý đúng là xác định nguyên nhân không tương thích và cập nhật chứng chỉ, runtime, đối tác hoặc hồ sơ được phê duyệt.

`SSLParameters.setAlgorithmConstraints(...)` cho phép thêm ràng buộc thuật toán ở kết nối, ngoài ràng buộc runtime. Chỉ triển khai khi ứng dụng thực sự cần kiểm soát này và hiểu các đầu vào thuật toán/khóa mà provider đánh giá; một lớp ràng buộc tự viết sai có thể từ chối nhầm hoặc không bao phủ yêu cầu. [API SSLParameters](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/javax/net/ssl/SSLParameters.html#setAlgorithmConstraints(java.security.AlgorithmConstraints)).

### Nhóm trao đổi khóa và chữ ký có cấu hình riêng

Các JDK mới có thêm API cấu hình nhóm trao đổi khóa và lược đồ chữ ký: `SSLParameters.setNamedGroups(...)` xuất hiện từ Java 20; `setSignatureSchemes(...)` từ Java 19. Vì vậy, không đưa chúng vào ví dụ ghi là biên dịch bằng `--release 17`. Mức hỗ trợ còn phụ thuộc provider. [API SSLParameters](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/javax/net/ssl/SSLParameters.html).

Nếu chính sách yêu cầu nhóm cụ thể, giải pháp phải gắn với đúng phiên bản JDK/provider và được kiểm thử thương lượng thật. Bật TLS 1.3 không tự chứng minh đã dùng trao đổi khóa hậu lượng tử; đó là yêu cầu riêng về nhóm/cơ chế, khả năng hai đầu và chuẩn đang áp dụng.

## 9. Thuật toán mạnh vẫn cần đúng danh tính

Một kết nối mã hóa tốt đến nhầm máy chủ vẫn không đáp ứng mục tiêu bảo mật. Với HTTPS, cấu hình nhận diện đầu cuối bằng `setEndpointIdentificationAlgorithm("HTTPS")` và truyền tên máy chủ mục tiêu phù hợp vào engine. Giữ bộ quản lý tin cậy kiểm tra chuỗi chứng chỉ; không tạo bộ quản lý tin cậy chấp nhận mọi chứng chỉ để chữa lỗi cấu hình.

Tên máy chủ truyền vào `createSSLEngine(host, port)` không tự mở socket. Ứng dụng vẫn phải kết nối và vận chuyển byte tới đích phù hợp. SNI, kiểm tra tên máy chủ, chuỗi tin cậy và chọn bộ mã là các trách nhiệm khác nhau; không dùng một cái thay cho cái còn lại. [JSSE Reference Guide](https://docs.oracle.com/en/java/javase/25/security/java-secure-socket-extension-jsse-reference-guide.html).

Trên máy chủ, nếu chính sách yêu cầu xác thực máy khách bằng chứng chỉ, cấu hình `setNeedClientAuth(true)` và nguồn tin cậy phù hợp trước bắt tay. `wantClientAuth` chỉ yêu cầu theo nghĩa tùy chọn; không thay thế điều kiện bắt buộc. Với giao thức khác HTTPS, chọn cơ chế xác minh danh tính thích hợp thay vì sao chép chuỗi `HTTPS` mà không xét quy tắc tên của giao thức đó.

## 10. Kiểm chứng kết quả và duy trì chính sách

Sau khi bắt tay thực sự hoàn tất, có thể đọc kết quả bằng đoạn mã sau trong bộ điều khiển kết nối:

```java
String protocol = engine.getSession().getProtocol();
String cipherSuite = engine.getSession().getCipherSuite();
```

Đây là mã minh họa, chưa bao gồm việc xác định thời điểm hoàn tất bắt tay. Trước thời điểm đó, các thuộc tính phiên chưa phải bằng chứng về một kết nối bảo mật đã thiết lập.

Một lượt kiểm thử có ý nghĩa cho hồ sơ TLS nên bao gồm:

1. Trường hợp được phép: đối tác có phiên bản, bộ mã và chứng chỉ phù hợp; kết nối thành công và kết quả thuộc chính sách.
2. Trường hợp không được phép: đối tác chỉ có phiên bản/bộ mã ngoài chính sách; kết nối thất bại, không có bước thử lại nới lỏng tự động.
3. Sai danh tính: chứng chỉ đáng tin nhưng tên máy chủ không phù hợp; máy khách từ chối.
4. Chuỗi chứng chỉ không được tin cậy hoặc vi phạm ràng buộc: kết nối bị từ chối đúng nguyên nhân.
5. Cập nhật JDK/provider/chứng chỉ: chạy lại ma trận đối tác thực tế để phát hiện thay đổi mặc định hoặc hạn chế thuật toán.

Khi cần chẩn đoán SunJSSE, có thể bật có kiểm soát `-Djavax.net.debug=ssl,handshake` trong môi trường phù hợp. Nhật ký bắt tay có thể chứa metadata kết nối và chứng chỉ; hạn chế nơi lưu, thời gian bật và người truy cập. Không công bố khóa, token, dữ liệu ứng dụng hay toàn bộ nhật ký nhạy cảm để giải thích một lỗi không tương thích.

Ghi nhận phiên bản JDK/provider, mã phiên bản chính sách và kết quả giao thức/bộ mã đã thương lượng. Chỉ cấu hình giao thức tối thiểu một lần trong mã rồi quên cập nhật không đủ cho yêu cầu “hiện hành”.

## 11. Những kết luận cần tránh

| Kết luận sai | Cách đánh giá đúng |
| --- | --- |
| JDK hỗ trợ nên được phép bật | Đối chiếu chính sách và ràng buộc runtime |
| Danh sách enabled là kết quả đã thương lượng | Chỉ đọc phiên sau bắt tay thành công mới biết lựa chọn thực tế |
| Có AES-256 là đủ an toàn | Kiểm tra cả danh tính, trao đổi khóa, chữ ký, nguồn tin cậy và triển khai |
| RSA ở đâu cũng là RSA key exchange | Phân biệt khóa/chữ ký xác thực với phương thức trao đổi khóa |
| Setter không lỗi nên cấu hình chắc chắn chạy | Cần đối tác, chứng chỉ và thuật toán có giao phù hợp khi bắt tay |
| Bật TLS 1.3 đồng nghĩa đã có bảo vệ hậu lượng tử | Kiểm tra riêng yêu cầu nhóm trao đổi khóa và triển khai |
| Không kết nối được thì bật mọi lựa chọn | Giữ mức tối thiểu, chẩn đoán và xử lý đúng bên không tương thích |

Bài tập: một máy khách bật `TLSv1.3` nhưng danh sách bộ mã chỉ có `TLS_ECDHE_RSA_WITH_AES_128_GCM_SHA256`. Hai đầu đều “hỗ trợ TLS 1.3” nhưng hồ sơ vẫn không có bộ mã TLS 1.3 để dùng. Cách sửa là đánh giá lại danh sách bộ mã theo phiên bản và chính sách, không bật thêm mọi giao thức hoặc tắt kiểm tra chứng chỉ.
