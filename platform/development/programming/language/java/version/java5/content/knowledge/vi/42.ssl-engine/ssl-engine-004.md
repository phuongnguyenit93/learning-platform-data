# wrap, unwrap và SSLEngineResult

## 1. SSLEngine xử lý byte, ứng dụng vận chuyển byte

SSLEngine cung cấp máy trạng thái TLS độc lập với cơ chế truyền tải. Nó không tự mở socket, đọc mạng hoặc ghi mạng cho ứng dụng.

Hai chiều chính:

```text
Byte ứng dụng cần gửi
          ↓ wrap
Byte giao thức TLS cần chuyển cho đối tác
          ↓ ứng dụng tự ghi ra transport

Byte giao thức nhận từ đối tác
          ↓ ứng dụng tự đọc từ transport
          ↓ unwrap
Byte ứng dụng đã nhận
```

Ở giai đoạn truyền dữ liệu, wrap bảo vệ dữ liệu ứng dụng thành các bản ghi TLS; unwrap xử lý dữ liệu giao thức đến và có thể tạo byte ứng dụng.

Nhưng không phải mọi byte TLS đều là dữ liệu ứng dụng đã mã hóa. Trong quá trình bắt tay hoặc đóng, engine còn tạo/nhận các bản tin điều khiển. Vì vậy không thể suy luận một lần wrap luôn tiêu thụ dữ liệu ứng dụng hoặc một lần unwrap luôn tạo dữ liệu ứng dụng.

Bài dùng API SSLEngine vẫn phù hợp trong Java hiện đại, minh họa bằng TLS 1.3 trên Java 17 trở lên. Tên lớp có SSL không phải lý do để bật các phiên bản giao thức cũ.

## 2. Hai cặp bộ đệm có vai trò khác nhau

Có thể đặt tên bốn bộ đệm theo mục đích:

| Bộ đệm | Nội dung | Vai trò với engine |
| --- | --- | --- |
| appOut | Byte ứng dụng muốn gửi | Nguồn của wrap |
| netOut | Byte TLS engine đã tạo | Đích của wrap; sau đó được transport gửi |
| netIn | Byte TLS nhận từ transport | Nguồn của unwrap |
| appIn | Byte ứng dụng engine đã tạo | Đích của unwrap; sau đó được ứng dụng đọc |

Các lời gọi cơ bản:

```java
SSLEngineResult outbound = engine.wrap(appOut, netOut);
SSLEngineResult inbound = engine.unwrap(netIn, appIn);
```

Đây là hai thao tác minh họa với engine và bộ đệm đã được chuẩn bị; không phải một chương trình TLS hoàn chỉnh.

Nguồn phải ở chế độ đọc phần byte hợp lệ; đích phải có không gian ghi trong khoảng position đến limit. Engine cập nhật position theo phần nó đã sử dụng hoặc tạo ra.

Không dùng cùng một vùng lưu trữ cho nguồn và đích theo cách vi phạm hợp đồng của API. Cũng không cho một tác vụ transport và một lời gọi engine đồng thời sửa position của cùng bộ đệm mà không có quyền sở hữu rõ ràng.

## 3. SSLEngineResult có bốn thông tin cần đọc cùng nhau

Mỗi wrap/unwrap trả một kết quả gồm:

| Thành phần | Câu hỏi được trả lời |
| --- | --- |
| getStatus() | Thao tác vừa rồi có đủ điều kiện bộ đệm, đã đóng hay hoàn tất bình thường? |
| getHandshakeStatus() | Máy trạng thái bắt tay cần bước gì tiếp theo? |
| bytesConsumed() | Bao nhiêu byte nguồn đã được tiêu thụ trong lời gọi này? |
| bytesProduced() | Bao nhiêu byte đã được ghi vào đích trong lời gọi này? |

Bốn giá trị mô tả lời gọi vừa thực hiện, không phải tổng byte cả kết nối.

Với wrap:

- Consumed là byte từ appOut.
- Produced là byte TLS vào netOut.

Với unwrap:

- Consumed là byte TLS từ netIn.
- Produced là byte ứng dụng vào appIn.

Chúng không phải số byte mà socket thực sự đã gửi/nhận. Wrap có thể tạo ra 100 byte, nhưng transport mới ghi được một phần. Phần còn lại vẫn phải được giữ để gửi tiếp.

Đừng tự cộng position thêm lần nữa theo bytesConsumed/bytesProduced nếu engine đã cập nhật bộ đệm. Các bộ đếm dùng để quan sát và điều phối, không phải lệnh yêu cầu ứng dụng lặp lại cùng phép dịch position.

## 4. Status: kết quả thao tác trên bộ đệm

### OK

Thao tác hoàn tất theo điều kiện hiện tại. Điều đó không chứng minh bắt tay xong, cũng không chứng minh toàn bộ bản tin ứng dụng đã được tiêu thụ.

Có thể gặp:

```text
Status = OK
HandshakeStatus = NEED_UNWRAP
bytesConsumed = 0
bytesProduced > 0
```

Đây là tình huống engine đã tạo bản tin bắt tay và đang cần dữ liệu phản hồi, không phải một mâu thuẫn.

### BUFFER_OVERFLOW

Không đủ không gian đích để engine tạo kết quả cần thiết.

Đối với wrap, xem netOut. Đối với unwrap, xem appIn.

Có hai nguyên nhân khác nhau cần phân biệt:

- Đích còn dữ liệu chưa được bên nhận tiêu thụ nên remaining nhỏ.
- Sức chứa đích thực sự nhỏ hơn mức cần thiết.

Nếu netOut còn dữ liệu đang chờ gửi, có thể cần gửi tiếp trước khi dùng lại vùng trống. Nếu appIn còn dữ liệu chưa được ứng dụng đọc, cần chuyển phần đó cho ứng dụng hoặc bảo toàn khi điều chỉnh bộ đệm.

Không giải quyết mọi overflow bằng cách clear bộ đệm; việc đó có thể làm mất byte chưa gửi hoặc chưa xử lý.

### BUFFER_UNDERFLOW

Unwrap chưa có đủ byte nguồn để xử lý một gói/bản ghi đầy đủ theo giao thức.

Thông thường cần giữ phần netIn chưa được tiêu thụ rồi nhận thêm dữ liệu. Nó không tự có nghĩa đối tác gửi dữ liệu sai.

Còn phải kiểm tra sức chứa netIn. Nếu một bản ghi cần lớn hơn toàn bộ bộ đệm hiện tại, chỉ đợi thêm mà không có chỗ ghi sẽ không tiến triển; cần điều chỉnh kích thước theo thông tin session và giới hạn của ứng dụng.

Underflow không phải trạng thái dùng để báo appOut không có dữ liệu cho wrap. Wrap có thể vẫn tạo bản tin bắt tay từ một nguồn ứng dụng rỗng.

### CLOSED

Lời gọi vừa đóng chiều tương ứng hoặc không thực hiện được vì chiều đó đã đóng.

Vẫn phải xem số byte được tạo/tiêu thụ và phần dữ liệu còn chờ. Ví dụ một lần wrap phục vụ đóng có thể tạo bản tin cuối cần được gửi. Không bỏ toàn bộ netOut chỉ vì status là CLOSED.

CLOSED của một thao tác không tự chứng minh cả hai chiều TLS và transport đều đã hoàn tất vòng đời.

## 5. HandshakeStatus: bước tiếp theo của máy trạng thái

| Trạng thái | Hướng xử lý |
| --- | --- |
| NEED_WRAP | Cần gọi wrap để tạo dữ liệu giao thức gửi đi |
| NEED_UNWRAP | Cần xử lý dữ liệu đến; có thể phải nhận thêm từ transport |
| NEED_TASK | Cần thực hiện các tác vụ được engine ủy nhiệm |
| FINISHED | Lời gọi wrap/unwrap này vừa hoàn tất bắt tay |
| NOT_HANDSHAKING | Hiện không trong quá trình bắt tay |
| NEED_UNWRAP_AGAIN | Trạng thái dành cho DTLS: cần unwrap tiếp dữ liệu đã nhận, không đợi nhận lại |

Ví dụ TLS trong bài không dùng DTLS, nhưng enum hiện hành có NEED_UNWRAP_AGAIN; không hiểu nó thành một yêu cầu đọc mạng mới trong một bộ điều phối hỗ trợ DTLS.

Một chi tiết quan trọng: FINISHED được trả trong SSLEngineResult của wrap/unwrap hoàn tất bắt tay. SSLEngine.getHandshakeStatus() không trả FINISHED.

Vì vậy nếu chỉ kiểm tra:

```java
engine.getHandshakeStatus() == FINISHED
```

thì không phải cách nhận biết đúng sự kiện hoàn tất này. Đoạn trên là minh họa ý tưởng sai; khi viết Java còn cần định danh enum hoặc import tương ứng.

NOT_HANDSHAKING cũng không phải cờ độc lập chứng minh kết nối đã xác thực và sẵn sàng dùng. Nó có thể xuất hiện ở các trạng thái khác của vòng đời; ứng dụng cần theo dõi quá trình bắt đầu/hoàn tất và lỗi của chính kết nối.

Luôn xét Status và HandshakeStatus cùng nhau. Một cái mô tả kết quả thao tác; cái kia điều khiển bước giao thức tiếp theo.

## 6. NEED_TASK không phải tín hiệu để quay lại wrap liên tục

Engine có thể cần các tác vụ như xử lý thông tin xác thực trước khi đi tiếp. Lấy tác vụ bằng getDelegatedTask:

```java
Runnable task;
while ((task = engine.getDelegatedTask()) != null) {
    task.run();
}
```

Đây là đoạn minh họa chạy đồng bộ cho mô hình đơn giản, không phải lời khuyên chạy mọi tác vụ như vậy trên vòng lặp I/O không chặn.

Nếu chuyển các tác vụ sang bộ thực thi khác, phải đợi hoặc nhận thông báo chúng đã hoàn tất theo mô hình điều phối trước khi tiếp tục những bước phụ thuộc. Không chỉ nộp tác vụ rồi lập tức gọi wrap/unwrap như thể kết quả đã có.

Các tác vụ có thể tốn thời gian. Thiết kế thực tế cần bảo toàn vòng đời kết nối và quyền truy cập engine/bộ đệm, đồng thời tránh chặn luồng điều phối quá lâu.

Sau khi hoàn tất tác vụ, kiểm tra lại trạng thái của engine; không mặc định bước kế tiếp luôn là wrap.

## 7. Chế độ ByteBuffer quyết định byte nào được nhìn thấy

Mẫu thu nhận dữ liệu đến thường có dạng:

```java
// netIn đang ở chế độ ghi sau khi transport đã thêm byte.
// appIn có chỗ ghi.
netIn.flip();
SSLEngineResult result = engine.unwrap(netIn, appIn);
netIn.compact();
```

Đây là mảnh cơ chế bộ đệm, chưa có xử lý đầy đủ mọi status và ngoại lệ.

Flip đặt phạm vi đọc về phần byte đã nhận. Sau unwrap, compact giữ byte chưa được tiêu thụ và chuẩn bị chỗ để nhận thêm.

Nếu thay compact bằng clear trong đường underflow, bạn có thể vứt phần đầu của một bản ghi chưa đủ. Lần nhận sau chỉ có phần đuôi nên engine không thể tái lập bản ghi gốc.

Ở chiều gửi:

```text
netOut ở chế độ ghi
    → wrap tạo byte TLS
    → flip để transport đọc
    → ghi một phần hoặc toàn bộ
    → giữ byte còn lại cho lần ghi tiếp
```

Khi SocketChannel không chặn trả số byte ghi bằng không, không quay vòng liên tục với cùng dữ liệu. Cần chờ khả năng ghi theo cơ chế I/O của ứng dụng.

Nếu appIn đã tạo byte ứng dụng, cũng phải flip để ứng dụng đọc và compact/điều chỉnh sau khi tiêu thụ. Giao thức ứng dụng có ranh giới bản tin riêng; một lần unwrap không nhất thiết tương ứng một thông điệp nghiệp vụ hoàn chỉnh.

## 8. Kích thước bộ đệm nên dựa vào SSLSession

Hai thông tin hữu ích:

```java
int packetSize = engine.getSession().getPacketBufferSize();
int applicationSize = engine.getSession().getApplicationBufferSize();
```

- Packet size phục vụ việc chứa dữ liệu giao thức.
- Application size phục vụ vùng dữ liệu ứng dụng mà engine có thể cần tạo.

Không ghi cứng một kích thước suy ra từ một lần chạy rồi mặc định mọi phiên và provider giống nhau. Thông tin session và khả năng thương lượng có thể làm yêu cầu thực tế thay đổi; khi xử lý trạng thái thiếu chỗ, xem lại kích thước hiện hành.

Khi tăng bộ đệm, phải bảo toàn dữ liệu chưa xử lý và giữ đúng chế độ đọc/ghi. Đồng thời đặt giới hạn tài nguyên thích hợp; không tăng không giới hạn nếu có lỗi điều phối khiến bộ đệm cứ lớn mãi.

Một bộ đệm có capacity lớn vẫn có thể overflow nếu remaining nhỏ do position/limit hoặc dữ liệu cũ. Kiểm tra cả chế độ và phần trống trước khi kết luận cần cấp phát lớn hơn.

## 9. Thí nghiệm Java chạy được, không mở kết nối mạng

Chương trình tạo engine phía client TLS 1.3, yêu cầu bước bắt tay đầu tiên rồi quan sát các kết quả.

Nó không tạo server, không hoàn tất bắt tay và không truyền dữ liệu ứng dụng cho một đối tác. Vì vậy không cần tạo chứng chỉ hoặc tắt cơ chế kiểm tra chứng chỉ để chạy ví dụ.

Lưu thành `EngineResultDemo.java`:

```java
import java.nio.ByteBuffer;
import javax.net.ssl.SSLContext;
import javax.net.ssl.SSLEngine;
import javax.net.ssl.SSLEngineResult;
import javax.net.ssl.SSLParameters;

public class EngineResultDemo {
    public static void main(String[] args) throws Exception {
        SSLContext context = SSLContext.getInstance("TLSv1.3");
        context.init(null, null, null);

        SSLEngine engine = context.createSSLEngine("example.invalid", 443);
        engine.setUseClientMode(true);
        SSLParameters parameters = engine.getSSLParameters();
        parameters.setEndpointIdentificationAlgorithm("HTTPS");
        engine.setSSLParameters(parameters);
        engine.beginHandshake();

        try {
            ByteBuffer emptyApplication = ByteBuffer.allocate(0);
            ByteBuffer tooSmallNetwork = ByteBuffer.allocate(0);

            SSLEngineResult small = engine.wrap(
                    emptyApplication, tooSmallNetwork);
            System.out.println("smallWrap=" + small.getStatus());

            ByteBuffer networkOutput = ByteBuffer.allocate(
                    engine.getSession().getPacketBufferSize());
            int before = networkOutput.position();

            SSLEngineResult wrapped = engine.wrap(
                    emptyApplication, networkOutput);

            System.out.println("wrap=" + wrapped.getStatus());
            System.out.println("handshake=" + wrapped.getHandshakeStatus());
            System.out.println("applicationConsumed=" + wrapped.bytesConsumed());
            System.out.println("networkProduced="
                    + (wrapped.bytesProduced() > 0));
            System.out.println("positionMatches="
                    + (networkOutput.position() - before
                        == wrapped.bytesProduced()));

            ByteBuffer emptyNetwork = ByteBuffer.allocate(0);
            ByteBuffer applicationInput = ByteBuffer.allocate(
                    engine.getSession().getApplicationBufferSize());

            SSLEngineResult unwrapped = engine.unwrap(
                    emptyNetwork, applicationInput);
            System.out.println("emptyUnwrap=" + unwrapped.getStatus());
            System.out.println("emptyConsumed=" + unwrapped.bytesConsumed());
            System.out.println("emptyProduced=" + unwrapped.bytesProduced());
        } finally {
            engine.closeOutbound();
        }
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```shell
javac --release 17 EngineResultDemo.java
java EngineResultDemo
```

Stdout đã kiểm chứng với provider TLS dựng sẵn của JDK 17:

```text
smallWrap=BUFFER_OVERFLOW
wrap=OK
handshake=NEED_UNWRAP
applicationConsumed=0
networkProduced=true
positionMatches=true
emptyUnwrap=BUFFER_UNDERFLOW
emptyConsumed=0
emptyProduced=0
```

### Đọc đúng kết quả

1. Đích mạng có sức chứa bằng 0 gây overflow ở lần thử đầu.
2. Sau khi cấp vùng packet phù hợp, engine tạo dữ liệu bắt tay mà không tiêu thụ byte ứng dụng.
3. Status OK đi cùng NEED_UNWRAP: thao tác vừa rồi thành công nhưng bắt tay vẫn cần đối tác.
4. bytesProduced khớp mức tăng position của bộ đệm đích trong lời gọi đó.
5. Unwrap một nguồn mạng rỗng chưa đủ dữ liệu, nên trả underflow.

Số byte ClientHello có thể thay đổi theo JDK, provider và cấu hình; chương trình chỉ in việc có tạo byte thay vì gắn expected vào một kích thước cụ thể.

createSSLEngine với tên và cổng là cung cấp ngữ cảnh cho engine, không mở TCP. Tên example.invalid trong thí nghiệm không được tra cứu hay kết nối bởi mã này.

CloseOutbound ở cuối chỉ kết thúc thí nghiệm cục bộ chưa có transport. Nó không phải mẫu hoàn tất đóng TLS cho một kết nối thực đang hoạt động.

## 10. Từ một kết quả đến bước điều phối tiếp theo

Một bộ điều phối cần quản lý đồng thời:

- Dữ liệu TLS đã tạo nhưng transport chưa gửi hết.
- Dữ liệu TLS nhận chưa đủ hoặc chưa được engine tiêu thụ hết.
- Dữ liệu ứng dụng đã tạo nhưng ứng dụng chưa xử lý.
- Trạng thái bắt tay, tác vụ được ủy nhiệm và trạng thái đóng.
- Khả năng đọc/ghi của transport.

Một cách suy nghĩ theo mỗi lần gọi:

1. Ghi nhận kết quả và phần bộ đệm đã thay đổi.
2. Bảo toàn những byte cần gửi hoặc giao cho ứng dụng.
3. Xử lý điều kiện thiếu đầu vào/thiếu chỗ/đóng.
4. Xét yêu cầu giao thức tiếp theo.
5. Nếu không còn bước có thể tiến hành ngay, trả quyền điều khiển và chờ sự kiện phù hợp.

Đừng chỉ viết vòng lặp “status OK thì gọi lại” hoặc “còn appOut thì wrap mãi”. Engine có thể đang cần dữ liệu từ phía bên kia hoặc chờ một tác vụ.

Một lần không tiêu thụ và không tạo byte chưa chắc là lỗi; nhưng lặp mãi với cùng trạng thái, cùng dữ liệu và cùng không gian trống sẽ quay CPU mà không tạo tiến triển. Cần phân biệt “có bước giao thức tiếp theo” với “phải chờ điều kiện mới”.

Không coi hai bộ đếm bằng không là điều kiện dừng tuyệt đối trong mọi tình huống; trước hết xem trạng thái bắt tay có yêu cầu task hoặc một bước khác hay không.

## 11. Đóng và lỗi vẫn đi qua wrap/unwrap

Trên kết nối TLS thật, closeOutbound bắt đầu đóng chiều gửi theo giao thức. Engine có thể cần wrap để tạo các bản tin đóng, và ứng dụng phải gửi phần netOut đó trước khi đóng transport theo chính sách.

Ở chiều nhận, unwrap có thể xử lý bản tin đóng từ đối tác và cho biết CLOSED. Điều đó khác với việc transport đột ngột kết thúc mà chưa có thông báo đóng TLS phù hợp.

CloseInbound khi chưa nhận được kết thúc hợp lệ có thể báo SSLException để ứng dụng nhận biết việc kết thúc không trọn vẹn. Không bắt rồi bỏ qua mọi lỗi này như một thao tác đóng bình thường.

Wrap/unwrap còn có thể ném SSLException, chẳng hạn lỗi bắt tay hoặc dữ liệu giao thức không hợp lệ. Các status bộ đệm không phải hệ thống báo mọi loại lỗi. Không diễn giải BUFFER_UNDERFLOW thành lỗi chứng chỉ, và không diễn giải SSLException thành yêu cầu “chỉ cấp thêm bộ nhớ rồi thử lại”.

Một kết nối đã lỗi cần chính sách kết thúc phù hợp. Việc giảm mức kiểm tra đối tác hoặc dùng bộ quản lý tin cậy chấp nhận mọi chứng chỉ không phải cách sửa một vòng điều phối sai.

## 12. Những nhầm lẫn cần tránh

| Nhầm lẫn | Cách hiểu đúng |
| --- | --- |
| wrap luôn tiêu thụ plaintext | Có thể chỉ tạo bản tin bắt tay/điều khiển |
| unwrap luôn tạo dữ liệu ứng dụng | Có thể chỉ làm tiến triển giao thức |
| OK nghĩa là bắt tay xong | Phải đọc HandshakeStatus và vòng đời kết nối |
| Produced nghĩa là đã gửi lên mạng | Đó chỉ là byte đã ghi vào bộ đệm đích |
| Underflow nghĩa là dữ liệu sai | Thường là nguồn chưa đủ; phải giữ byte chưa dùng |
| Overflow luôn cần cấp bộ nhớ lớn hơn | Có thể chỉ do đích còn dữ liệu/chế độ sai |
| CLOSED nghĩa là bỏ được mọi byte còn lại | Có thể còn dữ liệu cuối phải xử lý/gửi |
| Đợi FINISHED từ engine.getHandshakeStatus | FINISHED chỉ xuất hiện trong kết quả wrap/unwrap hoàn tất bắt tay |

Một kiểm thử tốt nên có nguồn bị chia nhỏ, transport ghi từng phần, đích thiếu chỗ, tác vụ bắt tay, dữ liệu ứng dụng nhiều bản ghi và đóng hai chiều. Các kiểm thử đó cần đối tác TLS có cấu hình chứng chỉ phù hợp; thí nghiệm nhỏ trong bài chỉ chứng minh những lời gọi đầu tiên và cách đọc kết quả.

## 13. Tự kiểm tra

1. bytesConsumed của wrap là byte mạng hay byte ứng dụng?
2. wrap có thể trả OK, NEED_UNWRAP và consumed bằng không không?
3. Khi unwrap underflow, có nên clear toàn netIn không?
4. Đích có capacity lớn nhưng remaining nhỏ có thể overflow không?
5. FINISHED có được trả bởi engine.getHandshakeStatus không?
6. Một lần unwrap có tạo đúng một bản tin nghiệp vụ không?
7. Có cần gửi byte đã tạo ở một lần wrap phục vụ đóng không?

Đáp án:

1. Byte ứng dụng từ nguồn.
2. Có; đó có thể là bước bắt tay.
3. Không; phải giữ phần chưa dùng và nhận thêm theo điều kiện.
4. Có.
5. Không.
6. Không có bảo đảm như vậy.
7. Có, theo giao thức và chính sách đóng kết nối.

Đọc SSLEngineResult như một quyết định điều phối gồm trạng thái thao tác, trạng thái giao thức và hai số byte. Sau đó chuyển quyền cho đúng thành phần: engine, transport, tác vụ được ủy nhiệm hoặc ứng dụng nhận dữ liệu.

## Tài liệu đối chiếu

- [SSLEngine — Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/javax/net/ssl/SSLEngine.html): wrap/unwrap, bộ đệm và vòng đời.
- [SSLEngineResult — Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/javax/net/ssl/SSLEngineResult.html): trạng thái và số byte.
- [Status](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/javax/net/ssl/SSLEngineResult.Status.html), [HandshakeStatus](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/javax/net/ssl/SSLEngineResult.HandshakeStatus.html): ý nghĩa từng kết quả điều phối.
