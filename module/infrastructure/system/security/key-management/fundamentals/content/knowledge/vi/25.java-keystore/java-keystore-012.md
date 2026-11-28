# TrustStore trong Java KeyStore

TrustStore là kho chứa các chứng thư mà một ứng dụng dùng làm cơ sở xác định bên nào được tin cậy. Trong Java, TrustStore thường được biểu diễn bằng API **KeyStore** và được cung cấp cho **TrustManagerFactory** để tạo các TrustManager xác minh chứng thư trong kết nối TLS. TrustStore vì thế là một phần của cấu hình niềm tin: một chứng thư được thêm vào kho có thể mở rộng những hệ thống, máy chủ hoặc tổ chức mà ứng dụng chấp nhận.

TrustStore liên quan trực tiếp đến quản lý khóa vì quyết định tin cậy một chứng thư cho phép ứng dụng chấp nhận danh tính mật mã được chứng thư đó đại diện. Nếu nhập nhầm CA, giữ CA đã bị xâm phạm hoặc phân phối truststore không an toàn, kẻ tấn công có thể tạo chứng thư mà ứng dụng chấp nhận. Do đó, quản lý TrustStore cần có chủ sở hữu, nguồn chứng thư đã xác minh, quy trình phê duyệt, kiểm soát thay đổi và kế hoạch thu hồi niềm tin.

## 1. TrustStore là gì?

TrustStore là một tập hợp chứng thư tin cậy được ứng dụng sử dụng khi xác minh chứng thư do bên kết nối trình ra. Trong mô hình hạ tầng khóa công khai (PKI), TrustStore thường chứa chứng thư CA gốc hoặc các chứng thư được tổ chức chỉ định làm **trust anchor** (điểm neo tin cậy). Khi kết nối TLS, máy chủ gửi chứng thư danh tính và thường gửi kèm các chứng thư trung gian. Ứng dụng kiểm tra xem có thể xây dựng một đường dẫn chứng thư hợp lệ từ chứng thư máy chủ đến một trust anchor đã được cấu hình hay không.

Một trust anchor là quyết định tin cậy được thiết lập trước thông qua một kênh quản trị đáng tin cậy. Chữ ký hợp lệ của một chứng thư CA trung gian chưa đủ để ứng dụng tin cậy CA đó nếu chuỗi không dẫn tới một trust anchor được chấp nhận. Tương tự, chứng thư tự ký không tự trở nên đáng tin chỉ vì chữ ký của nó có thể được kiểm tra; ứng dụng cần có cơ sở độc lập để quyết định tin cậy chứng thư đó.

Trong Java, TrustStore không phải một loại API riêng. Ứng dụng dùng **KeyStore** để đọc kho chứng thư, sau đó dùng **TrustManagerFactory** để tạo thành phần xác minh. Tên tệp thường gặp là **cacerts**, **truststore.jks**, **truststore.p12** hoặc **truststore.pfx**, nhưng phần mở rộng không quyết định nội dung hay mức độ tin cậy.

### TrustStore và KeyStore

| Tiêu chí | TrustStore | KeyStore dùng làm identity store |
|---|---|---|
| Mục đích | Xác minh chứng thư của bên khác. | Cung cấp danh tính mật mã của chính ứng dụng. |
| Nội dung thường gặp | Chứng thư CA hoặc chứng thư được tin cậy (TrustedCertificateEntry). | Khóa riêng và chuỗi chứng thư (PrivateKeyEntry). |
| Thành phần Java sử dụng | TrustManagerFactory và TrustManager. | KeyManagerFactory và KeyManager. |
| Câu hỏi được trả lời | “Tôi có chấp nhận chứng thư mà đối tác trình ra không?” | “Tôi sẽ dùng khóa và chứng thư nào để chứng minh danh tính của mình?” |

Cả hai vai trò đều có thể được lưu bằng KeyStore API và cùng sử dụng định dạng PKCS12 hoặc JKS. Một tệp KeyStore về mặt kỹ thuật có thể chứa nhiều loại mục, nhưng nên tổ chức truststore và identity store theo ranh giới quyền truy cập và mục đích vận hành. Ứng dụng chỉ cần xác minh chứng thư không nên được cấp quyền đọc khóa riêng của dịch vụ.

## 2. Trust anchor và quá trình xác minh chuỗi chứng thư

Chứng thư X.509 thường được CA ký để xác nhận khóa công khai gắn với một danh tính hoặc tên máy chủ. Trong một PKI phân cấp, chuỗi chứng thư có thể gồm:

1. **Chứng thư đầu cuối (leaf certificate)**: chứng thư máy chủ hoặc máy khách được sử dụng trong kết nối.
2. **Chứng thư CA trung gian**: CA ký chứng thư đầu cuối hoặc ký chứng thư của CA cấp dưới.
3. **Chứng thư CA gốc**: điểm neo tin cậy được phân phối và cấu hình trước trong TrustStore.

Ví dụ một máy khách kết nối **api.example.internal**. Máy chủ gửi chứng thư cho tên máy chủ và chứng thư CA trung gian. TrustManager của máy khách kiểm tra chữ ký của chứng thư đầu cuối, tiếp tục kiểm tra chữ ký và chính sách của chứng thư trung gian, rồi tìm đường dẫn tới CA gốc có trong TrustStore. Chứng thư gốc thường không cần được máy chủ gửi trong quá trình bắt tay vì máy khách đã có nó trong kho tin cậy.

Việc xác minh đường dẫn thường bao gồm nhiều kiểm tra:

- Chữ ký trên các chứng thư và khả năng xây dựng đường dẫn tới trust anchor.
- Thời hạn hiệu lực (Not Before và Not After) của các chứng thư trong đường dẫn.
- Ràng buộc CA, Basic Constraints, Key Usage và Extended Key Usage.
- Chính sách thuật toán và độ dài khóa mà runtime cho phép.
- Các ràng buộc tên và chính sách PKI liên quan.
- Trạng thái thu hồi nếu cơ chế kiểm tra CRL hoặc OCSP được cấu hình và hoạt động.

Xác minh chuỗi chứng thư và xác minh tên máy chủ là hai kiểm tra liên quan nhưng khác nhau. Chuỗi có thể dẫn tới một CA đáng tin cậy mà chứng thư đầu cuối vẫn được cấp cho tên máy chủ khác. Với HTTPS, ứng dụng phải xác minh tên máy chủ mà nó kết nối khớp với Subject Alternative Name (SAN) trong chứng thư. Các thư viện HTTPS cấp cao của Java thường thực hiện kiểm tra tên máy chủ theo cấu hình mặc định; khi tự tạo kết nối bằng SSLSocket, lập trình viên phải bảo đảm endpoint identification được bật.

### Thêm chứng thư vào TrustStore có nghĩa là gì?

Thêm một chứng thư vào TrustStore là thêm một quyết định tin cậy vào cấu hình của ứng dụng. Nếu chứng thư đó là CA gốc, ứng dụng có thể chấp nhận các đường dẫn chứng thư hợp lệ được xây dựng tới CA ấy, trong phạm vi chính sách xác minh. Nếu thêm chứng thư đầu cuối, ứng dụng có thể tin cậy trực tiếp chứng thư đó như một trust anchor theo cách triển khai của provider. Cách này tạo ra phạm vi tin cậy hẹp hơn trong một số trường hợp, nhưng việc thay chứng thư sẽ đòi hỏi cập nhật kho tin cậy và cần quản lý kỹ vòng đời.

Không nên nhập một chứng thư chỉ vì trình duyệt hoặc ứng dụng đang báo lỗi kết nối. Trước khi tin cậy, cần xác minh nguồn cấp, dấu vân tay, chủ thể, mục đích sử dụng và phạm vi hệ thống sẽ nhận chứng thư đó.

## 3. Các loại mục và định dạng trong Java

TrustStore thường chứa các mục **TrustedCertificateEntry**. Mỗi mục được định danh bằng alias và lưu một chứng thư được ứng dụng tin cậy. Alias giúp quản trị viên nhận biết mục đích, chẳng hạn **corp-root-ca-2026** hoặc **partner-signing-ca**; alias không phải bằng chứng xác thực của chứng thư.

| Thành phần | Ý nghĩa |
|---|---|
| Alias | Tên định danh mục chứng thư trong KeyStore. |
| Trusted certificate | Chứng thư được cấu hình làm điểm tin cậy hoặc chứng thư tin cậy trực tiếp. |
| Trust anchor | Cơ sở tin cậy mà quá trình xác minh đường dẫn có thể kết thúc tại đó. |
| Provider | Thành phần triển khai định dạng KeyStore và thuật toán xác minh chứng thư. |

Java hỗ trợ nhiều loại KeyStore. Hai định dạng thường gặp là:

- **PKCS12**: định dạng tiêu chuẩn để đóng gói dữ liệu khóa và chứng thư, thường có phần mở rộng .p12 hoặc .pfx. Đây là lựa chọn phù hợp cho nhiều ứng dụng Java hiện đại.
- **JKS**: định dạng KeyStore riêng của Java, thường gặp trong hệ thống cũ. Các ứng dụng hiện đại có thể tiếp tục đọc JKS nếu provider hỗ trợ, nhưng nên có kế hoạch chuyển đổi khi phù hợp.

Từ JDK 9, PKCS12 là loại KeyStore mặc định trong cấu hình JDK tiêu chuẩn. Dù vậy, khi làm việc với truststore, nên chỉ rõ PKCS12 hoặc JKS trong lệnh và cấu hình thay vì dựa vào mặc định có thể khác giữa môi trường. Tệp cacerts của một JDK cụ thể cũng cần được kiểm tra bằng công cụ đi kèm runtime đó.

TrustStore thường chứa chứng thư công khai, không phải bí mật khóa riêng. Mật khẩu của tệp có thể được dùng để kiểm tra tính toàn vẹn của kho và bảo vệ thao tác lưu. Vì chứng thư công khai có thể được đọc mà không làm lộ bí mật mật mã, mục tiêu quan trọng của việc bảo vệ truststore là ngăn người không có thẩm quyền thay đổi tập chứng thư được tin cậy. Phân quyền tệp, kiểm soát thay đổi và xác minh tính toàn vẹn của bản phân phối vẫn rất cần thiết.

## 4. Tạo và quản lý TrustStore bằng keytool

keytool đi kèm JDK hỗ trợ xem chứng thư, nhập chứng thư, liệt kê mục và xóa alias. Quy trình an toàn bắt đầu bằng việc kiểm tra chứng thư trước khi nhập.

### Bước 1: Xem chứng thư và xác minh dấu vân tay

Giả sử tổ chức nhận được chứng thư CA gốc trong tệp **corp-root-ca.pem**. Trước khi nhập, xem thông tin chứng thư:

~~~bash
keytool -printcert -file corp-root-ca.pem -v
~~~

Kiểm tra chủ thể (Subject), bên cấp (Issuer), thời hạn, Basic Constraints, Key Usage, thuật toán và dấu vân tay SHA-256. Dấu vân tay phải được đối chiếu với giá trị do chủ sở hữu CA cung cấp qua một kênh độc lập, ví dụ cổng quản trị đã xác thực hoặc tài liệu bàn giao có kiểm soát. Không xác minh chứng thư bằng cách chỉ hỏi chính máy chủ đang trình chứng thư đó.

### Bước 2: Nhập chứng thư đã xác minh

Tạo hoặc cập nhật truststore PKCS12:

~~~bash
keytool -importcert \
  -alias corp-root-ca-2026 \
  -file corp-root-ca.pem \
  -keystore app-truststore.p12 \
  -storetype PKCS12
~~~

keytool có thể yêu cầu mật khẩu và xác nhận có tin cậy chứng thư hay không. Chỉ xác nhận sau khi đã xác minh nguồn và dấu vân tay. Alias nên mô tả CA, đối tác hoặc mục đích sử dụng, tránh những tên chung chung như cert1.

### Bước 3: Liệt kê và kiểm tra lại

~~~bash
keytool -list -v \
  -keystore app-truststore.p12 \
  -storetype PKCS12
~~~

Kiểm tra alias, loại mục, chủ thể, bên cấp, thời hạn và dấu vân tay. Sau đó thử dùng truststore bằng chính ứng dụng và JDK sẽ triển khai. Việc nhập thành công chỉ xác nhận công cụ đã lưu mục; nó chưa chứng minh chứng thư được chọn đúng, chuỗi TLS hợp lệ hoặc tên máy chủ được xác minh đúng.

### Xóa một chứng thư khỏi TrustStore

Khi CA không còn được tin cậy hoặc chứng thư bị thay thế, xóa alias tương ứng:

~~~bash
keytool -delete \
  -alias old-partner-ca \
  -keystore app-truststore.p12 \
  -storetype PKCS12
~~~

Sau khi xóa, liệt kê lại kho và kiểm tra các ứng dụng phụ thuộc. Nếu một chứng thư CA được nhiều ứng dụng sử dụng, cần phối hợp thời điểm thay đổi để tránh làm gián đoạn kết nối hợp lệ. Không xóa chứng thư khỏi kho dùng chung khi chưa xác định được phạm vi phụ thuộc.

## 5. Nạp TrustStore trong Java

Java cung cấp API KeyStore để đọc kho và TrustManagerFactory để tạo TrustManager. Ví dụ sau nạp truststore PKCS12 riêng rồi tạo SSLContext dùng cho kết nối TLS:

~~~java
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.KeyStore;
import javax.net.ssl.SSLContext;
import javax.net.ssl.TrustManagerFactory;

public class CustomTrustContext {
    public static SSLContext create(
            Path trustStorePath,
            char[] trustStorePassword) throws Exception {

        KeyStore trustStore = KeyStore.getInstance("PKCS12");
        try (InputStream input = Files.newInputStream(trustStorePath)) {
            trustStore.load(input, trustStorePassword);
        }

        TrustManagerFactory trustManagers =
                TrustManagerFactory.getInstance(
                        TrustManagerFactory.getDefaultAlgorithm());
        trustManagers.init(trustStore);

        SSLContext sslContext = SSLContext.getInstance("TLS");
        sslContext.init(
                null,
                trustManagers.getTrustManagers(),
                null);
        return sslContext;
    }
}
~~~

Đối số thứ hai của SSLContext.init là danh sách TrustManager. Đối số thứ nhất được để null vì ví dụ này chỉ cấu hình xác minh đối tác; nếu ứng dụng cần trình chứng thư máy khách trong mutual TLS, nó phải cấu hình KeyManager từ identity store. Mã thực tế cần lấy mật khẩu từ secret manager hoặc cơ chế cấp phát bí mật phù hợp, quản lý vòng đời mảng char[] và xử lý ngoại lệ theo yêu cầu vận hành.

Khi gọi trustManagers.init(trustStore) với một KeyStore cụ thể, ứng dụng sử dụng tập chứng thư trong kho đó theo provider. Không nên giả định rằng các chứng thư trong truststore tùy chỉnh tự động được hợp nhất với các CA mặc định của JDK. Nếu ứng dụng cần tin cậy cả CA mặc định lẫn CA nội bộ, phải thiết kế và kiểm thử rõ cách kết hợp hai tập chứng thư, hoặc sử dụng truststore được quản lý chứa đầy đủ các trust anchor cần thiết.

### Sử dụng TrustStore mặc định của JSSE

Java Secure Socket Extension (JSSE) có cơ chế tìm truststore mặc định cho các thành phần TLS sử dụng cấu hình mặc định. Các thuộc tính hệ thống thường gặp gồm:

| Thuộc tính | Ý nghĩa |
|---|---|
| javax.net.ssl.trustStore | Đường dẫn đến truststore cần sử dụng. |
| javax.net.ssl.trustStoreType | Loại KeyStore, ví dụ PKCS12 hoặc JKS. |
| javax.net.ssl.trustStoreProvider | Provider dùng để đọc truststore khi cần chỉ định rõ. |
| javax.net.ssl.trustStorePassword | Mật khẩu dùng khi nạp truststore nếu cần. |

Khi javax.net.ssl.trustStore được chỉ định, JSSE sử dụng đường dẫn đó. Nếu không chỉ định, triển khai JSSE tiêu chuẩn thường tìm jssecacerts trước cacerts trong thư mục bảo mật của Java runtime. Vị trí thực tế phụ thuộc runtime và cách đóng gói JDK. Nếu thuộc tính trỏ tới tệp không tồn tại, không nên kỳ vọng JSSE tự động quay về kho mặc định; kết quả có thể là không có trust anchor phù hợp và xác minh TLS thất bại.

Có thể cấu hình đường dẫn và loại kho trong môi trường khởi chạy:

~~~text
-Djavax.net.ssl.trustStore=/opt/app/security/truststore.p12
-Djavax.net.ssl.trustStoreType=PKCS12
~~~

Không đưa mật khẩu thật vào dòng lệnh, tệp script được chia sẻ hoặc cấu hình được commit. Thuộc tính hệ thống và tham số tiến trình có thể bị lộ qua danh sách tiến trình, chẩn đoán JVM hoặc log khởi động. Hãy cấp phát bí mật qua cơ chế được kiểm soát và giới hạn người có thể đọc cấu hình runtime.

## 6. TrustStore trong TLS và xác thực hai chiều

Trong TLS một chiều thông thường, máy khách xác minh chứng thư máy chủ. TrustStore của máy khách cung cấp các trust anchor để TrustManager đánh giá chuỗi chứng thư mà máy chủ gửi. Identity store của máy chủ cung cấp khóa riêng và chứng thư mà máy chủ trình ra.

Trong TLS hai chiều (mutual TLS hoặc mTLS), cả hai phía đều xác minh chứng thư của phía còn lại. Mỗi bên thường cần:

- Identity store chứa khóa riêng và chứng thư của chính bên đó.
- TrustStore chứa CA hoặc chứng thư mà bên đó chấp nhận để xác minh đối tác.

Ví dụ: một dịch vụ nội bộ chỉ chấp nhận máy khách có chứng thư do CA thiết bị của doanh nghiệp cấp. TrustStore phía máy chủ cần chứa trust anchor của CA thiết bị. Máy khách phải có identity store với khóa riêng và chứng thư phù hợp. Việc chỉ cài CA vào truststore phía máy khách không khiến máy chủ tự động tin cậy máy khách; mỗi phía phải cấu hình chính sách xác minh của mình.

### Xác minh tên máy chủ

TrustManager có thể xác minh chuỗi chứng thư hợp lệ nhưng điều đó không thay thế kiểm tra tên máy chủ. Khi dùng SSLSocket trực tiếp, cần bật endpoint identification cho HTTPS trước khi bắt tay:

~~~java
import javax.net.ssl.SSLParameters;
import javax.net.ssl.SSLSocket;

SSLSocket socket = (SSLSocket) sslContext
        .getSocketFactory()
        .createSocket(host, port);

SSLParameters parameters = socket.getSSLParameters();
parameters.setEndpointIdentificationAlgorithm("HTTPS");
socket.setSSLParameters(parameters);
socket.startHandshake();
~~~

Biến host phải là tên máy chủ ứng dụng thực sự định kết nối. Không tắt xác minh tên máy chủ để khắc phục lỗi chứng thư; hãy sửa SAN, DNS hoặc cấu hình endpoint cho đúng. Các HTTP client cấp cao của Java thường quản lý kiểm tra tên máy chủ theo mặc định, nhưng cần xác minh hành vi nếu ứng dụng thay thế SSLContext hoặc tùy biến TLS.

## 7. Quản lý vòng đời TrustStore

TrustStore là dữ liệu cấu hình bảo mật có thể thay đổi quyết định chấp nhận kết nối. Cần quản lý nó như một tài sản quan trọng, có chủ sở hữu và lịch sử thay đổi.

| Giai đoạn | Hoạt động | Kiểm soát |
|---|---|---|
| Tiếp nhận | Nhận chứng thư CA hoặc chứng thư đối tác từ nguồn được phê duyệt. | Xác minh danh tính bên cấp, dấu vân tay qua kênh độc lập, mục đích và phạm vi tin cậy. |
| Phê duyệt | Quyết định ứng dụng/môi trường nào được tin cậy CA đó. | Chủ sở hữu hệ thống và bộ phận an ninh phê duyệt; ghi nhận lý do và thời hạn. |
| Phân phối | Đưa truststore tới máy chủ, container hoặc ứng dụng. | Bảo vệ kênh phân phối, quyền đọc/ghi và tính toàn vẹn của artifact; không để người dùng tùy ý bổ sung CA. |
| Sử dụng | TrustManager dùng các trust anchor để xác minh chuỗi. | Giới hạn phạm vi kho, theo dõi lỗi xác minh và thay đổi cấu hình. |
| Rà soát/xoay vòng | Cập nhật CA, xử lý CA hết hạn hoặc thay đổi hạ tầng PKI. | Có kế hoạch chồng lấp CA cũ/mới, kiểm thử các chuỗi thực tế và thời điểm loại bỏ CA cũ. |
| Thu hồi niềm tin | Xóa trust anchor không còn được chấp nhận. | Phối hợp các ứng dụng phụ thuộc, xác minh bản phân phối mới và kiểm tra kết nối sau thay đổi. |

### Xoay vòng CA

Khi tổ chức thay CA gốc hoặc CA trung gian, có thể tồn tại máy chủ vẫn trình chuỗi cũ trong khi hệ thống khác đã chuyển sang chuỗi mới. Một quy trình chuyển đổi có kiểm soát thường gồm:

1. Nhận chứng thư CA mới từ nguồn chính thức và xác minh dấu vân tay qua kênh độc lập.
2. Đánh giá ứng dụng, môi trường và đối tác sẽ phụ thuộc vào CA mới.
3. Thêm CA mới vào truststore trong giai đoạn chuyển tiếp, giữ CA cũ nếu các chuỗi hợp lệ vẫn cần nó.
4. Phân phối truststore mới và kiểm thử kết nối bằng đúng runtime, endpoint và giao thức sản xuất.
5. Xác nhận các máy chủ/đối tác đã chuyển sang chuỗi mới và không còn phụ thuộc CA cũ.
6. Xóa CA cũ, phân phối lại truststore và xác minh rằng các kết nối hợp lệ vẫn hoạt động.

Không nên giữ CA cũ vô thời hạn sau khi chuyển đổi. Mỗi trust anchor còn lại tiếp tục mở rộng phạm vi chứng thư mà ứng dụng có thể chấp nhận. Ngược lại, xóa CA quá sớm có thể làm gián đoạn các hệ thống chưa hoàn tất chuyển đổi.

### Thu hồi chứng thư và loại bỏ trust anchor

Thu hồi chứng thư và xóa trust anchor là hai thao tác khác nhau. CRL hoặc OCSP cung cấp thông tin về trạng thái thu hồi của chứng thư theo cơ chế của CA. Xóa một CA khỏi truststore thay đổi cơ sở tin cậy của ứng dụng và có thể làm mất khả năng xác minh mọi chuỗi phụ thuộc vào CA đó. TrustManager mặc định không nên được giả định là luôn kiểm tra CRL/OCSP; việc kiểm tra thu hồi cần được cấu hình, thử nghiệm và giám sát riêng theo provider và chính sách triển khai.

Khi CA bị xâm phạm hoặc không còn được phép tin cậy, tổ chức cần đánh giá phạm vi ảnh hưởng, cập nhật truststore, phân phối thay đổi khẩn cấp và theo dõi các ứng dụng đã nhận cấu hình mới. Nếu cần chặn một chứng thư đầu cuối cụ thể, cần chọn cơ chế phù hợp với kiến trúc và provider; chỉ xóa CA gốc có thể ảnh hưởng rộng hơn nhiều so với mục tiêu xử lý.

## 8. Rủi ro thường gặp và biện pháp bảo vệ

**Nhập nhầm chứng thư hoặc CA giả mạo.** Một chứng thư có thể có tên hiển thị giống CA hợp lệ nhưng khóa công khai khác. Luôn đối chiếu dấu vân tay SHA-256 với nguồn độc lập, xác minh mục đích và giới hạn phạm vi ứng dụng được phép tin cậy.

**Tin cậy CA quá rộng.** Thêm CA công cộng hoặc CA doanh nghiệp vào truststore có thể cho phép chấp nhận nhiều chứng thư được CA đó cấp. Chỉ đưa vào những trust anchor cần thiết cho ứng dụng; tránh sao chép toàn bộ truststore của một môi trường sang mọi dịch vụ nếu không có lý do.

**Sửa truststore trái phép.** Kẻ tấn công có thể thêm CA do mình kiểm soát, từ đó tạo chứng thư được ứng dụng chấp nhận. Giới hạn quyền ghi, bảo vệ artifact trong CI/CD, kiểm tra chữ ký hoặc checksum của gói triển khai và ghi nhận thay đổi alias.

**Nhầm chứng thư được tin cậy với chứng thư có khóa riêng.** TrustStore phục vụ xác minh đối tác; nó không cung cấp khóa riêng để ứng dụng chứng minh danh tính. Không đặt khóa riêng của dịch vụ vào truststore chỉ để “đủ chứng thư”.

**Tắt kiểm tra TLS để xử lý lỗi.** Trust-all TrustManager hoặc bỏ qua hostname verification làm mất cơ chế xác thực đối tác và mở đường cho tấn công trung gian. Hãy tìm nguyên nhân thật: CA thiếu, chuỗi trung gian không đầy đủ, chứng thư hết hạn, SAN sai hoặc truststore cấu hình nhầm.

**Thay đổi truststore mặc định toàn cục.** Sửa trực tiếp cacerts có thể ảnh hưởng nhiều ứng dụng dùng chung JDK và làm thay đổi hành vi sau khi nâng cấp runtime. Ưu tiên truststore riêng theo ứng dụng hoặc môi trường khi cần ranh giới tin cậy độc lập; nếu quản lý kho dùng chung, phải có quy trình thay đổi và kiểm thử tác động.

**Không quản lý bản sao và môi trường.** Truststore có thể tồn tại trong image container, máy ảo, bản sao triển khai, cache hoặc artifact cũ. Khi cập nhật hay thu hồi CA, cần biết phiên bản truststore nào đang chạy ở từng môi trường và xác minh rollout đã hoàn tất.

## 9. Xử lý lỗi xác minh chứng thư

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| PKIX path building failed | Không tìm được đường dẫn tới trust anchor, thiếu CA trung gian hoặc truststore không chứa CA cần thiết. | Kiểm tra chuỗi máy chủ gửi, alias trong truststore, CA gốc/trung gian và loại KeyStore đang nạp. |
| unable to find valid certification path | Chứng thư không dẫn tới trust anchor được chấp nhận hoặc chính sách xác minh không cho phép đường dẫn. | Xác minh nguồn CA, dấu vân tay, thời hạn và thuật toán của các chứng thư. |
| No subject alternative names matching... | Tên máy chủ kết nối không khớp SAN của chứng thư. | Kiểm tra hostname, DNS, SAN và cấu hình endpoint; không tắt hostname verification. |
| CertificateExpiredException | Chứng thư trong đường dẫn đã hết hạn hoặc chưa đến thời điểm có hiệu lực. | Kiểm tra thời gian hệ thống, thời hạn chứng thư và kế hoạch gia hạn. |
| Keystore was tampered with, or password was incorrect | Sai mật khẩu, tệp hỏng hoặc kiểm tra tính toàn vẹn thất bại. | Xác nhận nguồn mật khẩu, kiểm tra bản phân phối và đọc đúng loại/provider KeyStore. |
| Ứng dụng dùng CA mặc định được nhưng lỗi sau khi cấu hình truststore riêng | Truststore riêng không chứa các CA mà ứng dụng trước đó tin cậy; kho tùy chỉnh không tự động được hợp nhất với kho mặc định. | Xác định tập trust anchor cần thiết và xây dựng truststore phù hợp; kiểm thử các endpoint phụ thuộc. |

Để xem thông tin truststore bằng keytool:

~~~bash
keytool -list -v \
  -keystore app-truststore.p12 \
  -storetype PKCS12
~~~

Trong môi trường kiểm thử, có thể bật chẩn đoán JSSE bằng thuộc tính:

~~~text
-Djavax.net.debug=ssl,handshake,trustmanager
~~~

Log chẩn đoán có thể rất dài và chứa thông tin về chứng thư, endpoint hoặc cấu hình nội bộ. Chỉ bật khi cần, bảo vệ log và tắt sau khi hoàn tất điều tra. Không ghi mật khẩu truststore hoặc khóa riêng vào log.

## 10. Checklist vận hành TrustStore

- [ ] Mỗi trust anchor có nguồn gốc, chủ sở hữu, mục đích và phạm vi sử dụng rõ ràng.
- [ ] Dấu vân tay chứng thư đã được xác minh qua một kênh độc lập trước khi nhập.
- [ ] TrustStore chỉ chứa các chứng thư cần thiết cho ứng dụng hoặc môi trường đó.
- [ ] Loại KeyStore và provider được chỉ định rõ, tương thích với JDK triển khai.
- [ ] Quyền ghi truststore và quyền thay đổi cấu hình TLS được giới hạn.
- [ ] Có kiểm tra chuỗi chứng thư và hostname; không sử dụng TrustManager bỏ qua xác minh.
- [ ] Chính sách CRL/OCSP được đánh giá riêng nếu hệ thống cần kiểm tra thu hồi.
- [ ] Có quy trình phân phối, sao lưu, xoay vòng CA, loại bỏ trust anchor và khôi phục.
- [ ] Đã kiểm thử kết nối bằng runtime và endpoint thực tế sau mỗi lần thay đổi.
- [ ] Có thể xác định phiên bản truststore đang chạy trên từng môi trường.

TrustStore là nơi lưu quyết định tin cậy mà ứng dụng dùng để xác minh danh tính mật mã của đối tác. Java cung cấp KeyStore API, TrustManagerFactory và JSSE để thực hiện việc này, còn độ an toàn phụ thuộc vào cách tổ chức lựa chọn trust anchor, xác minh chứng thư, phân phối kho và duy trì vòng đời. Một truststore được quản lý tốt giúp TLS xác thực đúng đối tác; một truststore bị mở rộng hoặc thay đổi tùy tiện có thể làm suy yếu toàn bộ ranh giới tin cậy của ứng dụng.
