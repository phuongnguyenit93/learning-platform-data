# Thực hiện hợp đồng SessionRepository và vòng đời đối tượng Session

Spring Session tách vòng đời phiên HTTP khỏi bộ nhớ của một máy chủ. Thay vì để servlet container giữ HttpSession trong RAM của một instance, ứng dụng có thể dùng một SessionRepository để tạo, tìm, lưu và xóa đối tượng Session trong Redis, JDBC hoặc một kho lưu trữ tùy chỉnh. Khi nhiều instance cùng dùng repository, request trên node này có thể tiếp tục phiên đã được tạo ở node khác.

Muốn tự triển khai repository đúng, cần hiểu hai hợp đồng riêng: Session mô tả trạng thái và thao tác trên một phiên; SessionRepository quy định cách tạo và lưu phiên đó. Repository còn phải giữ các bất biến về ID, thời gian sống, thuộc tính, serialization, xóa và cập nhật đồng thời. Chỉ triển khai đủ bốn phương thức mà bỏ qua các bất biến này có thể làm session tồn tại sai hạn, bị ghi đè, không thu hồi được hoặc không tương thích giữa các node.

Bài này đi theo vòng đời đầy đủ của một session Servlet: tạo đối tượng, đọc thuộc tính, cập nhật metadata, lưu trước khi response commit, đổi ID, hết hạn, invalidate và xóa dữ liệu. Sau đó, bài phân tích cách thiết kế custom repository, kiểm thử hợp đồng và vận hành trong cụm nhiều instance.

## 1. Vai trò của Session và SessionRepository

Session là abstraction đại diện cho một phiên người dùng. Nó chứa định danh, metadata vòng đời và các thuộc tính ứng dụng. SessionRepository là abstraction chịu trách nhiệm lưu trữ và truy xuất Session.

Hợp đồng đồng bộ cốt lõi có dạng:

~~~java
public interface SessionRepository<S extends Session> {

    S createSession();

    void save(S session);

    S findById(String id);

    void deleteById(String id);
}
~~~

Các phương thức có ý nghĩa:

| Phương thức | Trách nhiệm | Kết quả cần hiểu |
|---|---|---|
| createSession | Tạo đối tượng Session mới | Thường trả đối tượng chưa được lưu bền vững |
| save | Lưu trạng thái Session | Tạo mới hoặc cập nhật bản ghi, metadata và TTL |
| findById | Tìm Session theo ID | Trả null nếu không tồn tại hoặc đã hết hạn |
| deleteById | Xóa Session theo ID | Xóa dữ liệu phiên; gọi nhiều lần nên an toàn |

Hợp đồng SessionRepository không tự quy định Redis key, SQL table, serializer hoặc cách phát event. Đó là trách nhiệm của implementation và phần tích hợp xung quanh.

Trong ứng dụng Servlet, SessionRepository thường được dùng qua SessionRepositoryFilter. Filter này bọc HttpServletRequest/HttpServletResponse để ánh xạ API HttpSession của Servlet sang Session của Spring Session. Controller và Spring Security có thể tiếp tục dùng HttpSession, còn filter chuyển các thao tác sang repository.

Sơ đồ thành phần:

~~~mermaid
flowchart TD
    A[HTTP request] --> B[SessionRepositoryFilter]
    B --> C[HttpSession wrapper]
    C --> D[Session object]
    D --> E[SessionRepository]
    E --> F[(Redis / JDBC / custom store)]
    F --> E
    E --> D
    D --> C
    C --> B
    B --> G[Save before response commit]
    G --> H[SessionIdResolver writes cookie]
~~~

Tách abstraction giúp ứng dụng không phụ thuộc vào một máy chủ cụ thể. Tuy nhiên, mọi node trong cùng một cụm phải dùng cách hiểu thống nhất về session ID, thuộc tính, serializer, timeout và schema.

## 2. Hợp đồng của đối tượng Session

Session biểu diễn dữ liệu và metadata của một phiên. Các thao tác phổ biến trong API Session gồm:

~~~java
public interface Session {

    String getId();

    void changeSessionId();

    Instant getCreationTime();

    Instant getLastAccessedTime();

    void setLastAccessedTime(Instant lastAccessedTime);

    Duration getMaxInactiveInterval();

    void setMaxInactiveInterval(Duration interval);

    Set<String> getAttributeNames();

    <T> T getAttribute(String attributeName);

    void setAttribute(String attributeName, Object attributeValue);

    void removeAttribute(String attributeName);
}
~~~

Các method trên là hình dạng hợp đồng khái niệm; hãy đối chiếu package và phiên bản Spring Session cụ thể trong dự án khi biên dịch implementation.

Session có hai nhóm trạng thái:

- **Metadata vòng đời:** ID, creation time, last accessed time và max inactive interval.
- **Attributes:** dữ liệu do ứng dụng hoặc framework lưu, ví dụ locale, cart ID, trạng thái wizard hoặc SecurityContext.

Không nên trộn dữ liệu nghiệp vụ dài hạn vào session. Session phù hợp với trạng thái tương tác ngắn hạn. Đơn hàng, số dư, tồn kho hoặc dữ liệu cần transaction nên được lưu trong kho nghiệp vụ và session chỉ giữ ID tham chiếu nếu cần.

## 3. Tạo session: đối tượng mới chưa đồng nghĩa dữ liệu đã bền vững

createSession() có nhiệm vụ tạo một đối tượng Session hợp lệ. Thông thường, nó thiết lập:

- ID mới có độ khó đoán cao.
- creationTime bằng thời điểm tạo.
- lastAccessedTime ban đầu.
- maxInactiveInterval mặc định theo cấu hình.
- tập thuộc tính ban đầu rỗng.

Tạo đối tượng và lưu đối tượng là hai bước riêng. Một implementation có thể trả Session từ createSession() trước, sau đó chỉ ghi dữ liệu khi save(session) được gọi. Đây là cách phù hợp với vòng đời request: request có thể tạo session, thêm nhiều thuộc tính, rồi lưu một lần khi response chuẩn bị commit.

Ví dụ sử dụng API Servlet:

~~~java
HttpSession session = request.getSession(true);
session.setAttribute("app.locale", "vi-VN");
session.setAttribute("app.cartId", cartId);
~~~

Lời gọi getSession(true) yêu cầu session nếu chưa có. Trong Spring Session, wrapper tạo đối tượng Session qua repository. Các thuộc tính được đặt lên đối tượng đó và sẽ được lưu theo chính sách commit/flush của filter.

Ngược lại:

~~~java
HttpSession existing = request.getSession(false);

if (existing == null) {
    // Request không có session hiện tại; không tạo phiên mới.
}
~~~

getSession(false) phải không tạo session. Đây là điều kiện quan trọng cho các endpoint chỉ muốn kiểm tra trạng thái đăng nhập hoặc xử lý request không cần phiên.

### ID phải an toàn

ID session là bearer credential. Người sở hữu ID còn hiệu lực có thể thử tiếp tục phiên tương ứng. Vì vậy:

- Dùng bộ sinh số ngẫu nhiên mật mã phù hợp.
- Không dùng user ID, email, timestamp hoặc bộ đếm tuần tự làm session ID.
- Không tự tạo ID trong controller.
- Kiểm tra va chạm trước khi chấp nhận ID mới nếu storage design yêu cầu.
- Không ghi ID thật vào log, metric hoặc URL.
- Hỗ trợ đổi ID sau xác thực theo session fixation protection.

Không dùng một ID có thể đoán được chỉ vì dữ liệu session được lưu trong Redis/JDBC. Bảo vệ repository không thay thế entropy của ID.

## 4. Vòng đời request qua SessionRepositoryFilter

Trong ứng dụng Servlet, SessionRepositoryFilter điều phối việc chuyển đổi giữa HttpSession và SessionRepository. Vòng đời điển hình:

1. Resolver đọc session ID từ cookie hoặc header của request.
2. Filter dùng repository tìm session theo ID khi cần.
3. Nếu session không tồn tại hoặc hết hạn, request không có session hợp lệ.
4. Khi code gọi getSession(true), filter yêu cầu repository tạo Session mới.
5. Controller, service và Spring Security đọc/ghi thuộc tính thông qua HttpSession wrapper.
6. Trước khi response được commit, filter lưu session đã thay đổi theo chính sách của nó.
7. Resolver ghi session ID vào response cookie/header khi cần.
8. Request tiếp theo gửi ID đó để tải lại session từ repository.

Đường đi này giải thích vì sao không nên tự ghi cookie trong controller. Repository quản lý dữ liệu; resolver quản lý cách ID đi qua ranh giới HTTP; filter kết nối hai phần với API Servlet.

Nếu ứng dụng tự đăng ký filter hoặc dùng cấu hình đặc biệt, cần bảo đảm SessionRepositoryFilter chạy đúng vị trí trước các filter cần HttpSession, đặc biệt là Spring Security. Cấu hình Spring Boot/Spring Session chuẩn thường hỗ trợ đăng ký này; custom registration phải kiểm tra thứ tự thực tế.

## 5. findById: phân biệt không tồn tại với lỗi kho dữ liệu

findById(String id) tìm session theo ID. Theo hợp đồng đồng bộ, kết quả không có session thường được biểu diễn bằng null.

Các trường hợp cần phân biệt:

| Tình huống | Kết quả phù hợp |
|---|---|
| ID chưa từng tồn tại | null |
| Session đã bị xóa | null |
| Session đã hết hạn logic | null |
| Redis/database timeout | Ném lỗi phù hợp |
| Không đủ quyền truy cập kho | Ném lỗi phù hợp |
| Payload không deserialize được | Báo lỗi dữ liệu/serialization, không coi như miss bình thường |

Không bắt mọi exception rồi trả null. Nếu Redis mất kết nối mà repository trả null, ứng dụng có thể hiểu nhầm người dùng chưa đăng nhập, tạo session mới hoặc làm sai hành vi bảo mật. Lỗi hạ tầng phải được quan sát riêng.

findById cũng phải bảo đảm dữ liệu trả về không cho phép request sửa trực tiếp một object đang được chia sẻ trong cache toàn cục. Thông thường, repository deserialize hoặc tạo một bản Session độc lập cho request. Việc dùng chung cùng một mutable Session instance giữa nhiều request có thể gây race condition và rò rỉ thay đổi chưa lưu.

## 6. save: ghi trạng thái và gia hạn thời gian sống

save(Session session) phải lưu trạng thái mà implementation cam kết hỗ trợ. Tùy storage design, thao tác có thể gồm:

- Ghi ID và metadata.
- Ghi các session attributes.
- Serialize giá trị thuộc tính.
- Đặt hoặc gia hạn TTL.
- Cập nhật index hoặc dữ liệu phụ trợ.
- Xử lý ID đã thay đổi.
- Dọn key cũ khi cần.

Một điểm quan trọng: save không chỉ ghi các thuộc tính ứng dụng. Metadata như lastAccessedTime và maxInactiveInterval quyết định session còn hợp lệ bao lâu.

Idle expiration thường được tính theo ý tưởng:

~~~text
expiresAt = lastAccessedTime + maxInactiveInterval
remainingTtl = expiresAt - currentTime
~~~

Khi session được truy cập theo chính sách của ứng dụng, lastAccessedTime có thể được cập nhật. Khi lưu, repository phải tính TTL phù hợp từ thời điểm truy cập và max inactive interval. Nếu chỉ ghi dữ liệu mà không refresh TTL, người dùng hoạt động vẫn có thể bị hết phiên sớm. Nếu không đặt TTL, session có thể tồn tại quá lâu.

Không dùng thời điểm tạo session làm idle expiration. Creation time và last accessed time có ý nghĩa khác nhau. Nếu ứng dụng cần absolute timeout, đó là một giới hạn riêng: hoạt động liên tục không được phép kéo dài phiên vượt quá thời điểm tối đa.

## 7. Metadata thời gian và quy tắc hết hạn

Session thường chứa ba giá trị thời gian quan trọng:

| Metadata | Ý nghĩa |
|---|---|
| creationTime | Thời điểm phiên được tạo |
| lastAccessedTime | Thời điểm truy cập gần nhất được tính là hoạt động |
| maxInactiveInterval | Khoảng thời gian không hoạt động tối đa |

Repository cần dùng một nguồn thời gian nhất quán. Trong hệ thống nhiều node, đồng hồ máy chủ nên được đồng bộ; nếu các node lệch giờ đáng kể, session có thể hết hạn sớm hoặc muộn tùy node xử lý request.

Khi findById, implementation phải kiểm tra hết hạn logic ngay cả khi storage chưa dọn vật lý key/row. TTL ở Redis hoặc cleanup job của JDBC là cơ chế dọn dữ liệu; chúng không nên là điều kiện duy nhất để xác định quyền truy cập.

Nếu session hết hạn:
- Không trả session đó như một phiên hợp lệ.
- Không gia hạn TTL chỉ vì key vẫn còn.
- Có thể xóa dữ liệu hết hạn nếu implementation hỗ trợ.
- Phát sự kiện hết hạn nếu repository tích hợp cơ chế event.
- Để request cần đăng nhập chuyển sang luồng xác thực lại.

Không nhầm session expiration với việc browser xóa cookie. Cookie còn tồn tại nhưng session đã hết hạn vẫn phải bị từ chối. Ngược lại, browser có thể xóa cookie trong khi dữ liệu session phía server vẫn còn cho tới TTL hoặc cleanup.

## 8. Thuộc tính Session: đặt, đọc và xóa

Các thuộc tính được thao tác qua API Session:

~~~java
session.setAttribute("app.locale", "vi-VN");

String locale = session.getAttribute("app.locale");

session.removeAttribute("app.locale");
~~~

Tên thuộc tính nên có namespace để tránh va chạm giữa module ứng dụng và framework. Tránh dùng tên quá chung như data, user hoặc state.

Các nguyên tắc:

- Giá trị null thường được xem là xóa thuộc tính; dùng removeAttribute để thể hiện ý định rõ ràng.
- getAttributeNames nên phản ánh các thuộc tính hiện có.
- Không trả về collection tên thuộc tính có thể sửa trực tiếp cấu trúc nội bộ của Session.
- Không lưu HttpServletRequest, HttpServletResponse, thread, connection hoặc resource không serialize ổn định.
- Không lưu object graph quá lớn hoặc entity/proxy ORM.
- Không giả định repository tự phát hiện thay đổi sâu bên trong object mutable.

Nếu lấy một List từ session rồi thêm phần tử tại chỗ, repository có thể không nhận được thao tác đặt thuộc tính mới tùy SaveMode. Ưu tiên object bất biến hoặc gọi setAttribute sau khi tạo giá trị mới. Hãy kiểm tra SaveMode thực tế của repository đang dùng.

## 9. Thay đổi session ID

changeSessionId() thay đổi định danh của một session đang tồn tại. Đây là thao tác quan trọng sau đăng nhập để giảm nguy cơ session fixation, hoặc khi chính sách bảo mật yêu cầu xoay ID.

Khi ID đổi, hệ thống cần bảo đảm:

- ID mới được tạo an toàn.
- Session vẫn giữ các thuộc tính hợp lệ và metadata cần thiết.
- ID cũ không còn được chấp nhận để truy cập phiên.
- Repository chuyển dữ liệu từ định danh cũ sang mới theo cách nhất quán.
- Resolver phát ID mới cho client.
- Logout và cleanup sau đó dùng đúng ID hiện tại.

Đổi ID không phải là tạo một session nghiệp vụ hoàn toàn mới. Nó thường giữ nội dung session nhưng thay định danh. Tuy nhiên, chi tiết chuyển key và lưu trữ phụ thuộc repository/filter integration. Custom implementation cần kiểm tra contract của phiên bản Spring Session và kiểm thử việc xóa ID cũ.

Ví dụ trong Spring Security:

~~~java
http.sessionManagement(session -> session
    .sessionFixation(fixation -> fixation.changeSessionId())
);
~~~

Không tự đặt ID mới bằng UUID trong controller. Dùng cơ chế session và security framework để bảo đảm resolver, repository và response cookie được đồng bộ.

## 10. deleteById và invalidate

deleteById(String id) xóa session khỏi kho dữ liệu. Trong API Servlet, thao tác này thường được gọi thông qua HttpSession.invalidate().

Xóa cần xử lý tất cả dữ liệu thuộc phiên:

- Session record hoặc hash.
- Attribute payload.
- Expiration metadata/key nếu tách riêng.
- Principal/session index nếu repository quản lý.
- Các bản sao hoặc cache liên quan nếu có.
- Mapping phụ trợ phục vụ WebSocket hoặc quản trị session nếu implementation sở hữu chúng.

Delete nên idempotent: gọi với ID không tồn tại hoặc gọi lặp lại không làm hỏng repository. Tuy nhiên, idempotent không có nghĩa là bỏ qua lỗi kết nối; nếu kho dữ liệu không truy cập được, cần phát hiện và báo lỗi.

Invalidate có ý nghĩa bảo mật: request hiện tại không được tiếp tục dùng session như thể còn hợp lệ. Các truy cập sau đó tới session đã invalidated cần tuân theo hành vi của Servlet wrapper, thường báo trạng thái session không còn hợp lệ. Cookie phía browser cũng cần được resolver xóa ở response.

Không chỉ xóa cookie mà bỏ session trong Redis/JDBC. Bản sao cookie bị đánh cắp có thể tiếp tục truy cập nếu record phía server còn hiệu lực.

## 11. Lưu trước khi phát hành session ID

Một lỗi nghiêm trọng là phát session ID tới browser trước khi dữ liệu session được lưu thành công. Khi browser gửi ID ở request sau, repository có thể không tìm thấy phiên.

Luồng an toàn ở mức khái niệm:

1. Request tạo Session.
2. Ứng dụng đặt thuộc tính.
3. Filter gọi save theo vòng đời response.
4. Repository xác nhận thao tác lưu hoàn tất.
5. Resolver ghi session ID vào response.
6. Response được gửi cho browser.

Nếu save thất bại, không nên trả về một cookie mới trỏ tới session chưa được lưu. Lỗi cần được truyền qua quá trình hoàn tất response để hệ thống ghi nhận đúng.

Với FlushMode.ON_SAVE, thay đổi thường được ghi khi session được save ở cuối request. Với chế độ flush ngay, thao tác có thể được đẩy xuống kho sớm hơn. Dù chọn chế độ nào, repository phải bảo đảm semantics nhất quán giữa dữ liệu và ID được phát hành.

## 12. Thiết kế một custom repository

Trước khi tự triển khai, hãy kiểm tra repository có sẵn của Spring Session. Redis và JDBC repository đã xử lý nhiều chi tiết như serialization, expiration, index và tích hợp filter. Custom repository phù hợp khi có yêu cầu về storage hoặc semantics mà implementation có sẵn không đáp ứng.

Một thiết kế tối thiểu cần xác định:

1. Kiểu Session cụ thể.
2. Cách sinh ID.
3. Cách serialize/deserialize thuộc tính.
4. Cấu trúc lưu metadata và attributes.
5. Quy tắc idle expiration và TTL.
6. Hành vi khi session đổi ID.
7. Cách xóa dữ liệu phụ trợ.
8. Chính sách cập nhật đồng thời.
9. Xử lý lỗi storage và serialization.
10. Tương thích giữa nhiều instance và nhiều phiên bản ứng dụng.

Không bắt đầu từ câu hỏi “lưu object vào Redis thế nào?” mà từ các bất biến của hợp đồng SessionRepository. Storage chỉ là một chi tiết thực hiện các bất biến đó.

### Pseudocode cho thuật toán repository

Đây là pseudocode mô tả luồng, không phải một class có thể biên dịch trực tiếp:

~~~text
createSession():
    id = secureRandomSessionId()
    now = clock.instant()
    return new Session(id, creationTime=now,
                       lastAccessedTime=now,
                       maxInactiveInterval=defaultInterval)

save(session):
    validateSessionId(session.id)
    snapshot = copyAndSerialize(session)
    ttl = calculateRemainingIdleTtl(session, clock.instant())
    atomicallyWrite(snapshot, ttl)

findById(id):
    stored = storage.read(id)
    if stored is absent:
        return null
    session = deserialize(stored)
    if isExpired(session, clock.instant()):
        deleteExpiredData(id)
        return null
    return detachedSessionCopy(session)

deleteById(id):
    atomicallyDeleteSessionAndIndexes(id)
~~~

Điểm quan trọng là repository trả một Session độc lập, không làm lộ object mutable được lưu trong cache nội bộ. TTL và logical expiration được kiểm tra nhất quán. Xóa dữ liệu chính và dữ liệu phụ trợ cần có một chiến lược atomic hoặc reconciliation rõ ràng.

## 13. Bảo vệ tính toàn vẹn của dữ liệu lưu trữ

Nếu repository dùng Redis, có thể lưu metadata và attributes trong một hash, hoặc tách thành nhiều key. Nếu dùng JDBC, có thể dùng bảng session và bảng attributes. Dù chọn cấu trúc nào, cần bảo đảm:

- ID là key duy nhất.
- Attribute name được lưu không va chạm.
- Metadata được serialize theo schema ổn định.
- Payload được kiểm tra kích thước và kiểu.
- TTL không âm ngoài chính sách đã định.
- Xóa session không để lại index mồ côi vô thời hạn.
- Ghi dở dang không làm session ở trạng thái nửa hợp lệ.
- Serializer không deserialize class tùy ý không tin cậy.
- Credential và thuộc tính nhạy cảm được bảo vệ ở storage, backup và log.

Nếu một session gồm nhiều key Redis, các lệnh ghi/xóa liên quan có thể cần Lua script hoặc transaction để tránh trạng thái nửa chừng. Nếu dùng JDBC, transaction cần bao phủ các thao tác record và attributes liên quan khi yêu cầu nhất quán đòi hỏi.

Không giả định nhiều lệnh Redis được gọi liên tiếp là một transaction. Cũng không giả định hai thao tác JDBC riêng lẻ tự động nằm trong cùng transaction nếu không có transaction manager phù hợp.

## 14. Cập nhật đồng thời và lost update

Hai request có thể cùng tải một session, mỗi request sửa một thuộc tính hoặc cùng sửa một thuộc tính, rồi lưu ở thời điểm khác nhau.

Ví dụ:

~~~mermaid
sequenceDiagram
    participant A as Request A
    participant R as Repository
    participant B as Request B
    A->>R: findById(id) -> snapshot S1
    B->>R: findById(id) -> snapshot S1
    A->>A: cập nhật locale
    B->>B: cập nhật cart từ S1
    A->>R: save(S2)
    B->>R: save(S3 dựa trên S1)
    Note over R: B có thể ghi đè thay đổi của A
~~~

SessionRepository không tự động cung cấp optimistic locking cho mọi implementation. Việc dùng ConcurrentHashMap hoặc synchronized trong một JVM không giải quyết ghi đồng thời giữa nhiều process.

Các lựa chọn:

- Chấp nhận last-write-wins nếu thuộc tính chỉ mang tính UI và nghiệp vụ cho phép.
- Dùng version và compare-and-set khi cần phát hiện snapshot cũ.
- Dùng transaction/atomic update ở kho dữ liệu.
- Tách dữ liệu nghiệp vụ quan trọng khỏi session.
- Giảm kích thước session để ít request cùng sửa một snapshot lớn.
- Dùng object bất biến và thay thế thuộc tính rõ ràng.

Nếu yêu cầu không mất cập nhật, phải định nghĩa chính sách conflict. Không thể suy ra tính atomic chỉ từ việc repository có phương thức save.

## 15. Serialization và tương thích phiên bản

Session thường sống lâu hơn một request và có thể tồn tại qua nhiều lần deploy. Payload vì vậy phải tương thích giữa các phiên bản ứng dụng đang chạy.

Khi thiết kế serializer:

- Ưu tiên DTO nhỏ và ổn định.
- Có schema version nếu payload có thể thay đổi.
- Có default an toàn cho field mới thực sự có default nghiệp vụ.
- Không đổi package/class tùy tiện nếu dùng Java serialization.
- Không lưu proxy ORM hoặc resource runtime.
- Kiểm thử payload do phiên bản cũ ghi bằng phiên bản mới.
- Nếu rolling deployment, kiểm tra cả chiều ngược lại khi node cũ còn phục vụ.
- Không bắt lỗi deserialize rồi coi session như rỗng mà không có chính sách rõ ràng.

Nếu dữ liệu SecurityContext không còn đọc được, không được khôi phục quyền bằng cách đoán. Có thể invalidate session và yêu cầu đăng nhập lại theo chính sách bảo mật.

## 16. Event và tích hợp vòng đời

SessionRepository interface cơ bản chỉ định nghĩa create, save, find và delete. Nó không bảo đảm mọi repository đều phát cùng loại event. Spring Session và implementation cụ thể có thể tích hợp các sự kiện tạo, xóa hoặc hết hạn theo cơ chế riêng.

Nếu ứng dụng cần audit hoặc đóng WebSocket khi session bị thu hồi, hãy xác định rõ:

- Event nào được phát khi deleteById.
- Expiration event có được phát khi TTL hết hạn hay không.
- Event có được truyền tới mọi application instance không.
- Listener có xử lý lặp lại an toàn không.
- Event bị mất khi subscriber ngắt kết nối được khắc phục thế nào.
- Event có chứa session ID hoặc thông tin nhạy cảm cần redaction không.

Không dùng event làm nguồn dữ liệu bền vững duy nhất. Repository state mới là nguồn sự thật để xác định session còn tồn tại và hợp lệ. Event thường là tín hiệu để các thành phần phụ trợ thực hiện cleanup.

## 17. Tích hợp repository tùy chỉnh vào ứng dụng Servlet

Spring Session cung cấp @EnableSpringHttpSession để bật tích hợp HttpSession dựa trên SessionRepository do ứng dụng cung cấp. Cấu hình khái niệm:

~~~java
@Configuration
@EnableSpringHttpSession
public class CustomSessionConfiguration {

    @Bean
    SessionRepository<MapSession> sessionRepository() {
        return new CustomSessionRepository();
    }
}
~~~

CustomSessionRepository ở đây là implementation của ứng dụng, không phải class có sẵn. Kiểu Session có thể là MapSession hoặc một implementation riêng phù hợp với storage.

Sau khi đăng ký, kiểm tra:

- SessionRepository bean được chọn đúng.
- SessionRepositoryFilter được đăng ký.
- Filter chạy trước các thành phần cần HttpSession.
- Session ID resolver dùng đúng cookie/header contract.
- SecurityContext được lưu và tải qua đúng session.
- Response commit lưu session trước khi phát ID.
- Logout invalidate dữ liệu và xóa cookie.
- Mọi node dùng cùng repository contract.

Nếu dùng Spring Boot starter cho Redis/JDBC, auto-configuration có thể đã tạo repository. Khi tự cung cấp bean hoặc bật cấu hình tùy chỉnh, tránh vô tình tạo hai repository/filter cùng quản lý session.

## 18. SessionRepository đồng bộ và ReactiveSessionRepository

SessionRepository là hợp đồng đồng bộ, phù hợp với tích hợp Servlet truyền thống. Trong WebFlux, thao tác storage cần giữ tính reactive để không chặn event loop. Spring Session có ReactiveSessionRepository với các phương thức trả Publisher/Mono tương ứng.

Không triển khai SessionRepository gọi Redis/JDBC blocking rồi gọi nó từ WebFlux như thể chỉ cần bọc kết quả bằng Mono là non-blocking. Việc đó vẫn chặn thread.

Quy tắc lựa chọn:

| Môi trường | Hợp đồng phù hợp |
|---|---|
| Spring MVC / Servlet | SessionRepository |
| WebFlux | ReactiveSessionRepository |
| Tích hợp storage đồng bộ cũ trong WebFlux | Chỉ dùng cầu nối boundedElastic có kiểm soát khi chưa có lựa chọn reactive; hiểu rõ chi phí blocking |

Không gọi block() trong event loop. Nếu cần một custom reactive repository, phải thiết kế từ đầu bằng reactive client và truyền lỗi/cancellation trong pipeline.

## 19. Kiểm thử hợp đồng SessionRepository

Unit test cần kiểm tra từng phương thức, nhưng integration test phải xác minh cả vòng đời qua filter và storage thật.

| Ca kiểm thử | Thao tác | Kết quả mong đợi |
|---|---|---|
| Tạo session | createSession | ID hợp lệ, metadata khởi tạo đúng |
| Chưa save | createSession rồi findById | Không giả định session đã bền vững |
| Lưu mới | setAttribute rồi save | findById đọc lại được giá trị |
| Cập nhật | Thay đổi metadata/attribute rồi save | Giá trị mới được lưu |
| Xóa | deleteById rồi findById | Kết quả không còn session |
| Xóa lặp lại | deleteById nhiều lần | Không làm repository hỏng |
| ID không tồn tại | findById | Trả null |
| Hết hạn | Đặt interval ngắn và chờ/điều khiển clock | findById từ chối session hết hạn |
| Gia hạn TTL | Cập nhật lastAccessedTime rồi save | Thời hạn được tính lại |
| Đổi ID | changeSessionId và save theo tích hợp | ID mới dùng được, ID cũ bị từ chối |
| Thuộc tính null/xóa | setAttribute null hoặc removeAttribute | Thuộc tính không còn |
| Serialization lỗi | Payload không hợp lệ | Lỗi được báo rõ, không biến thành miss |
| Storage outage | Ngắt Redis/JDBC | Lỗi hạ tầng được phân biệt với null |
| Hai request đồng thời | Cùng cập nhật session | Hành vi conflict đúng chính sách |
| Nhiều node | Node A save, node B find | Cùng nhìn thấy dữ liệu đã commit |

### Ví dụ kiểm thử repository

~~~java
@Test
void savesAndLoadsSessionAttributes() {
    Session session = repository.createSession();

    session.setAttribute("app.locale", "vi-VN");
    session.setMaxInactiveInterval(Duration.ofMinutes(20));

    repository.save(session);

    Session loaded = repository.findById(session.getId());

    assertThat(loaded).isNotNull();
    assertThat(loaded.getAttribute("app.locale"))
            .isEqualTo("vi-VN");
    assertThat(loaded.getMaxInactiveInterval())
            .isEqualTo(Duration.ofMinutes(20));
}
~~~

Ví dụ này minh họa hợp đồng và cần điều chỉnh generic/type/assertion theo implementation cụ thể. Khi kiểm thử expiry, dùng Clock có thể điều khiển hoặc test container với thời gian chờ ngắn; tránh dựa vào sleep dài và timing không ổn định.

### Kiểm thử qua SessionRepositoryFilter

Repository unit test không chứng minh cookie và Servlet lifecycle hoạt động đúng. Cần integration test với filter thực:

1. Gửi request tạo session.
2. Xác nhận response phát session cookie.
3. Gửi request tiếp theo với cookie đó.
4. Xác nhận thuộc tính đã lưu được tải lại.
5. Gửi logout/invalidate.
6. Xác nhận repository không còn session và response xóa cookie.
7. Gửi lại cookie cũ và xác nhận không được xác thực.

Không in cookie thật ra test report. Dùng giá trị giả lập và redaction.

## 20. Kiểm thử nhiều instance và triển khai

Custom repository chỉ hữu ích cho scale ngang nếu nhiều node cùng đọc và ghi một nguồn dữ liệu nhất quán.

Một kiểm thử nhiều node nên xác nhận:

- Node A tạo và save session.
- Node B tìm được cùng ID.
- Node B cập nhật thuộc tính và save.
- Node A đọc lại giá trị mới.
- Logout ở node bất kỳ khiến session không còn hợp lệ ở các node.
- TTL được nhìn nhận nhất quán.
- Serializer và namespace giống nhau.
- Node restart không làm mất session ngoài chính sách.
- Storage outage được báo rõ và không bị coi như session miss.

Khi rolling deployment, payload session phải tương thích giữa phiên bản cũ và mới. Không đổi serializer, class principal, namespace hoặc schema theo cách node cũ không thể đọc trong lúc chúng vẫn phục vụ request.

## 21. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Session tạo xong nhưng request sau không tìm thấy | createSession bị hiểu nhầm là đã persist; save không chạy hoặc lỗi | Kiểm tra filter commit và save |
| Người dùng bị logout sớm | TTL không refresh theo lastAccessedTime | Kiểm tra metadata và phép tính TTL |
| Session sống vô hạn | Không đặt TTL hoặc không kiểm tra logical expiration | Áp dụng expiry ở repository và cleanup |
| Logout nhưng cookie cũ còn dùng được | Chỉ xóa cookie, không xóa record | Invalidate/delete server-side |
| ID cũ còn hoạt động sau rotation | Repository không xóa/thu hồi key cũ | Kiểm tra changeSessionId và migration key |
| Redis outage bị coi là chưa đăng nhập | Nuốt exception rồi trả null | Phân biệt not found với storage failure |
| Thuộc tính mất khi request đồng thời | Lost update từ snapshot cũ | Version/CAS hoặc tách dữ liệu nghiệp vụ |
| Node này đọc được, node khác lỗi | Serializer/namespace/schema không đồng nhất | Chuẩn hóa cấu hình và cross-node test |
| Session record còn nhưng attributes thiếu | Ghi nhiều key không atomic hoặc serialization thất bại | Transaction/script và reconciliation |
| Test repository pass nhưng HTTP lỗi | Không kiểm thử filter/resolver/cookie | Bổ sung integration test Servlet |

## 22. Checklist trước khi phát hành custom SessionRepository

- Đã xác nhận repository có sẵn không đáp ứng yêu cầu cụ thể.
- Đã triển khai đầy đủ createSession, save, findById và deleteById.
- Session ID được sinh an toàn và không đoán được.
- Creation time, lastAccessedTime và maxInactiveInterval có semantics rõ ràng.
- findById trả null cho session không tồn tại/hết hạn, nhưng không nuốt lỗi storage.
- save ghi metadata, attributes và TTL nhất quán.
- Session object trả về độc lập, không chia sẻ mutable instance ngoài ý muốn.
- changeSessionId khiến ID cũ không còn truy cập được.
- deleteById dọn dữ liệu chính và index phụ trợ.
- Logical expiration được kiểm tra ngay cả khi cleanup vật lý trễ.
- Serialization có schema/version và chính sách tương thích.
- Cập nhật đồng thời có chính sách last-write-wins hoặc conflict rõ ràng.
- Event lifecycle được xác định theo implementation, không giả định từ interface.
- Filter/resolver được đăng ký đúng thứ tự.
- Logout xóa repository record và cookie.
- Có test unit, integration filter, expiry, outage, concurrency và cross-node.
- Mọi instance dùng chung namespace, serializer và timeout.
- Log/metric không chứa session ID hoặc dữ liệu nhạy cảm.

SessionRepository là hợp đồng về vòng đời và tính nhất quán của phiên, không chỉ là lớp bọc quanh Redis hoặc JDBC. createSession tạo đối tượng; save làm dữ liệu bền vững; findById chỉ trả phiên còn hợp lệ; deleteById thu hồi phiên và dữ liệu liên quan. Session quản lý ID, metadata thời gian và attributes qua một API thống nhất. Custom implementation phải giữ các bất biến đó qua response commit, đổi ID, timeout, logout, lỗi storage và request đồng thời. Hãy bắt đầu từ repository có sẵn, chỉ tự triển khai khi có yêu cầu cụ thể, và kiểm thử hợp đồng qua cả API repository lẫn SessionRepositoryFilter trên nhiều instance.

## Tài liệu tham khảo

- [Spring Session — Core API](https://docs.spring.io/spring-session/reference/api.html)
- [Spring Session — SessionRepository API](https://docs.spring.io/spring-session/reference/api/java/org/springframework/session/SessionRepository.html)
- [Spring Session — Session API](https://docs.spring.io/spring-session/reference/api/java/org/springframework/session/Session.html)
- [Spring Session — SessionRepositoryFilter API](https://docs.spring.io/spring-session/reference/api/java/org/springframework/session/web/http/SessionRepositoryFilter.html)
- [Spring Session — HttpSession Integration](https://docs.spring.io/spring-session/reference/http-session.html)
- [Spring Session — Redis Configuration](https://docs.spring.io/spring-session/reference/configuration/redis.html)
- [Spring Session — JDBC Configuration](https://docs.spring.io/spring-session/reference/configuration/jdbc.html)

