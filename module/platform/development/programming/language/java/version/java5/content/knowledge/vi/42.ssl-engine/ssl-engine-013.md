# Giới hạn trách nhiệm của SSLEngine so với quản lý kết nối

## 1. SSLEngine xử lý TLS, còn ai vận chuyển dữ liệu?

`SSLEngine` là thành phần xử lý TLS độc lập với cơ chế truyền dữ liệu. Ứng dụng đưa byte vào engine và lấy byte ra; ứng dụng cũng phải quyết định đọc từ đâu, ghi đi đâu, chờ khi nào và đóng kết nối ra sao.

Mô hình cần nhớ:

```text
Thông điệp của ứng dụng
        ↕ mã hóa/giải mã giao thức ứng dụng
Byte dữ liệu ứng dụng
        ↕ SSLEngine.wrap / SSLEngine.unwrap
Byte của giao thức TLS
        ↕ bộ quản lý kết nối
Socket / kênh truyền
```

Với TLS trên TCP:

- `wrap()` chuyển dữ liệu ứng dụng thành dữ liệu TLS, đồng thời có thể tạo thông điệp bắt tay hoặc đóng TLS.
- `unwrap()` xử lý dữ liệu TLS nhận được và có thể tạo dữ liệu ứng dụng.
- Cả hai thao tác làm việc với bộ đệm; chúng không tự đọc hay ghi socket.

Sự tách biệt này cho phép dùng engine trong vòng lặp sự kiện, cơ chế I/O bất đồng bộ hoặc kiểm thử hoàn toàn trong bộ nhớ. Đổi lại, phần bao quanh engine phải điều phối đúng. Xem [SSLEngine](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/net/ssl/SSLEngine.html).

“Không phụ thuộc cơ chế vận chuyển” không có nghĩa ứng dụng được đảo thứ tự hay bỏ byte TLS. Khi dùng TLS trên TCP, bộ quản lý kết nối phải cung cấp đúng luồng byte có thứ tự mà giao thức yêu cầu. DTLS có quy tắc riêng cho datagram, không dùng nguyên xi mọi giả định về luồng TCP trong bài này.

## 2. Bảng phân chia trách nhiệm

| Công việc | Engine TLS đảm nhiệm | Bộ quản lý kết nối/ứng dụng đảm nhiệm |
| --- | --- | --- |
| Tạo và xử lý bản ghi TLS | Có | Cung cấp bộ đệm đúng, chuyển byte đúng thứ tự |
| Bắt tay, thương lượng tham số mật mã | Có, theo cấu hình/provider | Cấu hình trước khi bắt tay, điều phối các bước engine yêu cầu |
| Kiểm tra chứng chỉ | Thực hiện qua cơ chế xác thực đã cấu hình | Chọn nguồn tin cậy, chính sách định danh và chứng chỉ phù hợp |
| DNS, proxy, chọn địa chỉ mạng | Không | Thực hiện phân giải/chọn đường kết nối |
| Mở TCP, accept, connect | Không | Quản lý socket/channel và lỗi kết nối |
| Chờ khả năng đọc/ghi | Không | Đăng ký sự kiện, quản lý selector hoặc cơ chế bất đồng bộ |
| Đọc/ghi từng phần | Không tự vận chuyển | Giữ byte chưa xử lý/chưa gửi và tiếp tục đúng vị trí |
| Cấp phát, tăng, giới hạn bộ đệm | Trả kích thước gợi ý và trạng thái | Sở hữu bộ nhớ và quyết định chính sách tài nguyên |
| Chạy tác vụ được giao | Tạo tác vụ khi cần | Thực thi, báo hoàn thành và tiếp tục TLS |
| Timeout, hủy, thử kết nối lại | Không tự quản lý vòng đời toàn bộ kết nối | Đặt deadline và chính sách xử lý |
| Đóng TLS | Tạo/xử lý thông điệp đóng | Bơm thông điệp đóng qua đường truyền, sau đó giải phóng tài nguyên |
| HTTP, RPC, thông điệp nghiệp vụ | Không | Phân tích, định tuyến, xác thực quyền và xử lý nghiệp vụ |

Các hàng bên phải không phải “công việc phụ”. Chúng quyết định một bộ ghép TLS có chạy ổn khi mạng chậm, quá tải, ngắt đột ngột hoặc chỉ ghi được một phần hay không.

Ví dụ, engine có thể mã hóa chính xác mọi byte, nhưng nếu ứng dụng xóa bộ đệm ngay sau lần ghi socket chỉ gửi được một nửa, kết nối vẫn hỏng. Nguyên nhân nằm ở việc vận chuyển byte chứ không phải thuật toán mật mã.

## 3. Một thao tác thành công chưa phải hoàn tất cả kết nối

Nên phân biệt ít nhất bốn mốc:

1. **TCP đã kết nối**: có đường truyền tới một địa chỉ.
2. **Bắt tay TLS đã hoàn tất và đạt chính sách xác thực**: có thể dùng kênh bảo mật theo cấu hình.
3. **Byte đã được đưa vào đường gửi**: một phần hay toàn bộ dữ liệu đã được xử lý ở phía cục bộ.
4. **Ứng dụng phía bên kia đã xác nhận xử lý**: cần phản hồi của giao thức ứng dụng nếu nghiệp vụ yêu cầu.

`SSLEngineResult` cho biết trạng thái thao tác, trạng thái bắt tay và số byte đã tiêu thụ/sinh ra. `bytesConsumed()` không phải số byte đối tác đã nhận; `bytesProduced()` cũng không phải xác nhận nghiệp vụ. Xem [SSLEngineResult](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/net/ssl/SSLEngineResult.html).

Ví dụ: `wrap()` tiêu thụ hết 100 byte ứng dụng và sinh dữ liệu TLS vào `netOut`. Ngay sau đó mạng ngắt. Engine đã làm phần việc của nó, nhưng ứng dụng không thể suy ra đối tác đã đọc hoặc xử lý 100 byte ấy.

Tương tự, `Status.OK` chỉ cho biết thao tác đã thực hiện được theo trạng thái đó. Phải đọc trạng thái bắt tay riêng; không coi `OK` là “kết nối đã sẵn sàng cho mọi yêu cầu”.

Đây cũng là lý do thử lại cần chính sách ở tầng ứng dụng. Nếu mất kết nối sau khi gửi yêu cầu thanh toán, tạo engine mới và gửi lại toàn bộ có thể gây xử lý trùng. Cần cơ chế xác định tính an toàn của phép thử lại, chẳng hạn khóa chống trùng hoặc mã yêu cầu theo hợp đồng nghiệp vụ.

## 4. Tên máy chủ là cấu hình, không phải một kết nối đã xác thực

Lệnh:

```java
SSLEngine engine = context.createSSLEngine("example.com", 443);
```

tạo engine với thông tin đối tác làm ngữ cảnh cấu hình. Nó không tự phân giải DNS, không mở TCP tới cổng 443 và không chứng minh danh tính máy chủ.

Cần tách ba khía cạnh:

- **Địa chỉ vận chuyển**: ứng dụng thực sự kết nối tới IP/socket nào.
- **Định danh mong đợi**: dịch vụ mà ứng dụng muốn xác thực, thường là tên máy chủ.
- **Chuỗi tin cậy và chính sách kiểm tra**: cách chấp nhận chứng chỉ đối tác.

Một chứng chỉ có chuỗi hợp lệ chưa tự động có nghĩa nó thuộc tên dịch vụ mong đợi. Với một client dùng quy tắc định danh HTTPS trên raw `SSLEngine`, phải cấu hình thuật toán định danh phù hợp, ví dụ `setEndpointIdentificationAlgorithm("HTTPS")`. Việc kiểm tra được tiến hành trong bắt tay theo cơ chế đã cấu hình; không suy ra nó chỉ từ `getPeerHost()`. Xem [SSLParameters](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/net/ssl/SSLParameters.html#setEndpointIdentificationAlgorithm(java.lang.String)).

Không khắc phục lỗi xác thực bằng cách dùng TrustManager chấp nhận mọi chứng chỉ hoặc bỏ kiểm tra tên máy chủ. Bộ quản lý kết nối cần chuyển lỗi xác thực thành kết quả thất bại rõ ràng, thay vì âm thầm tiếp tục.

Bảo mật kênh cũng không thay thế phân quyền. Biết đang nói chuyện với một dịch vụ hoặc chứng chỉ nào không trả lời người dùng đó được đọc bản ghi hay thực hiện nghiệp vụ nào.

## 5. Ví dụ chạy được: khởi động engine nhưng chưa có kết nối mạng

Chương trình dưới đây cấu hình client engine và yêu cầu bắt đầu bắt tay. Nó không tạo socket, không gửi dữ liệu, không nhận chứng chỉ và không hoàn tất bắt tay.

Lưu thành `EngineBoundaryDemo.java`:

```java
import javax.net.ssl.SSLContext;
import javax.net.ssl.SSLEngine;
import javax.net.ssl.SSLEngineResult.HandshakeStatus;
import javax.net.ssl.SSLParameters;

public class EngineBoundaryDemo {
    public static void main(String[] args) throws Exception {
        SSLContext context = SSLContext.getDefault();
        SSLEngine engine = context.createSSLEngine("example.com", 443);
        engine.setUseClientMode(true);

        SSLParameters parameters = engine.getSSLParameters();
        parameters.setEndpointIdentificationAlgorithm("HTTPS");
        engine.setSSLParameters(parameters);

        engine.beginHandshake();

        System.out.println("configuredHost=" + engine.getPeerHost());
        System.out.println("configuredPort=" + engine.getPeerPort());
        System.out.println("clientMode=" + engine.getUseClientMode());
        System.out.println("endpointIdentification="
                + engine.getSSLParameters()
                        .getEndpointIdentificationAlgorithm());
        System.out.println("handshakeNeedsWork="
                + (engine.getHandshakeStatus()
                        != HandshakeStatus.NOT_HANDSHAKING));
    }
}
```

Biên dịch và chạy bằng JDK 17+:

```shell
javac --release 17 -encoding UTF-8 EngineBoundaryDemo.java
java EngineBoundaryDemo
```

Hoặc chạy tệp nguồn trực tiếp:

```shell
java EngineBoundaryDemo.java
```

Kết quả với JDK tiêu chuẩn hỗ trợ TLS:

```text
configuredHost=example.com
configuredPort=443
clientMode=true
endpointIdentification=HTTPS
handshakeNeedsWork=true
```

Đọc kết quả theo đúng giới hạn:

- `configuredHost` và `configuredPort` là thông tin đã cấp cho engine, không phải địa chỉ socket đã kết nối hay danh tính đã được chứng minh.
- `endpointIdentification=HTTPS` cho biết cấu hình kiểm tra sẽ được áp dụng; chưa có chứng chỉ đối tác nào được kiểm tra trong chương trình này.
- `beginHandshake()` làm engine bước vào quy trình bắt tay; nó không tự hoàn tất việc trao đổi với đối tác.
- `handshakeNeedsWork=true` cho biết còn bước cần điều phối, không phải tín hiệu thất bại.
- Ví dụ giữ cấu hình giao thức/mật mã mặc định của runtime thay vì đưa vào danh sách giao thức lỗi thời.

Bước tiếp theo của một client thực sự là kết nối đường truyền, cấp bộ đệm, gọi `wrap()`/`unwrap()` theo trạng thái, thực thi tác vụ được giao và vận chuyển byte cho đến khi bắt tay đạt điều kiện hoàn tất. Chương trình cố ý dừng ở ranh giới cấu hình để thấy rõ engine không tự làm các bước đó.

## 6. Bộ quản lý kết nối phải làm gì với I/O không chặn?

### 6.1. Kết nối và sự kiện mạng

Với `SocketChannel`, ứng dụng mở channel, cấu hình chế độ không chặn, bắt đầu `connect()` và hoàn tất bằng `finishConnect()` khi cần. Các bước đó thuộc API mạng, không thuộc engine TLS.

Khi đọc/ghi không chặn:

- `read()` có thể trả 0 vì hiện chưa có byte để đọc.
- `read()` trả -1 báo kết thúc luồng đầu vào.
- `write()` có thể gửi ít hơn số byte đang chờ hoặc trả 0.
- Ứng dụng phải giữ bộ đệm và vị trí cho lần tiếp theo.

Xem [SocketChannel](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/SocketChannel.html). Sự kiện “có thể ghi” không chứng minh mọi byte sẽ được gửi trong một lần; sự kiện “có thể đọc” cũng không bảo đảm nhận đủ một bản ghi TLS hoặc một thông điệp ứng dụng.

### 6.2. Bốn bộ đệm, hai hướng dữ liệu

Một quy ước thường gặp:

```text
appOut -> wrap() -> netOut -> socket.write()
socket.read() -> netIn -> unwrap() -> appIn
```

Bộ quản lý kết nối phải biết mỗi bộ đệm đang ở chế độ đọc hay ghi, byte nào đã được tiêu thụ, byte nào còn chờ và ai được phép sửa nó.

`BUFFER_UNDERFLOW` yêu cầu giải quyết thiếu dữ liệu đầu vào; `BUFFER_OVERFLOW` yêu cầu giải quyết thiếu chỗ ở đầu ra. Engine báo điều kiện, còn ứng dụng quyết định đọc thêm, giải phóng chỗ, tăng bộ đệm hoặc dừng vì vượt ngân sách.

Không giả định một lần `unwrap()` sinh đúng một thông điệp HTTP/RPC. TLS bảo vệ luồng byte ứng dụng; phần đóng khung và phân tích thông điệp thuộc giao thức ứng dụng. Một thông điệp có thể trải qua nhiều bản ghi TLS, và một phần byte được giải mã cũng có thể chứa nhiều thông điệp.

### 6.3. Điều tiết và tài nguyên

Nếu bên xử lý ứng dụng tiêu thụ chậm, `appIn` hoặc hàng đợi dữ liệu giải mã có thể tăng. Nếu mạng gửi chậm, `netOut` có thể tồn đọng. Cần giới hạn hàng đợi và tạm ngừng tiếp nhận thêm khi phù hợp.

Không dùng việc tăng bộ đệm liên tục để thay cho cơ chế điều tiết. Không bật quan tâm ghi thường trực khi không có byte chờ gửi, vì một socket sẵn sàng ghi có thể làm vòng lặp thức liên tục.

## 7. Engine yêu cầu công việc, ứng dụng quyết định lịch chạy

Khi engine báo `NEED_TASK`, ứng dụng phải lấy các tác vụ bằng `getDelegatedTask()`, chạy chúng và tiếp tục khi đã có kết quả.

Engine không tự chọn nhóm luồng có bao nhiêu luồng, hàng đợi dài bao nhiêu hay xử lý quá tải thế nào. Đó là trách nhiệm điều phối.

Một thiết kế đơn giản:

```text
Một luồng sở hữu engine và bộ đệm của kết nối
    ↓ NEED_TASK
Giao đợt tác vụ sang executor có giới hạn
    ↓
Khi hoàn tất: gửi thông báo về vòng lặp và đánh thức nó
    ↓
Luồng sở hữu đọc trạng thái mới, tiếp tục TLS
```

Không chờ `Future.get()` trên luồng sự kiện dùng chung. Không để callback cũ tiếp tục một kết nối đã hết hạn hoặc đối tượng đã được tái sử dụng. Cần có định danh kết nối/đợt công việc và quy tắc xử lý lỗi rõ ràng.

Thiết kế “một luồng sở hữu” giúp tuần tự hóa phần quản lý. Nó không hàm ý rằng tất cả cấu trúc nội bộ của provider do ứng dụng trực tiếp quản lý; ranh giới vẫn là API engine và các tác vụ được engine trả ra.

## 8. Timeout và đóng kết nối cần phối hợp hai tầng

### 8.1. Nhiều loại timeout có ý nghĩa khác nhau

Ứng dụng có thể cần giới hạn thời gian cho DNS, kết nối TCP, bắt tay TLS, chờ phản hồi ứng dụng, khoảng im lặng và đóng có trật tự. Chúng không nên bị nhập thành một biến duy nhất mà không xác định rõ phạm vi.

Engine không tự bảo đảm rằng một đối tác im lặng sẽ bị loại sau đúng deadline nghiệp vụ. Bộ quản lý kết nối phải kiểm tra thời gian, hủy quan tâm I/O, giải phóng tài nguyên và báo kết quả cho nơi gọi.

Heartbeat, giữ kết nối trong pool và quyết định khi nào một kết nối không còn dùng được cũng nằm ở tầng quản lý/giao thức ứng dụng.

### 8.2. closeOutbound() chưa phải socket.close()

Đóng TLS có thông điệp giao thức riêng. Thông thường, phía chủ động đóng cần:

1. Yêu cầu engine đóng hướng gửi.
2. Tiếp tục điều phối engine để lấy dữ liệu đóng nếu có.
3. Gửi hết dữ liệu TLS đang chờ theo chính sách đóng.
4. Xử lý hướng nhận và tín hiệu đóng/EOF phù hợp.
5. Đóng transport và giải phóng tài nguyên khi hoàn tất hoặc hết deadline.

Một kết quả engine báo đóng không có nghĩa bộ đệm mạng đã được gửi hết. Ngược lại, TCP EOF không tự chứng minh đã nhận đầy đủ trình tự đóng TLS. Nếu phải báo kết thúc đầu vào cho engine, `closeInbound()` có thể phát hiện thiếu thông báo đóng; không nuốt mọi ngoại lệ rồi gọi đó là “đóng bình thường”.

Nếu đối tác không hợp tác, ứng dụng cần deadline đóng hữu hạn. Nếu tác vụ nền vẫn đang chạy, tuần tự hóa việc kết thúc engine và xử lý thông báo đến muộn. Engine đã đóng không được tái sử dụng cho kết nối mới.

## 9. Ranh giới này ảnh hưởng thiết kế và kiểm thử thế nào?

Có thể tổ chức phần tích hợp thành ba khối:

| Khối | Đầu vào/đầu ra chính | Câu hỏi nó phải trả lời |
| --- | --- | --- |
| Điều phối TLS | ByteBuffer, SSLEngineResult, tác vụ hoàn thành | Cần bước engine nào tiếp theo? |
| Quản lý kết nối | Sự kiện mạng, hàng đợi, deadline | Khi nào có thể đọc/ghi, giữ bao nhiêu byte, lúc nào đóng? |
| Giao thức ứng dụng | Byte đã giải mã, thông điệp, phản hồi | Đó là yêu cầu gì và đã xử lý thành công chưa? |

Không cần biến mọi hàng thành một lớp nếu ứng dụng nhỏ. Điều quan trọng là trạng thái và trách nhiệm không bị trộn đến mức không thể xác định ai sở hữu byte hoặc ai được đóng kết nối.

Kiểm thử nên đi theo các ranh giới:

- **Trong bộ nhớ**: ghép hai engine với bộ đệm trung gian để kiểm tra bắt tay và dữ liệu; vẫn dùng cấu hình chứng chỉ/tin cậy hợp lệ.
- **Vận chuyển**: ép đọc/ghi từng phần, trả 0, EOF giữa bản ghi, giới hạn bộ đệm và thời gian chờ.
- **Điều phối**: tác vụ chậm, executor từ chối, callback đến sau khi đóng.
- **Giao thức ứng dụng**: thông điệp bị chia/gộp qua nhiều lần giải mã, phản hồi lỗi, thử lại không gây xử lý trùng.

Các câu hỏi tự kiểm tra:

1. `wrap()` đã tiêu thụ hết dữ liệu nhưng `netOut` chưa gửi xong: dữ liệu còn thuộc trách nhiệm của ai? **Bộ quản lý kết nối phải giữ và gửi tiếp.**
2. Tạo engine với tên máy chủ và cổng đã chứng minh máy chủ thật chưa? **Chưa; đó là ngữ cảnh cấu hình, còn phải kết nối và hoàn tất xác thực.**
3. TLS bắt tay xong có nghĩa yêu cầu nghiệp vụ thành công chưa? **Chưa; cần kết quả của giao thức ứng dụng.**
4. Có cần tự viết SSLEngine để dùng HTTPS trong ứng dụng thông thường không? **Không bắt buộc; thành phần HTTP/TLS cấp cao có thể sở hữu toàn bộ phần tích hợp này. Tự dùng engine phù hợp khi cần kiểm soát cơ chế vận chuyển hoặc tích hợp ở tầng thấp.**
