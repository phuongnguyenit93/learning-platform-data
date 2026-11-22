# Khởi tạo từ SSLContext và vai trò client, server

## 1. SSLContext và SSLEngine không cùng một cấp

Một kết nối TLS cần chính sách bảo mật và trạng thái riêng của cuộc trao đổi. Trong JSSE:

- **SSLContext** chuẩn bị môi trường TLS: provider, nguồn khóa/xác thực, quyết định tin cậy và nguồn ngẫu nhiên.
- **SSLEngine** là máy trạng thái cho một lần sử dụng kết nối: vai client/server, các tham số được chọn và quá trình bắt tay/dữ liệu/đóng.

```text
Nguồn khóa + nguồn trust + cấu hình provider
                    |
                SSLContext
                /        \
       SSLEngine A      SSLEngine B
       client mode      server mode
       trạng thái A     trạng thái B
```

Một context có thể tạo nhiều engine. Điều đó không có nghĩa các engine được dùng chung trạng thái của một kết nối hoặc thay thế cho nhau giữa chừng.

API có tên SSL vì lịch sử, nhưng bài dùng TLS trên Java 17+. Không bật giao thức đã cũ chỉ để khớp tên lớp hoặc vì module bắt đầu từ Java 5.

[SSLContext](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/net/ssl/SSLContext.html) là factory tạo engine và các socket factory của JSSE.

## 2. Trình tự khởi tạo cần giữ rõ

```text
Chọn SSLContext/provider
        |
Khởi tạo context với key/trust material phù hợp
        |
Tạo engine cho kết nối
        |
Chọn vai client hoặc server
        |
Đặt protocol, xác thực peer và các tham số cần thiết
        |
Bắt đầu điều phối handshake qua wrap/unwrap và I/O
```

Không ghép các bước thành một giả định “createSSLEngine xong là đã có TLS”.

Tạo engine:

- Không mở socket.
- Không gọi connect.
- Không tự vận chuyển dữ liệu bắt tay.
- Không tự chứng minh phía đối diện đã được xác thực.
- Không kiểm tra sẵn rằng mọi cấu hình server sẽ chọn được chứng chỉ phù hợp.

Những điều ấy được xác định trong các bước cấu hình, bắt tay và quản lý I/O tiếp theo.

## 3. Tạo và init một context riêng

Mẫu tối giản:

```java
SSLContext context = SSLContext.getInstance("TLS");
context.init(keyManagers, trustManagers, secureRandom);
```

Đây là đoạn minh họa. Các biến phải được chuẩn bị từ cấu hình thật và cần xử lý các ngoại lệ bảo mật tương ứng.

`getInstance` chọn implementation/provider hỗ trợ tên giao thức. Nó không tự đồng nghĩa đã nạp mọi khóa và trust phù hợp với ứng dụng.

Với context yêu cầu khởi tạo, dùng factory/engine trước init có thể gây IllegalStateException. Cần hoàn tất init trước khi tạo engine từ context ấy.

### Ý nghĩa ba tham số init

| Tham số | Trách nhiệm |
| --- | --- |
| KeyManager[] | Cung cấp/lựa chọn danh tính và khóa xác thực cục bộ |
| TrustManager[] | Quyết định tin cậy đối với phía đối diện |
| SecureRandom | Nguồn ngẫu nhiên an toàn cho hoạt động giao thức |

Không hoán đổi key material và trust material chỉ vì cả hai thường được lưu trong dạng KeyStore.

Nếu truyền null, SSLContext có quy tắc chọn mặc định/provider cho những tham số ấy. Điều này **không** mang nghĩa “tin mọi chứng chỉ”, cũng không phải lời hứa rằng một server sẽ có danh tính đúng mong muốn.

Một context tạo được và init thành công chỉ nói bước chuẩn bị tương ứng đã hoàn tất. Tính phù hợp của khóa, trust và thuật toán còn phải được kiểm chứng với kịch bản bắt tay thực tế.

## 4. Context mặc định là một lựa chọn khác với context riêng

```java
SSLContext context = SSLContext.getDefault();
```

Context mặc định do API trả về đã ở trạng thái dùng được, không cần ứng dụng gọi init lại như đối tượng vừa lấy bằng getInstance cho một context riêng.

getDefault được bổ sung sau Java 5 nhưng vẫn là API hiện hành. Cần hiểu nó lấy chính sách mặc định của tiến trình/provider, có thể chịu ảnh hưởng bởi cấu hình hệ thống và cách ứng dụng đã thiết lập context mặc định.

Nếu một dịch vụ phải dùng bộ trust hoặc danh tính riêng, đừng dùng mặc định chỉ vì ít dòng hơn. Chuẩn bị một context riêng giúp thể hiện phạm vi chính sách rõ ràng.

Cũng không gọi SSLContext.setDefault tùy tiện trong một thành phần thư viện: đó là thay đổi mặc định có thể ảnh hưởng các thành phần khác trong cùng tiến trình. Tạo và truyền context riêng thường có phạm vi dễ kiểm soát hơn.

## 5. KeyManager và TrustManager theo hai vai

### Server xác thực danh tính của mình

Trong mô hình TLS xác thực bằng chứng chỉ thường dùng, server cần có:

- Khóa riêng tương ứng.
- Chuỗi chứng chỉ phù hợp.
- KeyManager có thể chọn đúng alias/danh tính theo thuật toán và yêu cầu bắt tay.

Một truststore chỉ có chứng chỉ CA không tự biến thành danh tính server. Chứng chỉ tin cậy không đồng nghĩa có private key tương ứng.

### Client kiểm tra server

Client cần trust policy để đánh giá chứng chỉ phía server. Ngoài kiểm tra chuỗi tin cậy, còn phải kiểm tra danh tính đích theo giao thức ứng dụng, chẳng hạn tên host của HTTPS.

Một chuỗi chứng chỉ được CA tin cậy ký không tự chứng minh đó là tên host mà client đang định gọi.

### TLS hai chiều — mTLS

Nếu server yêu cầu chứng chỉ client, client còn cần danh tính/khóa cục bộ, và server cần trust policy để kiểm tra client.

| Mô hình | Client cần danh tính cục bộ? | Server cần trust để xác thực client? |
| --- | --- | --- |
| TLS chỉ xác thực server | Thường không cần chứng chỉ client | Không bắt buộc cho mục đích xác thực client ở mô hình này |
| mTLS yêu cầu chứng chỉ client | Có danh tính phù hợp | Có chính sách xác thực client |

Cấu hình vai client/server không tự chọn ra mô hình mTLS. Phải đặt yêu cầu client authentication và cung cấp vật liệu tương ứng.

Các factory chuẩn: [KeyManagerFactory](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/net/ssl/KeyManagerFactory.html), [TrustManagerFactory](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/net/ssl/TrustManagerFactory.html).

## 6. Mẫu nạp context từ KeyStore đã được quản lý

Đây là một phương thức minh họa có thể đặt trong lớp tiện ích. Nó giả định identityStore và trustStore đã được nạp từ nguồn mà ứng dụng cho phép; không tự mở tệp hoặc tạo chứng chỉ thử.

```java
static SSLContext createContext(
        KeyStore identityStore,
        char[] keyPassword,
        KeyStore trustStore) throws GeneralSecurityException {

    Objects.requireNonNull(identityStore, "identityStore");
    Objects.requireNonNull(trustStore, "trustStore");

    KeyManagerFactory keyFactory = KeyManagerFactory.getInstance(
            KeyManagerFactory.getDefaultAlgorithm());
    keyFactory.init(identityStore, keyPassword);

    TrustManagerFactory trustFactory = TrustManagerFactory.getInstance(
            TrustManagerFactory.getDefaultAlgorithm());
    trustFactory.init(trustStore);

    SSLContext context = SSLContext.getInstance("TLS");
    context.init(
            keyFactory.getKeyManagers(),
            trustFactory.getTrustManagers(),
            new SecureRandom());
    return context;
}
```

Cần import các kiểu tương ứng từ java.security, java.util và javax.net.ssl. Đây không phải chương trình độc lập có main, vì nguồn KeyStore và vòng đời mật khẩu thuộc cấu hình thật của ứng dụng.

Hàm thể hiện hai nguồn riêng: identityStore phục vụ khóa/danh tính cục bộ, trustStore phục vụ quyết định tin cậy.

Với client không dùng chứng chỉ client, có thể thiết kế một hàm tạo context không yêu cầu identityStore. Với server/mTLS, cần kiểm tra những key entry và trust anchor thật sự đáp ứng hợp đồng. Đừng dùng cùng một helper chung rồi bỏ qua những giả thiết của nó.

Mật khẩu, private key và nội dung nhạy cảm không cần được in ra log để chứng minh init thành công. Vòng đời char[] và nguồn secret phải được quản lý theo bên sở hữu; ví dụ không tự thay đổi mảng mật khẩu đang được nơi khác dùng.

## 7. Tạo engine với hoặc không có thông tin peer

```java
SSLEngine client = context.createSSLEngine("api.example", 443);
client.setUseClientMode(true);
```

Host/port là thông tin peer mang tính tư vấn cho engine. Nó có thể hỗ trợ những chức năng như quản lý session và xác thực danh tính khi được cấu hình phù hợp, nhưng không mở kết nối tới host/port ấy.

```java
SSLEngine server = context.createSSLEngine();
server.setUseClientMode(false);
```

Engine server cũng không tự listen trên một cổng. Ứng dụng/framework phải nhận kết nối và gắn đúng dữ liệu vận chuyển vào engine.

Không dùng việc createSSLEngine có truyền host hay không để suy ra vai. Vai được chọn tường minh bằng setUseClientMode.

Không dùng cùng một engine cho nhiều kết nối độc lập. Context có thể được tái sử dụng theo thiết kế chính sách, còn engine phải giữ vòng đời và thứ tự byte của kết nối nó phục vụ.

## 8. Vai client/server phải được đặt trước handshake

```java
engine.setUseClientMode(true);  // vai client
engine.setUseClientMode(false); // vai server, nếu còn trước handshake
```

Hai dòng trên chỉ minh họa hai lựa chọn. Khi cấu hình một kết nối, hãy chọn đúng một vai theo giao thức, thay vì vô tình ghi đè qua lại.

Vai quyết định cách engine tham gia bắt tay, bao gồm kiểu bản tin mà mỗi bên tạo và xử lý. Một phiên TLS cần các vai đối ứng đúng.

Mặc định của engine mới phụ thuộc provider. Không dựa vào getUseClientMode ban đầu để thay cho một quyết định cấu hình có chủ đích.

Sau khi bắt tay bắt đầu, không được đổi vai trong vòng đời engine. Những lời gọi wrap/unwrap cũng có thể kích hoạt bắt tay ban đầu, nên không đặt vai sau lần gọi đầu tiên ấy.

[SSLEngine.setUseClientMode](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/net/ssl/SSLEngine.html#setUseClientMode(boolean)) mô tả thời điểm cấu hình và ràng buộc vai.

Vai TLS không được suy ra chỉ từ nhãn “máy chủ nghiệp vụ” hoặc “máy khách nghiệp vụ”. Khi tích hợp một giao thức đặc thù, cần xác định rõ đầu nào đóng vai client/server TLS ở phiên ấy. Với trường hợp HTTPS thường gặp, bên khởi tạo yêu cầu thường là TLS client và bên phục vụ là TLS server.

## 9. Yêu cầu chứng chỉ client: want và need khác nhau

Các tùy chọn này có ý nghĩa cho engine ở vai server:

| Cấu hình | Ý nghĩa |
| --- | --- |
| setWantClientAuth(true) | Yêu cầu theo hướng tùy chọn: client không cung cấp danh tính thì phiên vẫn có thể tiếp tục |
| setNeedClientAuth(true) | Bắt buộc client authentication theo hợp đồng; thiếu thông tin cần thiết làm thương lượng không tiếp tục thành công |
| Không want/need | Không yêu cầu xác thực client bằng tùy chọn ấy |

Hai cờ không phải hai mức độc lập cần cùng bật. Lời gọi đặt want/need có quy tắc ghi đè yêu cầu trước đó. Ví dụ đặt need sau want chuyển sang yêu cầu bắt buộc, không giữ hai trạng thái cùng true.

Không nhầm needClientAuth với “server có chứng chỉ của chính nó”. Nó nói về yêu cầu **đối với client**, còn danh tính server vẫn cần được cấu hình qua vật liệu khóa.

Cũng không dùng want khi hợp đồng nghiệp vụ thực sự bắt buộc mTLS rồi coi mọi kết nối bắt tay xong là đã có chứng chỉ client hợp lệ.

## 10. Cấu hình tham số của từng engine

Sau khi đặt vai, có thể lấy SSLParameters, thay tham số cần thiết rồi áp lại:

```java
SSLParameters parameters = client.getSSLParameters();
parameters.setProtocols(new String[]{"TLSv1.3", "TLSv1.2"});
parameters.setEndpointIdentificationAlgorithm("HTTPS");
client.setSSLParameters(parameters);
```

Đây là cấu hình minh họa cho client trên JDK hỗ trợ những phiên bản đó. Chính sách triển khai phải xét provider/JDK và yêu cầu hệ thống; không suy ra “hỗ trợ” đồng nghĩa “nên bật mọi phiên bản”.

Một số phân biệt quan trọng:

- Tên "TLS" của SSLContext không phải thông báo phiên kết nối đã thương lượng TLS phiên bản nào.
- Supported protocols là khả năng implementation; enabled protocols là tập được cho phép cho engine.
- Phiên bản và cipher suite thương lượng thực tế chỉ được xác định qua bắt tay.
- SNI không thay cho endpoint identification.
- Endpoint identification tên HTTPS không biến SSLEngine thành một HTTP client.

Lấy một SSLParameters mới rồi áp lại có thể tác động nhiều trường tham số, gồm các cờ client authentication theo hợp đồng. Không vô tình ghi đè chính sách server đã đặt trước đó bằng một đối tượng tham số không phản ánh đầy đủ ý định.

Đặt cấu hình trước khi bắt tay và đọc lại cấu hình cần kiểm chứng là cách tốt để tránh nhầm giữa đối tượng parameters cục bộ và trạng thái đã áp vào engine.

## 11. Chương trình kiểm chứng khởi tạo và vai

Ví dụ chỉ kiểm tra tạo đối tượng và đọc lại cấu hình. Nó không mở socket, không nạp bộ chứng chỉ server tường minh và không thực hiện handshake, nên không phải bằng chứng về một server TLS có thể phục vụ thật.

Lưu thành `EngineInitializationDemo.java`:

```java
import java.security.SecureRandom;
import java.util.Arrays;
import javax.net.ssl.SSLContext;
import javax.net.ssl.SSLEngine;
import javax.net.ssl.SSLParameters;

public class EngineInitializationDemo {
    public static void main(String[] args) throws Exception {
        SSLContext context = SSLContext.getInstance("TLS");

        try {
            context.createSSLEngine();
        } catch (IllegalStateException e) {
            System.out.println("Uninitialized context rejected: true");
        }

        context.init(null, null, new SecureRandom());

        SSLEngine client = context.createSSLEngine("api.example", 443);
        client.setUseClientMode(true);

        SSLParameters parameters = client.getSSLParameters();
        parameters.setProtocols(new String[]{"TLSv1.3", "TLSv1.2"});
        parameters.setEndpointIdentificationAlgorithm("HTTPS");
        client.setSSLParameters(parameters);

        SSLEngine server = context.createSSLEngine();
        server.setUseClientMode(false);

        try {
            System.out.println("Client role: "
                    + client.getUseClientMode());
            System.out.println("Client peer hint: "
                    + client.getPeerHost() + ":" + client.getPeerPort());
            System.out.println("Client endpoint identification: "
                    + client.getSSLParameters()
                            .getEndpointIdentificationAlgorithm());
            System.out.println("Client enabled protocols: "
                    + Arrays.toString(client.getEnabledProtocols()));

            System.out.println("Server role is client: "
                    + server.getUseClientMode());

            server.setWantClientAuth(true);
            System.out.println("Server initially wants client auth: "
                    + server.getWantClientAuth());

            server.setNeedClientAuth(true);
            System.out.println("Server now requires client auth: "
                    + server.getNeedClientAuth());
            System.out.println("Server still only wants client auth: "
                    + server.getWantClientAuth());

            System.out.println("Different engine instances: "
                    + (client != server));
        } finally {
            client.closeOutbound();
            server.closeOutbound();
        }
    }
}
```

Chạy trên JDK 17+ có hỗ trợ những giao thức đã chọn:

```shell
javac EngineInitializationDemo.java
java EngineInitializationDemo
```

Stdout của lần kiểm chứng trên JDK 17.0.15:

```text
Uninitialized context rejected: true
Client role: true
Client peer hint: api.example:443
Client endpoint identification: HTTPS
Client enabled protocols: [TLSv1.3, TLSv1.2]
Server role is client: false
Server initially wants client auth: true
Server now requires client auth: true
Server still only wants client auth: false
Different engine instances: true
```

Phần init(null, null, ...) dùng quy tắc mặc định của JSSE/provider để thí nghiệm tự chạy. Nó không cài một TrustManager bỏ qua xác thực, cũng không bảo đảm có danh tính phù hợp cho một server triển khai thật.

Một context tạo hai engine trong ví dụ chỉ chứng minh quan hệ factory và trạng thái vai riêng. Ứng dụng có các trust policy khác nhau cho client và server có thể cần các context riêng để thể hiện đúng phạm vi.

Khối finally đóng outbound của các engine chưa bắt tay. Nó không minh họa quy trình gửi close_notify qua một kết nối hoạt động.

## 12. Sau khởi tạo còn phải làm gì?

Để có kết nối TLS thật, tầng tích hợp còn phải:

1. Tạo hoặc nhận transport theo kiến trúc.
2. Chuẩn bị các ByteBuffer plaintext/TLS.
3. Điều phối wrap, unwrap và delegated task theo HandshakeStatus.
4. Thu và gửi byte theo đúng thứ tự, xử lý đọc/ghi từng phần.
5. Xác nhận bắt tay thành công và kết quả peer/session phù hợp.
6. Trao đổi dữ liệu ứng dụng theo giao thức.
7. Đóng hai hướng TLS và transport theo chính sách.
8. Quản lý timeout, lỗi, hủy và giới hạn tài nguyên.

Không đánh dấu một yêu cầu là “đã kết nối an toàn” ngay sau createSSLEngine, init context hoặc setUseClientMode.

Nếu handshake thất bại, hãy phân biệt lỗi vật liệu khóa, trust, tên đích, thuật toán chung và điều phối I/O. Tắt kiểm tra chứng chỉ/hostname để “hết lỗi” sẽ làm thay đổi thuộc tính bảo mật thay vì sửa nguyên nhân.

## 13. Vòng đời cấu hình và tái sử dụng

Context nên có phạm vi gắn với chính sách khóa/trust/provider rõ ràng. Không tạo lại toàn bộ context cho mọi lần wrap, cũng không tự coi một context mặc định dùng chung là phù hợp với mọi khách hàng/miền tin cậy.

Khi thay danh tính hoặc trust policy, cần thiết kế vòng đời cập nhật cấu hình và các engine mới/cũ. Một lựa chọn dễ lập luận là chuẩn bị context mới cho cấu hình mới rồi cấp engine mới theo chính sách chuyển đổi.

Không dùng việc re-init hoặc đổi cấu hình chung tùy tiện như một cơ chế xoay vòng mà chưa hiểu ảnh hưởng tới engine/session đang tồn tại.

Với mỗi engine, giữ quyền sở hữu trạng thái và buffer phù hợp. Hai engine riêng không đồng nghĩa có thể tùy ý sửa chung những cấu trúc bên ngoài mà key/trust manager tùy biến tham chiếu tới.

## 14. Tự kiểm tra

**getInstance("TLS") có luôn cho một context đã sẵn dùng như getDefault không?**  
Không. Context riêng cần được khởi tạo theo hợp đồng/provider trước khi dùng factory/engine.

**Tạo engine có peerHost thì tự thành client không?**  
Không. Đặt vai rõ bằng setUseClientMode(true).

**setNeedClientAuth(true) cung cấp chứng chỉ cho server không?**  
Không. Nó yêu cầu xác thực phía client; danh tính server là trách nhiệm khác.

**Một truststore CA có tự chứa private key server không?**  
Không. Trust material và identity/key material có vai trò khác nhau.

**Engine được cấu hình đúng có nghĩa đã xác thực peer không?**  
Chưa. Cần bắt tay thực tế và kiểm chứng kết quả theo hợp đồng.

Khởi tạo đúng là một chuỗi quyết định rõ ràng: context lấy khóa/trust từ đâu, engine phục vụ kết nối nào, đóng vai gì và phải áp chính sách xác thực nào trước khi bắt tay.
