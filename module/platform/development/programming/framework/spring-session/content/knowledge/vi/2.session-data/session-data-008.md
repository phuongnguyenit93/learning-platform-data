# Danh tính người dùng, principal và chỉ mục tìm phiên

Trong một ứng dụng Spring Session, một người dùng có thể tạo nhiều phiên trên nhiều trình duyệt hoặc thiết bị. Khi cần xem người dùng đang có những phiên nào, giới hạn số phiên đồng thời hoặc đăng xuất khỏi tất cả thiết bị, ứng dụng cần một cách liên kết **danh tính đã xác thực** với các phiên đang được lưu. Spring Session hỗ trợ việc này thông qua chỉ mục theo principal trong các repository triển khai FindByIndexNameSessionRepository.

Để sử dụng đúng cơ chế này, cần hiểu ba khái niệm: người dùng là đối tượng nghiệp vụ của ứng dụng; principal là danh tính mà cơ chế bảo mật sử dụng trong một lần xác thực; chỉ mục phiên là cấu trúc tra cứu liên kết principal với các session ID. Chúng có quan hệ với nhau nhưng không phải cùng một dữ liệu.

## 1. Người dùng và principal khác nhau thế nào?

**Người dùng (user)** là đối tượng nghiệp vụ do ứng dụng quản lý. Một bản ghi người dùng thường có khóa chính, tên đăng nhập, email, trạng thái tài khoản, hồ sơ và các dữ liệu liên quan. Ví dụ, bảng users có người dùng với id = 42, username = linh.nguyen và trạng thái ACTIVE.

**Principal** đại diện cho chủ thể đã được xác thực trong ngữ cảnh bảo mật. Trong Spring Security, thông tin này thường nằm trong Authentication. Authentication.getPrincipal() trả về đối tượng principal; Authentication.getName() trả về tên định danh của principal theo cách triển khai xác thực.

Principal có thể là:

- Một đối tượng UserDetails chứa tên đăng nhập và thông tin cần cho xác thực.
- Một đối tượng tùy chỉnh của ứng dụng, chẳng hạn AppPrincipal.
- Một chuỗi hoặc kiểu principal khác tùy cơ chế xác thực.

Vì vậy, principal không nhất thiết là toàn bộ entity User được đọc từ cơ sở dữ liệu. Ứng dụng có thể chỉ đưa vào principal một định danh ổn định và những thông tin tối thiểu cần cho bảo mật. Khi cần tải hồ sơ đầy đủ, service dùng định danh đó để truy vấn lại dữ liệu nghiệp vụ.

Ví dụ, một lần xác thực có thể tạo ra thông tin như sau:

| Thành phần | Giá trị ví dụ | Vai trò |
|---|---|---|
| User entity | id = 42, username = linh.nguyen | Bản ghi tài khoản trong miền nghiệp vụ |
| Principal | userId = 42 | Danh tính chủ thể đã xác thực |
| Authentication.getName() | 42 | Chuỗi định danh mà cơ chế bảo mật cung cấp |
| Authorities | ROLE_USER, ORDER_READ | Quyền được cấp cho lần xác thực |
| Session ID | A1...X9 | Định danh một phiên cụ thể |

Authentication.getName() là giá trị quan trọng khi lập chỉ mục theo principal. Nếu ứng dụng dùng username làm tên principal, chỉ mục sẽ tra cứu theo username. Nếu username có thể đổi, các thao tác tra cứu cần xử lý việc đổi tên hoặc dùng một định danh ổn định hơn. Với hệ thống nhiều tenant, cần bảo đảm tên principal không bị trùng giữa các tenant, ví dụ bằng cách kết hợp tenant ID và user ID theo một quy tắc chuẩn hóa.

Không dùng session ID làm user ID. Một tài khoản có thể có nhiều session ID; mỗi ID chỉ đại diện cho một phiên cụ thể. Cũng không dùng địa chỉ IP hoặc thông tin thiết bị làm principal vì chúng có thể thay đổi và không chứng minh danh tính.

## 2. Spring Security đưa principal vào phiên như thế nào?

Trong mô hình đăng nhập stateful, Spring Security xác thực thông tin đăng nhập và tạo Authentication. Sau đó, SecurityContext chứa thông tin xác thực được lưu theo cơ chế lưu trữ context đang cấu hình. Với ứng dụng Servlet dùng session, context thường được lưu trong HTTP session để các request tiếp theo có thể khôi phục principal và authorities.

Spring Session thay thế cơ chế lưu HttpSession mặc định của container bằng repository được cấu hình, chẳng hạn Redis hoặc JDBC. Do đó, khi SecurityContext được lưu trong session và các instance dùng chung repository, request tiếp theo có thể được xử lý ở instance khác mà vẫn khôi phục được principal.

Luồng tổng quát:

    Người dùng gửi thông tin đăng nhập
              |
              v
    Spring Security xác thực
              |
              v
    Tạo Authentication và SecurityContext
              |
              v
    Lưu SecurityContext vào HTTP session
              |
              v
    Spring Session lưu session trong Redis / JDBC
              |
              v
    Repository cập nhật chỉ mục principal (nếu được hỗ trợ)

Ở request tiếp theo, trình duyệt gửi cookie chứa session ID. Spring Session tải session từ repository; Spring Security khôi phục SecurityContext; ứng dụng có thể lấy principal để kiểm tra quyền hoặc truy vấn dữ liệu người dùng.

Luồng này phụ thuộc vào cấu hình. Ứng dụng Spring Security stateless, chẳng hạn xác thực từng request bằng bearer token, có thể không lưu SecurityContext vào HTTP session. Khi đó, không thể mặc định rằng repository sẽ tìm được session theo principal của request đó. Chỉ mục phiên phục vụ các session thực sự được lưu và được repository lập chỉ mục.

## 3. Chỉ mục tìm phiên theo principal là gì?

Thông thường, repository có thể tải session khi biết session ID. Nhưng một số chức năng quản trị cần đi theo chiều ngược lại: biết principal rồi tìm tất cả session đang gắn với principal đó.

Spring Session định nghĩa FindByIndexNameSessionRepository, mở rộng khả năng của SessionRepository bằng thao tác tìm theo tên chỉ mục và giá trị chỉ mục. Chỉ mục chuẩn để tìm theo principal được cung cấp bởi hằng:

**FindByIndexNameSessionRepository.PRINCIPAL_NAME_INDEX_NAME**

Các repository có hỗ trợ tìm theo chỉ mục principal có thể lưu liên kết giữa tên principal và các session ID tương ứng. Khi gọi phương thức tìm kiếm với tên chỉ mục chuẩn và principal name, repository trả về một Map trong đó khóa là session ID và giá trị là đối tượng session.

Ví dụ về cách tra cứu:

    Map<String, ? extends Session> sessions =
        sessionRepository.findByIndexNameAndIndexValue(
            FindByIndexNameSessionRepository.PRINCIPAL_NAME_INDEX_NAME,
            principalName
        );

Cần dùng repository triển khai FindByIndexNameSessionRepository, chẳng hạn repository được hỗ trợ cho Redis hoặc JDBC trong phiên bản Spring Session đang dùng. Chỉ có một bean SessionRepository tổng quát chưa đủ để bảo đảm thao tác tìm theo principal tồn tại. Hãy kiểm tra loại repository và cấu hình index resolver của phiên bản ứng dụng.

Chỉ mục này là một cấu trúc tra cứu phụ trợ. Nó không phải bảng người dùng, không thay thế kho session và cũng không phải công cụ tìm kiếm toàn văn. Mục tiêu chính là tìm các session theo một định danh đã được xác định trước, thường là principal name.

## 4. Spring Session xác định principal name ra sao?

Khi repository lập chỉ mục, nó cần biết giá trị principal name nào gắn với một session. Spring Session có cơ chế resolver để xác định giá trị này. Với tích hợp Spring Security, resolver có thể đọc thông tin SecurityContext được lưu trong session và lấy tên từ Authentication.

Nếu ứng dụng dùng principal tùy chỉnh hoặc cơ chế xác thực riêng, cần xác nhận resolver có thể đọc được principal đó. Khi không dùng Spring Security hoặc resolver mặc định không tìm được danh tính, ứng dụng có thể chủ động đặt thuộc tính chỉ mục chuẩn vào session sau khi xác thực thành công:

    session.setAttribute(
        FindByIndexNameSessionRepository.PRINCIPAL_NAME_INDEX_NAME,
        principalName
    );

Giá trị principalName phải được lấy từ kết quả xác thực đáng tin cậy, không lấy trực tiếp từ tham số do client gửi lên. Chỉ đặt thuộc tính này sau khi danh tính đã được xác minh. Nếu một session được chuyển sang tài khoản khác hoặc đăng xuất mà session vẫn tiếp tục được sử dụng, cần bảo đảm thông tin principal cũ được cập nhật hoặc xóa theo đúng vòng đời xác thực. Nếu vô hiệu hóa toàn bộ session khi đăng xuất, repository sẽ xử lý việc xóa session và chỉ mục tương ứng theo cơ chế của nó.

Một principal tùy chỉnh có thể cung cấp định danh ổn định:

    public record AppPrincipal(String userId, String username)
            implements AuthenticatedPrincipal {

        @Override
        public String getName() {
            return userId;
        }
    }

Trong ví dụ này, getName() trả về user ID bất biến. Nếu Authentication sử dụng đối tượng principal này và resolver lấy tên từ Authentication.getName(), chỉ mục không bị thay đổi chỉ vì người dùng đổi username. Cách triển khai principal thực tế cần tương thích với cơ chế xác thực và cách tạo Authentication của ứng dụng.

Không nên nhồi toàn bộ entity JPA vào principal hoặc session nếu không cần thiết. Entity có thể chứa dữ liệu cá nhân, quan hệ lazy, proxy hoặc trạng thái cũ. Principal nhỏ và ổn định giúp giảm dữ liệu phải serialize, giảm rủi ro tương thích khi deploy phiên bản mới và tránh giữ thông tin hồ sơ quá lâu trong session.

## 5. Tra cứu các phiên của một người dùng

Một service có thể nhận repository hỗ trợ tìm theo chỉ mục và cung cấp thao tác tra cứu. Ví dụ sau minh họa cách dùng API; kiểu session cụ thể phụ thuộc repository được cấu hình trong ứng dụng:

    @Service
    public class UserSessionService {

        private final FindByIndexNameSessionRepository<? extends Session>
                sessionRepository;

        public UserSessionService(
                FindByIndexNameSessionRepository<? extends Session>
                        sessionRepository) {
            this.sessionRepository = sessionRepository;
        }

        public Map<String, ? extends Session> findSessions(
                String principalName) {

            return sessionRepository.findByIndexNameAndIndexValue(
                FindByIndexNameSessionRepository.PRINCIPAL_NAME_INDEX_NAME,
                principalName
            );
        }
    }

Khi gọi service, principal name nên được lấy từ Authentication hiện tại đối với người dùng tự xem phiên của mình:

    Authentication authentication =
        SecurityContextHolder.getContext().getAuthentication();

    String principalName = authentication.getName();

Đối với chức năng quản trị xem phiên của người khác, endpoint phải kiểm tra quyền quản trị và xác định rõ phạm vi tenant. Không cho phép người dùng gửi một principal name tùy ý rồi xem thông tin phiên của tài khoản khác. Kết quả tra cứu cũng không nên trả session ID thô cho trình duyệt nếu không có nhu cầu nghiệp vụ rõ ràng, vì session ID là bí mật xác thực.

Ví dụ, tài khoản 42 đang đăng nhập trên laptop và điện thoại. Repository có thể trả về hai phần tử:

| Khóa trong kết quả | Session tương ứng | Thiết bị minh họa |
|---|---|---|
| SID-LAPTOP | Session thứ nhất | Laptop |
| SID-PHONE | Session thứ hai | Điện thoại |

Ứng dụng có thể dùng danh sách này để hiển thị phiên đang hoạt động, áp dụng giới hạn số phiên hoặc cho người dùng kết thúc một phiên khác. Thông tin như tên thiết bị, trình duyệt hay thời điểm đăng nhập chỉ có nếu ứng dụng chủ động lưu chúng trong session hoặc một kho dữ liệu riêng; chỉ mục principal không tự suy ra các thông tin đó.

## 6. Kết thúc các phiên theo principal

Một trường hợp sử dụng phổ biến là đăng xuất khỏi tất cả thiết bị sau khi người dùng yêu cầu hoặc khi tài khoản bị khóa. Sau khi tra cứu các session theo principal, ứng dụng có thể xóa từng session bằng ID:

    Map<String, ? extends Session> sessions =
        sessionRepository.findByIndexNameAndIndexValue(
            FindByIndexNameSessionRepository.PRINCIPAL_NAME_INDEX_NAME,
            principalName
        );

    for (String sessionId : sessions.keySet()) {
        sessionRepository.deleteById(sessionId);
    }

deleteById yêu cầu repository xóa session có ID tương ứng. Khi session bị xóa, dữ liệu session và liên kết chỉ mục được repository quản lý theo cách triển khai của nó. Cần kiểm tra hành vi thực tế của repository đang dùng, đặc biệt khi có nhiều instance cùng ghi hoặc xóa session.

Đây là thao tác trên các session tìm được tại thời điểm truy vấn. Một thiết bị có thể đăng nhập lại ngay sau đó, hoặc một session mới có thể được tạo đồng thời với quá trình xóa. Vì vậy, nếu nghiệp vụ đòi hỏi thu hồi mọi phiên với bảo đảm chặt chẽ trong điều kiện đồng thời, cần kết hợp chỉ mục với chính sách ở cấp tài khoản, chẳng hạn trạng thái khóa, phiên bản xác thực hoặc cơ chế thu hồi được kiểm tra trong mỗi request. Xóa danh sách session một lần không tự ngăn việc tạo session mới.

Cũng cần xác định rõ phạm vi hành động:

- **Đăng xuất phiên hiện tại:** vô hiệu hóa session gắn với request hiện tại.
- **Đăng xuất một thiết bị khác:** tìm session của principal rồi xóa đúng session ID đã chọn.
- **Đăng xuất mọi thiết bị:** tra cứu toàn bộ session theo principal rồi xóa từng session.
- **Khóa tài khoản:** cập nhật trạng thái tài khoản và bảo đảm các request tiếp theo không thể tiếp tục được xác thực chỉ nhờ một session cũ.

Các thao tác này có mục tiêu khác nhau. Việc xóa session không xóa user entity, không xóa tài khoản và không tự thay đổi mật khẩu hay quyền trong cơ sở dữ liệu.

## 7. Những điểm cần chú ý khi vận hành

**Principal phải ổn định và chuẩn hóa.** Nếu dùng username, hãy thống nhất chữ hoa/chữ thường, khoảng trắng và quy tắc đổi tên. Nếu username có thể thay đổi, cần có kế hoạch cập nhật hoặc thu hồi các session cũ. Trong ứng dụng đa tenant, phải đưa tenant vào phạm vi định danh để tránh hai người dùng cùng username bị gộp chỉ mục.

**Repository phải hỗ trợ index.** Không phải mọi triển khai SessionRepository đều cung cấp truy vấn theo principal. Cần chọn triển khai hỗ trợ FindByIndexNameSessionRepository và cấu hình resolver phù hợp. Nếu ứng dụng tự viết repository, phải triển khai cả việc tạo, cập nhật và xóa liên kết chỉ mục.

**Chỉ mục phụ thuộc vào vòng đời session.** Session hết hạn, bị xóa hoặc thay đổi principal cần làm cho liên kết chỉ mục được cập nhật. Với repository phân tán, cơ chế TTL, sự kiện hết hạn và dọn dẹp có thể hoạt động bất đồng bộ. Kết quả truy vấn là ảnh chụp tại một thời điểm; session có thể hết hạn hoặc bị xóa ngay sau khi được trả về. Các thao tác quản trị cần xử lý trường hợp session biến mất giữa lúc liệt kê và lúc xóa.

**Không coi chỉ mục là nguồn xác thực.** Tìm thấy một session trong chỉ mục không có nghĩa tài khoản hiện vẫn được phép truy cập. Tài khoản có thể đã bị khóa, quyền đã thay đổi hoặc session đã bị thu hồi. Mỗi request vẫn phải đi qua xác thực và authorization phù hợp; nếu yêu cầu thu hồi tức thời, cần có chính sách kiểm tra trạng thái tài khoản hoặc phiên bản xác thực.

**Bảo vệ dữ liệu nhạy cảm.** Principal name có thể là username hoặc user ID, vì vậy không nên ghi toàn bộ chỉ mục vào log công khai. Session ID là bí mật, không đưa vào URL, log thông thường hoặc phản hồi API. Chỉ cho phép người có quyền thích hợp tra cứu và xóa session.

**Theo dõi hoạt động của kho session.** Khi số phiên tăng nhanh hoặc truy vấn principal trả kết quả thiếu, cần quan sát kết nối Redis/JDBC, TTL, lỗi serialize, sự kiện hết hạn và cấu hình resolver. Nếu các instance dùng cấu hình hoặc namespace khác nhau, chúng có thể không nhìn thấy cùng một dữ liệu phiên và chỉ mục.

## 8. Kiểm tra chỉ mục principal

Có thể xác nhận cấu hình bằng một kịch bản kiểm thử tích hợp:

1. Đăng nhập cùng một tài khoản trên hai client độc lập để tạo hai session.
2. Lấy Authentication.getName() từ mỗi request và xác nhận hai client có cùng principal name.
3. Gọi findByIndexNameAndIndexValue với PRINCIPAL_NAME_INDEX_NAME và principal name đó.
4. Xác nhận kết quả chứa hai session ID khác nhau.
5. Đăng xuất một client và kiểm tra session tương ứng không còn được tìm thấy.
6. Xóa các session còn lại theo principal rồi truy vấn lại để xác nhận kết quả rỗng.
7. Chờ một session hết TTL và xác nhận session hết hạn không được sử dụng như một phiên còn hiệu lực.
8. Thử principal không tồn tại và xác nhận repository trả về kết quả rỗng.

Khi viết test, không phụ thuộc vào session ID được sinh ngẫu nhiên hoặc thứ tự phần tử trong Map. Hãy kiểm tra số lượng, tập ID hoặc thuộc tính đã lưu. Với test nhiều instance, cần dùng cùng một repository thực tế hoặc môi trường tích hợp tương đương để chứng minh instance A tạo session có thể được instance B tìm thấy qua cùng principal index.

## Kết luận

Người dùng là tài khoản nghiệp vụ; principal là danh tính được cơ chế xác thực sử dụng; chỉ mục principal liên kết tên principal với các session ID để repository có thể tìm các phiên của một người dùng. Spring Session cung cấp API FindByIndexNameSessionRepository và chỉ mục chuẩn PRINCIPAL_NAME_INDEX_NAME cho các triển khai hỗ trợ. Cơ chế này hữu ích khi quản lý nhiều thiết bị, giới hạn phiên đồng thời và đăng xuất từ xa. Để vận hành chính xác, cần dùng principal ổn định, cấu hình resolver đúng, bảo vệ quyền tra cứu và xử lý các thay đổi session trong môi trường nhiều instance.
