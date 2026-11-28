# Khác biệt giữa truy vấn phiên với danh sách tất cả người dùng

Spring Session có thể lập chỉ mục phiên theo tên principal để ứng dụng tìm các phiên đang gắn với một người dùng đã biết. Khả năng này hữu ích khi cần xem người dùng đang đăng nhập ở những thiết bị nào, giới hạn số phiên đồng thời hoặc thu hồi các phiên của một tài khoản.

Tuy nhiên, truy vấn phiên theo principal và liệt kê tất cả người dùng là hai bài toán khác nhau. Chỉ mục phiên trả lời câu hỏi “người dùng X có những phiên nào đang được lưu?”. Nó không phải danh bạ tài khoản, không chứa người dùng chưa từng tạo phiên và không cung cấp danh sách đầy đủ những người dùng trong hệ thống.

## Mục tiêu

Sau bài học, bạn có thể:

- Phân biệt bản ghi người dùng với phiên làm việc của người dùng.
- Giải thích principal index trong Spring Session Redis.
- Dùng `FindByIndexNameSessionRepository` để tìm các phiên của một principal đã biết.
- Bảo đảm phiên được gắn với đúng principal để có thể tìm kiếm.
- Thiết kế chức năng quản trị danh sách phiên và danh sách người dùng đúng nguồn dữ liệu.
- Tránh dùng Redis key nội bộ như một API liệt kê tài khoản.

## 1. Người dùng và phiên là hai thực thể khác nhau

Một người dùng là một tài khoản trong hệ thống. Tài khoản thường có bản ghi bền vững trong database người dùng, identity provider hoặc dịch vụ quản lý danh tính. Một phiên là trạng thái truy cập tạm thời được tạo khi người dùng hoặc một client bắt đầu sử dụng ứng dụng.

Quan hệ giữa chúng thường là một người dùng có thể có nhiều phiên:

~~~text
User account
  userId = 42
  username = linh@example.test
       |
       +---- Session A (laptop, trình duyệt)
       |
       +---- Session B (điện thoại)
       |
       +---- Session C (máy tính bảng)
~~~

Một tài khoản có thể tồn tại nhưng chưa từng đăng nhập, hoặc hiện không có phiên nào còn hiệu lực. Ngược lại, một phiên có thể thuộc về khách chưa đăng nhập, ví dụ phiên ẩn danh chứa giỏ hàng hoặc trạng thái điều hướng.

| Đối tượng | Câu hỏi nó trả lời | Nguồn dữ liệu phù hợp |
|---|---|---|
| Người dùng | Tài khoản nào tồn tại, đang hoạt động, bị khóa hoặc có vai trò gì? | User database hoặc identity provider |
| Phiên | Session nào đang hoạt động, thuộc principal nào, được tạo và truy cập khi nào? | Spring Session repository |
| Quan hệ người dùng - phiên | Người dùng đã xác thực đang có những phiên nào? | Principal index của repository phiên |

Vì vậy, “danh sách tất cả người dùng” phải lấy từ nguồn quản lý tài khoản. “Danh sách phiên của một người dùng” có thể lấy từ Spring Session nếu repository hỗ trợ principal index và phiên được gắn với principal.

## 2. Principal index trong Spring Session Redis

`FindByIndexNameSessionRepository` là abstraction của Spring Session cho phép tìm phiên theo một chỉ mục. Chỉ mục chuẩn thường dùng là:

~~~java
FindByIndexNameSessionRepository.PRINCIPAL_NAME_INDEX_NAME
~~~

Giá trị của chỉ mục là tên principal, thường là username hoặc định danh ổn định mà ứng dụng chọn. Với repository Redis có lập chỉ mục, Spring Session duy trì cấu trúc phụ trợ để ánh xạ principal tới các session ID liên quan.

Khi ứng dụng truy vấn theo principal, repository dùng index để tìm các phiên phù hợp thay vì yêu cầu ứng dụng tự quét tất cả key phiên trong Redis.

Có thể hình dung index:

~~~text
Principal index
  "linh@example.test"
       |
       +---- session-id-A
       +---- session-id-B

  "minh@example.test"
       |
       +---- session-id-C
~~~

Đây là mô hình khái niệm. Cách Redis lưu index, tên key và cấu trúc dữ liệu phụ trợ là chi tiết nội bộ phụ thuộc phiên bản và cấu hình. Ứng dụng nên dùng API `FindByIndexNameSessionRepository` thay vì thao tác trực tiếp trên các key index.

Principal index không phải chỉ mục của bảng người dùng. Nó chỉ ghi nhận principal có liên quan tới các phiên mà repository đang quản lý và có thể lập chỉ mục.

## 3. Chọn repository có hỗ trợ chỉ mục

Không phải mọi repository session đều hỗ trợ truy vấn theo principal. Với Redis, hãy chọn cấu hình Spring Session sử dụng repository có lập chỉ mục, thường là `RedisIndexedSessionRepository`.

Nếu dùng Spring Boot, cấu hình repository type theo phiên bản Boot đang sử dụng:

~~~yaml
spring:
  session:
    store-type: redis
    redis:
      repository-type: indexed
~~~

Tên property và khả năng cấu hình có thể thay đổi theo dòng Spring Boot. Hãy xác minh trong metadata cấu hình của đúng phiên bản. Với cấu hình Java thuần, có thể dùng annotation dành cho Redis indexed session, ví dụ `@EnableRedisIndexedHttpSession`, thay vì cấu hình repository Redis không lập chỉ mục.

Sau khi cấu hình, kiểm tra bean thực tế được tạo và bảo đảm nó triển khai `FindByIndexNameSessionRepository`. Nếu ứng dụng chỉ có repository không hỗ trợ index, lời gọi tìm phiên theo principal sẽ không có implementation phù hợp.

## 4. Truy vấn phiên cho một principal đã biết

API thuận tiện nhất là `findByPrincipalName`. Nó nhận principal name và trả về map có khóa là session ID, giá trị là session tương ứng.

Ví dụ service:

~~~java
import java.util.Map;

import org.springframework.session.FindByIndexNameSessionRepository;
import org.springframework.session.Session;
import org.springframework.stereotype.Service;

@Service
public class UserSessionQueryService {

    private final FindByIndexNameSessionRepository<? extends Session>
            sessionRepository;

    public UserSessionQueryService(
            FindByIndexNameSessionRepository<? extends Session>
                    sessionRepository) {
        this.sessionRepository = sessionRepository;
    }

    public Map<String, ? extends Session> findSessions(String principalName) {
        return sessionRepository.findByPrincipalName(principalName);
    }
}
~~~

Một cách gọi tương đương là dùng tên index và giá trị index rõ ràng:

~~~java
Map<String, ? extends Session> sessions =
        sessionRepository.findByIndexNameAndIndexValue(
                FindByIndexNameSessionRepository.PRINCIPAL_NAME_INDEX_NAME,
                principalName);
~~~

Kết quả là các phiên được index với principal đó. Map không phải danh sách user và cũng không chứa các tài khoản không có phiên.

Ví dụ xử lý kết quả:

~~~java
Map<String, ? extends Session> sessions =
        userSessionQueryService.findSessions("linh@example.test");

for (Map.Entry<String, ? extends Session> entry : sessions.entrySet()) {
    String sessionId = entry.getKey();
    Session session = entry.getValue();

    Instant createdAt = Instant.ofEpochMilli(session.getCreationTime());
    Instant lastAccessedAt =
            Instant.ofEpochMilli(session.getLastAccessedTime());

    // Chỉ tạo DTO metadata cần thiết cho giao diện quản trị.
}
~~~

Để đoạn ví dụ hoàn chỉnh, thêm import `java.time.Instant`. Trong API quản trị, không trả session ID thô hoặc toàn bộ thuộc tính session cho trình duyệt quản trị. Session ID là thông tin nhạy cảm có thể cho phép tiếp tục phiên nếu bị lộ. Chỉ trả metadata cần thiết như thời điểm tạo, lần truy cập gần nhất và trạng thái.

## 5. Làm thế nào để phiên được gắn với principal?

Repository chỉ có thể tìm phiên theo principal nếu thông tin principal được đưa vào chỉ mục. Cách cung cấp thông tin phụ thuộc cơ chế xác thực.

### 5.1. Khi dùng Spring Security

Trong tích hợp Spring Security tiêu chuẩn, repository indexed có thể suy ra principal từ `SecurityContext` được lưu trong session, thông qua cơ chế phân giải principal tương ứng. Cần bảo đảm SecurityContext thực sự được lưu trong session và cách tích hợp đang dùng tương thích với `PrincipalNameIndexResolver` của phiên bản Spring Session.

Nếu ứng dụng dùng cấu hình bảo mật tùy chỉnh, lưu SecurityContext theo cách khác hoặc không lưu vào HttpSession, không nên giả định index tự động có đủ dữ liệu. Hãy kiểm tra cấu hình và kết quả truy vấn trong integration test.

### 5.2. Khi dùng cơ chế xác thực riêng

Ứng dụng có thể lưu principal name vào thuộc tính index chuẩn của Spring Session:

~~~java
import org.springframework.session.FindByIndexNameSessionRepository;

HttpSession session = request.getSession();
session.setAttribute(
        FindByIndexNameSessionRepository.PRINCIPAL_NAME_INDEX_NAME,
        principalName);
~~~

Ở đây `principalName` phải là định danh ổn định mà ứng dụng sẽ dùng khi truy vấn. Không nên dùng display name có thể thay đổi hoặc giá trị không duy nhất. Nếu username thay đổi, cần có chính sách cập nhật hoặc chuyển đổi index cho các phiên hiện có.

Đối với Servlet app dùng Spring Session Redis, ví dụ trên đặt thuộc tính trên `HttpSession`. Repository indexed có thể dùng thuộc tính đó để xây dựng principal index. Nếu dùng API khác hoặc custom index resolver, hãy tuân theo hợp đồng của implementation đó.

### 5.3. Phiên ẩn danh

Phiên chưa xác thực thường không có principal người dùng. Những phiên này có thể vẫn tồn tại trong repository để giữ giỏ hàng, CSRF state hoặc dữ liệu tạm, nhưng sẽ không xuất hiện trong truy vấn principal của một tài khoản đã biết trừ khi ứng dụng chủ động gắn principal.

Không gán một principal giả dùng chung cho mọi phiên ẩn danh chỉ để chúng xuất hiện trong index. Việc đó có thể khiến truy vấn trả về một nhóm phiên rất lớn và làm sai ý nghĩa của chỉ mục người dùng.

## 6. Kết quả truy vấn phiên không phải danh sách người dùng

Giả sử database có 5.000 tài khoản:

- 3.000 tài khoản chưa từng đăng nhập.
- 1.500 tài khoản đã từng đăng nhập nhưng hiện không có phiên hoạt động.
- 400 tài khoản có một phiên.
- 90 tài khoản có từ hai phiên trở lên.
- 10 tài khoản có phiên ẩn danh hoặc dữ liệu phiên chưa được gắn principal.

Principal index chỉ phản ánh các phiên có principal được index và còn được repository quản lý. Nó không thể trả về đủ 5.000 tài khoản. Ngay cả khi một truy vấn index cho từng principal trả về map rỗng, điều đó chỉ cho biết hiện không tìm thấy phiên theo index đó; nó không chứng minh tài khoản không tồn tại.

| Yêu cầu | Cách truy vấn |
|---|---|
| Tìm các phiên của một người dùng | `findByPrincipalName(principalName)` |
| Kiểm tra một tài khoản có bản ghi hay không | Truy vấn user database hoặc identity provider |
| Liệt kê tất cả tài khoản | API phân trang của user database hoặc identity provider |
| Liệt kê các tài khoản có ít nhất một phiên | Nguồn user kết hợp truy vấn principal index, hoặc projection quản trị được duy trì riêng |
| Liệt kê tất cả phiên của hệ thống | Cơ chế quản trị/quan sát riêng; không coi principal index là user directory |

## 7. Thiết kế trang quản trị người dùng đang đăng nhập

Một trang quản trị có thể cần hiển thị người dùng nào đang có phiên hoạt động. Có hai cách thiết kế phổ biến.

**Cách thứ nhất: lấy trang người dùng từ user database rồi truy vấn phiên theo từng principal.**

Luồng:

1. Truy vấn trang tài khoản từ user database theo điều kiện và phân trang.
2. Với mỗi tài khoản trong trang, gọi `findByPrincipalName` bằng principal name ổn định.
3. Gắn số phiên hoặc metadata phiên vào DTO người dùng.
4. Trả kết quả cho giao diện quản trị.

Cách này giữ user database làm nguồn dữ liệu chính của tài khoản. Tuy nhiên, nếu gọi repository một lần cho mỗi người dùng, trang lớn có thể phát sinh nhiều truy vấn. Cần giới hạn kích thước trang, đo độ trễ và cân nhắc batching hoặc cache ngắn hạn cho dữ liệu hiển thị.

**Cách thứ hai: duy trì projection quản trị riêng.**

Nếu cần dashboard hoạt động thường xuyên với số lượng lớn, có thể duy trì bảng hoặc read model chứa thông tin tổng hợp như principal ID, số phiên đang hoạt động và lần hoạt động gần nhất. Projection được cập nhật từ luồng đăng nhập, logout, hết hạn và các sự kiện phiên.

Projection này là dữ liệu tổng hợp phục vụ quản trị, không thay thế user database hoặc session repository. Cần có cơ chế reconcile định kỳ vì sự kiện có thể đến trễ, bị bỏ lỡ hoặc khác nhau theo repository. Khi cần quyết định bảo mật như thu hồi phiên, luôn kiểm tra repository và trạng thái tài khoản có thẩm quyền.

## 8. Không quét Redis để xây dựng user directory

Một cách làm dễ bị cám dỗ là dùng `KEYS` hoặc `SCAN` để tìm tất cả key session, đọc hash rồi suy ra danh sách người dùng. Cách này không phù hợp để xây dựng API danh sách tài khoản:

- `KEYS` có thể chặn Redis trong lúc quét keyspace lớn.
- `SCAN` có thể trả kết quả theo từng batch và không tạo snapshot nhất quán khi dữ liệu đang thay đổi.
- Cấu trúc key/index là chi tiết triển khai có thể thay đổi theo phiên bản.
- Phiên hết hạn, key phụ trợ hoặc index dọn dẹp trễ có thể làm kết quả không phản ánh chính xác trạng thái nghiệp vụ.
- Người dùng chưa từng tạo phiên sẽ không xuất hiện.
- Phiên ẩn danh có thể không có principal để ánh xạ tới tài khoản.

`SCAN` có thể hữu ích cho công việc vận hành hoặc điều tra giới hạn trong môi trường kiểm soát, nhưng không nên biến việc quét key nội bộ thành cơ chế truy vấn người dùng của ứng dụng.

## 9. Thu hồi các phiên của một người dùng

Principal index đặc biệt hữu ích khi cần logout tất cả thiết bị của một tài khoản. Sau khi tìm các phiên theo principal, ứng dụng có thể thu hồi từng phiên bằng API repository phù hợp.

Ví dụ khái niệm:

~~~java
Map<String, ? extends Session> sessions =
        sessionRepository.findByPrincipalName(principalName);

for (String sessionId : sessions.keySet()) {
    sessionRepository.deleteById(sessionId);
}
~~~

Ví dụ này minh họa ý tưởng; kiểu repository và generic type thực tế cần được điều chỉnh theo implementation. `deleteById` là thao tác thu hồi phiên phía máy chủ. Trình duyệt của từng thiết bị có thể vẫn giữ cookie cũ, nhưng ID đó không còn ánh xạ tới phiên hợp lệ. Ứng dụng không thể xóa cookie từ xa trên mọi thiết bị; nó chỉ có thể làm cho session ID cũ mất hiệu lực ở server.

Trong môi trường nhiều request đồng thời, một phiên mới có thể được tạo sau khi truy vấn index hoặc trong lúc vòng lặp xóa đang chạy. Nếu yêu cầu logout toàn bộ phải bao gồm cả phiên tạo đồng thời, cần phối hợp với trạng thái tài khoản hoặc cơ chế thu hồi tập trung, chẳng hạn tăng `sessionVersion` của tài khoản và kiểm tra version ở các request nhạy cảm.

Không để endpoint thu hồi phiên có thể được gọi bởi người dùng thông thường cho principal tùy ý. Chỉ quản trị viên được ủy quyền hoặc chính chủ tài khoản theo chính sách mới được thực hiện hành động phù hợp. Ghi audit event với actor, đối tượng bị thu hồi, thời điểm và kết quả, nhưng không ghi session ID thô.

## 10. Hiệu năng và giới hạn của truy vấn

`findByPrincipalName` trả về map các session phù hợp với principal. API này không phải API phân trang user directory. Nếu một principal có rất nhiều phiên, kết quả có thể lớn và cần xử lý cẩn thận.

Các biện pháp:

- Đặt giới hạn số phiên đồng thời phù hợp với chính sách bảo mật.
- Không gọi truy vấn index cho hàng nghìn principal trong một request quản trị.
- Phân trang danh sách tài khoản trước khi tra cứu phiên.
- Chỉ tải metadata cần hiển thị, tránh trả toàn bộ thuộc tính session.
- Dùng projection hoặc cache ngắn hạn cho dashboard nếu cần quy mô lớn.
- Đo độ trễ Redis, số lượng phiên trên mỗi principal và chi phí serialization.

Principal index không thay thế giới hạn phiên đồng thời. Nếu cần giới hạn một tài khoản chỉ được có tối đa N phiên, hãy dùng cơ chế quản lý concurrent session phù hợp của Spring Security hoặc logic nghiệp vụ có đồng bộ để xử lý các request đăng nhập đồng thời. Chỉ truy vấn số phiên rồi quyết định tạo phiên mới có thể gặp race condition nếu nhiều lần đăng nhập xảy ra cùng lúc.

## 11. Kiểm thử principal index

Kiểm thử cần chứng minh quan hệ principal-session được tạo, truy vấn và xóa đúng.

Các trường hợp cơ bản:

| Kịch bản | Kết quả mong đợi |
|---|---|
| Tạo hai phiên với cùng principal | Truy vấn principal trả về cả hai session ID |
| Tạo phiên cho principal khác | Không xuất hiện trong kết quả của principal đầu |
| Tạo phiên ẩn danh không có principal | Không xuất hiện trong truy vấn principal |
| Tạo phiên và đặt principal index attribute | Repository có thể tìm phiên theo principal đó |
| Xóa một phiên | Phiên đó không còn trong kết quả sau khi index được cập nhật |
| Hết hạn phiên | Phiên không còn được coi là phiên hoạt động; kiểm tra cleanup/index theo repository |
| Đổi principal của phiên | Index cũ và mới được cập nhật theo hành vi repository đã cấu hình |
| Hai instance cùng dùng Redis | Phiên tạo ở instance A có thể được truy vấn ở instance B |

Ví dụ integration test có thể tạo session qua repository, đặt principal attribute và gọi `findByPrincipalName`. Dùng Redis test instance phù hợp để xác minh index thực tế; mock repository chỉ xác nhận code gọi đúng API, không chứng minh Redis index được tạo.

Ngoài ra, kiểm thử các trường hợp:

- Principal name có phân biệt chữ hoa/chữ thường hay không theo chính sách ứng dụng.
- Username đổi tên nhưng ID người dùng ổn định.
- Nhiều tenant có thể có cùng username; khi đó principal index cần giá trị duy nhất theo phạm vi tenant, ví dụ một principal key đã chuẩn hóa.
- Phiên hết hạn trong lúc trang quản trị đang đọc kết quả.
- Tài khoản bị khóa nhưng phiên cũ vẫn tồn tại; quyền truy cập phải kiểm tra trạng thái tài khoản, không dựa riêng vào index.

## 12. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| `findByPrincipalName` trả map rỗng cho người đã đăng nhập | Repository không hỗ trợ index hoặc principal không được lưu/giải phân giải | Dùng indexed repository và kiểm tra SecurityContext/principal attribute |
| Một user có nhiều thiết bị nhưng chỉ thấy một phiên | Các phiên không cùng principal key hoặc cách xác thực không đồng nhất | Chuẩn hóa principal name và kiểm thử nhiều phiên |
| Danh sách principal index thiếu tài khoản | Tài khoản không có phiên hoặc phiên chưa được index | Lấy danh sách tài khoản từ user database |
| Phiên ẩn danh không xuất hiện | Không có principal gắn với phiên | Đây là hành vi dự kiến; quản lý phiên ẩn danh theo use case riêng |
| Truy vấn dashboard chậm | Lặp truy vấn principal cho quá nhiều người dùng | Phân trang, batching hoặc duy trì projection quản trị |
| Thu hồi xong vẫn có phiên mới | Request đăng nhập đồng thời tạo session sau khi truy vấn index | Dùng session version hoặc chính sách thu hồi tập trung |
| Index còn tham chiếu phiên không còn tồn tại | Expiration event hoặc cleanup đang trễ | Kiểm tra repository và cơ chế dọn index; không sửa key nội bộ tùy tiện |

## 13. Checklist lựa chọn đúng API

- [ ] Cần biết tài khoản nào tồn tại: truy vấn user database/identity provider.
- [ ] Đã biết principal và cần tìm phiên của họ: dùng `findByPrincipalName`.
- [ ] Repository được cấu hình hỗ trợ principal index.
- [ ] Phiên đăng nhập có principal ổn định được lưu hoặc phân giải đúng.
- [ ] Phiên ẩn danh được hiểu là phiên không gắn principal.
- [ ] Không dùng Redis `KEYS`/`SCAN` để làm API danh sách tất cả người dùng.
- [ ] Dashboard lớn có phân trang hoặc projection riêng.
- [ ] Thu hồi phiên được bảo vệ bằng authorization và có audit.
- [ ] Không trả session ID hoặc thuộc tính nhạy cảm ra giao diện quản trị.
- [ ] Có integration test với Redis và nhiều instance.

Principal index của Spring Session Redis giúp tìm các phiên gắn với một principal đã biết. Nó trả lời câu hỏi về phiên, không trả lời câu hỏi về toàn bộ tài khoản trong hệ thống. Hãy để user database quản lý danh sách người dùng và dùng `FindByIndexNameSessionRepository` cho các thao tác cần tìm, đếm hoặc thu hồi phiên theo principal. Tách đúng hai nguồn dữ liệu giúp dashboard chính xác hơn, tránh quét Redis và giữ được ranh giới bảo mật khi vận hành nhiều instance.
