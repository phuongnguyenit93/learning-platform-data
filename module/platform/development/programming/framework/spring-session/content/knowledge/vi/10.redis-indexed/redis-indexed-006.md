# Tạo, cập nhật, xóa chỉ mục khi phiên hoặc danh tính thay đổi

Redis có thể lưu dữ liệu phiên Spring Session cùng các chỉ mục giúp tìm phiên theo một giá trị nghiệp vụ, phổ biến nhất là tên người dùng đã xác thực. Với repository có hỗ trợ chỉ mục, ứng dụng có thể tìm tất cả phiên của một principal để hiển thị thiết bị đang đăng nhập, giới hạn số phiên đồng thời hoặc thu hồi phiên khi tài khoản bị khóa.

Chỉ mục phải phản ánh đúng trạng thái hiện tại của phiên. Khi phiên được tạo, thay đổi danh tính hoặc bị xóa, các thành viên trong tập chỉ mục cũng phải được thêm, chuyển hoặc loại bỏ tương ứng. Nếu chỉ cập nhật hash dữ liệu phiên mà bỏ quên chỉ mục, truy vấn theo principal có thể trả kết quả cũ, thiếu phiên hoặc khiến thao tác quản trị thu hồi nhầm phiên.

Bài học tập trung vào RedisIndexedSessionRepository trong Spring Session. Đây là phần mở rộng của quản lý phiên dùng Redis, với khả năng tra cứu phiên theo chỉ mục. Repository JDBC và các repository khác có thể có cách hỗ trợ truy vấn riêng; không nên giả định chúng có cùng cấu trúc chỉ mục nội bộ của Redis.

## 1. Vì sao cần chỉ mục phiên?

Nếu chỉ lưu phiên theo session ID, ứng dụng có thể tải một phiên khi đã biết ID. Nhưng một số nghiệp vụ bắt đầu từ danh tính thay vì ID phiên:

- Hiển thị các phiên đang hoạt động của một người dùng.
- Đăng xuất tất cả thiết bị khi tài khoản bị khóa hoặc đổi mật khẩu.
- Giới hạn một tài khoản chỉ được có một số phiên đồng thời.
- Tìm phiên theo tenant, loại client hoặc một thuộc tính nghiệp vụ đã được cho phép lập chỉ mục.
- Hỗ trợ quản trị và kiểm toán các phiên đang tồn tại.

Không có chỉ mục, ứng dụng phải quét toàn bộ kho phiên rồi đọc từng bản ghi để tìm principal phù hợp. Cách này tốn tài nguyên và khó mở rộng khi số phiên tăng. Chỉ mục ánh xạ một giá trị như tên principal đến các session ID liên quan, nhờ đó truy vấn có thể đi thẳng đến nhóm phiên cần tìm.

Trong Spring Session, giao diện FindByIndexNameSessionRepository cung cấp khả năng tìm phiên theo tên chỉ mục và giá trị. RedisIndexedSessionRepository là implementation dành cho Redis hỗ trợ kiểu truy vấn này.

## 2. Phân biệt dữ liệu phiên và dữ liệu chỉ mục

Dữ liệu phiên chứa các thuộc tính mà ứng dụng cần khôi phục giữa các request. Chỉ mục là cấu trúc phụ trợ giúp tìm các phiên có đặc điểm nhất định.

Ví dụ, một người dùng có hai phiên:

| Session ID | Principal | Client | Trạng thái |
|---|---|---|---|
| S-101 | alice | Web | Đang hoạt động |
| S-202 | alice | Mobile | Đang hoạt động |

Dữ liệu phiên của S-101 và S-202 được lưu riêng. Chỉ mục principal có thể biểu diễn quan hệ:

    principal:alice -> { S-101, S-202 }

Khi truy vấn theo principal alice, repository trả về hai phiên. Chỉ mục không thay thế bản ghi phiên và cũng không phải nguồn xác thực. Nó chỉ là cấu trúc tra cứu.

Một số khái niệm cần tách biệt:

| Thành phần | Vai trò |
|---|---|
| Session hash/document | Lưu thuộc tính phiên, thời gian tạo, thời gian truy cập và thời hạn |
| Principal index | Ánh xạ principal name đến các session ID |
| Custom index | Ánh xạ một thuộc tính bổ sung như tenant hoặc loại client đến session ID |
| Session ID | Định danh duy nhất của một phiên |
| Principal | Danh tính được xác thực, thường lấy từ Authentication |

Tên key và cách mã hóa nội bộ của RedisIndexedSessionRepository có thể thay đổi theo phiên bản. Hãy coi cấu trúc Redis nội bộ là chi tiết triển khai của repository; không xây dựng ứng dụng phụ thuộc trực tiếp vào tên key hoặc format serialization đó.

## 3. RedisIndexedSessionRepository và principal index

RedisIndexedSessionRepository triển khai khả năng tìm phiên theo chỉ mục thông qua FindByIndexNameSessionRepository. Chỉ mục mặc định quan trọng nhất là principal name, được định danh bằng hằng số FindByIndexNameSessionRepository.PRINCIPAL_NAME_INDEX_NAME.

Khi Spring Security lưu SecurityContext vào HTTP session, PrincipalNameIndexResolver có thể trích xuất tên principal từ thông tin xác thực trong session. Giá trị này được dùng để lập chỉ mục. Trong cấu hình Spring Security thông thường, tên principal thường tương ứng với Authentication.getName(), nhưng ứng dụng có thể dùng username, email hoặc một định danh khác tùy cách triển khai UserDetails và Authentication.

Một số điểm cần nhớ:

- Chỉ mục principal xuất hiện khi session có dữ liệu đủ để resolver xác định principal.
- Session ẩn danh hoặc session chưa đăng nhập có thể chưa có principal index.
- Nếu ứng dụng dùng tên thuộc tính SecurityContext tùy chỉnh hoặc lưu danh tính theo cách riêng, resolver mặc định có thể không trích xuất được.
- Việc tìm theo principal không chứng minh phiên còn được phép truy cập một chức năng; Spring Security vẫn phải xác thực và phân quyền cho từng request.
- Repository phải thực sự là loại indexed. Một Redis repository chỉ lưu phiên theo ID không tự cung cấp các truy vấn theo principal.

Với Spring Boot, hãy kiểm tra cấu hình Redis Session của đúng phiên bản và chọn repository indexed khi phiên bản đó yêu cầu lựa chọn tường minh. Trong các cấu hình Java, có thể tạo hoặc tùy chỉnh RedisIndexedSessionRepository và cấu hình IndexResolver. Không nên chỉ thêm dependency Redis rồi mặc định rằng mọi repository đều có đầy đủ chỉ mục.

## 4. Tạo chỉ mục khi phiên được tạo và xác thực

Một phiên có thể được tạo trước khi người dùng đăng nhập. Ví dụ, client truy cập trang công khai và ứng dụng tạo session để lưu tùy chọn ngôn ngữ. Ở thời điểm đó, chưa có principal nên chỉ mục principal chưa có thành viên.

Khi người dùng đăng nhập thành công, Spring Security lưu Authentication hoặc SecurityContext vào session. Khi repository lưu phiên với trạng thái mới, resolver có thể xác định principal name và repository cập nhật chỉ mục tương ứng.

Luồng khái quát:

    Request chưa xác thực
           |
           v
    Tạo HttpSession
           |
           v
    Lưu session vào Redis
           |
           | Chưa có principal
           v
    Chưa có thành viên trong principal index
           |
           v
    Người dùng đăng nhập thành công
           |
           v
    Lưu SecurityContext vào session
           |
           v
    Repository lưu thay đổi
           |
           v
    Resolver tìm principal name
           |
           v
    Thêm session ID vào principal index

Ví dụ truy vấn các phiên theo principal:

~~~java
import org.springframework.session.FindByIndexNameSessionRepository;
import org.springframework.session.Session;

import java.util.Map;

public class UserSessionService {

    private final FindByIndexNameSessionRepository<? extends Session> sessions;

    public UserSessionService(
            FindByIndexNameSessionRepository<? extends Session> sessions) {
        this.sessions = sessions;
    }

    public Map<String, ? extends Session> findSessions(String principalName) {
        return sessions.findByIndexNameAndIndexValue(
                FindByIndexNameSessionRepository.PRINCIPAL_NAME_INDEX_NAME,
                principalName
        );
    }
}
~~~

Đoạn mã minh họa cách truy vấn qua abstraction của Spring Session. Trong ứng dụng thật, nên đặt thao tác này trong service và giới hạn quyền gọi theo chính sách quản trị hoặc quyền của chính người dùng.

Không nên tự thêm session ID vào Redis set principal bằng một lệnh riêng trong controller nếu repository đã chịu trách nhiệm lập chỉ mục. Việc đó dễ tạo hai nguồn dữ liệu không đồng nhất khi phiên được đổi ID, cập nhật principal hoặc bị xóa.

## 5. Cập nhật chỉ mục khi danh tính thay đổi

Một phiên có thể thay đổi danh tính trong các luồng đặc biệt: chuyển từ session ẩn danh sang đăng nhập, chuyển tài khoản trong cùng trình duyệt, đăng nhập bằng cơ chế impersonation có kiểm soát, hoặc thay đổi principal sau khi xác thực lại.

Giả sử session S-101 ban đầu thuộc principal alice, sau đó được chuyển sang bob. Chỉ mục cần phản ánh trạng thái mới:

    Trước:
      principal:alice -> { S-101, S-202 }
      principal:bob   -> { S-303 }

    Sau khi S-101 đổi principal:
      principal:alice -> { S-202 }
      principal:bob   -> { S-303, S-101 }

Đây là một thay đổi gồm hai phía: loại S-101 khỏi tập cũ và thêm S-101 vào tập mới. Nếu chỉ thêm vào chỉ mục bob mà không loại khỏi alice, truy vấn alice vẫn có thể trả về một session không còn thuộc alice. Nếu chỉ xóa khỏi alice mà không thêm vào bob, truy vấn bob sẽ thiếu phiên.

Với RedisIndexedSessionRepository và resolver được cấu hình đúng, repository quản lý việc cập nhật chỉ mục dựa trên dữ liệu phiên mà nó lưu. Ứng dụng cần bảo đảm thay đổi Authentication/SecurityContext thực sự được lưu vào session. Nếu thay đổi một đối tượng mutable trong bộ nhớ mà không đánh dấu thuộc tính session đã thay đổi, tùy SaveMode và repository, thay đổi có thể không được ghi như dự kiến. Khi cần, hãy lưu lại thuộc tính qua session.setAttribute hoặc dùng cơ chế lưu SecurityContext đúng của Spring Security.

Ví dụ cập nhật SecurityContext theo cách khái niệm:

~~~java
SecurityContext context = SecurityContextHolder.createEmptyContext();
context.setAuthentication(newAuthentication);

SecurityContextHolder.setContext(context);
request.getSession().setAttribute(
        "SPRING_SECURITY_CONTEXT",
        context
);
~~~

Trong ứng dụng Spring Security hiện đại, nên để SecurityContextRepository và cơ chế xác thực của framework lưu context đúng cách; đoạn mã trên chỉ minh họa việc thuộc tính xác thực trong session phải được cập nhật để resolver có thể thấy principal mới. Không tự ghi đè context nếu ứng dụng đã có một authentication flow được cấu hình.

Thay đổi principal cũng là một điểm nhạy cảm về bảo mật. Khi chuyển từ alice sang bob, cần xác định rõ session hiện tại có được phép tái sử dụng hay phải invalidate và tạo phiên mới. Bảo vệ session fixation, xóa quyền cũ và thay ID theo chiến lược của Spring Security cần được thực hiện trước khi cho request tiếp tục sử dụng danh tính mới.

## 6. Xóa chỉ mục khi phiên bị xóa hoặc hết hạn

Khi phiên bị invalidate hoặc bị xóa bởi repository, session ID phải được loại khỏi các chỉ mục liên quan. Nếu không, chỉ mục có thể chứa session ID trỏ đến phiên đã không còn tồn tại.

Với RedisIndexedSessionRepository, việc xóa qua repository là đường chính để phối hợp xóa dữ liệu phiên và cập nhật chỉ mục. Ví dụ:

~~~java
public void revokeSession(String sessionId) {
    sessions.deleteById(sessionId);
}
~~~

Nếu cần đăng xuất tất cả phiên của một principal, có thể tìm phiên theo principal rồi xóa từng ID:

~~~java
public void revokeAllSessions(String principalName) {
    Map<String, ? extends Session> matches =
            sessions.findByIndexNameAndIndexValue(
                    FindByIndexNameSessionRepository.PRINCIPAL_NAME_INDEX_NAME,
                    principalName
            );

    for (String sessionId : matches.keySet()) {
        sessions.deleteById(sessionId);
    }
}
~~~

Ví dụ trên thể hiện luồng cơ bản. Với hệ thống nhiều request đồng thời, cần xem xét việc người dùng tạo phiên mới trong lúc quá trình thu hồi đang chạy. Nếu yêu cầu là đăng xuất mọi thiết bị tại một thời điểm, ứng dụng nên có cơ chế thu hồi theo tài khoản và kiểm tra thêm trạng thái tài khoản trong mọi request theo chính sách.

Không xóa trực tiếp Redis hash hoặc set index bằng lệnh DEL/SREM tùy tiện. Thao tác trực tiếp có thể bỏ qua expiration metadata, event, namespace hoặc các cấu trúc phụ trợ mà repository cần duy trì. Hãy dùng API của SessionRepository/FindByIndexNameSessionRepository để xóa phiên.

## 7. Chỉ mục có thể trễ hoặc chứa thành viên cũ

Trong hệ phân tán, cập nhật session và chỉ mục có thể liên quan đến nhiều thao tác Redis. Sự kiện hết hạn cũng có thể được xử lý trễ nếu phụ thuộc Redis keyspace notifications. Vì vậy, cần phân biệt:

- Phiên không còn hợp lệ theo repository.
- Chỉ mục đã được cập nhật.
- Tác vụ dọn dữ liệu phụ hoặc sự kiện đã được xử lý hoàn tất.

Nếu sự kiện expiration bị trì hoãn hoặc mất, thành viên cũ có thể tồn tại trong cấu trúc chỉ mục lâu hơn dự kiến, tùy implementation và cấu hình. Khi truy vấn theo index, repository có thể kiểm tra lại phiên hoặc xử lý phần tử cũ theo cách riêng; không nên dựa vào giả định mọi kết quả index luôn là phiên đang hoạt động.

Một số nguyên tắc vận hành:

- Dùng API repository để truy vấn và thu hồi phiên.
- Xác minh session còn tồn tại và còn hợp lệ trước thao tác quản trị quan trọng.
- Không dùng index làm nguồn duy nhất để quyết định quyền truy cập.
- Theo dõi số lượng session ID trong index và số phiên thực tế.
- Kiểm thử trường hợp Redis notification đến muộn, listener mất kết nối và instance khởi động lại.
- Nếu có custom index, thiết kế một tác vụ đối soát có thể loại bỏ thành viên mồ côi.

Chỉ mục là dữ liệu dẫn xuất từ phiên. Khi có mâu thuẫn, trạng thái phiên trong repository và chính sách bảo mật mới là căn cứ để quyết định request có được phép tiếp tục hay không.

## 8. Tạo custom index cho tenant hoặc loại client

Ngoài principal name, ứng dụng có thể cần tìm phiên theo tenant, loại thiết bị hoặc một thuộc tính khác. Ví dụ, hệ thống đa tenant muốn tìm phiên thuộc tenant tenant-42, hoặc trang quản trị cần liệt kê các phiên mobile.

Spring Session cung cấp abstraction IndexResolver để xác định các cặp tên chỉ mục và giá trị chỉ mục từ một Session. Với RedisIndexedSessionRepository, có thể cấu hình resolver tùy chỉnh để trả thêm index bên cạnh principal index.

Ví dụ khái niệm resolver kết hợp:

~~~java
public class TenantAndPrincipalIndexResolver
        implements IndexResolver<Session> {

    private final IndexResolver<Session> principalResolver =
            new PrincipalNameIndexResolver();

    @Override
    public Map<String, String> resolveIndexesFor(Session session) {
        Map<String, String> indexes =
                new HashMap<>(principalResolver.resolveIndexesFor(session));

        String tenantId = session.getAttribute("tenantId");
        if (tenantId != null && !tenantId.isBlank()) {
            indexes.put("tenantId", tenantId);
        }

        String clientType = session.getAttribute("clientType");
        if (clientType != null && !clientType.isBlank()) {
            indexes.put("clientType", clientType);
        }

        return indexes;
    }
}
~~~

Đây là ví dụ minh họa ý tưởng; package, generic type và cách đăng ký resolver cần khớp phiên bản Spring Session đang dùng. Khi thay resolver mặc định, hãy giữ lại khả năng phân giải principal nếu ứng dụng vẫn cần tra cứu theo người dùng. Một resolver chỉ trả tenantId có thể vô tình làm mất principal index.

Các thuộc tính dùng để lập chỉ mục phải được ghi vào session trước khi repository lưu phiên. Nếu tenant hoặc clientType thay đổi, repository phải nhận được thay đổi đó để cập nhật membership. Không dùng một giá trị do client gửi trực tiếp làm tenant identity mà chưa xác minh từ authentication hoặc dữ liệu tin cậy.

Khi tra cứu custom index, dùng tên index chính xác:

~~~java
Map<String, ? extends Session> tenantSessions =
        sessions.findByIndexNameAndIndexValue("tenantId", "tenant-42");
~~~

Chỉ mục tenant có thể chứa nhiều phiên của nhiều người dùng. Vì vậy, kết quả truy vấn vẫn phải được kiểm tra theo phạm vi tenant và quyền của người gọi.

## 9. Cập nhật chỉ mục khi session ID thay đổi

Session ID có thể được thay đổi sau xác thực để phòng session fixation hoặc khi ứng dụng chủ động đổi định danh. Vì chỉ mục thường chứa session ID làm thành viên, việc đổi ID phải được repository phối hợp với dữ liệu chỉ mục.

Không tự xóa session cũ rồi thêm session ID mới vào Redis set bằng các lệnh rời rạc. Hãy dùng API thay đổi ID của Servlet/Spring Security hoặc repository theo cách được hỗ trợ. Repository cần duy trì quan hệ giữa phiên và các index khi định danh thay đổi.

Trong kiểm thử, hãy xác nhận:

1. Trước khi đổi ID, truy vấn principal trả về phiên cũ.
2. Sau khi đổi ID và lưu thành công, phiên được tìm thấy với ID hiện tại.
3. ID cũ không còn được dùng để truy cập phiên.
4. Chỉ mục principal hoặc custom index vẫn trả về đúng phiên.
5. Việc đổi ID không làm mất thuộc tính phiên hợp lệ.

Việc đổi ID và việc đổi principal là hai thay đổi khác nhau. Một session có thể đổi ID nhưng vẫn thuộc cùng principal; khi đó membership phải đổi session ID nhưng giá trị principal không đổi. Ngược lại, principal có thể thay đổi trong khi ID không đổi; khi đó membership cần chuyển từ index cũ sang index mới. Chiến lược bảo mật có thể yêu cầu thực hiện cả hai.

## 10. Xử lý cập nhật đồng thời

Hai request cùng dùng một session có thể tải cùng trạng thái ban đầu rồi cùng cập nhật. Ví dụ, request A thay principal từ alice sang bob trong khi request B cập nhật tenant hoặc client type. Nếu các thay đổi được lưu dựa trên snapshot cũ, kết quả cuối có thể không như mong đợi hoặc index không còn phản ánh dữ liệu ứng dụng dự kiến.

Các cách giảm rủi ro:

- Không thực hiện nhiều thay đổi danh tính độc lập song song trên cùng session.
- Gom thay đổi Authentication và các thuộc tính liên quan vào một luồng xác thực có kiểm soát.
- Khi chuyển tài khoản, cân nhắc invalidate phiên cũ và tạo phiên mới theo chính sách.
- Dùng transaction hoặc cơ chế đồng bộ phù hợp cho dữ liệu nghiệp vụ nằm ngoài session.
- Định nghĩa rõ cách xử lý khi một request logout đồng thời với request đang cập nhật session.
- Kiểm thử hai request cùng session chạy song song, gồm cả cập nhật principal và xóa phiên.

Không nên dùng session index để làm khóa đồng bộ nghiệp vụ. Index được tối ưu cho tra cứu, không phải primitive lock hay cơ chế transaction cho toàn bộ ứng dụng.

## 11. Theo dõi và đối soát index

Chỉ mục cần được quan sát giống các cấu trúc dữ liệu khác. Các chỉ số hữu ích gồm:

- Số phiên đang được index theo principal.
- Số kết quả truy vấn không còn phiên tương ứng.
- Số lần cập nhật principal hoặc custom index thất bại.
- Độ trễ từ lúc phiên đổi danh tính đến khi truy vấn index phản ánh thay đổi.
- Số thành viên mồ côi được phát hiện và loại bỏ.
- Số lần thu hồi phiên theo principal và kết quả.

Nếu custom index nằm trong một hệ thống riêng do ứng dụng quản lý, nên lưu metadata để có thể đối soát. Tác vụ reconciliation có thể so sánh registry index với session repository theo lô, phát hiện session ID không tồn tại và loại bỏ membership cũ. Thiết kế job có giới hạn batch và có thể chạy đồng thời an toàn.

Không nên quét toàn bộ Redis keyspace thường xuyên trong production để kiểm tra index. Dùng API repository, metric và tác vụ đối soát có phạm vi rõ ràng. Nếu cần đọc cấu trúc Redis nội bộ để điều tra, thực hiện qua quy trình vận hành có kiểm soát và theo đúng phiên bản đang chạy.

## 12. Kiểm thử tạo, cập nhật và xóa index

Một bộ kiểm thử tích hợp nên sử dụng Redis thật hoặc môi trường tương thích để xác nhận hành vi của RedisIndexedSessionRepository. Mock repository có thể kiểm tra logic service nhưng không chứng minh index trong Redis được cập nhật đúng.

Các tình huống nên kiểm thử:

1. Tạo session chưa xác thực và xác nhận truy vấn principal chưa trả về session đó.
2. Lưu SecurityContext cho alice và xác nhận index alice chứa session ID.
3. Đổi Authentication sang bob, lưu session và xác nhận index alice không còn session, index bob có session.
4. Tạo hai session cho cùng alice và xác nhận truy vấn trả về cả hai.
5. Xóa một session và xác nhận chỉ membership của session đó bị loại bỏ.
6. Xóa tất cả session theo principal và xác nhận repository không còn khôi phục các phiên đó.
7. Đổi session ID và xác nhận index phản ánh ID hiện tại.
8. Để phiên hết hạn và kiểm tra hành vi index theo cấu hình expiration notification.
9. Tắt hoặc làm trễ listener expiration để kiểm tra cơ chế đối soát.
10. Cập nhật custom index như tenantId và clientType, sau đó kiểm tra giá trị cũ được loại và giá trị mới được thêm.
11. Chạy request đồng thời thay đổi principal và cập nhật thuộc tính khác để phát hiện race condition.
12. Xác nhận request với session đã bị thu hồi không thể tiếp tục truy cập, dù dữ liệu phụ hoặc index cleanup chưa hoàn tất.

Nên kiểm thử cả API FindByIndexNameSessionRepository lẫn hành vi HTTP thực tế qua SessionRepositoryFilter. Điều đó xác nhận session attribute được ghi, resolver đọc đúng principal và repository cập nhật index sau khi request kết thúc.

## 13. Những lỗi thiết kế thường gặp

| Lỗi | Hệ quả | Cách khắc phục |
|---|---|---|
| Chỉ cập nhật session hash, tự bỏ qua index | Truy vấn theo principal trả kết quả thiếu hoặc cũ | Để repository quản lý index qua API chính thức |
| Thay resolver và quên principal resolver | Mất khả năng tìm phiên theo người dùng | Kết hợp principal index với custom index |
| Xóa phiên bằng lệnh Redis trực tiếp | Có thể để lại index hoặc metadata hết hạn | Gọi deleteById qua repository |
| Dùng user ID để xóa mọi index khi chỉ logout một thiết bị | Phiên thiết bị khác bị ảnh hưởng | Thu dọn theo session ID cụ thể |
| Tin index là nguồn xác thực | Phiên hết hạn hoặc bị thu hồi có thể bị hiểu nhầm là hợp lệ | Xác minh session và quyền ở mỗi request |
| Không xử lý thay đổi principal | Session có thể xuất hiện dưới danh tính cũ | Lưu SecurityContext mới và xác nhận index được cập nhật |
| Không kiểm thử ID rotation | Index có thể trỏ đến ID cũ hoặc client tiếp tục gửi ID cũ | Kiểm thử đổi ID qua API framework và repository |
| Cho phép nhiều request đổi danh tính đồng thời | Kết quả index có thể không nhất quán | Tuần tự hóa luồng thay đổi danh tính và kiểm thử cạnh tranh |

## 14. Quy trình vận hành đề xuất

Khi thiết kế chỉ mục phiên, hãy xác định trước các giá trị thực sự cần truy vấn. Principal name thường là chỉ mục mặc định hữu ích. Tenant hoặc client type chỉ nên được thêm khi có nhu cầu truy vấn rõ ràng và giá trị được xác minh từ nguồn tin cậy.

Quy trình nên gồm:

1. Chọn RedisIndexedSessionRepository nếu cần truy vấn theo index.
2. Cấu hình principal resolver mặc định hoặc resolver kết hợp có chủ đích.
3. Lưu thuộc tính nhận dạng vào session theo cơ chế Spring Security/Servlet.
4. Để repository tạo và cập nhật membership khi session được lưu.
5. Dùng repository API để tìm và xóa phiên.
6. Kiểm thử chuyển principal, đổi session ID, logout và expiration.
7. Theo dõi index và có phương án reconciliation nếu ứng dụng quản lý thêm index riêng.
8. Giữ xác thực và authorization độc lập với kết quả truy vấn index.

Khi có yêu cầu thu hồi tất cả phiên của một tài khoản, hãy xác định rõ thời điểm bắt đầu thu hồi và xử lý phiên được tạo đồng thời. Có thể kết hợp danh sách phiên theo principal với một trạng thái thu hồi hoặc phiên bản bảo mật của tài khoản được kiểm tra ở mỗi request, tùy yêu cầu. Chỉ xóa những ID được tìm thấy một lần có thể chưa đủ nếu người dùng vẫn có thể tạo phiên mới trong lúc thao tác thu hồi đang diễn ra.

## Kết luận

RedisIndexedSessionRepository dùng các chỉ mục để ánh xạ principal hoặc thuộc tính được resolver xác định đến các session ID. Khi phiên được tạo, xác thực, đổi principal, đổi ID hoặc bị xóa, repository cần duy trì các membership tương ứng. Ứng dụng nên dùng FindByIndexNameSessionRepository để truy vấn và SessionRepository để xóa phiên, tránh sửa trực tiếp cấu trúc Redis nội bộ. Với custom index, hãy giữ principal resolver, lưu thay đổi session đầy đủ, xử lý cạnh tranh, theo dõi thành viên mồ côi và kiểm thử expiration. Chỉ mục giúp tìm phiên nhanh; trạng thái repository và Spring Security vẫn quyết định phiên có hợp lệ và được phép truy cập hay không.
