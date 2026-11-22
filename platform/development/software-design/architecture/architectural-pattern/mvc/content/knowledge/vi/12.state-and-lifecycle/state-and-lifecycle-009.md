# Ngăn dữ liệu của người dùng này ảnh hưởng người dùng khác

Trong module **MODEL_VIEW_CONTROLLER**, ứng dụng web tiếp nhận request, xử lý trạng thái và nghiệp vụ, rồi trả dữ liệu qua View hoặc API. Nhiều người dùng có thể gửi request đến cùng một ứng dụng trong cùng thời điểm. Vì vậy, mỗi request phải làm việc với đúng danh tính và phạm vi dữ liệu của người gửi. Một lỗi nhỏ trong cách giữ trạng thái, truy vấn hoặc lưu cache có thể khiến người dùng nhìn thấy hay thay đổi dữ liệu của người khác.

Nguyên tắc cốt lõi là xác định danh tính người dùng ở phía server, kiểm tra quyền trên từng tài nguyên và giới hạn mọi thao tác dữ liệu theo đúng phạm vi người dùng hoặc tổ chức. Đồng thời, không đặt trạng thái riêng của một request vào thành phần dùng chung giữa nhiều request. Cô lập dữ liệu là trách nhiệm xuyên suốt từ Controller, tầng ứng dụng, Model, kho lưu trữ đến cache và tác vụ nền.

## 1. Vì sao dữ liệu có thể bị lẫn giữa người dùng?

Một ứng dụng MVC thường phục vụ nhiều request bằng cùng một tiến trình và nhiều thành phần được tái sử dụng. Controller, service, repository hoặc cache có thể được dùng chung trong suốt vòng đời ứng dụng. Nếu dữ liệu riêng của một người dùng được giữ sai nơi hoặc truy vấn không giới hạn theo quyền, dữ liệu có thể vượt qua ranh giới giữa các tài khoản.

Các nguyên nhân thường gặp:

- **Trạng thái dùng chung bị thay đổi:** một Spring singleton bean giữ currentUser, currentOrder hoặc danh sách kết quả trong field rồi request khác ghi đè.
- **Tin vào ID do client gửi:** endpoint nhận userId hoặc accountId từ URL rồi truy vấn trực tiếp mà không xác minh người gọi có quyền truy cập.
- **Truy vấn thiếu điều kiện sở hữu:** tìm đơn hàng theo orderId mà không ràng buộc chủ sở hữu hoặc tenant.
- **Cache dùng khóa không đầy đủ:** kết quả của người dùng A được lưu dưới một khóa chung và trả cho người dùng B.
- **Session dùng sai mục đích:** lưu dữ liệu của nhiều tài khoản vào cùng một session hoặc không xóa dữ liệu cũ khi đăng xuất/đổi tài khoản.
- **Tác vụ bất đồng bộ mất ngữ cảnh:** công việc nền không giữ đúng danh tính, tenant hoặc quyền đã được xác minh khi request khởi tạo nó.
- **Kiểm thử chỉ dùng một tài khoản:** lỗi cô lập không xuất hiện vì test không mô phỏng hai người dùng cùng truy cập.

Một ứng dụng chạy đúng với một người dùng vẫn có thể sai khi có nhiều request đồng thời. Vì vậy, cần thiết kế và kiểm thử ranh giới dữ liệu ngay từ đầu.

## 2. Hiểu vòng đời của các thành phần trong MVC

Trong Spring MVC, Controller và service được quản lý theo scope mặc định là singleton. Một instance có thể xử lý nhiều request theo thời gian và nhiều thread có thể gọi cùng lúc. Vì vậy, các bean dùng chung nên giữ cấu hình và dependency ổn định, còn dữ liệu riêng của request nên nằm trong biến cục bộ hoặc đối tượng có scope phù hợp.

| Vùng lưu trạng thái | Vòng đời / phạm vi | Dữ liệu phù hợp |
| --- | --- | --- |
| Biến cục bộ trong phương thức | Một lần gọi phương thức | Giá trị trung gian của request |
| Request scope | Một HTTP request | Dữ liệu phục vụ riêng request hiện tại |
| Session scope | Một phiên trình duyệt/người dùng | Thông tin phiên cần duy trì qua nhiều request, như lựa chọn quy trình tạm thời |
| Application/singleton scope | Toàn ứng dụng | Cấu hình, dependency và dữ liệu dùng chung có kiểm soát |
| Database | Lâu dài, theo bản ghi và quyền truy cập | Dữ liệu nghiệp vụ được lưu bền vững |

Không nên dùng field có thể thay đổi trong singleton Controller hoặc service để lưu người dùng hiện tại:

~~~java
@Controller
public class AccountController {
    private String currentUserId; // Sai: được chia sẻ giữa các request

    @GetMapping("/account")
    public String account(@RequestParam String userId, Model model) {
        currentUserId = userId;
        // Request khác có thể ghi đè currentUserId tại đây
        return "account/detail";
    }
}
~~~

Khi hai request chạy gần nhau, request của người dùng B có thể ghi đè field trong lúc request A đang sử dụng nó. Kết quả có thể là hiển thị nhầm dữ liệu hoặc thực hiện thao tác trên tài khoản sai.

Hãy dùng biến cục bộ và lấy danh tính đã xác thực từ security context:

~~~java
@Controller
public class AccountController {
    private final AccountQuery accountQuery;

    public AccountController(AccountQuery accountQuery) {
        this.accountQuery = accountQuery;
    }

    @GetMapping("/account")
    public String account(
            @AuthenticationPrincipal AppPrincipal principal,
            Model model) {
        AccountViewModel page = accountQuery.getForUser(principal.userId());
        model.addAttribute("page", page);
        return "account/detail";
    }
}
~~~

Controller không giữ principal trong field. Mỗi lần gọi phương thức nhận danh tính tương ứng với request đã được xác thực.

## 3. Không tin danh tính hoặc quyền do client tự khai báo

Client có thể gửi ID qua path, query, form hoặc JSON. ID giúp xác định tài nguyên mà client muốn truy cập, nhưng bản thân ID không chứng minh client có quyền xem hoặc sửa tài nguyên đó.

Ví dụ endpoint sau có rủi ro:

~~~java
@GetMapping("/users/{userId}/orders")
public List<OrderResponse> orders(@PathVariable long userId) {
    return orderService.findByUserId(userId);
}
~~~

Nếu không kiểm tra quyền, người dùng có thể thay userId trong URL để yêu cầu đơn hàng của tài khoản khác. Đây là dạng lỗi truy cập đối tượng trực tiếp không an toàn (IDOR/BOLA).

Với trang “đơn hàng của tôi”, server nên lấy user ID từ danh tính đã xác thực:

~~~java
@GetMapping("/my/orders")
public List<OrderSummaryResponse> myOrders(
        @AuthenticationPrincipal AppPrincipal principal) {
    return orderQuery.findForOwner(principal.userId());
}
~~~

Nếu chức năng cho phép nhân viên xem đơn của khách hàng khác, đó là một use case khác và phải kiểm tra quyền rõ ràng. Không dùng một endpoint chung cho phép tùy ý truyền userId mà không có chính sách phân quyền.

## 4. Giới hạn truy vấn theo chủ sở hữu hoặc tenant

Kiểm tra quyền không nên chỉ nằm ở giao diện hoặc một câu if trong Controller. Tầng ứng dụng và truy vấn dữ liệu cần bảo đảm tài nguyên được lấy trong đúng phạm vi đã xác thực.

Ví dụ repository có thể cung cấp truy vấn theo cả ID đơn hàng và chủ sở hữu:

~~~java
public interface OrderRepository {
    Optional<Order> findByIdAndOwnerId(OrderId orderId, UserId ownerId);
}
~~~

Use case sử dụng danh tính do server cung cấp:

~~~java
public final class GetOrderForOwner {
    private final OrderRepository orders;

    public GetOrderForOwner(OrderRepository orders) {
        this.orders = orders;
    }

    public Order execute(OrderId orderId, UserId ownerId) {
        return orders.findByIdAndOwnerId(orderId, ownerId)
                .orElseThrow(OrderNotFoundException::new);
    }
}
~~~

Truy vấn SQL tương ứng có thể có dạng:

~~~sql
SELECT id, owner_id, status, total_amount
FROM orders
WHERE id = :orderId
  AND owner_id = :ownerId;
~~~

Điều kiện owner_id khiến bản ghi chỉ được trả về nếu thuộc đúng người dùng. Một cách triển khai có thể trả 404 cho cả trường hợp không tồn tại và trường hợp người gọi không được phép xem, nhằm tránh tiết lộ sự tồn tại của tài nguyên. Nếu hợp đồng sản phẩm cần phân biệt 403 và 404, hãy áp dụng nhất quán theo chính sách bảo mật.

### Ứng dụng nhiều tổ chức (multi-tenant)

Với hệ thống nhiều tổ chức, phạm vi dữ liệu thường là tenant thay vì chỉ user. Một người dùng có thể thuộc nhiều tenant; khi đó server phải xác định tenant đang hoạt động và xác minh người dùng là thành viên có quyền trong tenant đó.

~~~java
public interface InvoiceRepository {
    Optional<Invoice> findByIdAndTenantId(
            InvoiceId invoiceId,
            TenantId tenantId
    );
}
~~~

Mọi thao tác đọc, sửa và xóa cần áp dụng cùng phạm vi tenant. Chỉ lọc danh sách ở Controller mà bỏ điều kiện tenant trong truy vấn chi tiết hoặc cập nhật vẫn để lại lỗ hổng.

## 5. Bảo vệ thao tác cập nhật và xóa

Kiểm tra quyền khi đọc là chưa đủ. Người dùng cũng không được cập nhật hoặc xóa tài nguyên của người khác bằng cách thay ID.

Không nên tải bản ghi chỉ theo ID rồi cập nhật mà bỏ qua quyền sở hữu:

~~~java
Order order = orders.findById(orderId).orElseThrow();
order.changeDeliveryAddress(address);
orders.save(order);
~~~

Hãy tải trong phạm vi đã xác minh:

~~~java
Order order = orders.findByIdAndOwnerId(orderId, currentUserId)
        .orElseThrow(OrderNotFoundException::new);
order.changeDeliveryAddress(address);
orders.save(order);
~~~

Với các thao tác nhạy cảm, kiểm tra quyền nên được đặt tại use case hoặc policy được gọi từ use case. Điều này giúp cùng quy tắc áp dụng cho MVC, REST API, tác vụ nền và các đường gọi khác. Không dựa vào việc View ẩn nút “Sửa” hoặc “Xóa” như một biện pháp phân quyền.

## 6. Dùng session đúng phạm vi

HTTP về bản chất không lưu trạng thái giữa các request. Session cho phép server gắn một nhóm dữ liệu với phiên được nhận diện qua cookie hoặc cơ chế tương đương. Session phù hợp cho một số thông tin cần tồn tại qua nhiều bước, nhưng cần quản lý cẩn thận.

Thông tin có thể phù hợp với session:

- ID phiên và trạng thái đăng nhập do framework bảo mật quản lý.
- Ngôn ngữ hoặc tùy chọn giao diện của người dùng.
- Một quy trình nhiều bước có thời hạn, nếu dữ liệu được kiểm soát và xác minh khi hoàn tất.

Không nên đưa vào session:

- Danh sách lớn các entity hoặc dữ liệu nghiệp vụ có thể thay đổi.
- Dữ liệu nhạy cảm không cần thiết cho nhiều request.
- Thông tin quyền được xem như cố định trong thời gian dài nếu quyền có thể bị thu hồi.
- Một đối tượng mutable dùng chung cho nhiều tài khoản hoặc nhiều phiên.

Khi người dùng đăng xuất, ứng dụng cần kết thúc session và xóa dữ liệu gắn với phiên theo cơ chế framework. Khi đổi tài khoản trên cùng trình duyệt, không được tái sử dụng dữ liệu tạm của tài khoản trước. Với Spring Security, hãy dùng luồng logout và quản lý session được framework hỗ trợ thay vì tự lưu một cờ đăng nhập rời rạc.

Session cũng không thay thế kiểm tra quyền trên từng tài nguyên. Một session hợp lệ chỉ cho biết request thuộc phiên đã xác thực; use case vẫn cần xác minh quyền truy cập bản ghi được yêu cầu.

## 7. Cẩn trọng với cache và dữ liệu dùng chung

Cache có thể lưu dữ liệu để giảm truy vấn, nhưng khóa cache phải đại diện đầy đủ cho phạm vi dữ liệu. Nếu kết quả khác nhau theo user hoặc tenant mà cache key chỉ chứa orderId, một kết quả đã lưu có thể bị trả cho người dùng khác.

Ví dụ khóa cache không đủ phạm vi:

~~~java
@Cacheable("orderDetails")
public OrderDetailViewModel getOrder(long orderId, long userId) {
    // Kết quả phụ thuộc cả orderId và quyền của userId
}
~~~

Nếu cấu hình cache chỉ dùng orderId làm key, dữ liệu có thể bị dùng chung sai. Một khóa phù hợp hơn phải bao gồm các yếu tố quyết định kết quả, chẳng hạn tenant và người dùng:

~~~java
@Cacheable(
    cacheNames = "orderDetails",
    key = "#tenantId + ':' + #userId + ':' + #orderId"
)
public OrderDetailViewModel getOrder(
        long tenantId,
        long userId,
        long orderId) {
    // Xác minh quyền trước khi trả kết quả
}
~~~

Nếu dữ liệu giống nhau cho mọi người dùng trong một tenant, key có thể chỉ cần tenant và ID tài nguyên, nhưng quyền truy cập vẫn phải được kiểm tra. Không dùng cache key theo user để thay thế authorization. Cũng cần xác định thời hạn, invalidation khi dữ liệu hoặc quyền thay đổi, và tránh cache response chứa dữ liệu cá nhân trong cache công khai của proxy/CDN.

## 8. Tác vụ bất đồng bộ và ngữ cảnh người dùng

Một request có thể khởi tạo tác vụ nền như xuất báo cáo, gửi email hoặc xử lý tệp. Khi công việc chạy ở thread khác, không nên giả định security context hoặc request context tự động có sẵn.

Thay vì truyền toàn bộ đối tượng request hoặc lưu currentUser vào singleton, hãy truyền một thông điệp công việc tối thiểu với danh tính và phạm vi đã được xác định:

~~~java
public record ExportOrdersJob(
        UserId requestedBy,
        TenantId tenantId,
        Instant requestedAt
) {}
~~~

Worker xử lý cần xác minh job đến từ nguồn đáng tin cậy, kiểm tra quyền theo chính sách của hệ thống và giới hạn truy vấn theo tenant/user tương ứng. Nếu quyền có thể bị thu hồi trong lúc chờ, cần quyết định kiểm tra tại thời điểm tạo job, thời điểm thực thi hoặc cả hai tùy nghiệp vụ.

Không nên tin một userId tùy ý được gửi trong message từ client. Job nên được tạo ở server sau khi xác thực request, lưu danh tính yêu cầu và có cơ chế bảo vệ message. Với tác vụ dài hạn, cần ghi nhận ai yêu cầu, phạm vi dữ liệu nào được phép xử lý và kết quả được cung cấp cho đúng người nhận.

## 9. An toàn khi xử lý đồng thời

Nhiều request có thể đọc và cập nhật cùng một tài nguyên. Cô lập người dùng ngăn truy cập chéo, còn kiểm soát đồng thời giúp tránh ghi đè hoặc cập nhật mất dữ liệu trong cùng phạm vi.

Một số biện pháp:

- Dùng transaction với phạm vi rõ ràng cho use case cần cập nhật nhất quán.
- Dùng optimistic locking (ví dụ @Version trong JPA) khi cần phát hiện bản ghi đã bị thay đổi kể từ lúc đọc.
- Dùng khóa hoặc mức cô lập transaction phù hợp cho nghiệp vụ cần tuần tự hóa thao tác.
- Không giữ mutable state của request trong singleton bean.
- Tránh dùng static Map làm kho lưu trạng thái người dùng nếu không có thiết kế đồng bộ, giới hạn dung lượng, phân tán và bảo mật phù hợp.

Ví dụ entity dùng optimistic locking:

~~~java
@Entity
public class OrderEntity {
    @Id
    private Long id;

    @Version
    private long version;

    private String status;
}
~~~

Khi hai request cùng cập nhật một đơn, phiên bản giúp phát hiện một thao tác đã dựa trên dữ liệu cũ. Ứng dụng có thể trả lỗi xung đột phù hợp hoặc yêu cầu người dùng tải lại trạng thái mới.

## 10. Phân tách dữ liệu trong từng lớp MVC

Mỗi lớp có trách nhiệm bảo vệ một phần của ranh giới:

| Thành phần | Trách nhiệm cô lập |
| --- | --- |
| Controller | Lấy danh tính đã xác thực, binding dữ liệu request, không giữ trạng thái request trong field |
| View | Chỉ hiển thị dữ liệu được cung cấp; không coi việc ẩn phần tử là kiểm soát quyền |
| Application/use case | Kiểm tra quyền và phạm vi thao tác, điều phối hành động theo danh tính/tenant |
| Model | Bảo vệ bất biến nghiệp vụ và trạng thái hợp lệ |
| Repository | Truy vấn theo ID cùng điều kiện owner/tenant khi phù hợp |
| Cache | Dùng key và chính sách lưu trữ đúng phạm vi, xóa hoặc cập nhật khi dữ liệu thay đổi |
| Background worker | Nhận ngữ cảnh công việc có kiểm soát và xác minh phạm vi khi thực thi |

Sơ đồ sau minh họa đường đi của danh tính và điều kiện truy cập:

~~~mermaid
sequenceDiagram
    actor User as Người dùng
    participant S as Security filter
    participant C as Controller
    participant U as Use case
    participant R as Repository
    participant DB as Database
    User->>S: Request kèm session/token
    S->>S: Xác thực danh tính
    S->>C: Chuyển request đã xác thực
    C->>U: Gọi use case với userId/tenantId từ server
    U->>U: Kiểm tra quyền và phạm vi tài nguyên
    U->>R: Truy vấn theo resourceId + owner/tenant
    R->>DB: SELECT có điều kiện phạm vi
    DB-->>R: Chỉ bản ghi phù hợp
    R-->>U: Dữ liệu trong phạm vi
    U-->>C: Kết quả đã được phép
    C-->>User: View/response DTO
~~~

Sơ đồ là luồng khái quát. Cách xác thực có thể dùng session cookie, token hoặc cơ chế khác; điều quan trọng là danh tính được xác minh ở server và phạm vi dữ liệu được kiểm tra trước khi trả hoặc thay đổi dữ liệu.

## 11. Kiểm thử cô lập giữa nhiều người dùng

Kiểm thử với một tài khoản không thể chứng minh dữ liệu đã được cô lập. Cần tạo ít nhất hai người dùng hoặc hai tenant với dữ liệu riêng và xác nhận họ không thể vượt qua ranh giới.

Các tình huống nên kiểm tra:

- Người dùng A chỉ thấy danh sách tài nguyên của A.
- A không thể xem, sửa hoặc xóa tài nguyên của B bằng cách thay ID trong URL hoặc body.
- Người dùng thuộc tenant A không thể truy cập dữ liệu tenant B.
- Hai request đồng thời không làm lẫn trạng thái hoặc dữ liệu trả về.
- Cache không trả response của A cho B; thay đổi dữ liệu hoặc quyền được phản ánh theo chính sách invalidation.
- Đăng xuất và đăng nhập tài khoản khác không để lại dữ liệu tạm của phiên cũ.
- Tác vụ nền chỉ xuất dữ liệu trong phạm vi đã được cấp.
- View và response DTO không chứa dữ liệu ngoài quyền của người nhận.

Ví dụ kiểm thử endpoint:

~~~java
@Test
void userCannotReadAnotherUsersOrder() throws Exception {
    // Tài khoản hiện tại là user 10; đơn hàng 900 thuộc user 20.
    mvc.perform(get("/api/orders/900")
                    .with(user("user-10").roles("USER")))
            .andExpect(status().isNotFound());

    verify(orderQuery).getForOwner(new OrderId(900), new UserId(10));
}
~~~

Ví dụ chỉ minh họa ý tưởng; cấu hình principal, mock query và status cần khớp ứng dụng. Kiểm thử tích hợp nên xác nhận security filter thực sự đặt đúng danh tính vào context và repository áp dụng điều kiện owner/tenant. Có thể bổ sung test song song để phát hiện field mutable hoặc cache key dùng chung sai.

## 12. Quy trình thiết kế một chức năng an toàn cho nhiều người dùng

Khi xây dựng một chức năng mới, hãy đi theo các bước:

1. Xác định ai là người dùng hoặc tenant sở hữu dữ liệu.
2. Lấy danh tính từ cơ chế xác thực phía server, không tin ID do client tự khai báo.
3. Xác định chính sách ai được đọc, tạo, sửa và xóa tài nguyên.
4. Đưa điều kiện owner/tenant vào use case và truy vấn repository.
5. Giữ dữ liệu riêng của request trong biến cục bộ hoặc scope phù hợp; tránh mutable field trong singleton.
6. Nếu dùng session, chỉ lưu thông tin phiên cần thiết và xóa đúng lúc đăng xuất/đổi tài khoản.
7. Nếu dùng cache hoặc tác vụ nền, đưa phạm vi user/tenant vào thiết kế key và ngữ cảnh công việc.
8. Kiểm soát cập nhật đồng thời và transaction theo nghiệp vụ.
9. Kiểm thử bằng ít nhất hai danh tính, nhiều tenant và request đồng thời.
10. Kiểm tra response để bảo đảm chỉ gửi dữ liệu mà người nhận được phép xem.

Ví dụ chức năng “đơn hàng của tôi” nên lấy user ID từ principal, gọi query service với danh tính đó, truy vấn repository theo owner ID và tạo response DTO chỉ chứa trường cần thiết. Khi mở rộng thành chức năng hỗ trợ khách hàng, hãy thêm use case với chính sách quyền riêng thay vì bỏ điều kiện sở hữu khỏi endpoint hiện tại.

## Kết luận

Cô lập dữ liệu giữa người dùng đòi hỏi kiểm soát cả trạng thái trong bộ nhớ lẫn quyền truy cập dữ liệu lâu dài. Trong MVC, Controller lấy danh tính đã xác thực cho từng request; use case kiểm tra quyền và phạm vi; repository giới hạn truy vấn theo owner hoặc tenant; cache, session và worker giữ đúng ngữ cảnh. Khi không lưu trạng thái riêng trong thành phần dùng chung và kiểm thử với nhiều danh tính, ứng dụng giảm nguy cơ lộ dữ liệu, sửa nhầm tài nguyên và ảnh hưởng chéo giữa các người dùng.
