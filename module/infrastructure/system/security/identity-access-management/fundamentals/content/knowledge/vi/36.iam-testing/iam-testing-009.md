# Token replay test

## 1. Mục tiêu kiểm thử

Token replay test kiểm tra điều gì xảy ra khi một thông tin xác thực đã được sử dụng được gửi lại: hệ thống tiếp tục cho phép, từ chối, hay phát hiện và xử lý một sự cố bảo mật. Trong IAM, câu trả lời phụ thuộc vào loại token và hợp đồng sử dụng của nó.

Một access token có thể được thiết kế để gọi API nhiều lần. Ngược lại, authorization code hoặc token xác nhận một thao tác có thể chỉ được dùng một lần. Vì vậy, không thể dùng tiêu chí “request thứ hai phải thất bại” cho mọi loại token.

Sau bài học, người học có thể:

- Xác định token nào được phép tái sử dụng và bằng chứng nào phải có tính mới.
- Thiết kế ca kiểm thử phát lại tuần tự, đồng thời và qua nhiều node.
- Phân biệt lỗi chống replay với lỗi xác thực, phân quyền và lặp thao tác nghiệp vụ.
- Thu thập bằng chứng mà không làm lộ token hoặc khóa bí mật.

Ví dụ xuyên suốt là một ứng dụng quản trị doanh nghiệp: người dùng đăng nhập qua nhà cung cấp danh tính, gọi API danh sách tài khoản, làm mới access token và xác nhận cấp một quyền đặc biệt. Mỗi luồng có yêu cầu chống replay khác nhau.

## 2. Tái sử dụng hợp lệ và phát lại trái phép

### 2.1. Bearer token không tự có thuộc tính dùng một lần

Bearer token cho phép bên đang giữ token sử dụng quyền gắn với token mà không phải chứng minh sở hữu một khóa mật mã riêng. Do đó, một bearer access token còn hiệu lực thường có thể phục vụ nhiều request. Việc sao chép token sang một tiến trình khác vẫn có thể thành công nếu hệ thống không có ràng buộc bổ sung. Đây là rủi ro cần đánh giá, không tự động chứng minh bộ xác minh token làm sai hợp đồng. [RFC 6750, mục 1.2](https://www.rfc-editor.org/rfc/rfc6750.html#section-1.2).

Chẳng hạn, ứng dụng dùng cùng access token để gọi `GET /accounts` rồi `GET /profile`. Không nên biến toàn bộ access token thành dùng một lần chỉ để làm cho một bài test replay “xanh”.

### 2.2. Đối tượng chống replay có thể là proof hoặc một lần đổi token

Một thiết kế có thể ràng buộc access token với khóa của client. Với DPoP, request mang thêm proof được ký; với access token ràng buộc chứng chỉ mTLS, bên gọi phải chứng minh sở hữu khóa của chứng chỉ phù hợp. Access token vẫn có thể phục vụ nhiều request của chủ thể hợp lệ. [RFC 9449, mục 3](https://www.rfc-editor.org/rfc/rfc9449.html#section-3), [RFC 8705, mục 3](https://www.rfc-editor.org/rfc/rfc8705.html#section-3).

Trong một triển khai DPoP có kiểm tra proof dùng một lần, thứ cần bị từ chối khi lặp lại là proof cũ trong cùng ngữ cảnh chấp nhận. Một proof mới, hợp lệ, ký bằng đúng khóa cho access token hiện tại có thể được chấp nhận. Phải xác nhận chính sách triển khai trước khi viết assertion về tính dùng một lần của proof.

### 2.3. Những thuộc tính không được đánh đồng

| Thuộc tính | Câu hỏi mà nó trả lời | Điều chưa được bảo đảm chỉ bằng thuộc tính này |
|---|---|---|
| Chữ ký hợp lệ | Token có được ký bởi khóa được tin cậy không? | Token chưa từng được dùng |
| Thời hạn hợp lệ | Token có nằm trong khoảng thời gian chấp nhận không? | Token chỉ được dùng một lần trong khoảng đó |
| Đúng audience | Token có dành cho dịch vụ này không? | Người gửi là chủ thể ban đầu |
| Đúng scope/quyền | Chủ thể có quyền thực hiện hành động không? | Request chưa được gửi trước đó |
| Ràng buộc người gửi | Người gửi có chứng minh được khóa/chứng chỉ phù hợp không? | Một thao tác nghiệp vụ không bị thực hiện hai lần |
| Kiểm soát dùng một lần | Bằng chứng hoặc token này đã bị tiêu thụ chưa? | Toàn bộ giao dịch nghiệp vụ đã hoàn tất đúng một lần |

Một claim `jti` chỉ là dữ liệu định danh nếu không có logic kiểm tra lịch sử sử dụng phù hợp. Tương tự, thời hạn ngắn giới hạn cửa sổ rủi ro nhưng không thay thế kiểm soát replay trong cửa sổ ấy.

## 3. Viết hợp đồng trước khi viết test

Với mỗi luồng, hãy ghi rõ:

1. **Đối tượng:** access token, refresh token, authorization code, DPoP proof hay token xác nhận thao tác.
2. **Đơn vị được phép dùng lại:** toàn bộ token, một proof, một phiên hay một giao dịch.
3. **Ràng buộc:** issuer, audience, client, khóa, tài nguyên, tenant, thời gian và trạng thái phiên nếu có.
4. **Phạm vi kiểm soát:** một node, một cụm, nhiều vùng hay toàn bộ hệ thống.
5. **Hậu quả khi vi phạm:** từ chối request, vô hiệu hóa token liên quan, thu hồi grant hoặc phát sự kiện cảnh báo.

Ví dụ hợp đồng giả định cho bài thực hành:

```yaml
testProfile:
  resource: account-admin-api
  accessToken:
    mode: DPoP
    reusableWithFreshProof: true
  proof:
    duplicatePolicy: reject
    duplicateScope: all-nodes-serving-the-same-resource
    maximumAgeSeconds: 60
    allowedFutureSkewSeconds: 5
  refreshToken:
    mode: strict-rotation
    reuseAction: revoke-active-refresh-token-in-grant
  confirmationToken:
    operation: grant-privileged-role
    successfulConsumptionLimit: 1
```

Các con số 60 và 5 giây là cấu hình minh họa của bài thực hành, không phải thời hạn mặc định của DPoP. Hợp đồng thực tế phải lấy từ cấu hình và yêu cầu của hệ thống đang kiểm thử.

Nếu sản phẩm chỉ hỗ trợ bearer token, các ca DPoP được đánh dấu không áp dụng. Không ghi PASS cho một cơ chế chưa được triển khai.

## 4. Ma trận kiểm thử nền tảng

| Mã | Điều kiện và hành động | Kỳ vọng theo hợp đồng tương ứng |
|---|---|---|
| B01 | Gọi API đọc hai lần bằng bearer access token còn hiệu lực, đủ quyền | Có thể thành công cả hai; đây là đối chứng tái sử dụng hợp lệ |
| B02 | Mang bearer token sang client kiểm thử thứ hai | Ghi nhận rủi ro chiếm hữu bearer; chỉ đòi từ chối nếu có ràng buộc đã công bố |
| D01 | Gửi request DPoP hợp lệ, sau đó gửi lại nguyên proof | Với profile dùng một lần: chỉ lần đầu được chấp nhận |
| D02 | Giữ access token, tạo proof mới bằng đúng khóa | Được chấp nhận nếu token và quyền vẫn hợp lệ |
| D03 | Dùng token với proof ký bằng khóa không được ràng buộc | Bị từ chối trước khi truy cập tài nguyên |
| D04 | Gửi một proof mới nhưng sai method, URI hoặc access-token hash | Bị từ chối do sai ràng buộc tương ứng |
| D05 | Gửi cùng proof đồng thời tới nhiều node | Tổng số lần chấp nhận không vượt giới hạn của profile |
| R01 | Đổi refresh token R0 thành R1 rồi gửi lại R0 | Với strict rotation: từ chối R0 và thực hiện chính sách phát hiện reuse |
| C01 | Đổi cùng authorization code hai lần bằng dữ liệu client hợp lệ | Lần đổi lại bị từ chối |
| O01 | Gửi token xác nhận cấp quyền hai lần | Không cấp quyền hoặc tạo tác động phụ lần thứ hai |

Authorization code có yêu cầu không được dùng nhiều hơn một lần; khi code đã dùng bị gửi lại, authorization server phải từ chối. [RFC 6749, mục 4.1.2](https://www.rfc-editor.org/rfc/rfc6749.html#section-4.1.2).

Không ép tất cả các dòng dùng cùng HTTP status. Resource server, token endpoint và tầng TLS có cơ chế báo lỗi khác nhau. Assertion cần khớp với giao thức và hợp đồng endpoint cụ thể.

## 5. Chuẩn bị môi trường và bằng chứng đối chứng

### 5.1. Dữ liệu kiểm thử

Dùng môi trường kiểm thử được cấp quyền, tài khoản riêng và tài nguyên có thể phục hồi. Với ví dụ quản trị tài khoản, chuẩn bị:

- Hai tài khoản test thuộc các tenant tách biệt để kiểm tra ranh giới tenant.
- Hai client hoặc hai bộ khóa test, gọi là K1 và K2.
- Access token có audience và scope đúng cho API cần gọi.
- Một grant riêng cho mỗi ca refresh-token reuse vì ca này có thể làm mất hiệu lực token còn lại.
- Ít nhất hai node của cùng dịch vụ nếu hợp đồng yêu cầu chống replay trên toàn cụm.
- Cách quan sát tác động: số lần ghi quyền, số sự kiện outbox hoặc số bản ghi xác nhận thao tác.

Không sử dụng token của người dùng thật và không đưa token, refresh token hay private key vào báo cáo CI. Các ca thử chỉ cần lưu định danh tương quan đã được bảo vệ và kết quả kiểm tra.

### 5.2. Chứng minh request ban đầu hợp lệ

Trước ca replay, gửi request đối chứng và xác nhận nó thành công vì đúng token, đúng quyền và đúng tài nguyên. Nếu lần đầu đã thất bại do scope thiếu hoặc endpoint sai, việc lần hai cũng thất bại không cung cấp bằng chứng chống replay.

Đối với ca replay chính xác, lưu nguyên các byte token và proof trong bộ nhớ của test runner. Đừng gọi hàm sinh proof một lần nữa cho lần gửi thứ hai. Tắt cơ chế tự refresh token hoặc tự retry của client trong ca này để biết request thực tế đã chứa gì.

### 5.3. Tránh thay đổi nhiều biến cùng lúc

Nếu chỉ muốn kiểm tra proof bị dùng lại, hãy giữ nguyên method, URI, access token, body và ngữ cảnh quyền. Nếu vừa đổi endpoint vừa phát lại proof, kết quả từ chối có thể chỉ do sai URI.

Với ca kiểm tra sai ràng buộc, dùng một proof mới, chưa tiêu thụ, có chữ ký hợp lệ nhưng claim mục tiêu sai. Sửa trực tiếp payload của JWT đã ký chỉ kiểm tra chữ ký bị hỏng; nó chưa chứng minh bộ kiểm tra `htm` hay `ath` hoạt động.

## 6. Kiểm thử DPoP tuần tự

### 6.1. Luồng kiểm thử chính

```text
1. Nhận access token AT ràng buộc với khóa K1.
2. Tạo proof P1 bằng K1 cho request GET /accounts.
3. Gửi request với AT và P1 tới node A: kỳ vọng được chấp nhận.
4. Gửi lại nguyên request với cùng AT và P1: kỳ vọng bị từ chối
   nếu profile thực thi proof dùng một lần.
5. Tạo proof P2 mới bằng K1 cho cùng request.
6. Gửi request với cùng AT và P2: kỳ vọng được chấp nhận.
```

Bước 6 quan trọng vì nó chứng minh hệ thống chặn proof cũ mà vẫn cho client hợp lệ tiếp tục hoạt động. Nếu cả bước 4 lẫn bước 6 đều thất bại, cần kiểm tra xem test có vô tình làm hết hạn token, thu hồi phiên hoặc kích hoạt rate limit hay không.

Request minh họa dưới đây chỉ thể hiện cấu trúc; các placeholder không phải token có thể sử dụng:

```http
GET /accounts HTTP/1.1
Host: iam-test.example
Authorization: DPoP <access-token-test>
DPoP: <proof-P1-da-ky>
```

Trong DPoP, `htm` ràng buộc method; `htu` ràng buộc URI không gồm query và fragment; `ath` ràng buộc access token khi truy cập protected resource. Proof còn phải phù hợp khóa và cửa sổ thời gian được chấp nhận. [RFC 9449, mục 4.2–4.3](https://www.rfc-editor.org/rfc/rfc9449.html#section-4.2).

Từ đó, tách riêng ca sai method, sai đường dẫn và sai token. Việc thay query hoặc body không mặc nhiên phải làm DPoP proof sai: DPoP không phải chữ ký toàn bộ thông điệp HTTP. Nếu nghiệp vụ đòi ràng buộc payload giao dịch, kiểm thử cơ chế bổ sung được thiết kế cho mục đích đó.

### 6.2. Nonce, tính mới và retry

Nếu server yêu cầu nonce, trước hết hoàn thành đúng luồng nhận nonce và tạo proof hợp lệ. Sau đó kiểm thử nonce thiếu, nonce không phù hợp và proof trùng theo chính sách. Không suy ra “nonce dùng một lần” chỉ từ tên nonce: DPoP cho phép cùng nonce được dùng với các proof khác nhau; replay protection cần xét định danh proof và khoảng chấp nhận tương ứng. [RFC 9449, mục 11.1](https://www.rfc-editor.org/rfc/rfc9449.html#section-11.1).

Tách hai ca:

- **Phát lại có chủ đích:** gửi lại nguyên proof cũ để đo khả năng phát hiện.
- **Retry của client hợp lệ:** tạo proof mới theo giao thức và áp dụng cơ chế chống lặp nghiệp vụ nếu thao tác có tác động phụ.

Request đầu tiên có thể đã thành công nhưng response bị mất. Việc proof cũ bị từ chối không cho client biết chắc giao dịch đầu tiên chưa thực hiện. Đây là lý do cần kiểm tra cả trạng thái nghiệp vụ.

## 7. Kiểm thử refresh-token rotation

Với refresh-token rotation, mỗi lần làm mới tạo refresh token mới và vô hiệu hóa token trước đó. Thông tin quan hệ giữa các token giúp phát hiện việc token cũ bị sử dụng lại. RFC 9700 yêu cầu public client được bảo vệ bằng sender-constrained refresh token hoặc rotation; không phải mọi hệ thống đều áp dụng cùng một kiểu rotation. [RFC 9700, mục 2.2.2 và 4.14](https://www.rfc-editor.org/rfc/rfc9700.html#section-4.14).

Với profile strict rotation đã nêu, trình tự test là:

1. Tạo grant mới, nhận R0.
2. Gửi yêu cầu refresh hợp lệ bằng R0, nhận R1 và access token mới.
3. Gửi lại R0 với các dữ liệu client vẫn hợp lệ; kiểm tra lỗi từ token endpoint.
4. Xác nhận sự kiện reuse được ghi nhận.
5. Thử sử dụng R1 để xác minh chính sách vô hiệu hóa refresh token đang hoạt động của grant.
6. Kiểm tra grant của tài khoản khác vẫn hoạt động để phát hiện thu hồi quá rộng.

Trong mô hình rotation của RFC 9700, server không thể biết chắc bên gửi token cũ là client hợp lệ hay kẻ đánh cắp, nên việc phát hiện reuse dẫn tới thu hồi refresh token đang hoạt động. [RFC 9700, mục 4.14.2](https://www.rfc-editor.org/rfc/rfc9700.html#section-4.14.2).

Không suy ra mọi access token đã cấp cũng bị hủy ngay. Điều đó phụ thuộc cơ chế thu hồi và chính sách riêng của hệ thống. Nếu yêu cầu có độ trễ thu hồi tối đa, phải đo theo độ trễ đó.

Nếu một sản phẩm có cơ chế xử lý retry hoặc cửa sổ dung sai, ghi rõ kết quả được phép trong cửa sổ và ngoài cửa sổ. Cần chứng minh nó không tạo ra nhiều nhánh refresh-token còn hoạt động ngoài hợp đồng. Không âm thầm nới assertion của strict rotation để làm test vượt qua.

## 8. Kiểm thử đồng thời và trên nhiều node

### 8.1. Cuộc đua kiểm tra rồi đánh dấu

Một lỗi phổ biến xuất hiện khi việc “đã dùng chưa?” và “đánh dấu đã dùng” là hai thao tác tách rời:

```text
Node A: chưa thấy proof P1 trong replay store.
Node B: chưa thấy proof P1 trong replay store.
Node A: cho phép request và ghi P1.
Node B: cũng cho phép request và ghi P1.
```

Ca tuần tự có thể PASS trong khi ca đồng thời FAIL. Cần kiểm tra thao tác tiêu thụ có tính nguyên tử trong đúng phạm vi triển khai.

Với contract “proof hợp lệ dùng một lần”, gửi N request chứa cùng proof mới bằng một điểm xuất phát đồng bộ. Trong điều kiện các thành phần hoạt động bình thường, kỳ vọng có đúng một lần chấp nhận; nếu chỉ kiểm tra an toàn trong một ca gây lỗi hạ tầng, điều kiện tối thiểu là không quá một lần chấp nhận. Trường hợp không request nào thành công vẫn cần được điều tra riêng.

### 8.2. Mẫu điều phối bằng Java

Đoạn Java sau minh họa cách khởi chạy tám lời gọi cùng lúc. `sendSameProof` do bộ test tích hợp cung cấp: mỗi lời gọi phải gửi đúng cùng token và proof, đồng thời trả `true` chỉ khi nhận response thành công đã được xác định trong contract. Nó không tự sinh lại proof và không tự retry.

```java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.Callable;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public final class ReplayRaceProbe {
    public static int countAccepted(Callable<Boolean> sendSameProof)
            throws Exception {
        int workers = 8;
        ExecutorService pool = Executors.newFixedThreadPool(workers);
        CountDownLatch ready = new CountDownLatch(workers);
        CountDownLatch start = new CountDownLatch(1);
        List<Future<Boolean>> results = new ArrayList<>();

        try {
            for (int i = 0; i < workers; i++) {
                results.add(pool.submit(() -> {
                    ready.countDown();
                    if (!start.await(5, TimeUnit.SECONDS)) {
                        throw new IllegalStateException("Start barrier timeout");
                    }
                    return sendSameProof.call();
                }));
            }

            if (!ready.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Workers not ready");
            }
            start.countDown();

            int accepted = 0;
            for (Future<Boolean> result : results) {
                if (result.get(10, TimeUnit.SECONDS)) {
                    accepted++;
                }
            }
            return accepted;
        } finally {
            start.countDown();
            pool.shutdownNow();
            pool.awaitTermination(5, TimeUnit.SECONDS);
        }
    }
}
```

Bộ chuyển tiếp HTTP cần an toàn khi gọi đồng thời, đặt timeout cho từng request và ghi lại từng kết quả. Ngoại lệ mạng phải được báo là lỗi hạ tầng hoặc kết quả chưa xác định; không đổi ngoại lệ thành `false` rồi tính nó là một lần chặn replay thành công.

Đây là mã minh họa thiết kế test, chưa phải kết quả thực thi trên một IAM cụ thể. Điểm xuất phát đồng bộ giúp tạo cạnh tranh nhưng không bảo đảm mọi request tới server đúng cùng thời điểm; có thể cần chạy nhiều lượt với proof mới cho mỗi lượt.

### 8.3. Phạm vi toàn cụm

Chạy cùng test theo các cách định tuyến:

- Lần đầu tới node A, lần phát lại tới node B.
- Nhiều request đồng thời được phân phối tới A và B.
- Phát lại sau khi node A khởi động lại nhưng proof vẫn còn được chấp nhận về thời gian.
- Phát lại sau failover của replay store trong kịch bản hạ tầng được hỗ trợ.

Nếu các node chỉ giữ bộ nhớ cục bộ, ca qua hai node sẽ giúp phát hiện việc “dùng một lần trên mỗi node” không đáp ứng hợp đồng “dùng một lần trên toàn dịch vụ”. Sticky session có thể che lỗi này nên không được xem là bằng chứng toàn cụm đã an toàn.

Với mTLS, thử token ràng buộc chứng chỉ bằng client không có khóa tương ứng hoặc bằng chứng chỉ khác. Sau đó dùng đúng chứng chỉ làm đối chứng. TLS có thể từ chối trước khi có HTTP response, nên test runner phải phân biệt lỗi bắt tay TLS mong đợi với lỗi kết nối không liên quan.

## 9. Cửa sổ thời gian, replay store và thu hồi

### 9.1. Kiểm thử sát ranh giới

Đối với profile proof có giới hạn tuổi, thử các thời điểm ngay trước, đúng tại và ngay sau ranh giới. Ghi rõ độ lệch đồng hồ cho phép và quy tắc làm tròn timestamp. Nếu có thể, dùng đồng hồ có thể điều khiển trong test thành phần để tránh phụ thuộc vào lệnh ngủ.

Thử một proof đã tiêu thụ trong toàn bộ khoảng thời gian mà bộ xác minh vẫn có thể chấp nhận proof ấy. Replay store không được quên bản ghi quá sớm, khiến một proof cũ được dùng lại trước khi cửa sổ chấp nhận kết thúc.

Lặp lại với node có độ lệch đồng hồ trong giới hạn vận hành để phát hiện TTL và bộ xác minh hiểu khác nhau về thời điểm hết hạn. Những ca này kiểm tra sự nhất quán của cấu hình, không chỉ kiểm tra claim có tồn tại.

### 9.2. Mất replay store

Nếu hợp đồng yêu cầu từ chối khi không thể xác định proof đã dùng hay chưa, gây lỗi replay store trong môi trường kiểm thử và xác nhận request không được phép đi tiếp. Không nhất thiết phải giả dạng token sai: lỗi phụ thuộc có thể được trả dưới dạng dịch vụ tạm thời không sẵn sàng theo thiết kế.

Kiểm tra việc khôi phục store không xóa mất trạng thái còn cần thiết. Nếu hệ thống công bố chế độ suy giảm khác, phải đo đúng hành vi ấy và ghi rõ giới hạn bảo đảm chống replay trong giai đoạn suy giảm.

### 9.3. Logout và revocation là hợp đồng riêng

Một ca “logout rồi dùng lại token” kiểm tra hiệu lực sau logout, không tự động kiểm tra proof dùng một lần. Với JWT được xác minh hoàn toàn cục bộ, việc đóng phiên ở nơi cấp token không tự truyền trạng thái mới tới mọi API.

Nếu yêu cầu là token phải mất hiệu lực trong một khoảng thời gian tối đa sau thu hồi, hãy gửi lại token trên các node trong khoảng đó và đo thời điểm bị từ chối. Kiểm tra cache, sự kiện thu hồi và đường đi thực tế của token thay vì mặc định mọi request phải thất bại tức thì.

## 10. Kiểm tra tác động nghiệp vụ và quan sát hệ thống

### 10.1. Từ chối replay chưa đồng nghĩa giao dịch chỉ chạy một lần

Trong thao tác cấp quyền đặc biệt, hãy kiểm tra cả response lẫn dữ liệu:

- Số bản ghi cấp quyền mới đúng với hợp đồng.
- Số sự kiện hoặc tác vụ phát sinh không bị nhân đôi.
- Trạng thái token xác nhận đã tiêu thụ gắn đúng với giao dịch.
- Request hợp lệ khác không bị chặn nhầm.

Nếu request vượt qua bước tiêu thụ proof nhưng lỗi trước khi hoàn tất nghiệp vụ, client có thể cần gửi một request mới. Khóa idempotency, trạng thái thao tác hoặc giao dịch dữ liệu giải quyết câu hỏi “nghiệp vụ đã chạy chưa”; replay store giải quyết câu hỏi “bằng chứng này đã dùng chưa”. Hai cơ chế cần có test riêng và test kết hợp.

### 10.2. Bằng chứng cần lưu

Một kết quả test nên chứa phiên bản cấu hình, thời gian, mã ca, node đích, request correlation ID, kết quả xác thực và tác động nghiệp vụ. Dùng định danh proof đã được che hoặc dấu vân tay được bảo vệ để tương quan khi cần; không coi mọi hash đơn thuần đều an toàn cho mọi loại token.

Ví dụ bản ghi được thiết kế cho môi trường test:

```json
{
  "testCase": "D05",
  "runId": "replay-run-42",
  "node": "resource-node-b",
  "proofReference": "protected-reference-7",
  "decision": "DENY",
  "internalReason": "PROOF_ALREADY_USED",
  "businessEffectCount": 0
}
```

`PROOF_ALREADY_USED` là mã quan sát nội bộ minh họa, không phải mã lỗi OAuth bắt buộc và không cần tiết lộ ra client. Khi phân tích, đối chiếu sự kiện với request cụ thể để tránh nhận nhầm một cảnh báo của ca chạy trước.

## 11. Những kết luận sai cần tránh

| Nhận định | Vì sao chưa đủ hoặc không đúng |
|---|---|
| “JWT có chữ ký nên không replay được” | Token nguyên vẹn vẫn có thể bị gửi lại; chữ ký không ghi nhận lịch sử tiêu thụ |
| “Có HTTPS nên token bị sao chép không dùng được” | Bảo vệ đường truyền không tự ràng buộc token với bên giữ khóa riêng |
| “Cùng access token gọi hai lần đều thành công là lỗi” | Access token có thể được thiết kế để tái sử dụng |
| “Đổi body làm DPoP proof sai” | Phải kiểm tra phạm vi dữ liệu thực sự được proof bảo vệ |
| “Mọi request thứ hai đều thất bại nên đã PASS” | Có thể lần đầu đã sai quyền, token hết hạn hoặc rate limit đang chặn |
| “Một node PASS nghĩa là cả cụm PASS” | Trạng thái có thể chưa được chia sẻ hoặc tiêu thụ nguyên tử trên toàn cụm |
| “HTTP báo lỗi nghĩa là không có tác động” | Nghiệp vụ có thể đã commit trước khi response bị lỗi |
| “Reuse refresh token phải thu hồi mọi phiên của người dùng” | Phạm vi thu hồi phải theo grant và chính sách, tránh ảnh hưởng quá rộng |

## 12. Bài thực hành và tiêu chí hoàn thành

Với ứng dụng quản trị doanh nghiệp giả định, thực hiện lần lượt:

1. Viết hợp đồng cho access token, proof, refresh token và token xác nhận cấp quyền.
2. Tạo ca đối chứng cho mỗi luồng và chứng minh request hợp lệ có thể thành công.
3. Kiểm tra replay tuần tự bằng chính các byte đã dùng.
4. Kiểm tra proof mới với access token cũ để phát hiện chặn nhầm.
5. Chạy ca đồng thời và ca qua hai node với dữ liệu mới cho từng lượt.
6. Kiểm tra thời gian, thu hồi và lỗi replay store theo hợp đồng.
7. Đối chiếu số lần chấp nhận, số tác động nghiệp vụ và bằng chứng quan sát.

Một ca được kết luận PASS khi nó đạt kỳ vọng của đúng loại token, có đối chứng hợp lệ và có bằng chứng cho phạm vi đang tuyên bố. Kết quả chỉ chạy trên một node phải được ghi là kiểm chứng một node; ca chưa thể định tuyến đa node phải được ghi là chưa kiểm chứng phần toàn cụm.

Khi phát hiện lỗi, báo rõ đối tượng bị phát lại, điều kiện để tái hiện, số lần được chấp nhận, phạm vi ảnh hưởng và dữ liệu quan sát đã che bí mật. Cách báo này giúp nhóm IAM xác định lỗi nằm ở ràng buộc token, bộ nhớ chống replay, rotation hay giao dịch nghiệp vụ.
