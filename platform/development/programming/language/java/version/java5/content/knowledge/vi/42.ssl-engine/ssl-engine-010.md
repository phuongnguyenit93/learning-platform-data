# Đóng chiều gửi, chiều nhận và kết thúc phiên với SSLEngine

## 1. Vì sao đóng TLS cần nhiều hơn đóng socket?

Một kết nối có hai hướng độc lập: dữ liệu từ ứng dụng cục bộ đi ra đối tác và dữ liệu từ đối tác đi vào ứng dụng. `SSLEngine` xử lý TLS trong bộ nhớ; ứng dụng chịu trách nhiệm vận chuyển byte. Khi kết thúc, cần phối hợp trạng thái TLS, dữ liệu còn trong bộ đệm và việc đóng tài nguyên mạng.

Hãy phân biệt bốn việc:

| Việc cần thực hiện | Ý nghĩa |
| --- | --- |
| Ngừng gửi dữ liệu nghiệp vụ | Ứng dụng không nhận thêm thông điệp cần gửi trên kết nối này |
| Đóng chiều gửi TLS | Yêu cầu engine kết thúc hướng ra, tạo dữ liệu đóng cần gửi cho đối tác |
| Kết thúc chiều nhận TLS | Xử lý thông báo đóng của đối tác hoặc ghi nhận luồng nhận đã kết thúc bất thường |
| Giải phóng kết nối | Đóng kênh, hủy đăng ký sự kiện và trả các bộ đệm sau khi hoàn thành nghĩa vụ đóng hoặc hết thời hạn |

`close_notify` là thông báo đóng của TLS. Nó giúp phân biệt kết thúc do đối tác thông báo với việc đường truyền đột ngột biến mất. Đóng socket ngay sau `closeOutbound()` có thể làm mất thông báo này. Xem [API SSLEngine](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/javax/net/ssl/SSLEngine.html).

Tên module Java 5 chỉ phản ánh thời điểm xuất hiện API. Bài này sử dụng cách tiếp cận vẫn áp dụng với JDK hiện đại, tập trung TLS trên TCP và không yêu cầu bật giao thức bảo mật cũ.

## 2. Đóng chiều gửi: yêu cầu, tạo byte, rồi vận chuyển

`engine.closeOutbound()` báo rằng ứng dụng không tiếp tục gửi dữ liệu ứng dụng qua engine. Đây là yêu cầu chuyển trạng thái, không phải thao tác ghi mạng. Sau đó vẫn cần gọi `wrap()` để lấy dữ liệu đóng mà engine cần phát.

Một trình tự đóng bình thường do ứng dụng khởi xướng có thể được tổ chức như sau:

1. Ngừng nhận thêm công việc gửi trên kết nối.
2. Quyết định xử lý dữ liệu nghiệp vụ đang đợi theo hợp đồng ứng dụng. Nếu hứa gửi hết, phải tiếp tục mã hóa chúng trước khi yêu cầu đóng chiều gửi.
3. Gọi `closeOutbound()` khi không còn dữ liệu nghiệp vụ phải chuyển qua engine.
4. Tiếp tục điều khiển engine để tạo các byte đóng, thường bằng `wrap()` với nguồn rỗng.
5. Đưa toàn bộ byte đã tạo vào hàng đợi gửi theo đúng thứ tự, sau dữ liệu đã mã hóa trước đó.
6. Tiếp tục xả hàng đợi qua kênh mạng, bảo toàn phần chưa ghi được.

Không đưa thêm thông điệp nghiệp vụ vào bộ đệm nguồn sau bước 3 rồi trông chờ engine gửi chúng. Nếu ứng dụng chọn hủy phần việc đang đợi khi dừng kết nối, cần trả lỗi hoặc trạng thái hủy tương ứng cho bên gọi; không báo rằng chúng đã được gửi.

### Đoạn gọi tạo dữ liệu đóng

```java
engine.closeOutbound();

// netOut phải ở chế độ ghi và có chỗ trống.
// Không được xóa byte của lần trước còn chưa gửi.
SSLEngineResult result = engine.wrap(ByteBuffer.allocate(0), netOut);

// Đọc Status, HandshakeStatus và giữ lại mọi byte được tạo ra.
// Chỉ giải phóng netOut khi lớp vận chuyển không còn cần nó.
```

Đây là đoạn minh họa trong một kết nối đã khởi tạo và được quản lý bởi vòng lặp I/O, không phải chương trình độc lập. Một lần gọi chưa được giả định là toàn bộ quá trình đóng. Nếu engine còn công việc cần làm, tiếp tục theo kết quả và trạng thái hiện tại; nếu kênh chưa ghi được, nhường quyền chờ sự kiện thay vì quay vòng.

## 3. isOutboundDone không có nghĩa hàng đợi mạng đã hết

`isOutboundDone()` cho biết engine sẽ không tạo thêm dữ liệu mạng ở chiều gửi. Nó không nhìn thấy hàng đợi byte của ứng dụng và cũng không biết socket đã gửi được bao nhiêu byte. Tương tự, kết quả `wrap()` có `Status.CLOSED` vẫn phải được kiểm tra số byte tạo ra; không bỏ bộ đệm chỉ vì gặp trạng thái đóng. [API giải thích trạng thái chiều gửi](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/javax/net/ssl/SSLEngine.html#isOutboundDone()).

Tình huống tự thiết kế: engine tạo một bản ghi cuối và báo đóng chiều gửi. Ứng dụng ghi được 20 byte, còn 10 byte trong hàng đợi. Điều kiện `isOutboundDone() == true` có thể đã đúng, nhưng việc gọi `channel.close()` lúc này vẫn có thể làm mất 10 byte cuối.

Trong thiết kế có một chủ sở hữu kết nối, hãy theo dõi ít nhất:

```text
Đã ngừng nhận thêm dữ liệu ứng dụng?
Còn dữ liệu ứng dụng đã nhận trách nhiệm gửi?
Engine còn có thể tạo byte chiều gửi?
Còn byte đã mã hóa chưa chuyển hết cho lớp vận chuyển?
Chiều nhận đã kết thúc theo chính sách đóng?
Đã hết thời hạn đóng hay xảy ra lỗi buộc hủy?
```

Hàng đợi gửi hết nghĩa là ứng dụng đã chuyển hết byte cho lớp vận chuyển theo mô hình I/O đang dùng. Nó không chứng minh ứng dụng bên kia đã đọc, xử lý hay ghi dữ liệu vào nơi lưu trữ bền vững. Nếu nghiệp vụ cần xác nhận như vậy, phải có phản hồi ở giao thức ứng dụng.

## 4. Đóng chiều nhận: ưu tiên xử lý thông báo của đối tác

Thông báo đóng từ đối tác đi qua cùng đường nhận như các bản ghi TLS khác: đọc vào bộ đệm mạng rồi gọi `unwrap()`. Khi engine đã xử lý thông báo đóng hợp lệ, có thể quan sát `Status.CLOSED` của thao tác nhận hoặc `isInboundDone()`.

`closeInbound()` có ý nghĩa thông báo rằng sẽ không còn dữ liệu mạng đi vào engine. Nó không phải lệnh gửi thông báo đóng cho đối tác và không thay cho `unwrap()` dữ liệu đã nhận. Nếu tự gọi nó quá sớm, ứng dụng có thể bỏ mất dữ liệu hợp lệ còn trong bộ đệm hoặc tạo lỗi đóng không đúng thủ tục.

Khi nhận được `close_notify`, cần:

1. Hoàn tất xử lý các kết quả `unwrap()` đã sinh dữ liệu ứng dụng trước đó.
2. Ghi nhận chiều nhận TLS đã kết thúc.
3. Quyết định hướng gửi còn lại theo giao thức ứng dụng và phiên bản TLS đang thương lượng.
4. Nếu cần kết thúc hướng gửi, thực hiện quy trình `closeOutbound()` và vận chuyển byte đóng như trên.

Đóng một chiều không phải tín hiệu tái sử dụng lại cùng engine cho một kết nối mới. Engine đã đóng cần được bỏ sau khi hoàn tất dọn dẹp; kết nối mới dùng engine mới.

## 5. TCP EOF trước close_notify: phân biệt mất đường truyền với kết thúc hợp lệ

`SocketChannel.read()` trả `-1` báo kết thúc luồng TCP nhận. Điều đó không tự chứng minh đã nhận đủ dữ liệu TLS. Đối tác có thể đã thoát đột ngột, thiết bị mạng có thể đã cắt đường truyền, hoặc dữ liệu cuối đã bị mất.

Khi phát hiện EOF, đừng xóa ngay bộ đệm mạng. Trước hết xử lý các byte đã đọc còn hợp lệ trong bộ đệm; sau đó thông báo không còn đầu vào cho engine. Nếu không nhận được thông báo đóng TLS đúng thủ tục, `closeInbound()` có thể ném `SSLException`. Hãy giữ thông tin này trong kết quả kết nối thay vì nuốt lỗi và báo thành công. Xem [hợp đồng closeInbound](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/javax/net/ssl/SSLEngine.html#closeInbound()).

Đoạn xử lý sau chỉ minh họa bước thông báo EOF, sau khi phần dữ liệu đang có đã được xử lý:

```java
try {
    engine.closeInbound();
} catch (SSLException incompleteClose) {
    // Ghi nhận chiều nhận kết thúc không đúng thủ tục.
    // Chuyển lỗi đến bộ điều khiển kết nối và bên tiêu thụ dữ liệu.
    reportTlsClosureFailure(incompleteClose);
}
```

`reportTlsClosureFailure` là hàm do ứng dụng cung cấp, không phải API JDK. Đoạn mã chưa bao gồm việc phát dữ liệu đóng/lỗi còn lại và giải phóng kênh; đó là trách nhiệm tiếp theo của bộ điều khiển kết nối.

### Nguy cơ cắt cụt dữ liệu là gì?

Giả sử ứng dụng mong một tài liệu có phần kết thúc xác nhận nhưng chỉ nhận được phần đầu rồi EOF. Nếu coi EOF bất kỳ là kết thúc hợp lệ, phần tài liệu thiếu có thể bị hiểu là đầy đủ. `close_notify` hỗ trợ xác định ranh giới kết thúc TLS, nhưng tính đầy đủ của một thông điệp nghiệp vụ vẫn cần được kiểm tra bằng cấu trúc giao thức ứng dụng, chẳng hạn độ dài hoặc thông điệp kết thúc đã thỏa thuận.

Không biến lỗi đóng thành một lệnh tự động gửi lại mọi yêu cầu: nếu máy chủ có thể đã thực hiện một thao tác thay đổi dữ liệu trước khi kết nối mất, gửi lại thiếu cơ chế chống lặp có thể thực hiện thao tác lần thứ hai.

## 6. TLS 1.3 và việc kết thúc hai chiều

TLS 1.3 cho phép một bên đóng chiều gửi mà không tự động đóng chiều nhận. Nhận thông báo đóng không buộc phía còn lại phải hủy ngay mọi dữ liệu đang đợi gửi như một quy tắc chung cho mọi tình huống. Hai bên cần hoàn thành cách kết thúc mà giao thức ứng dụng yêu cầu. Trường hợp ngừng nhận trước thông báo đóng của đối tác có thể chấp nhận nguy cơ dữ liệu bị cắt cụt; đó phải là quyết định có chủ đích. [RFC 8446, mục 6.1](https://www.rfc-editor.org/rfc/rfc8446.html#section-6.1).

Vì vậy, bộ điều khiển không nên chỉ có một biến `closed` dùng cho mọi ý nghĩa. Một thiết kế dễ kiểm tra hơn là tách:

| Trạng thái ứng dụng theo dõi | Mục đích |
| --- | --- |
| Đang dừng gửi mới | Chặn yêu cầu nghiệp vụ đến sau thời điểm dừng |
| Đang hoàn tất chiều gửi TLS | Tiếp tục xử lý các bước engine yêu cầu |
| Engine đã hết đầu ra | Không chờ engine tạo thêm byte |
| Hàng đợi gửi đã hết | Không còn giữ byte chờ lớp vận chuyển |
| Chiều nhận kết thúc hợp lệ hoặc bất thường | Giữ nguyên nguyên nhân kết thúc |
| Tài nguyên đã được giải phóng | Ngăn sử dụng lại kênh/bộ đệm sau khi trả về nơi cấp phát |

Với kết nối phải nhận hết phản hồi trước khi đóng hoàn toàn, đợi chiều nhận kết thúc và đặt thời hạn. Với chính sách chỉ hoàn tất hướng gửi rồi dừng, ghi rõ việc không đợi hướng nhận; không dùng cùng nhãn “đóng hai chiều thành công” cho hai chính sách này.

## 7. Một bộ điều khiển đóng có thời hạn

Sơ đồ sau là thiết kế định hướng cho đóng bình thường của ứng dụng; không phải mã TLS hoàn chỉnh:

```text
Nhận yêu cầu dừng kết nối
  -> ngừng nhận thêm dữ liệu nghiệp vụ cần gửi
  -> gửi hết hoặc hủy có báo lỗi phần nghiệp vụ đang đợi theo hợp đồng
  -> yêu cầu closeOutbound

Trong các lượt xử lý tiếp theo:
  -> tiếp tục wrap/task/unwrap theo trạng thái engine
  -> bảo toàn thứ tự mọi byte đầu ra
  -> kênh ghi được: xả phần đợi gửi
  -> kênh chưa ghi được: đăng ký/chờ khả năng ghi
  -> có dữ liệu nhận: unwrap và chuyển dữ liệu ứng dụng còn lại
  -> EOF: xử lý byte còn lại rồi ghi nhận trạng thái đóng chiều nhận

Khi engine không còn đầu ra và hàng đợi gửi đã hết:
  -> nếu chính sách cần: tiếp tục đợi kết thúc chiều nhận
  -> khi điều kiện hoàn tất đã đủ: đóng kênh và giải phóng tài nguyên

Nếu hết thời hạn hoặc lỗi không thể phục hồi:
  -> kết thúc theo nhánh hủy/lỗi
  -> trả lỗi cho phần việc chưa hoàn tất
  -> giải phóng tài nguyên, giữ nguyên nguyên nhân
```

Khi engine trả `BUFFER_OVERFLOW`, tạo chỗ cho vùng đích trước khi thử lại. Khi `BUFFER_UNDERFLOW`, bảo toàn phần nhận chưa xử lý và chờ thêm dữ liệu nếu chưa có EOF; đã EOF thì không còn lý do chờ một phần bản ghi mãi mãi. Khi `NEED_TASK`, chạy và đợi các tác vụ được giao theo mô hình luồng đã chọn. Không lặp `wrap()`/`unwrap()` vô hạn khi không có tiến triển.

Một bộ đếm thời gian đóng nên gắn với kết nối, được hủy khi kết nối hoàn tất và được đánh giá trên cùng luồng sở hữu trạng thái. Nếu công việc nền hoàn tất sau khi kết nối đã bị hủy, kiểm tra vòng đời trước khi sử dụng lại engine hoặc bộ đệm. Điều này tránh lỗi callback muộn chạm vào tài nguyên đã trả về nơi cấp phát.

Khi xảy ra lỗi TLS nghiêm trọng hoặc lỗi mạng làm không thể vận chuyển thêm, không nên cố tiếp tục luồng dữ liệu nghiệp vụ. Chỉ cố phát dữ liệu cảnh báo/đóng mà engine còn cho phép khi đường truyền và chính sách lỗi cho phép; sau đó giải phóng tài nguyên có giới hạn thời gian. Nhánh hủy không phải một lần đóng bình thường thành công.

## 8. Chương trình minh họa điều kiện được giải phóng

Ví dụ sau chạy độc lập trên Java 17+. Nó mô hình hóa một kết quả thao tác và hàng đợi đầu ra để kiểm tra quyết định đóng. Đây không phải một phiên TLS thực và không phát `close_notify`; `SSLEngineResult` được tạo bằng constructor nhằm làm rõ rằng `CLOSED` có thể đi cùng số byte đầu ra lớn hơn 0.

Lưu thành `CloseGateDemo.java`:

```java
import java.nio.ByteBuffer;
import javax.net.ssl.SSLEngineResult;

public class CloseGateDemo {
    static boolean mayRelease(boolean outboundDone,
                              boolean inboundDone,
                              ByteBuffer pendingNetwork) {
        // Chính sách của ví dụ: phải hoàn tất cả hai chiều
        // và không còn byte chờ gửi trong hàng đợi duy nhất này.
        return outboundDone && inboundDone && !pendingNetwork.hasRemaining();
    }

    public static void main(String[] args) {
        SSLEngineResult lastWrap = new SSLEngineResult(
                SSLEngineResult.Status.CLOSED,
                SSLEngineResult.HandshakeStatus.NOT_HANDSHAKING,
                0, 6);
        ByteBuffer pending = ByteBuffer.wrap(new byte[6]);

        System.out.println("status=" + lastWrap.getStatus());
        System.out.println("produced=" + lastWrap.bytesProduced());
        System.out.println("pending=" + pending.remaining());
        System.out.println("releaseBeforeDrain=" + mayRelease(true, true, pending));

        // Mô phỏng lớp vận chuyển đã nhận hết byte.
        pending.position(pending.limit());
        System.out.println("releaseAfterDrain=" + mayRelease(true, true, pending));
        System.out.println("releaseWhileInboundOpen="
                + mayRelease(true, false, pending));
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 CloseGateDemo.java
java CloseGateDemo
```

Stdout:

```text
status=CLOSED
produced=6
pending=6
releaseBeforeDrain=false
releaseAfterDrain=true
releaseWhileInboundOpen=false
```

Không sao chép nguyên điều kiện `mayRelease` vào mọi ứng dụng: nó chỉ biểu diễn chính sách đợi cả hai chiều và đúng một bộ đệm đợi gửi. Hệ thống thật có thể có nhiều bộ đệm và thao tác ghi bất đồng bộ chưa hoàn tất. Khi đó phải theo dõi tất cả phần việc còn đang sở hữu byte. Nếu một thao tác ghi chưa hoàn tất còn giữ buffer, chưa được trả buffer ấy về nơi cấp phát dù hàng đợi của ứng dụng đã lấy nó ra.

## 9. Kết thúc kết nối khác với hủy SSLSession

“Phiên” thường được dùng chung cho nhiều khái niệm, nhưng cần tách rõ:

- Kết nối TLS hiện tại gắn với một engine và luồng vận chuyển.
- `SSLSession` cung cấp thông tin phiên của TLS và liên quan đến khả năng tiếp tục phiên trên kết nối khác.
- Phiên đăng nhập ở tầng ứng dụng, token hay cookie có vòng đời riêng.

Đóng engine/kênh không phải thao tác đăng xuất người dùng. `engine.getSession().invalidate()` cũng không thay thế việc phát thông báo đóng hoặc đóng socket. Theo hợp đồng `SSLSession`, vô hiệu hóa ngăn kết nối tương lai tiếp tục/tham gia phiên đó, nhưng kết nối đang dùng phiên có thể tiếp tục hoạt động đến khi đóng. [API SSLSession.invalidate](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/javax/net/ssl/SSLSession.html#invalidate()).

Chỉ vô hiệu hóa phiên theo chính sách bảo mật hoặc quản lý phiên đã xác định; không gọi nó như bước bắt buộc của mọi lần đóng kết nối bình thường. Nếu mục tiêu là thu hồi quyền truy cập người dùng, phải xử lý cơ chế xác thực/ủy quyền ở tầng ứng dụng thay vì dựa vào việc đóng một kết nối TCP.

## 10. Lỗi thường gặp và câu hỏi tự kiểm tra

| Sai sót | Hệ quả cần tránh |
| --- | --- |
| `closeOutbound(); channel.close();` ngay lập tức | Dữ liệu đóng và đầu ra đang đợi có thể chưa được vận chuyển |
| Thấy `Status.CLOSED` rồi bỏ toàn bộ buffer kết quả | Mất byte đầu ra mà thao tác vừa tạo |
| Gọi `closeInbound()` thay cho xử lý byte nhận cuối | Không xử lý thông báo đóng hợp lệ hoặc dữ liệu đang có |
| Nuốt `SSLException` lúc EOF và báo hoàn tất | Che mất việc kết thúc không đúng thủ tục |
| Chỉ đợi hai cờ engine mà bỏ qua hàng đợi I/O | Giải phóng tài nguyên khi còn byte hoặc callback ghi chưa hoàn tất |
| Chờ đối tác đóng vô thời hạn | Giữ kênh, bộ đệm và trạng thái kết nối không có giới hạn |
| Đồng nhất `SSLSession.invalidate()` với đóng mạng/đăng xuất | Thực hiện sai tầng trách nhiệm |

Tự suy luận ba tình huống:

1. Engine đã hết đầu ra nhưng còn hai buffer chờ gửi: chưa hoàn thành nghĩa vụ vận chuyển. Tiếp tục xả theo thứ tự hoặc chuyển sang nhánh lỗi khi hết hạn.
2. Đã nhận thông báo đóng hợp lệ nhưng còn dữ liệu nghiệp vụ cần phản hồi trong một giao thức cho phép kết thúc hai chiều độc lập: đánh giá chính sách chiều gửi theo giao thức và phiên bản TLS; không tự động xóa phần đợi gửi bằng một quy tắc chung.
3. Socket báo EOF khi bộ đệm còn nửa bản ghi: không coi phần bản ghi ấy là thông điệp đầy đủ. Ghi nhận kết thúc bất thường, trả lỗi cho công việc liên quan và dọn tài nguyên.

Khi quan sát vận hành, ghi nguyên nhân kết thúc, thời gian chờ đóng, trạng thái hai chiều, số byte còn đợi gửi và số thao tác I/O chưa hoàn tất. Những thông tin này giúp nhận diện mất dữ liệu hoặc rò rỉ tài nguyên mà không cần ghi nội dung bản rõ hay bí mật TLS.
