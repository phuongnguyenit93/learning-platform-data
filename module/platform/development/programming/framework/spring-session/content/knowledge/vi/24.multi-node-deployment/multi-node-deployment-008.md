# Rolling deployment và phiên được tạo bởi hai phiên bản cùng tồn tại

Trong rolling deployment, phiên bản ứng dụng mới được đưa vào cụm theo từng node trong khi các node cũ vẫn tiếp tục phục vụ request. Trong khoảng thời gian này, một người dùng có thể gửi request tới phiên bản cũ ở lần đầu và phiên bản mới ở lần tiếp theo. Cả hai phiên bản thường dùng chung session ID và cùng đọc, ghi dữ liệu trong Redis hoặc JDBC.

Điều đó tạo ra một yêu cầu tương thích hai chiều: phiên được tạo bởi phiên bản cũ phải đọc được bởi phiên bản mới; trong giai đoạn hai phiên bản cùng chạy, dữ liệu do phiên bản mới ghi cũng phải được phiên bản cũ đọc được nếu request có thể quay lại node cũ. Chỉ kiểm tra ứng dụng mới chạy được sau khi triển khai xong là chưa đủ.

Bài này trình bày cách thiết kế dữ liệu session tương thích qua rolling deployment, cách phối hợp serializer, cookie, schema Redis/JDBC và Spring Security, cách xử lý request đồng thời ghi cùng một session, cùng quy trình triển khai và rollback an toàn.

## 1. Vì sao rolling deployment ảnh hưởng tới session?

Spring Session tách dữ liệu phiên khỏi bộ nhớ cục bộ của từng instance. Khi nhiều node cùng dùng một repository, session được tạo trên node A có thể được tải trên node B. Đây là nền tảng để scale ngang, nhưng cũng có nghĩa mọi phiên bản ứng dụng đang chạy phải hiểu cùng dữ liệu.

Giả sử cụm có hai phiên bản:

- V1: phiên bản hiện tại, lưu thuộc tính theo định dạng cũ.
- V2: phiên bản mới, có thêm field hoặc thay đổi kiểu dữ liệu trong một thuộc tính session.

Trong quá trình triển khai, load balancer có thể định tuyến như sau:

~~~mermaid
flowchart LR
    C[Browser] --> LB[Load balancer]
    LB --> A[Node A - V1]
    LB --> B[Node B - V2]
    A --> R[(Shared Redis or JDBC)]
    B --> R
    A -. reads and writes .-> R
    B -. reads and writes .-> R
~~~

Cookie session ID của trình duyệt thường vẫn giữ nguyên. Request kế tiếp không nhất thiết quay lại cùng node hoặc cùng phiên bản. Sticky session chỉ làm giảm việc chuyển node; nó không bảo đảm tương thích khi node bị restart, failover hoặc load balancer thay đổi định tuyến.

Các rủi ro thường gặp:

- V2 không deserialize được object do V1 ghi.
- V1 không deserialize được object mới do V2 ghi trong lúc V1 vẫn còn nhận request.
- Hai phiên bản dùng serializer hoặc namespace Redis khác nhau.
- Một phiên bản đổi tên cookie hoặc thuộc tính cookie khiến trình duyệt không gửi đúng session ID.
- Database schema bị đổi theo cách node cũ không còn truy vấn được.
- Spring Security đổi class Authentication, principal hoặc authorities khiến SecurityContext cũ không đọc được.
- Hai phiên bản cùng cập nhật một thuộc tính session từ hai snapshot khác nhau và ghi đè thay đổi của nhau.
- Rollback đưa V1 trở lại sau khi V2 đã ghi dữ liệu mà V1 không hiểu.

Vì vậy, session là một hợp đồng dữ liệu tồn tại lâu hơn một request và thường lâu hơn một lần triển khai.

## 2. Những lớp tương thích cần được giữ

Không chỉ schema SQL hoặc key Redis cần tương thích. Cần kiểm tra toàn bộ hợp đồng giữa client, ứng dụng và repository.

| Lớp | Điều cần tương thích giữa V1 và V2 |
|---|---|
| Session ID | Cùng cách đọc và tìm ID trong repository |
| Cookie/resolver | Tên cookie hoặc header, Domain, Path, Secure, SameSite và cách xóa cookie |
| Repository | Cùng Redis namespace hoặc JDBC tableName/schema |
| Serialization | V2 đọc được payload V1; trong mixed rollout, V1 đọc được payload V2 nếu V2 có thể ghi |
| Session attributes | Tên thuộc tính, kiểu dữ liệu và ý nghĩa của payload |
| Spring Security | SecurityContext, Authentication, principal và authorities |
| Timeout | Max inactive interval, TTL và quy tắc refresh |
| Save/flush policy | Cách chọn thuộc tính cần lưu và thời điểm ghi |
| Event handling | Cùng hiểu sự kiện hết hạn/xóa và quy trình thu hồi session |
| Business semantics | Cùng hiểu ý nghĩa của thuộc tính trong thời gian hai phiên bản cùng chạy |

Tương thích có thể chia thành ba câu hỏi:

1. V2 có đọc được session được tạo bởi V1 không?
2. Trong thời gian V1 và V2 cùng chạy, V1 có đọc được session do V2 ghi không?
3. Nếu triển khai V2 thất bại và phải rollback, V1 có đọc được các session đã bị V2 cập nhật không?

Nếu câu trả lời cho câu 2 hoặc 3 là không, cần trì hoãn việc ghi định dạng mới cho tới khi không còn node hoặc phương án rollback nào cần đọc định dạng cũ.

## 3. Phân biệt session metadata với session attribute payload

Repository lưu metadata như session ID, thời điểm tạo, lần truy cập gần nhất và thời gian không hoạt động tối đa. Ngoài ra, ứng dụng lưu các thuộc tính như locale, cart ID, trạng thái wizard hoặc SecurityContext.

Hai loại dữ liệu này có rủi ro migration khác nhau:

- Metadata và schema repository cần tương thích với SQL/key layout, index và cấu hình repository.
- Attribute payload cần tương thích với serializer và class/type được lưu.

Một migration thêm index hoặc cột database có thể hoàn toàn thành công nhưng payload Java cũ vẫn không deserialize được. Ngược lại, đổi serializer sang JSON không nhất thiết yêu cầu đổi bảng JDBC, nhưng có thể khiến các byte đã lưu trước đó không đọc được.

Hãy lập danh sách các thuộc tính session do ứng dụng và framework tạo ra. Đặc biệt chú ý:

- Các DTO riêng của ứng dụng.
- Collection và object lồng nhau.
- Principal tùy chỉnh.
- Authentication implementation tùy chỉnh.
- SecurityContext.
- Các thuộc tính do thư viện đăng nhập, OAuth2 hoặc remember-me lưu.
- Các thuộc tính có thể được tạo bởi nhiều phiên bản trong cùng một session.

Không giả định mọi thuộc tính đều có cùng tuổi thọ hoặc cùng serializer. Kiểm tra cấu hình thực tế của phiên bản Spring Session đang dùng.

## 4. Thiết kế session payload ổn định

Session nên chứa dữ liệu nhỏ và có hợp đồng ổn định. Ví dụ, lưu ID giỏ hàng thay vì cả entity:

~~~java
session.setAttribute("app.cartId", cartId);
~~~

Cách này giúp V1 và V2 không cần chia sẻ toàn bộ class graph của Cart, Hibernate proxy hoặc các object nghiệp vụ có cấu trúc thay đổi thường xuyên.

Ưu tiên các kiểu dữ liệu đơn giản hoặc DTO chuyên dụng:

- String, số, boolean và giá trị thời gian có quy ước rõ ràng.
- ID tham chiếu tới dữ liệu nghiệp vụ.
- DTO nhỏ có field ổn định.
- Collection có phần tử cùng kiểu và có giới hạn kích thước.
- Enum dùng tên ổn định hoặc mã chuỗi đã quy ước, không dùng ordinal làm hợp đồng lưu trữ lâu dài.

Hạn chế lưu:

- JPA entity hoặc Hibernate proxy.
- Object chứa dependency, service, connection hoặc resource.
- Lambda, anonymous class hoặc class nội bộ dễ thay đổi.
- Đồ thị object lớn, vòng tham chiếu phức tạp.
- Class thuộc package thường xuyên đổi tên.
- Dữ liệu nghiệp vụ cần transaction hoặc optimistic locking.

Nếu cần thay đổi cấu trúc, hãy coi session attribute như một message contract có version. Ví dụ payload JSON:

~~~json
{
  "schemaVersion": 2,
  "cartId": "cart-7f21",
  "displayCurrency": "VND",
  "lastViewedCategory": "books"
}
~~~

V2 có thể đọc schemaVersion 1 và 2, rồi chuyển về model nội bộ hiện tại. Một reader tương thích nên xử lý field mới bị thiếu bằng default hợp lý và bỏ qua field không còn sử dụng khi điều đó an toàn.

Không tự động áp dụng default cho dữ liệu bảo mật hoặc quyền hạn. Nếu thiếu claim/authority quan trọng, phải từ chối hoặc yêu cầu xác thực lại thay vì suy đoán quyền.

## 5. Java serialization và rủi ro đổi class

Nếu session attribute được lưu bằng Java serialization, payload thường phụ thuộc tên class, cấu trúc class, class hierarchy và serialVersionUID. Đổi package, đổi tên class, thay kiểu field hoặc thay quan hệ kế thừa có thể làm payload cũ không đọc được.

Ví dụ, V1 lưu:

~~~java
public class CartPreference implements Serializable {
    private static final long serialVersionUID = 1L;

    private String currency;
}
~~~

V2 muốn đổi currency thành một kiểu Money object. Việc thay field trực tiếp có thể khiến quá trình đọc object cũ không còn tương thích như mong đợi.

Cách an toàn hơn là giữ class lưu trữ ổn định trong giai đoạn chuyển đổi, thêm field mới có thể thiếu, hoặc chuyển đổi sang DTO versioned. Tuy nhiên, serialVersionUID bằng nhau không bảo đảm mọi thay đổi class đều an toàn; vẫn phải kiểm tra quy tắc tương thích của Java serialization và chạy test với byte fixture thật từ V1.

Nếu đổi từ Java serialization sang JSON hoặc một serializer khác, cần một giai đoạn đọc được cả hai định dạng hoặc có migration riêng. Chỉ đổi cấu hình serializer đồng loạt khi không còn session cũ, hoặc khi reader có thể nhận biết và chuyển đổi payload cũ.

Không thử deserialize payload không tin cậy bằng Java serialization mà không có kiểm soát class allowlist/filter phù hợp. Session store cần được bảo vệ như dữ liệu nhạy cảm.

## 6. Tương thích với Spring Security

Trong ứng dụng stateful, SecurityContext thường được lưu trong session để request tiếp theo khôi phục Authentication. Do đó, thay đổi Spring Security hoặc class principal có thể làm session cũ không đọc được.

Những thay đổi cần kiểm tra:

- Class principal tùy chỉnh đổi package hoặc tên.
- Authentication implementation thay đổi.
- UserDetails có field mới hoặc thay đổi kiểu.
- Authority được đổi tên hoặc chuyển cách biểu diễn.
- Các thuộc tính SecurityContext được serialize theo serializer khác.
- Cấu hình SecurityContextRepository thay đổi.
- Cơ chế session fixation hoặc đăng nhập thay đổi cách tạo session.

Không nên lưu toàn bộ entity User vào principal nếu class entity thay đổi thường xuyên. Một principal nhỏ, ổn định với user ID và thông tin cần thiết sẽ giảm rủi ro.

Nếu SecurityContext cũ không thể đọc an toàn, chính sách hợp lệ có thể là invalidate session và yêu cầu đăng nhập lại. Không bắt lỗi deserialize rồi tiếp tục request như một user đã xác thực, cũng không khôi phục quyền từ dữ liệu không rõ định dạng.

Kiểm thử login bằng V1, sau đó gửi request qua V2 và xác nhận principal/authorities đúng. Làm ngược lại trong giai đoạn mixed deployment nếu V2 có thể ghi SecurityContext mới.

## 7. Chiến lược reader và writer tương thích hai chiều

Trong rolling deployment, V1 và V2 cùng hoạt động. Nếu V2 ghi ngay payload mới mà V1 không hiểu, request kế tiếp có thể được định tuyến về V1 và lỗi.

Một chiến lược an toàn thường gồm các bước:

- Reader mới hiểu cả định dạng cũ và mới.
- Writer tiếp tục ghi định dạng cũ trong lúc còn node cũ.
- Chỉ bật writer định dạng mới sau khi mọi node không tương thích đã được rút khỏi cụm.
- Reader mới tiếp tục đọc định dạng cũ trong toàn bộ thời gian session cũ có thể còn tồn tại.
- Rollback chỉ được phép về phiên bản vẫn đọc được dữ liệu đã ghi.

Sơ đồ triển khai hai giai đoạn:

~~~mermaid
flowchart TD
    A[V1: đọc/ghi format 1] --> B[V2 bridge: đọc format 1 và 2, vẫn ghi format 1]
    B --> C[Triển khai V2 bridge tới toàn bộ node]
    C --> D[V2 writer: bắt đầu ghi format 2]
    D --> E[V2 reader tiếp tục đọc format 1 và 2]
    E --> F[Hết thời gian lưu session cũ]
    F --> G[Loại bỏ reader format 1 trong release sau]
~~~

Điểm quan trọng: nếu V2 bridge chỉ được triển khai trên một phần node và đã ghi format 2, các node V1 còn lại vẫn có thể nhận request và không đọc được session. Vì vậy, bridge release phải duy trì định dạng ghi tương thích cũ cho tới khi không còn V1.

Nếu không thể tạo bridge release, các lựa chọn gồm giữ định dạng cũ lâu hơn, tách namespace/cookie để buộc người dùng tạo session mới, hoặc chủ động invalidate session và yêu cầu đăng nhập lại. Đây là thay đổi trải nghiệm người dùng cần được lên kế hoạch rõ ràng.

## 8. Quy trình rolling deployment theo từng giai đoạn

Một quy trình triển khai có kiểm soát:

### Giai đoạn 1: Kiểm kê và chuẩn bị

- Liệt kê mọi session attribute do ứng dụng và framework lưu.
- Xác định serializer đang dùng trong Redis/JDBC.
- Ghi nhận Redis namespace, JDBC tableName, cookie name và timeout.
- Tạo fixture session được ghi bởi build hiện tại.
- Xác định phiên bản tối thiểu có thể đọc payload mới.
- Xác định thời gian session tối đa có thể còn tồn tại.
- Kiểm tra rollback target có đọc được dữ liệu trong repository không.

### Giai đoạn 2: Mở rộng schema và reader

Nếu cần thay đổi schema JDBC, dùng expand-contract:

1. Thêm cột/index/bảng mới theo hướng tương thích với code cũ.
2. Chưa xóa hoặc đổi tên cột mà V1 còn sử dụng.
3. Triển khai code có thể đọc schema cũ và schema mở rộng.
4. Giữ writer tương thích với V1.
5. Kiểm tra tất cả node đã dùng cấu hình mới.

Với Redis, giữ namespace và cấu trúc key cũ trong giai đoạn mixed deployment nếu V1 vẫn cần đọc. Nếu cần key mới, có thể thêm key song song nhưng phải có kế hoạch đồng bộ và dọn dữ liệu rõ ràng.

### Giai đoạn 3: Triển khai bridge version

Triển khai V2 bridge theo từng node:

- V2 đọc được payload V1.
- V2 vẫn ghi payload V1 hoặc một format mà V1 hiểu.
- V1 và V2 dùng cùng repository/cookie contract.
- Kiểm tra request chuyển qua lại giữa V1 và V2.
- Theo dõi lỗi deserialize và session lookup.

Khi node cuối cùng của V1 đã được drain và không còn xử lý request, xác nhận điều đó bằng deployment state và metric, không chỉ bằng thời gian chờ.

### Giai đoạn 4: Bật định dạng ghi mới

Sau khi không còn node V1:

- Bật writer format 2 bằng feature flag hoặc cấu hình được kiểm soát.
- V2 tiếp tục đọc format 1 và format 2.
- Kiểm tra rollback target. Nếu rollback về V1 không còn an toàn, phải ghi rõ điểm không thể quay lại hoặc giữ một phiên bản bridge làm rollback target.
- Theo dõi tỷ lệ payload cũ/mới và lỗi chuyển đổi.

### Giai đoạn 5: Thu hẹp tương thích

Chỉ bỏ reader format 1 khi:

- Không còn session format 1 có thể truy cập.
- Đã hết idle timeout và absolute timeout theo chính sách.
- Đã hết cửa sổ rollback.
- Đã kiểm tra backup/restore và các bản sao dữ liệu liên quan.
- Không còn node hoặc tác vụ nền nào cần đọc format cũ.

Không xóa khả năng đọc format cũ ngay sau khi rolling deployment kết thúc; session cũ có thể vẫn sống lâu hơn deployment.

## 9. Redis repository trong giai đoạn mixed version

Khi dùng Spring Session Redis, tất cả node cần hiểu cùng namespace và cấu trúc dữ liệu của repository. Các cấu hình cần đồng nhất:

- Redis endpoint/cluster và database index nếu có.
- Redis namespace.
- Serializer cho session attributes.
- Cách đặt TTL và refresh expiration.
- Chính sách SaveMode/FlushMode phù hợp với phiên bản.
- Cookie serializer và resolver.
- Cấu hình index hoặc event nếu ứng dụng sử dụng.

Không để V1 ghi vào namespace A còn V2 đọc namespace B nếu mục tiêu là chia sẻ session. Nếu chủ động tách namespace để cô lập version, phải chấp nhận session không được chia sẻ giữa hai nhóm và xác định cách chuyển hoặc yêu cầu đăng nhập lại.

Ví dụ cấu hình minh họa:

~~~java
@Configuration
@EnableRedisHttpSession(
    redisNamespace = "spring:session:application",
    maxInactiveIntervalInSeconds = 1800
)
public class SessionConfiguration {
}
~~~

Không đổi namespace chỉ vì release mới có tên khác. Namespace là một phần của hợp đồng lưu trữ. Thay namespace trong rolling deployment có thể khiến phiên bản mới không tìm thấy session cũ dù dữ liệu vẫn còn trong Redis.

Khi đổi serializer, hãy chạy test đọc fixture cũ bằng đúng serializer và dependency của release mới. Nếu cần dual-format reader, thiết kế lớp chuyển đổi có nhận diện format rõ ràng; không đoán format bằng cách thử deserialize tùy tiện rồi bỏ qua mọi lỗi.

## 10. JDBC repository và schema migration

Với Spring Session JDBC, các phiên bản thường chia sẻ bảng session và bảng attributes. Tất cả node cần dùng cùng tableName và schema tương thích.

Các quy tắc triển khai:

- Dùng migration Flyway/Liquibase hoặc quy trình DDL có kiểm soát.
- Thêm cấu trúc mới trước khi triển khai code cần nó.
- Giữ cột, index và constraint cũ cho tới khi V1 không còn chạy.
- Không để từng node tự khởi tạo hoặc thay đổi schema trong production.
- Dùng tài khoản migration riêng có quyền DDL.
- Runtime account chỉ có quyền DML cần thiết.
- Kiểm thử SQL repository trên database vendor thực tế.

Nếu V2 thêm một bảng phụ để lưu metadata mới, V1 có thể bỏ qua bảng đó trong thời gian mixed deployment. Nhưng nếu V2 thay đổi cách đọc bảng hiện có theo hướng không tương thích, cần một giai đoạn chuyển tiếp.

Cần tách biệt migration schema với migration payload. Việc thêm cột vào SPRING_SESSION không tự chuyển đổi byte trong SPRING_SESSION_ATTRIBUTES. Nếu payload cũ chứa class không còn tồn tại, vẫn cần reader tương thích hoặc chính sách yêu cầu xác thực lại.

## 11. Cookie và session ID phải ổn định qua rollout

Session ID là định danh để repository tìm session. Cookie hoặc header resolver là cách client gửi ID về server. Trong rolling deployment, mọi node cần hiểu cùng định danh.

Kiểm tra các cấu hình:

- Cookie name.
- Domain và Path.
- Secure và HttpOnly.
- SameSite.
- Header name nếu dùng HeaderHttpSessionIdResolver.
- Cách xóa cookie khi logout.
- Cấu hình proxy và TLS termination.

Không đổi cookie name, Domain hoặc Path giữa V1 và V2 nếu cả hai phải nhận cùng session. Nếu cần đổi, hãy triển khai giai đoạn tương thích có thể đọc cả cookie cũ và mới, hoặc chấp nhận session reset có kế hoạch.

Không tạo session ID mới chỉ vì phiên bản ứng dụng đổi. Session ID cần tiếp tục tham chiếu tới dữ liệu hiện có, trừ khi có lý do bảo mật như session fixation protection hoặc chính sách thu hồi.

## 12. Timeout và thời gian tồn tại của dữ liệu cũ

Session thường có idle timeout. Nếu người dùng hoạt động, thời hạn có thể được refresh. Do đó, thời gian tồn tại của payload cũ không nhất thiết bằng một con số cố định kể từ ngày triển khai.

Trước khi bỏ reader cũ, cần xác định:

- Max inactive interval.
- Có absolute session timeout hay không.
- Request nào refresh lastAccessedTime.
- WebSocket/STOMP message có cập nhật activity không.
- Có remember-me hoặc cơ chế tự tạo session mới không.
- Có session được khôi phục từ backup hoặc replication delay không.
- Cleanup job có thể chạy trễ bao lâu.

Nếu session timeout là 30 phút nhưng người dùng có thể hoạt động liên tục, một session được tạo từ trước deploy có thể tồn tại lâu hơn 30 phút kể từ lúc deploy. Reader cũ chỉ có thể bỏ sau khi mọi session cũ đã hết hạn hoặc đã được chuyển đổi/xóa theo chính sách.

Đối với hệ thống có absolute timeout, dùng mốc đó để xác định giới hạn tuổi tối đa. Không dựa vào TTL hiện tại của Redis nếu ứng dụng còn cơ chế refresh.

## 13. Hai phiên bản cùng ghi một session

Trong rolling deployment, hai request cùng session có thể được xử lý bởi hai phiên bản. Ví dụ:

1. V1 tải session với cart snapshot S1.
2. V2 cũng tải session với snapshot S1.
3. V2 cập nhật locale và lưu.
4. V1 cập nhật cart từ snapshot cũ và lưu sau.
5. Tùy repository và SaveMode, V1 có thể ghi đè một phần hoặc toàn bộ dữ liệu V2 đã cập nhật.

Đây là vấn đề concurrency, không chỉ serialization compatibility.

Các biện pháp giảm rủi ro:

- Tránh hai phiên bản thay đổi cùng một thuộc tính trong cùng cửa sổ rollout.
- Dùng tên thuộc tính mới cho dữ liệu mới nếu cần tách semantics, nhưng vẫn phải thiết kế reader và cleanup.
- Ưu tiên immutable DTO và cập nhật thuộc tính tường minh.
- Không lưu dữ liệu nghiệp vụ cần atomic update trong session.
- Dùng version/CAS hoặc transaction riêng khi cần chống lost update.
- Giữ SaveMode/FlushMode nhất quán giữa các node trong giai đoạn mixed version.
- Kiểm thử thứ tự đọc/ghi có chủ đích giữa V1 và V2.

Không giả định Redis hoặc JDBC repository tự động merge hai snapshot. Không dùng synchronized trong JVM như khóa cho các node khác nhau.

## 14. Thay đổi thuộc tính theo kiểu expand-contract

Nếu cần đổi tên hoặc cấu trúc thuộc tính, hãy chuyển đổi theo từng bước.

Ví dụ V1 lưu app.profile với cấu trúc cũ. V2 cần thêm displayName và timezone.

Một phương án:

- Release bridge: đọc app.profile cũ, có thể đọc thêm app.profile.v2 nếu tồn tại, nhưng tiếp tục ghi cấu trúc cũ.
- Khi toàn bộ node đã là bridge, bật ghi cấu trúc mới đồng thời giữ reader cũ.
- Trong một thời gian, reader mới có thể chuyển đổi profile cũ sang model mới khi đọc.
- Khi không còn session cũ, ngừng ghi và sau đó bỏ hỗ trợ cấu trúc cũ.

Ví dụ payload:

~~~json
{
  "schemaVersion": 1,
  "locale": "vi-VN"
}
~~~

V2 có thể đọc version 1 và chuyển đổi nội bộ:

~~~java
ProfilePreferences toCurrent(ProfilePayload payload) {
    return switch (payload.schemaVersion()) {
        case 1 -> new ProfilePreferences(
                payload.locale(),
                "Asia/Ho_Chi_Minh",
                "default"
        );
        case 2 -> new ProfilePreferences(
                payload.locale(),
                payload.timeZone(),
                payload.displayName()
        );
        default -> throw new UnsupportedSessionSchemaException();
    };
}
~~~

Đoạn code minh họa mapper theo version. Default chỉ an toàn nếu field mới thực sự có giá trị mặc định đúng nghiệp vụ. Với quyền, tenant, consent hoặc trạng thái bảo mật, không tự gán default làm tăng quyền.

Không dual-write hai cấu trúc mà không có kế hoạch nhất quán. Nếu ghi cấu trúc cũ và mới bằng hai thao tác độc lập, một thao tác có thể thành công còn thao tác kia thất bại. Nếu bắt buộc dual-write, cần transaction/atomic operation hoặc cơ chế reconciliation.

## 15. Rollback khi session đã được V2 cập nhật

Rollback ứng dụng không tự rollback dữ liệu session. Redis/JDBC có thể vẫn chứa payload được tạo bởi V2 sau khi binary V1 được khởi động lại.

Trước rollout, xác định rollback matrix:

| Trạng thái dữ liệu | V1 có đọc được? | Hành động |
|---|---|---|
| Chỉ format cũ | Có | Có thể rollback về V1 |
| Format mới nhưng tương thích ngược | Có | Có thể rollback sau khi xác nhận bằng test |
| Format mới V1 không đọc được | Không | Không rollback trực tiếp về V1 |
| SecurityContext không tương thích | Có thể không | Thu hồi session và yêu cầu login lại hoặc dùng bridge |
| Schema mới chỉ thêm cấu trúc tương thích | Thường có | Giữ schema mở rộng khi rollback |
| Schema đã xóa/đổi cột V1 cần | Không | Cần phục hồi schema tương thích trước khi rollback |

Một quy trình rollback an toàn:

1. Dừng bật writer format mới nếu có feature flag.
2. Giữ hoặc triển khai bridge version có thể đọc cả hai format.
3. Nếu V1 không đọc được dữ liệu mới, không đưa V1 trở lại phục vụ request session đó.
4. Có thể invalidate các session không tương thích và yêu cầu người dùng xác thực lại nếu đó là phương án được phê duyệt.
5. Không xóa dữ liệu session hàng loạt để “sửa” lỗi mà chưa đánh giá ảnh hưởng.
6. Xác nhận cookie, repository và schema vẫn tương thích với phiên bản rollback.
7. Theo dõi lỗi deserialize, login failure và session lookup sau rollback.

Nếu yêu cầu rollback tức thời về V1, V2 phải tiếp tục ghi định dạng V1 trong toàn bộ cửa sổ rollback. Đây là lý do cần tách thời điểm triển khai binary mới khỏi thời điểm bật format writer mới.

## 16. Kiểm thử tương thích trước khi triển khai

Kiểm thử cần dùng artifact thực tế của hai phiên bản, không chỉ hai class trong cùng một source tree.

### Bộ fixture

Tạo fixture session bằng V1, gồm:

- Session attribute ứng dụng.
- SecurityContext và principal.
- Collection lồng nhau.
- Các thuộc tính do login/remember-me tạo nếu được dùng.
- Session có thời gian còn hạn và session sắp hết hạn.

Lưu fixture theo cách bảo vệ dữ liệu. Không dùng session của người dùng thật vì có thể chứa token hoặc thông tin cá nhân.

### Ma trận đọc/ghi

| Người ghi | Người đọc | Điều cần xác nhận |
|---|---|---|
| V1 | V1 | Hành vi baseline |
| V1 | V2 | V2 đọc session cũ |
| V2 bridge ghi format cũ | V1 | V1 vẫn đọc được trong mixed rollout |
| V2 writer ghi format mới | V2 | V2 đọc lại đúng |
| V2 writer ghi format mới | V1 | Chỉ cần pass nếu V1 vẫn nằm trong rollout/rollback window |
| V1 fixture | V2 sau nâng cấp | Không lỗi serializer hoặc SecurityContext |
| V2 session | V1 rollback | Chỉ cho phép nếu đã chứng minh tương thích ngược |

### Kiểm thử qua HTTP và repository

- Đăng nhập qua V1, gửi request tiếp theo tới V2.
- Đăng nhập qua V2 bridge, gửi request tiếp theo tới V1.
- Giữ nguyên cookie session qua các request.
- Xác nhận principal và authorities không đổi ngoài dự kiến.
- Kiểm tra logout trên node khác xóa session dùng chung.
- Kiểm tra TTL và cleanup.
- Gửi hai request đồng thời qua hai phiên bản để phát hiện lost update.
- Chạy với Redis/JDBC thật, serializer và schema production-like.
- Kiểm tra rollback bằng artifact cũ, không chỉ mock object.

Test có thể dùng Testcontainers, embedded server hoặc môi trường staging với hai deployment riêng. Quan trọng là mỗi request thực sự đi qua đúng binary/version và cùng repository.

## 17. Quan sát trong quá trình rollout

Cần đo khả năng tương thích khi V1 và V2 cùng chạy:

- Số request theo application version.
- Tỷ lệ session lookup miss.
- Lỗi deserialize theo loại exception và phiên bản node.
- Lỗi lưu session và lỗi serialization.
- Số lần session bị invalidate hoặc yêu cầu login lại.
- Độ trễ Redis/JDBC và connection pool.
- Tỷ lệ session payload theo schema version nếu có thể đo an toàn.
- Số request được định tuyến giữa hai phiên bản.
- Tỷ lệ logout, login failure và 401/403.
- Số session được chuyển đổi khi đọc.

Không ghi session ID, cookie, token hoặc SecurityContext vào log. Metric label chỉ nên dùng giá trị hữu hạn như applicationVersion, serializerVersion, operation và outcome. Không dùng principal name hoặc session ID làm label.

Có thể ghi một trường telemetry riêng cho schema version của payload mà không lưu nội dung payload. Điều này giúp xác định khi nào không còn session format cũ, nhưng cần bảo đảm không tạo metric cardinality lớn.

## 18. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Người dùng bị logout ngẫu nhiên trong rollout | V2 không đọc được payload V1 hoặc SecurityContext cũ | Dùng fixture cũ và bridge reader |
| Request lỗi tùy node | Node V1/V2 dùng serializer hoặc namespace khác | Đồng bộ cấu hình và kiểm thử cross-version |
| V1 lỗi sau khi V2 đã chạy | V2 ghi format mới trong khi V1 vẫn phục vụ | Giữ writer cũ cho tới khi V1 được drain |
| Rollback làm mọi session lỗi | V1 không đọc payload V2 | Duy trì rollback-compatible writer hoặc bridge |
| V2 không tìm thấy session cũ | Cookie name, repository namespace hoặc tableName thay đổi | Giữ ID transport và repository contract ổn định |
| JDBC node cũ lỗi SQL | Migration xóa/đổi cột quá sớm | Áp dụng expand-contract |
| Redis session tồn tại nhưng không deserialize được | Serializer hoặc class payload thay đổi | Dual reader/migration hoặc invalidate có kiểm soát |
| SecurityContext mất authorities | Principal/Authentication schema thay đổi | Kiểm thử security fixture và yêu cầu re-auth nếu cần |
| Mất cập nhật khi request đổi node | Hai phiên bản ghi snapshot khác nhau | Kiểm thử concurrency, version/CAS hoặc tách dữ liệu nghiệp vụ |
| Không biết khi nào bỏ format cũ | Không đo schema version và session lifetime | Theo dõi payload version và chờ hết TTL/absolute timeout |

## 19. Checklist rolling deployment

Trước khi bắt đầu rollout:

- Đã liệt kê mọi thuộc tính session và serializer thực tế.
- Đã tạo fixture session từ phiên bản hiện tại.
- Phiên bản mới đọc được payload cũ.
- Trong thời gian mixed deployment, writer không phát payload mà node cũ không đọc được.
- Rollback target đọc được dữ liệu mà release mới ghi.
- Redis namespace hoặc JDBC tableName không thay đổi ngoài kế hoạch.
- Schema database được mở rộng trước khi code mới cần dùng.
- Cookie name, Domain, Path, Secure, HttpOnly và SameSite được giữ tương thích.
- SecurityContext, principal và authorities đã được kiểm thử chéo phiên bản.
- Timeout và cleanup được hiểu rõ.
- SaveMode/FlushMode không thay đổi tùy tiện giữa các node.
- Đã kiểm thử hai request đồng thời cập nhật cùng session.
- Có metric theo version và lỗi deserialize.
- Có phương án yêu cầu đăng nhập lại cho session không thể chuyển đổi an toàn.
- Chỉ bỏ reader cũ sau khi session cũ hết hạn và rollback window kết thúc.

Rolling deployment chỉ an toàn khi mọi phiên bản cùng tồn tại có thể đọc và xử lý session mà các phiên bản khác tạo ra. Hãy giữ session payload nhỏ, ổn định và có version; triển khai reader tương thích trước, trì hoãn writer mới cho tới khi node cũ đã được drain, và giữ khả năng đọc format cũ trong toàn bộ thời gian session có thể tồn tại. Schema Redis/JDBC, cookie, SecurityContext và chính sách TTL cũng là một phần của hợp đồng. Kiểm thử bằng artifact cũ/mới và repository thật giúp phát hiện lỗi trước khi người dùng bị đăng xuất hoặc dữ liệu session bị ghi đè.

## Tài liệu tham khảo

- [Spring Session — Redis Configuration](https://docs.spring.io/spring-session/reference/configuration/redis.html)
- [Spring Session — JDBC Configuration](https://docs.spring.io/spring-session/reference/configuration/jdbc.html)
- [Spring Session — HttpSession Integration](https://docs.spring.io/spring-session/reference/http-session.html)
- [Spring Security — SecurityContext Persistence](https://docs.spring.io/spring-security/reference/servlet/authentication/persistence.html)
- [Spring Boot — Database Initialization and Migration](https://docs.spring.io/spring-boot/how-to/data-initialization.html)
- [Flyway — Versioned Migrations](https://documentation.red-gate.com/flyway/flyway-concepts/migrations/versioned-migrations)

