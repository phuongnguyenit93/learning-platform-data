# Giới hạn getAllPrincipals và tránh suy diễn khả năng liệt kê người dùng

Spring Session có thể lập chỉ mục session theo principal name để ứng dụng tìm các phiên đăng nhập của một người dùng. API FindByIndexNameSessionRepository còn có phương thức getAllPrincipals() ở các phiên bản hỗ trợ, cho phép lấy tập tên principal mà repository biết thông qua dữ liệu chỉ mục. Phương thức này hữu ích cho một số màn hình quản trị hoặc tác vụ vận hành, nhưng không phải API liệt kê toàn bộ tài khoản người dùng.

Phân biệt này rất quan trọng trong hệ thống nhiều phiên đăng nhập. Repository session chỉ quản lý các phiên mà nó lưu và các chỉ mục mà implementation duy trì. Nó không phải user directory, không biết mọi tài khoản đã đăng ký và không thể chứng minh một người dùng không tồn tại chỉ vì tên người dùng không xuất hiện trong kết quả. Hãy dùng nguồn dữ liệu người dùng chuyên trách để liệt kê tài khoản; dùng repository session để tra cứu các phiên gắn với một principal đã biết.

## 1. Principal index dùng để làm gì?

Một người dùng có thể đăng nhập trên nhiều thiết bị hoặc trình duyệt. Mỗi lần đăng nhập có thể tạo một session ID riêng. Khi cần hiển thị danh sách thiết bị, giới hạn số phiên hoặc thu hồi phiên từ xa, ứng dụng cần tìm các session theo danh tính người dùng thay vì chỉ tìm theo session ID từ cookie hiện tại.

Spring Session định nghĩa chỉ mục principal name thông qua hằng số:

~~~java
FindByIndexNameSessionRepository.PRINCIPAL_NAME_INDEX_NAME
~~~

Repository có thể dùng index này để ánh xạ principal name đến các session ID. API phổ biến:

- findByPrincipalName(principalName): tìm các session đã được index cho một principal.
- findByIndexNameAndIndexValue(indexName, indexValue): tìm theo tên index và giá trị index nếu implementation hỗ trợ.
- getAllPrincipals(): lấy tập principal mà repository có thể liệt kê theo khả năng của implementation và phiên bản.

Ví dụ, principal alice có ba session:

~~~text
alice
  -> session-A
  -> session-B
  -> session-C
~~~

Principal là danh tính người dùng; session ID là định danh của một phiên cụ thể. Một principal có thể không có session nào, có một session hoặc có nhiều session.

## 2. getAllPrincipals() trả lời câu hỏi nào?

getAllPrincipals() hướng đến tập principal có mặt trong dữ liệu index của repository. Tùy implementation và phiên bản, phương thức này có thể được hỗ trợ đầy đủ, bị giới hạn hoặc không cung cấp danh sách hữu ích. Cần đọc JavaDoc và kiểm tra hành vi của repository thực tế trước khi dựa vào kết quả.

Ngay cả khi implementation hỗ trợ, kết quả chỉ phản ánh principal mà repository biết qua các session và index của nó. Nó không trả về:

- Tất cả tài khoản trong cơ sở dữ liệu người dùng.
- Người dùng chưa từng đăng nhập.
- Người dùng đã đăng xuất và không còn session.
- Người dùng chỉ có danh tính trong hệ thống OAuth/OIDC nhưng chưa tạo session tại ứng dụng.
- Tài khoản bị khóa, đã xóa hoặc chưa kích hoạt nếu các trạng thái đó không được lưu trong session index.
- Mọi principal ở các repository, namespace hoặc ứng dụng khác.

Vì vậy, tên phương thức có chữ all không có nghĩa là tất cả người dùng của sản phẩm. Phạm vi của nó là principal mà repository có thể liệt kê, không phải toàn bộ danh tính trong hệ thống.

## 3. Khác biệt giữa danh sách principal và danh sách người dùng

User directory là nguồn dữ liệu quản lý tài khoản: ID người dùng, tên hiển thị, trạng thái hoạt động, email, vai trò, tenant và các thuộc tính hồ sơ. Session repository là kho trạng thái phiên: session ID, thời điểm tạo, thời điểm truy cập, timeout và thuộc tính phiên.

| Nhu cầu | Nguồn dữ liệu phù hợp |
| --- | --- |
| Liệt kê tất cả tài khoản, kể cả chưa đăng nhập | User database hoặc Identity Provider |
| Tìm các phiên của một principal đã biết | FindByIndexNameSessionRepository |
| Xem số session đang được index cho một principal | Repository session, có lưu ý về độ mới và khả năng của implementation |
| Tìm người dùng đã đăng nhập trong một khoảng thời gian | Audit/event store hoặc dữ liệu hoạt động chuyên biệt |
| Kiểm tra tài khoản có bị khóa hay không | User directory hoặc Identity Provider |
| Thu hồi các session của một người dùng | Repository session sau khi xác thực principal và quyền thao tác |

Không dùng getAllPrincipals() để xây dựng trang quản trị người dùng, thống kê tổng số tài khoản, phân trang danh sách khách hàng hoặc tính tỷ lệ người dùng hoạt động toàn hệ thống. Các phép tính đó cần nguồn dữ liệu có định nghĩa rõ ràng và khả năng truy vấn đầy đủ.

## 4. Giới hạn do implementation và phiên bản

FindByIndexNameSessionRepository là abstraction. Các implementation có thể lưu index bằng cấu trúc dữ liệu khác nhau và có mức hỗ trợ liệt kê khác nhau. Một số implementation có thể hỗ trợ truy vấn theo một principal đã biết nhưng không tối ưu hoặc không hỗ trợ liệt kê toàn bộ principal.

Khi sử dụng getAllPrincipals():

1. Kiểm tra phiên bản Spring Session đang dùng và JavaDoc của interface.
2. Kiểm tra implementation cụ thể, ví dụ JDBC indexed repository hoặc Redis indexed repository.
3. Xác nhận phương thức có được hỗ trợ và có giới hạn về backend, cluster mode hoặc cấu hình hay không.
4. Xác định kết quả rỗng có nghĩa là không có principal được index hay implementation không cung cấp tính năng liệt kê.
5. Kiểm tra chi phí truy vấn và giới hạn số lượng phần tử.
6. Kiểm thử với repository thật và dữ liệu có nhiều session.

Không suy luận từ việc code biên dịch thành công rằng backend có thể liệt kê toàn bộ principal hiệu quả. Một method có mặt trong interface vẫn có thể có semantics giới hạn hoặc implementation cụ thể có thể không hỗ trợ đầy đủ.

Nếu phương thức ném UnsupportedOperationException, không bắt exception rồi chuyển thành danh sách người dùng rỗng. Hãy coi đây là dấu hiệu chức năng liệt kê không được hỗ trợ và chuyển sang nguồn dữ liệu phù hợp. Nếu implementation trả tập rỗng cho trường hợp không hỗ trợ, cần dựa vào tài liệu và kiểm thử để phân biệt với trường hợp thực sự không có principal nào được index.

## 5. Ví dụ sử dụng API một cách thận trọng

Ví dụ sau minh họa việc lấy tập principal từ repository nếu implementation hỗ trợ:

~~~java
import java.util.Set;
import org.springframework.session.FindByIndexNameSessionRepository;
import org.springframework.session.Session;

class SessionPrincipalInspector {

    private final FindByIndexNameSessionRepository<? extends Session> sessions;

    SessionPrincipalInspector(
            FindByIndexNameSessionRepository<? extends Session> sessions) {
        this.sessions = sessions;
    }

    Set<String> indexedPrincipals() {
        return sessions.getAllPrincipals();
    }
}
~~~

Đây là ví dụ ở tầng repository. Trước khi dùng trong ứng dụng, xác nhận generic type, method và implementation của dependency. Không trả nguyên tập principal này cho bất kỳ người dùng nào nếu chưa có kiểm tra quyền quản trị và chính sách bảo vệ thông tin định danh.

Nếu mục tiêu là tìm phiên của một người dùng đã xác thực, không cần gọi getAllPrincipals(). Dùng principal của người gọi rồi gọi findByPrincipalName():

~~~java
Map<String, ? extends Session> findSessionsFor(
        FindByIndexNameSessionRepository<? extends Session> repository,
        String authenticatedPrincipal) {
    return repository.findByPrincipalName(authenticatedPrincipal);
}
~~~

Trong ví dụ thực tế, authenticatedPrincipal phải được lấy từ Authentication hoặc security context đáng tin cậy, không lấy tùy ý từ query parameter. Đoạn mã là đồng bộ vì interface được dùng ở đây là imperative; nếu ứng dụng WebFlux, dùng reactive repository tương ứng và compose Mono thay vì gọi API đồng bộ trên event loop.

## 6. Kết quả rỗng không chứng minh người dùng không tồn tại

Giả sử getAllPrincipals() không trả về tên bob. Chỉ có thể kết luận rằng lần gọi này không cung cấp principal bob trong tập kết quả. Không thể kết luận tài khoản bob không tồn tại.

Có nhiều khả năng:

- bob có tài khoản nhưng chưa đăng nhập.
- bob đã đăng xuất và không còn session.
- bob đăng nhập ở ứng dụng hoặc repository khác.
- session của bob chưa được index theo principal.
- resolver không nhận diện được principal từ session.
- index chưa được cập nhật hoặc bị ảnh hưởng bởi lỗi lưu trữ.
- implementation không hỗ trợ liệt kê toàn bộ principal.
- cấu hình namespace hoặc tenant khiến truy vấn đang nhìn vào một phạm vi dữ liệu khác.

Tương tự, nếu bob xuất hiện trong kết quả, điều đó không chứng minh tài khoản vẫn đang hoạt động hoặc được phép truy cập. Tài khoản có thể đã bị khóa trong user database trong khi session cũ chưa được thu hồi.

Khi cần xác minh một tài khoản, truy vấn user directory. Khi cần xác minh một phiên, truy vấn repository bằng principal hoặc session ID và kiểm tra trạng thái phiên theo API được hỗ trợ.

## 7. Principal index phụ thuộc vào resolver

Repository không thể tự suy ra danh tính người dùng từ mọi thuộc tính tùy ý. Một IndexResolver cần trích xuất principal name theo cấu trúc mà ứng dụng sử dụng. Trong ứng dụng Spring Security, resolver mặc định có thể đọc principal từ SecurityContext được lưu trong session.

Nếu ứng dụng dùng cơ chế xác thực tùy chỉnh, cần kiểm tra:

- SecurityContext có được lưu trong session hay không.
- Resolver có đọc đúng thuộc tính chứa Authentication hay không.
- Principal name có ổn định và nhất quán giữa các instance không.
- Session được tạo trước đăng nhập có được index sau khi xác thực hay không.
- Thay đổi principal hoặc logout có cập nhật/xóa index tương ứng hay không.

Một session không có principal index vẫn có thể là session hợp lệ. Ví dụ session ẩn danh được tạo trước khi đăng nhập có thể chưa gắn với người dùng nào. Không tính các session đó thành một người dùng riêng và không dùng index rỗng để đại diện danh tính.

## 8. Index có thể không phản ánh trạng thái tài khoản theo thời gian thực

Index phục vụ tra cứu session, không phải bảng trạng thái tài khoản. Độ mới của kết quả phụ thuộc cách repository cập nhật index, cách backend xử lý expiration và trạng thái kết nối.

Một số yếu tố có thể ảnh hưởng:

- Session hết hạn nhưng tác vụ dọn hoặc notification chưa được xử lý.
- Redis Pub/Sub notification bị bỏ lỡ khi listener mất kết nối.
- Database cleanup chạy theo lịch, nên bản ghi hết hạn có thể còn tồn tại vật lý.
- Một phiên bản ứng dụng thay đổi resolver hoặc cách chuẩn hóa principal.
- Thao tác đăng xuất và tra cứu diễn ra đồng thời.
- Nhiều instance ghi/xóa session cùng lúc.

Vì vậy, không coi kết quả getAllPrincipals() là ảnh chụp chính xác, nguyên tử của mọi người dùng đang đăng nhập tại một thời điểm. Nếu cần chỉ số hoạt động chính xác, thiết kế event/audit pipeline và đối soát với dữ liệu session theo yêu cầu nghiệp vụ.

## 9. Không dùng getAllPrincipals() để thực thi chính sách bảo mật

Không dùng danh sách principal trả về để quyết định một người dùng có được phép truy cập hay không. Việc không xuất hiện trong danh sách không chứng minh tài khoản bị vô hiệu hóa; việc xuất hiện cũng không chứng minh tài khoản được phép.

Các chính sách cần kiểm tra riêng:

- Tài khoản có tồn tại và đang hoạt động không: user directory hoặc Identity Provider.
- Người dùng đã xác thực chưa: Spring Security Authentication.
- Session hiện tại còn hợp lệ không: WebSession/HttpSession và repository.
- Người dùng có quyền thao tác trên session của principal khác không: authorization policy.
- Có cần thu hồi tất cả phiên không: quy trình thu hồi được bảo vệ và có kiểm soát đồng thời.

Ví dụ, tài khoản bị khóa phải bị từ chối ở lớp xác thực/authorization ngay cả khi session index vẫn còn. Khi khóa tài khoản, ứng dụng có thể chủ động tìm và thu hồi các session của principal đó, nhưng việc kiểm tra trạng thái khóa không được phụ thuộc vào việc getAllPrincipals() có liệt kê tên người dùng hay không.

## 10. Quy trình quản lý nhiều phiên cho một principal

Đối với chức năng quản lý thiết bị, nên đi theo quy trình:

1. Lấy principal của người gọi từ security context đã xác thực.
2. Kiểm tra người gọi có quyền xem hoặc thu hồi phiên theo yêu cầu.
3. Gọi findByPrincipalName(principal) để lấy các session của người dùng đó.
4. Chuyển session thành metadata an toàn như thời điểm tạo, lần truy cập cuối và nhãn thiết bị.
5. Không trả session ID thô, cookie hoặc toàn bộ thuộc tính session cho client.
6. Khi thu hồi, xác nhận mục tiêu thuộc principal được phép quản lý rồi gọi API xóa session.
7. Ghi audit event không chứa credential và theo dõi kết quả thao tác.

getAllPrincipals() không cần thiết trong luồng này vì principal đã được biết từ Authentication. Dùng truy vấn trực tiếp theo principal vừa rõ phạm vi, vừa tránh liệt kê toàn bộ index.

## 11. Khi nào cần danh sách người dùng đang có session?

Một trang vận hành có thể cần hiển thị người dùng nào đang có phiên. Nếu yêu cầu chỉ là một báo cáo gần đúng về các principal có session trong repository, có thể cân nhắc getAllPrincipals() sau khi xác nhận implementation hỗ trợ và chi phí phù hợp.

Nếu yêu cầu là báo cáo kiểm toán hoặc số liệu sản phẩm, cần xác định chính xác định nghĩa:

- “Có session” nghĩa là có entry trong repository hay có session chưa hết idle timeout?
- Session ẩn danh có được tính không?
- Principal đã bị khóa có được tính không?
- Có bao gồm tất cả tenant và ứng dụng không?
- Có chấp nhận độ trễ do cleanup hoặc index update không?
- Có cần lịch sử đăng nhập và đăng xuất hay chỉ trạng thái hiện tại?

Đối với audit, nên ghi sự kiện đăng nhập, đăng xuất, timeout và thu hồi vào kho sự kiện hoặc audit log chuyên biệt. getAllPrincipals() không lưu lịch sử và không cho biết thời điểm một principal đã đăng nhập hoặc rời hệ thống.

## 12. Chi phí và khả năng mở rộng

Liệt kê principal có thể tốn tài nguyên tùy implementation. Nếu backend phải quét index hoặc tổng hợp nhiều cấu trúc dữ liệu, chi phí có thể tăng theo số lượng session và số principal. API trả Set cũng không cung cấp cơ chế phân trang trong chữ ký cơ bản.

Các nguyên tắc vận hành:

- Không gọi getAllPrincipals() trên mỗi HTTP request.
- Không dùng nó làm nguồn cho dashboard phải refresh liên tục.
- Đặt timeout và giới hạn thời gian cho tác vụ quản trị.
- Chạy báo cáo lớn trong job nền, không chặn request người dùng.
- Đo thời gian truy vấn, kích thước kết quả và tải Redis/database.
- Nếu cần phân trang hoặc báo cáo toàn hệ thống, dùng bảng nghiệp vụ/audit được thiết kế cho truy vấn đó.
- Tránh log toàn bộ danh sách principal; đây có thể là dữ liệu cá nhân.

Với số lượng principal lớn, cân nhắc lưu số liệu tổng hợp hoặc phát sự kiện sang hệ thống phân tích thay vì quét repository session liên tục.

## 13. Kiểm thử giới hạn của getAllPrincipals()

Kiểm thử cần xác nhận hành vi của đúng repository implementation và phiên bản đang chạy. Không chỉ mock một Set có vài tên rồi kết luận tính năng hoạt động.

Các kịch bản nên có:

| Kịch bản | Thiết lập | Điều cần xác nhận |
| --- | --- | --- |
| Không có session | Repository rỗng | Kết quả và semantics khi không có principal |
| Một principal, một session | Tạo session có principal index | Principal xuất hiện nếu implementation hỗ trợ liệt kê |
| Một principal, nhiều session | Tạo nhiều phiên cho cùng principal | Principal vẫn là một phần tử; tra cứu theo principal trả các phiên |
| Người dùng chưa đăng nhập | Tài khoản chỉ tồn tại trong user database | Không suy ra tài khoản không tồn tại từ kết quả repository |
| Session ẩn danh | Tạo session không có principal index | Không kỳ vọng principal lookup tìm được |
| Hết hạn hoặc logout | Cho session hết hạn hoặc xóa | Kiểm tra index được dọn theo semantics implementation |
| Implementation không hỗ trợ | Dùng backend/phiên bản giới hạn | Xác nhận trả rỗng, exception hoặc hành vi được tài liệu hóa |
| Nhiều instance | Tạo/xóa session từ các instance khác nhau | Xác nhận các instance dùng cùng repository/index |
| Namespace khác nhau | Tạo session ở hai ứng dụng hoặc tenant | Xác nhận phạm vi kết quả không bị hiểu nhầm là toàn hệ thống |

Ví dụ kiểm thử ý tưởng với JUnit:

~~~java
@Test
void principalEnumerationIsOnlyRepositoryIndexData() {
    Set<String> principals = repository.getAllPrincipals();

    // Chỉ xác nhận hợp đồng của implementation test đang dùng.
    // Không suy ra danh sách này bằng với user directory.
    assertThat(principals).contains("user-17");
}
~~~

Test này cần fixture session có principal index được lưu trước đó. Với implementation không hỗ trợ enumeration, viết test riêng để xác nhận đúng hành vi được tài liệu hóa; không ép tất cả backend phải trả cùng một tập dữ liệu.

## 14. Xử lý khi kết quả không như mong đợi

Nếu getAllPrincipals() trả rỗng hoặc thiếu principal:

1. Xác nhận repository đang dùng đúng implementation và phiên bản.
2. Đọc JavaDoc và tài liệu của method ở phiên bản đó.
3. Xác nhận implementation hỗ trợ enumeration hay chỉ hỗ trợ tìm theo principal đã biết.
4. Kiểm tra session có được lưu và principal index có được tạo không.
5. Kiểm tra IndexResolver, SecurityContext và cách chuẩn hóa principal.
6. Kiểm tra Redis/database namespace, quyền truy cập và tình trạng index.
7. Kiểm tra session expiration, cleanup và lỗi listener có thể ảnh hưởng dữ liệu phụ trợ.
8. Dùng user directory để xác minh tài khoản có tồn tại và đang hoạt động hay không.

Không tự tạo danh sách principal bằng cách quét key nội bộ Redis hoặc đọc trực tiếp bảng implementation-specific nếu chưa có hợp đồng hỗ trợ. Cấu trúc key, index và schema có thể thay đổi giữa các phiên bản; truy vấn trực tiếp còn có thể bỏ qua quy tắc serialization, expiration và cleanup của repository.

## 15. Nguyên tắc sử dụng

- Xem getAllPrincipals() là khả năng liệt kê principal từ repository index, không phải danh sách người dùng.
- Kiểm tra hỗ trợ và semantics của implementation/version trước khi sử dụng.
- Không diễn giải kết quả rỗng thành “không có tài khoản” hoặc “tài khoản không hợp lệ”.
- Dùng user database hoặc Identity Provider để liệt kê và xác minh người dùng.
- Dùng findByPrincipalName() để tìm các phiên của một principal đã biết.
- Dùng Authentication và authorization để bảo vệ chức năng xem/thu hồi session.
- Không coi principal index là audit log hoặc ảnh chụp nguyên tử của trạng thái đăng nhập.
- Đánh giá chi phí khi liệt kê số lượng principal lớn; tránh gọi trong request thường xuyên.
- Kiểm thử với repository thật, nhiều session, expiration, logout và nhiều instance.

getAllPrincipals() có thể hữu ích khi cần quan sát principal đang được repository session index ghi nhận, nhưng phạm vi và độ đầy đủ phụ thuộc implementation, phiên bản và trạng thái index. Nó không phải cơ chế khám phá toàn bộ người dùng của hệ thống. Trong ứng dụng nhiều phiên đăng nhập, hãy lấy danh tính từ security context, tra cứu các session theo principal đã biết và dùng user directory hoặc Identity Provider cho mọi nghiệp vụ cần danh sách tài khoản đầy đủ.
