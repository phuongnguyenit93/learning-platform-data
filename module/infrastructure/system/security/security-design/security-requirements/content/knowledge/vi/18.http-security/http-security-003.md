# Certificate validation

## 1. HTTPS cần xác minh đúng đối tác

Một kết nối có mã hóa chưa đủ để chứng minh client đang trao đổi với đúng dịch vụ. Nếu client chấp nhận mọi chứng thư mà phía bên kia gửi tới, kẻ trung gian có thể cung cấp chứng thư của mình và nhận dữ liệu qua một kênh vẫn có mã hóa.

Certificate validation là quá trình đánh giá chứng thư và các điều kiện tin cậy để quyết định có chấp nhận danh tính của bên kia trong kết nối hay không. Đối với HTTP client sử dụng HTTPS, cần phân biệt hai câu hỏi: chứng thư có đáp ứng chính sách tin cậy không, và danh tính được chứng thư trình bày có khớp với dịch vụ mà client định gọi không?

Trong module yêu cầu bảo mật, mục tiêu là chuyển câu “dùng HTTPS” thành nghĩa vụ có thể kiểm chứng: client nào xác minh, dùng nguồn tin cậy nào, tên nào được dùng để đối chiếu, xử lý lỗi ra sao và bằng chứng nào chứng minh các trường hợp sai bị từ chối.

Sau bài này, người học có thể:

- Phân biệt xác minh chứng thư, xác minh hostname và thiết lập kênh TLS.
- Xác định reference identity, trust anchor và các ranh giới kết nối trong kiến trúc HTTP.
- Đặc tả hành vi với chứng thư sai tên, hết hạn, không được tin cậy hoặc có trạng thái thu hồi không đáp ứng chính sách.
- Tránh các cách khắc phục sự cố bằng cách vô hiệu hóa kiểm tra.
- Xây dựng tiêu chí nghiệm thu, kế hoạch thay chứng thư và quy trình phục hồi an toàn.

## 2. Mô hình đe dọa và tài sản cần bảo vệ

Giả sử dịch vụ học tập gọi API thông báo để gửi thông tin đăng ký khóa học. Request chứa credential của dịch vụ và dữ liệu người học. Dịch vụ gọi qua HTTPS nhưng cấu hình client chấp nhận mọi chứng thư vì môi trường thử nghiệm từng dùng CA riêng.

Khi cấu hình đó đi vào môi trường vận hành, người kiểm soát một điểm trên đường mạng hoặc một đích bị chuyển hướng có thể trình bày chứng thư không hợp lệ mà client vẫn tiếp tục. Tài sản bị đe dọa gồm credential, dữ liệu cá nhân, tính toàn vẹn của phản hồi và các hành động client thực hiện dựa trên phản hồi đó.

Các tình huống cần đưa vào mô hình gồm:

- Chứng thư có chuỗi tin cậy hợp lệ nhưng cấp cho một tên dịch vụ khác.
- Chứng thư đúng tên nhưng không dẫn đến trust anchor được client chấp thuận.
- Chứng thư hoặc điều kiện chứng thực không còn hợp lệ theo thời gian và chính sách.
- Proxy hoặc service mesh tạo thêm một chặng TLS mà không có chủ sở hữu kiểm tra rõ ràng.
- Client thay đổi đích sau redirect hoặc failover nhưng dùng lại giả định tin cậy của đích trước.
- Một bản sửa vận hành bật chế độ bỏ kiểm tra rồi không được gỡ bỏ.

Xác minh chứng thư bảo vệ danh tính của đầu nối TLS trong mô hình đã chọn. Nó không chứng minh ứng dụng phía bên kia không có lỗ hổng, nội dung trả về đúng nghiệp vụ hoặc người gọi có quyền thực hiện mọi chức năng.

## 3. Chuỗi tin cậy và danh tính endpoint là hai lớp khác nhau

### 3.1. Chuỗi chứng thư

Một mô hình đơn giản gồm chứng thư dịch vụ, một hoặc nhiều chứng thư CA trung gian và trust anchor đã được client cấu hình tin cậy. Việc server gửi kèm một chứng thư tự ký không khiến nó tự trở thành trust anchor.

Theo mô hình PKIX, việc đánh giá đường chứng thực không chỉ là đọc tên issuer. Nó bao gồm chữ ký, thời hạn, ràng buộc và mục đích sử dụng phù hợp; trust anchor là đầu vào của chính sách tin cậy. [RFC 5280 về chứng thư và kiểm tra đường chứng thực](https://www.rfc-editor.org/rfc/rfc5280.html).

Không nên tự thay validator bằng vài phép so sánh `issuer == subject` hoặc một kiểm tra `notAfter`. Đặc tả yêu cầu kết quả đúng theo chính sách; cơ chế thực hiện nên là thành phần xác minh chuẩn của nền tảng được cấu hình và kiểm thử phù hợp.

### 3.2. Danh tính dịch vụ mà client dự định gọi

Client phải có một reference identity: danh tính dịch vụ mà ứng dụng định kết nối. Với HTTPS thông thường, điểm bắt đầu là host của URL đích đã được ứng dụng chấp thuận, không phải tên mà chứng thư tự khai rồi yêu cầu client tin theo.

RFC 9525 quy định đối chiếu DNS qua SAN `dNSName`, không dùng Common Name làm danh tính thay thế; IP dùng SAN `iPAddress`. Wildcard chỉ là toàn bộ nhãn trái nhất và khớp một nhãn. Ví dụ `*.learning.example` khớp `api.learning.example`, không khớp `learning.example` hay `a.api.learning.example`. [RFC 9525, quy tắc xác minh danh tính dịch vụ](https://www.rfc-editor.org/rfc/rfc9525.html#section-6).

Một hệ thống có yêu cầu chặt hơn có thể hạn chế wildcard hoặc yêu cầu tập tên rất cụ thể. Đây là lựa chọn chính sách của hệ thống, cần được nêu rõ và kiểm thử, không suy ra từ việc chứng thư đã được CA cấp.

### 3.3. Kết hợp hai quyết định

| Chuỗi tin cậy | Danh tính endpoint | Quyết định theo chính sách HTTPS minh họa |
| --- | --- | --- |
| Đạt | Khớp | Tiếp tục các kiểm tra còn lại và handshake |
| Đạt | Không khớp | Từ chối |
| Không đạt | Khớp | Từ chối |
| Không xác minh được | Chưa xác định | Không coi là kết nối đã được xác thực |

Không được cho phép một điều kiện bù trừ điều kiện kia. “Chứng thư do CA nổi tiếng cấp” không sửa được lỗi sai endpoint. “Tên trông đúng” không sửa được lỗi không có nguồn tin cậy phù hợp.

## 4. Xác định danh tính tham chiếu đúng từ đầu

### 4.1. URL, DNS, SNI và HTTP Host có vai trò khác nhau

Ứng dụng có thể định gọi `https://api.learning.example`. DNS giúp tìm địa chỉ để kết nối; SNI hỗ trợ server chọn cấu hình hoặc chứng thư cho tên dịch vụ; HTTP Host hoặc authority tham gia định tuyến ở lớp HTTP. Không thành phần nào trong số này tự thay thế quyết định xác minh danh tính của chứng thư.

SNI truyền tên dịch vụ trong bước thiết lập TLS để server có thể chọn dịch vụ phù hợp. Nó không phải kết quả xác minh rằng server đáng tin cậy. [RFC 6066, Server Name Indication](https://www.rfc-editor.org/rfc/rfc6066.html#section-3).

Không đổi reference identity thành một tên tùy ý lấy từ chứng thư chỉ để làm phép đối chiếu thành công. Cũng không sửa HTTP Host rồi coi rằng hostname verification đã được thay đổi đúng; lớp HTTP và lớp xác thực TLS cần được thiết kế nhất quán.

### 4.2. Gọi bằng địa chỉ IP

Nếu chức năng được cấu hình gọi một IP thay vì DNS name, yêu cầu cấp và chấp nhận chứng thư phải phù hợp với danh tính IP đó. Không nên sửa bằng cách tắt hostname verification chỉ vì chứng thư hiện có được cấp cho một DNS name.

Một lựa chọn khác là cấu hình ứng dụng dùng tên dịch vụ ổn định, đồng thời để hạ tầng giải quyết việc tên đó đi tới địa chỉ nào. Quyết định này cần phù hợp với routing, SNI, failover và kiểm soát đích được phép của hệ thống.

### 4.3. Redirect và failover

Một phản hồi redirect có thể đưa client tới một authority khác. Chứng thư hợp lệ của đích ban đầu không chứng minh đích mới được phép. Mỗi kết nối mới phải đáp ứng chính sách xác minh của nó; việc đích đó có được phép gọi hay nhận credential là một quyết định bổ sung.

Yêu cầu cho client tích hợp có thể chọn không tự theo redirect, hoặc chỉ theo trong một phạm vi đích đã định nghĩa. Không tự chuyển từ HTTPS sang HTTP để tiếp tục nghiệp vụ khi có lỗi xác minh.

Failover cũng cần được thiết kế trước: endpoint dự phòng có danh tính, trust policy và quyền nhận dữ liệu nào? Không lấy một địa chỉ dự phòng ngoài danh mục chỉ vì endpoint chính đang gặp lỗi chứng thư.

## 5. Chính sách tin cậy phải có nguồn và phạm vi

### 5.1. Public CA và private CA

Một HTTP client gọi dịch vụ Internet có thể dùng nguồn trust anchor được nền tảng quản lý theo chính sách của tổ chức. Client gọi dịch vụ nội bộ có thể cần một tập CA riêng. Cả hai đều cần nguồn cấp phát đáng tin cậy và quy trình thay đổi.

Không tải trust anchor từ chính kết nối chưa được xác minh rồi tự thêm vào để kết nối thành công. Quy trình thiết lập niềm tin ban đầu phải có kênh quản trị hoặc cơ chế xác thực phù hợp.

Private CA không có nghĩa không cần kiểm tra tên, thời hạn hoặc mục đích. “Nội bộ” mô tả môi trường; nó không tự chứng minh bất kỳ chứng thư nào trong mạng đều có quyền đại diện mọi dịch vụ.

### 5.2. Truststore và keystore không cùng mục đích

Trong ngữ cảnh cấu hình Java, trust material dùng để quyết định tin đối tác; key material dùng khi một bên phải trình bày danh tính và chứng minh quyền sử dụng khóa riêng tương ứng. Một định dạng tệp có thể chứa nhiều loại entry, nhưng vai trò của dữ liệu trong cấu hình vẫn cần phân biệt.

Yêu cầu nên chỉ rõ thành phần nào nạp trust material, ai được thay đổi, áp dụng cho client nào và cách triển khai tới các instance. Không thay truststore toàn tiến trình để sửa một tích hợp mà không đánh giá các kết nối khác bị ảnh hưởng.

### 5.3. Giới hạn phạm vi tin cậy

Thêm một CA có thể mở rộng tập chứng thư mà client chấp nhận. Vì vậy, thay đổi truststore là thay đổi chính sách bảo mật, không chỉ là thao tác sao chép tệp.

Nếu một tích hợp chỉ cần tin một PKI nội bộ cụ thể, có thể cấp cấu hình client riêng thay vì đưa mọi CA phát triển vào nguồn tin cậy dùng chung. Phạm vi lựa chọn tùy kiến trúc, nhưng phải có owner và bằng chứng rằng nó không mở rộng ngoài chủ đích.

### 5.4. Môi trường phát triển và thử nghiệm

Môi trường thử nghiệm có thể dùng CA thử nghiệm và chứng thư được cấp đúng tên trong môi trường đó. Cách này giữ cơ chế xác minh hoạt động, giúp phát hiện lỗi cấu hình trước khi triển khai.

Không nên dùng “trust all trong dev” làm con đường cấu hình duy nhất. Nếu cơ chế production khác hoàn toàn môi trường thử nghiệm, bằng chứng từ test có thể không phản ánh hành vi thực của client khi triển khai.

## 6. Thời gian, thu hồi và khả năng xác minh

### 6.1. Thời gian là đầu vào bảo mật

Chứng thư có khoảng thời gian hiệu lực; client cần nguồn thời gian đủ tin cậy cho chính sách của mình. Đồng hồ lệch có thể làm chứng thư hợp lệ bị từ chối hoặc làm một trạng thái thời gian không đúng được chấp nhận.

Yêu cầu vận hành cần xác định cách đồng bộ, phát hiện sai lệch và xử lý lỗi thời gian. Không sửa sự cố đồng hồ bằng cách vô hiệu hóa kiểm tra hiệu lực chứng thư.

Các ngưỡng cảnh báo sắp hết hạn là lựa chọn vận hành. Nên chọn chúng dựa trên thời gian cấp lại, triển khai và rollback, không dựa trên một con số mặc định chưa có owner.

### 6.2. Thu hồi không được suy ra từ một handshake thành công

OCSP là cơ chế hỏi trạng thái chứng thư, có các kết quả như `good`, `revoked` và `unknown`; nó có quy tắc riêng về nguồn trả lời và thời gian của thông tin trạng thái. `unknown` không có nghĩa chứng thư đã được xác nhận không bị thu hồi. [RFC 6960 về OCSP](https://www.rfc-editor.org/rfc/rfc6960.html).

Hệ thống cần chọn chính sách thu hồi phù hợp với client và PKI thực tế: cơ chế nào được sử dụng, độ mới tối đa, timeout, cache và hành vi khi không có thông tin đáp ứng yêu cầu. Không viết “có OCSP” mà không biết client có yêu cầu, kiểm tra và xử lý kết quả theo chính sách hay không.

### 6.3. Hard fail và soft fail phải được quyết định có chủ đích

Nếu chính sách yêu cầu không tiếp tục khi không xác minh được trạng thái thu hồi, cần tính tới tính sẵn sàng của nguồn trạng thái và hành vi khi mạng gián đoạn. Nếu chấp nhận một số trường hợp không có thông tin mới, phải nêu rõ điều kiện và phần rủi ro còn lại.

Không đồng nhất soft fail vì không liên lạc được nguồn trạng thái với việc chấp nhận một kết quả đã xác minh là bị thu hồi. Đây là hai tình huống khác nhau và cần các ca nghiệm thu riêng.

### 6.4. Cache, kết nối tái sử dụng và thời điểm thay đổi chính sách

Không nên giả định mọi HTTP request đều thực hiện một lần xác minh chứng thư hoàn toàn mới. Client có thể dùng pool kết nối hoặc tái sử dụng trạng thái TLS theo thiết kế.

Nếu yêu cầu thu hồi, thay truststore hoặc đổi chính sách phải có hiệu lực trong một khoảng thời gian cụ thể, cần xác định cách xử lý kết nối đang mở, session, cache và các instance chưa cập nhật. Việc thay một tệp cấu hình chưa tự chứng minh mọi kết nối hiện có đã được đánh giá lại.

## 7. Kiến trúc nhiều chặng phải chỉ rõ ai xác minh ai

### 7.1. TLS termination tạo ra ranh giới mới

Một trang có HTTPS ở trình duyệt không chứng minh mọi chặng từ edge tới backend hoặc từ backend tới dịch vụ tích hợp đều được xác thực. Nếu TLS kết thúc ở một thành phần trung gian, kết nối kế tiếp là một quan hệ tin cậy riêng.

| Chặng minh họa | Bên thực hiện xác minh đối tác | Danh tính đích cần xác định | Nguồn tin cậy cần quản lý |
| --- | --- | --- | --- |
| Trình duyệt tới edge | Trình duyệt | Tên website người dùng truy cập | Chính sách trust của môi trường trình duyệt |
| Edge tới dịch vụ học tập bằng TLS | HTTP client tại edge | Tên dịch vụ backend đã cấu hình | Trust policy cho kết nối backend |
| Dịch vụ học tập tới API thông báo | HTTP client của dịch vụ học tập | Endpoint tích hợp đã chấp thuận | Trust policy của client tích hợp |

Nếu một chặng không dùng TLS theo quyết định kiến trúc, phải mô tả ranh giới bảo vệ và rủi ro của chặng đó riêng. Không gắn nhãn “end-to-end HTTPS” cho toàn luồng chỉ dựa vào chứng thư ở edge.

### 7.2. TLS inspection và proxy doanh nghiệp

Một proxy có thể kết thúc TLS rồi trình bày chứng thư do PKI của tổ chức cấp. Khi client tin PKI đó, đối tác được xác thực trực tiếp trên chặng client là proxy theo mô hình triển khai, không phải một kênh không bị chấm dứt tới server gốc.

Nếu tổ chức sử dụng mô hình này, cần đặc tả rõ phạm vi, loại dữ liệu được phép đi qua, quyền của proxy và cách proxy xác minh upstream. Không thêm CA của một công cụ chặn bắt vào mọi môi trường chỉ để một phiên chẩn đoán hoạt động.

### 7.3. mTLS vẫn cần phân quyền ứng dụng

Trong mTLS, server còn xác minh chứng thư của client theo chính sách danh tính client. Quy tắc ánh xạ danh tính và quyền của client cần được định nghĩa riêng; không lấy nguyên quy tắc so hostname của server để áp dụng tùy tiện cho mọi chứng thư client.

Một client có chứng thư hợp lệ không mặc nhiên được phép gọi mọi chức năng. Sau xác thực kênh và danh tính, ứng dụng vẫn cần phân quyền chức năng, đối tượng và phạm vi nghiệp vụ.

### 7.4. Certificate pinning là một quyết định bổ sung

Nếu mô hình đe dọa yêu cầu giới hạn thêm tập khóa hoặc chứng thư được chấp nhận, có thể đánh giá pinning. Cần nêu rõ pin gì, áp dụng cho đích nào, cơ chế phân phối, backup, thay khóa và phục hồi khi lệch cấu hình.

Không thêm một phép so fingerprint rồi bỏ toàn bộ kiểm tra chuỗi và danh tính mà không có mô hình tin cậy tương đương đã được xác định. Cũng không tự học pin từ kết nối đầu tiên chưa được xác minh nếu hợp đồng không cho phép kiểu thiết lập niềm tin đó.

Một pin quá cứng và thiếu quy trình thay đổi có thể làm gián đoạn dịch vụ. Yêu cầu bảo mật phải bao gồm cả vòng đời, không chỉ điều kiện so khớp ở thời điểm viết mã.

## 8. Ví dụ với Java HTTP client

### 8.1. Dùng cơ chế nền tảng, giữ kiểm tra danh tính

Java `HttpClient.Builder` cho phép cấu hình `SSLContext`, tham số TLS và chính sách redirect. Khi không cung cấp context riêng, client dùng default context. Đây là các điểm cấu hình cần kiểm soát trong thiết kế client. [Java HttpClient.Builder](https://docs.oracle.com/en/java/javase/25/docs/api/java.net.http/java/net/http/HttpClient.Builder.html).

Ví dụ minh họa:

```java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import javax.net.ssl.SSLParameters;

public final class NotificationHealthClient {
    public static void main(String[] args) throws Exception {
        SSLParameters parameters = new SSLParameters();
        parameters.setEndpointIdentificationAlgorithm("HTTPS");

        HttpClient client = HttpClient.newBuilder()
            .sslParameters(parameters)
            .connectTimeout(Duration.ofSeconds(5))
            .followRedirects(HttpClient.Redirect.NEVER)
            .build();

        HttpRequest request = HttpRequest.newBuilder()
            .uri(URI.create("https://api.learning.example/health"))
            .timeout(Duration.ofSeconds(10))
            .GET()
            .build();

        HttpResponse<Void> response = client.send(
            request,
            HttpResponse.BodyHandlers.discarding()
        );

        System.out.println(response.statusCode());
    }
}
```

Địa chỉ trong ví dụ là tên minh họa, không phải dịch vụ cần gọi thật. Các timeout là giá trị ví dụ, cần thay bằng ngân sách thời gian của sản phẩm. Đoạn mã không cấu hình đầy đủ chính sách thu hồi, private CA, thuật toán hoặc vòng đời kết nối.

`setEndpointIdentificationAlgorithm` chọn cơ chế xác minh endpoint trong handshake khi thuật toán được đặt phù hợp. Nó không phải nơi nạp trust anchor. [Java SSLParameters, endpoint identification](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/javax/net/ssl/SSLParameters.html#setEndpointIdentificationAlgorithm(java.lang.String)).

Không suy ra ví dụ này tự chứng minh mọi điều kiện của profile chứng thư đã chọn. Nếu yêu cầu SAN-only hoặc chính sách thu hồi chặt hơn hành vi của runtime, phải xác minh hỗ trợ của đúng phiên bản và provider, cấu hình cơ chế phù hợp và có ca nghiệm thu riêng. Tên thuật toán `HTTPS` không phải lời cam kết tự động về mọi phiên bản tiêu chuẩn danh tính dịch vụ.

### 8.2. Raw TLS socket cần chú ý riêng

Tài liệu JSSE phân biệt rõ việc dùng `SSLSocket` hoặc `SSLEngine` trực tiếp: các lớp này không tự bảo đảm tên host khớp thông tin danh tính nếu ứng dụng không bật hoặc thực hiện endpoint identification phù hợp. [Hướng dẫn JSSE về kiểm tra endpoint](https://docs.oracle.com/en/java/javase/25/security/java-secure-socket-extension-jsse-reference-guide.html).

Ví dụ một phần cấu hình, với `socket` đã được tạo đúng đích từ context đã quản lý:

```java
SSLParameters parameters = socket.getSSLParameters();
parameters.setEndpointIdentificationAlgorithm("HTTPS");
socket.setSSLParameters(parameters);
socket.startHandshake();
```

Đây không phải một HTTP client hoàn chỉnh. Khi chức năng là HTTP, nên chọn client HTTP phù hợp để không tự triển khai thêm parsing, redirect và các quy tắc giao thức không cần thiết.

### 8.3. Private CA phải được cấp qua trust material phù hợp

Nếu API nội bộ dùng private CA, hướng thiết kế là chuẩn bị trust material đúng nguồn, tạo context có trust manager chuẩn theo chính sách và gắn nó vào client cần sử dụng. Không thay trust manager bằng một callback luôn chấp nhận chứng thư.

Việc nạp trust material cần có lỗi khởi động hoặc lỗi cấu hình rõ ràng khi thiếu, sai định dạng hoặc sai nguồn. Không bắt lỗi nạp truststore rồi lùi về chế độ bỏ kiểm tra.

Trong cùng tiến trình có nhiều tích hợp, cần tránh thay cấu hình mặc định toàn cục ngoài chủ đích. Một cấu hình client riêng giúp thể hiện phạm vi, nhưng vẫn cần kiểm soát cách client đó được cấp phát và dùng lại.

## 9. Đặc tả yêu cầu bảo mật có thể kiểm chứng

### 9.1. Viết rõ chủ thể, đích và điều kiện

Yêu cầu yếu:

> Mọi API phải dùng SSL và certificate hợp lệ.

Câu này không xác định ai kiểm tra, tin CA nào, so tên gì, chặng kết nối nào được bao phủ hoặc xử lý ra sao khi cơ chế kiểm tra không đưa ra kết quả.

Yêu cầu rõ hơn:

> HTTP client của dịch vụ học tập chỉ được gửi credential và dữ liệu nghiệp vụ tới endpoint thông báo sau khi xác minh thành công danh tính TLS theo profile đã chọn. Profile phải xác định reference identity, nguồn trust anchor, điều kiện hiệu lực, chính sách thu hồi và ràng buộc của nền tảng. Mọi lỗi không đáp ứng profile phải ngăn gửi request nghiệp vụ tới đối tác chưa được xác thực; không tự tắt kiểm tra hoặc chuyển sang HTTP.

Để yêu cầu có thể thực thi, profile phải là cấu hình và tiêu chí có owner, không phải một tên gọi trống.

### 9.2. Bộ yêu cầu minh họa

| Mã | Yêu cầu | Bằng chứng dự kiến |
| --- | --- | --- |
| CV-01 | Mỗi kết nối HTTP outbound có dữ liệu thuộc phạm vi phải có owner, đích được phép và profile xác minh | Danh mục client, endpoint và cấu hình |
| CV-02 | Reference identity phải đến từ đích đã được chấp thuận, không tự suy từ chứng thư do peer gửi | Kiểm thử sai danh tính và cấu hình đích |
| CV-03 | Client phải thực thi xác minh chuỗi và danh tính bằng cơ chế chuẩn đáp ứng profile | Ca chứng thư không tin cậy và sai endpoint |
| CV-04 | Trust material phải có nguồn quản trị đã xác minh, phạm vi và quy trình thay đổi | Hồ sơ phân phối, quyền thay đổi và readback cấu hình |
| CV-05 | Không có đường fallback bỏ kiểm tra hoặc chuyển sang HTTP khi xác minh thất bại | Kiểm thử lỗi và kiểm tra nhánh xử lý |
| CV-06 | Hành vi thu hồi, timeout và độ mới phải được định nghĩa; kết quả bị thu hồi không được coi là đạt | Ca revoked, unknown, dữ liệu cũ và nguồn trạng thái không sẵn sàng |
| CV-07 | Redirect và failover phải tuân thủ chính sách đích và xác minh trên từng kết nối mới | Ca đổi authority và endpoint dự phòng |
| CV-08 | Thay trust policy phải có giới hạn hiệu lực được công bố cho instance, pool và trạng thái TLS | Kiểm thử cập nhật và thời gian hội tụ |
| CV-09 | Thay chứng thư hoặc CA phải có kế hoạch triển khai và rollback vẫn giữ kiểm tra | Diễn tập rotation với client thực |
| CV-10 | Lỗi xác minh phải quan sát được mà không ghi bí mật hoặc dữ liệu không cần thiết | Schema log, metric và kiểm tra quyền truy cập |
| CV-11 | Mỗi chặng TLS qua proxy, edge hoặc mesh phải có trách nhiệm xác minh rõ | Bản đồ kết nối và bằng chứng từng chặng |
| CV-12 | Khi cần trạng thái thu hồi từ mạng, hoạt động truy vấn phải có giới hạn tài nguyên và đích phù hợp | Cấu hình egress, timeout và thử nghiệm lỗi trong môi trường kiểm soát |

Các mã trên chỉ minh họa cách tổ chức đặc tả. Profile, giới hạn thời gian và độ bao phủ cần được xác định cho hệ thống thực tế.

### 9.3. Truy vết từ tài sản tới bằng chứng

```text
Tài sản: credential tích hợp và dữ liệu người học
    ↓
Mối đe dọa: client gửi request tới peer có chứng thư sai danh tính
    ↓
Yêu cầu: CV-02, CV-03 và CV-05
    ↓
Thiết kế: client quản lý tập trung theo profile; không override bỏ kiểm tra
    ↓
Bằng chứng: peer có chuỗi được tin nhưng sai endpoint bị từ chối;
không nhận được credential hoặc HTTP body nghiệp vụ
```

Một ca chứng thư sai tên đặc biệt hữu ích vì nó tách hostname verification khỏi việc tin CA. Nếu test chỉ dùng một chứng thư tự ký không tin cậy, client có thể thất bại ở bước chuỗi mà chưa chứng minh đã kiểm tra danh tính đích.

## 10. Tiêu chí nghiệm thu và dữ liệu thử

Phần này mô tả bằng chứng cần có khi triển khai yêu cầu, không tuyên bố một hệ thống đã được kiểm thử chỉ vì tài liệu có danh sách ca thử.

### 10.1. Dùng client thật trong môi trường kiểm soát

Cần thực hiện bằng HTTP client và cấu hình gần với triển khai thực: runtime, provider, truststore, proxy, container và cơ chế nạp cấu hình tương ứng.

Một công cụ dòng lệnh xác minh thành công không chứng minh ứng dụng Java dùng cùng truststore hoặc cùng chính sách. Ngược lại, một trình duyệt tin CA nội bộ không chứng minh một JVM trong container cũng tin CA đó.

Tạo dữ liệu thử có chủ đích: CA thử nghiệm, chứng thư đúng tên, sai tên, hết hạn hoặc các tình huống chính sách khác. Không sử dụng credential thật và không can thiệp hạ tầng ngoài phạm vi thử nghiệm.

### 10.2. Ma trận trường hợp

| Trường hợp | Thiết lập | Kết quả theo profile minh họa |
| --- | --- | --- |
| Hợp lệ | Endpoint và dữ liệu chứng thực đáp ứng toàn bộ profile | Cho phép request nghiệp vụ |
| Sai endpoint | Chuỗi được tin nhưng chứng thư không đại diện đích | Từ chối, không gửi credential hoặc body nghiệp vụ |
| Không có nguồn tin cậy | Đúng tên nhưng không tới trust anchor được chấp thuận | Từ chối |
| Hết hạn hoặc chưa có hiệu lực | Thời gian thử được kiểm soát và điều kiện tương ứng | Không chấp nhận ngoài profile |
| Thiếu thành phần xây dựng đường | Không có đường chứng thực hợp lệ trong môi trường thử cô lập | Từ chối thay vì bỏ kiểm tra |
| Mục đích hoặc ràng buộc không phù hợp | Chứng thư được tạo để vi phạm điều kiện profile | Từ chối theo cơ chế xác minh |
| SAN-only | Chỉ có Common Name phù hợp nhưng không đạt yêu cầu SAN của profile | Không dùng fallback ngoài chính sách đã chọn |
| Wildcard ngoài phạm vi | Tên đích không thuộc tập được profile cho phép | Từ chối |
| Thu hồi | Nguồn trạng thái được xác minh báo bị thu hồi | Không chấp nhận chứng thư đó |
| Không có thông tin trạng thái đạt yêu cầu | Timeout, unknown hoặc thông tin quá cũ | Thực hiện đúng chính sách đã công bố |
| Redirect | Đích mới không được chấp thuận hoặc không đạt profile | Không gửi dữ liệu tới đích trái chính sách |
| Rotation | Chứng thư hoặc CA mới được triển khai theo kế hoạch | Client tiếp tục xác minh đúng; không cần trust-all |
| Lỗi nạp trust material | Thiếu hoặc sai cấu hình | Báo lỗi và không fallback sang bỏ kiểm tra |
| Nhiều instance | Một số instance còn cấu hình cũ | Phát hiện và xử lý trong giới hạn hội tụ đã chọn |

Test thiếu intermediate cần kiểm soát các nguồn bổ sung hoặc cache của validator. Nếu client đã có intermediate cần thiết, việc server không gửi nó chưa chắc tạo ra tình huống không xây được đường. Cần thiết lập test đúng thuộc tính đang kiểm chứng.

### 10.3. Kiểm tra không gửi dữ liệu trước khi đạt điều kiện

Không chỉ quan sát exception ở client. Peer thử nghiệm phải được quan sát để xác nhận nó không nhận HTTP request nghiệp vụ có credential hoặc body thuộc phạm vi khi xác minh thất bại.

Bằng chứng này không yêu cầu không có byte mạng nào. Việc thiết lập TCP và trao đổi TLS có thể đã xảy ra. Điều cần chứng minh là dữ liệu ứng dụng thuộc phạm vi không được chuyển tới peer chưa đáp ứng điều kiện xác thực đã định nghĩa.

Nếu sản phẩm dùng các cơ chế tiếp tục phiên hoặc tối ưu gửi dữ liệu đặc biệt, cần đưa chúng vào mô hình riêng. Một ca kết nối mới không tự chứng minh mọi đường tái sử dụng trạng thái đều tuân thủ cùng thời điểm áp dụng chính sách.

### 10.4. Kiểm tra các nhánh xử lý lỗi

Cần đi tới nhánh timeout, lỗi đọc truststore, lỗi nguồn trạng thái và lỗi handshake. Xác nhận rằng các nhánh này không tạo một client khác có cấu hình nới lỏng để retry.

Retry có thể hữu ích với lỗi tạm thời theo chính sách, nhưng không sửa được chứng thư sai danh tính. Vòng retry cần giới hạn và giữ cùng yêu cầu xác minh; không tăng mức chấp nhận mỗi lần thất bại.

### 10.5. Những bằng chứng chưa đủ

- URL bắt đầu bằng `https://` chưa chứng minh client có xác minh đúng.
- Handshake hoàn tất chưa chứng minh đáp ứng mọi điều kiện profile bổ sung.
- Có truststore chưa chứng minh đúng truststore đã được nạp bởi client đang chạy.
- Một endpoint hợp lệ hoạt động chưa chứng minh endpoint sai bị từ chối.
- Kiểm tra bằng công cụ khác chưa chứng minh hành vi của runtime ứng dụng.
- Một chứng thư mới đã cài ở server chưa chứng minh mọi instance client kết nối được.

Bằng chứng nên ghi reference identity, phiên bản cấu hình, runtime/provider, tập trust material, proxy liên quan và trạng thái kết nối mới hay tái sử dụng. Không cần ghi bí mật để có khả năng truy vết.

## 11. Vận hành và vòng đời chứng thư

### 11.1. Kiểm kê từ phía consumer

Một dịch vụ có thể dùng client trong nhiều thư viện: gọi API, tải tài liệu, gửi webhook, health check hoặc tác vụ nền. Chỉ kiểm kê chứng thư ở ingress không bao phủ các kết nối outbound.

Mỗi consumer cần owner, endpoint, nguồn trust và profile. Nếu một thư viện tự tạo client khác, phải đưa hành vi đó vào danh mục và bằng chứng nghiệm thu.

### 11.2. Chuẩn bị thay chứng thư và CA

Một kế hoạch rotation có thể gồm:

1. Kiểm tra tên và mục đích của chứng thư mới so với các consumer thật.
2. Xác nhận trust material cần thiết đã có hoặc được phân phối an toàn.
3. Thử nghiệm trên các runtime và tuyến proxy đang hỗ trợ.
4. Triển khai theo phạm vi có kiểm soát, quan sát lỗi handshake và lỗi nghiệp vụ.
5. Hoàn tất chuyển đổi, xử lý pool hoặc trạng thái cũ theo chính sách.
6. Thu hồi hoặc gỡ cấu hình cũ khi không còn cần, theo vòng đời đã phê duyệt.

Khoảng chồng lấn giữa cấu hình cũ và mới phải có mục đích và thời hạn. Rollback không được hiểu là bật trust-all hoặc chấp nhận mọi hostname.

### 11.3. Quan sát lỗi mà không làm lộ bí mật

Log có thể ghi client, endpoint được rút gọn theo chính sách, loại lỗi xác minh, phiên bản trust policy và correlation ID. Những trường chứng thư phục vụ chẩn đoán cần được giới hạn theo độ nhạy, vì tên nội bộ hoặc danh tính cũng có thể là dữ liệu không nên phát tán.

Không ghi private key, token, mật khẩu truststore hoặc toàn bộ payload nghiệp vụ chỉ để giải thích một lỗi TLS. Quyền xem log và thời hạn lưu cần được quản lý.

### 11.4. Xử lý sự cố

Khi kết nối thất bại, điều tra theo thứ tự có bằng chứng: đích cấu hình, danh tính tham chiếu, thời gian, trust material thực tế, chuỗi được trình bày, profile runtime và tuyến proxy.

Nếu phát hiện chứng thư hoặc CA bị ảnh hưởng, cần đánh giá những consumer tin nó và thời điểm chính sách mới có hiệu lực. Không giới hạn xử lý ở server cấp chứng thư mà bỏ các client, pool và cấu hình phân phối.

Khả năng tiếp tục nghiệp vụ nên dựa vào endpoint dự phòng đã được chấp thuận hoặc hàng đợi có chính sách, thay vì hạ mức xác thực của kết nối đang lỗi.

## 12. Các sai lầm cần nhận diện

### 12.1. Trust manager luôn chấp nhận

Callback trả thành công với mọi chuỗi làm mất quyết định tin cậy mà ứng dụng cần. Nó không phải giải pháp dài hạn cho private CA hoặc lỗi triển khai.

### 12.2. Hostname verifier luôn trả true

Cách này cho phép chứng thư không đại diện endpoint vẫn được chấp nhận nếu các lớp khác cho phép. Nó làm mất ranh giới giữa tin một CA và xác nhận đúng dịch vụ.

### 12.3. Tự sửa tên đích để khớp chứng thư nhận được

Nếu client dùng dữ liệu do peer chưa được xác minh cung cấp để chọn reference identity, phép kiểm tra có thể trở thành tự xác nhận. Đích phải đến từ ý định và cấu hình được chấp thuận của ứng dụng.

### 12.4. Import mọi chứng thư gặp lỗi

Không phải lỗi nào cũng do thiếu CA, và không phải mọi chứng thư thu thập được đều nên được tin. Cần xác định nguồn gốc và vai trò trước khi thay trust policy.

### 12.5. Kiểm tra ngày hết hạn là đủ

Một chứng thư còn hạn vẫn có thể sai danh tính, sai ràng buộc hoặc không được tin. Cần cơ chế xác minh đầy đủ theo profile, không một kiểm tra đơn lẻ thay toàn bộ chính sách.

### 12.6. Mọi lỗi đều xử lý bằng retry

Sai tên hoặc sai nguồn tin cậy không tự biến mất sau nhiều lần thử. Retry không giới hạn còn có thể gây tải và che khuất sự cố cấu hình. Hành vi lỗi cần phân loại và có giới hạn.

## 13. Mẫu đặc tả cho một HTTP client tích hợp

```text
ID: SEC-HTTP-NOTIFICATION-CERTIFICATE-VALIDATION

Tài sản:
Credential tích hợp, dữ liệu người học và tính toàn vẹn của phản hồi.

Phạm vi:
Mọi lời gọi HTTPS của client thông báo, gồm tác vụ nền, health check,
redirect hoặc failover được sản phẩm cho phép.

Danh tính và nguồn tin cậy:
Endpoint lấy từ cấu hình đã chấp thuận. Reference identity được xác định
trước khi nhận chứng thư. Trust material có nguồn quản trị đã xác minh
và chỉ áp dụng trong phạm vi client được giao.

Điều kiện chấp nhận:
Chuỗi và danh tính đáp ứng profile đã chọn, gồm điều kiện hiệu lực,
ràng buộc sử dụng, thuật toán và chính sách thu hồi tương ứng.
Các điều kiện bổ sung như SAN-only phải được thực thi và kiểm thử rõ.

Hành vi lỗi:
Không gửi credential hoặc HTTP body nghiệp vụ tới peer không đạt.
Không tắt kiểm tra, không đổi reference identity theo chứng thư nhận được,
không chuyển sang HTTP và không fallback sang client nới lỏng.

Thay đổi và thời gian hiệu lực:
Quy định cách cập nhật trust material, xử lý pool/session và các instance.
Có ngưỡng cảnh báo, kế hoạch rotation và rollback vẫn giữ xác minh.

Bằng chứng nghiệm thu:
Client thật chấp nhận chứng thư đạt profile; từ chối sai endpoint,
không tin cậy và các trường hợp vi phạm profile. Kiểm tra nhánh lỗi,
dữ liệu ứng dụng không bị gửi, redirect, rotation và cập nhật cấu hình.

Chủ sở hữu:
Nhóm tích hợp quản lý client và endpoint; nhóm nền tảng quản lý cơ chế
và trust material; nhóm vận hành quản lý triển khai, cảnh báo và phục hồi.
```

Certificate validation giúp ràng buộc một kênh được mã hóa với đúng danh tính mà ứng dụng dự định tin cậy. Một yêu cầu có thể kiểm chứng phải nêu rõ nguồn niềm tin, reference identity, profile chấp nhận, thời điểm áp dụng và hành vi khi lỗi; đồng thời giữ được các bảo đảm đó qua proxy, thay chứng thư và sự cố vận hành.
