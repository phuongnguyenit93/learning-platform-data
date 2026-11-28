# Tránh lưu kết nối, request, tài nguyên mở và thực thể phụ thuộc ngữ cảnh

Spring Session cho phép ứng dụng giữ dữ liệu qua nhiều HTTP request bằng các thuộc tính của `HttpSession` hoặc `WebSession`. Khi dùng Redis, JDBC hay một repository dùng chung khác, dữ liệu phiên phải được chuyển thành dạng mà repository có thể lưu và khôi phục. Vì vậy, một thuộc tính session không chỉ cần dùng được trong request hiện tại; nó còn phải có thể serialize, tồn tại độc lập với vòng đời request và được đọc an toàn từ instance khác.

Không lưu trực tiếp các đối tượng gắn với tài nguyên đang mở hoặc ngữ cảnh thực thi như `HttpServletRequest`, `HttpServletResponse`, JDBC `Connection`, `EntityManager`, Hibernate `Session`, stream, socket, file handle, thread hay thực thể ORM còn phụ thuộc persistence context. Các đối tượng này thường không serialize được; ngay cả khi một thư viện có thể serialize một phần, chúng vẫn có thể chứa tham chiếu tới container, transaction, connection pool hoặc tài nguyên chỉ tồn tại trong một tiến trình. Hãy lưu định danh và dữ liệu nhỏ, ổn định; khi request mới đến, dùng định danh đó để nạp tài nguyên hoặc thực thể trong đúng request và transaction.

## 1. Vì sao session cần dữ liệu có thể tồn tại độc lập?

Trong ứng dụng chạy một máy chủ, đôi khi lập trình viên có thể vô tình dựa vào object còn nằm trong heap của một process. Với Spring Session, phiên có thể được lưu trong Redis hoặc JDBC và được khôi phục bởi một instance khác. Điều này làm rõ yêu cầu: session attributes phải là dữ liệu có thể chuyển qua ranh giới request, process và thời gian.

Ví dụ, request A lấy một `OrderEntity` từ JPA repository. Entity có thể chứa lazy proxy, tham chiếu tới persistence context hoặc quan hệ hai chiều tới nhiều entity khác. Nếu lưu nguyên entity vào session, request B có thể được xử lý bởi instance khác, nơi không còn `EntityManager` của request A. Khi mã truy cập thuộc tính lazy, ứng dụng có thể gặp `LazyInitializationException`; nếu serializer cố duyệt object graph, nó có thể tải quá nhiều dữ liệu hoặc gặp vòng tham chiếu.

Tương tự, một `Connection` được lấy từ connection pool chỉ có ý nghĩa trong khoảng thời gian được cấp phát và thường phải được đóng/trả về pool sau khi transaction hoặc thao tác hoàn tất. Lưu connection vào session có thể giữ tài nguyên quá lâu, không thể serialize và không thể sử dụng an toàn ở instance khác.

Nguyên tắc thiết kế là:

- Session giữ trạng thái nghiệp vụ nhỏ cần thiết qua request, ví dụ ID của giỏ hàng, lựa chọn giao diện hoặc mã luồng xử lý.
- Database và dịch vụ chuyên trách giữ dữ liệu bền vững, giao dịch và tài nguyên có vòng đời riêng.
- Mỗi request mở, sử dụng và giải phóng tài nguyên trong đúng phạm vi quản lý của framework.
- Request tiếp theo nạp lại dữ liệu cần thiết bằng ID, rồi chuyển thành DTO phù hợp với màn hình hoặc thao tác.

## 2. Những loại đối tượng không nên đặt trong session

| Loại đối tượng | Ví dụ | Vì sao không phù hợp |
| --- | --- | --- |
| Servlet request/response | `HttpServletRequest`, `HttpServletResponse`, `ServletInputStream` | Gắn với một request/response cụ thể và vòng đời do container quản lý |
| JDBC resource | `Connection`, `Statement`, `ResultSet` | Gắn với pool, transaction và trạng thái kết nối của một process |
| JPA/Hibernate context | `EntityManager`, Hibernate `Session`, `PersistenceContext` | Quản lý identity map, dirty checking và lazy loading trong một transaction/context |
| ORM entity phụ thuộc context | Entity có lazy proxy hoặc quan hệ lớn | Có thể chứa proxy, object graph lớn, trạng thái stale hoặc tham chiếu không serialize được |
| I/O đang mở | `InputStream`, `OutputStream`, `Reader`, `Writer`, `Socket`, channel | Đại diện cho tài nguyên đang hoạt động, không phải dữ liệu có thể khôi phục từ session |
| Tài nguyên hệ điều hành | `File`, file descriptor, lock, process handle | Phụ thuộc máy, đường dẫn, quyền và vòng đời của process hiện tại |
| Đối tượng thực thi đồng thời | `Thread`, `ExecutorService`, `Future`, lock, semaphore | Không thể khôi phục ngữ nghĩa thực thi an toàn ở request hoặc instance khác |
| Đối tượng framework theo request | Request context, transaction synchronization, security helper tạm thời | Có thể giữ tham chiếu tới thread, container hoặc tài nguyên có vòng đời ngắn |

Không nên dùng khả năng `Serializable` của một lớp làm tiêu chí duy nhất. Một object có thể triển khai `Serializable` nhưng vẫn chứa trạng thái không có ý nghĩa khi khôi phục, dữ liệu quá lớn, tham chiếu tới tài nguyên bên ngoài hoặc cấu trúc không tương thích giữa các phiên bản ứng dụng.

Spring Security có thể lưu `SecurityContext` vào session như một phần của cơ chế đăng nhập dựa trên session. Đây là tích hợp được framework thiết kế để quản lý. Không nên tự sao chép các object authentication tùy biến hoặc token thô vào session ngoài cơ chế bảo mật đã cấu hình; hãy dùng `SecurityContextRepository` và các thành phần Spring Security phù hợp.

## 3. Request và response chỉ tồn tại trong một lượt xử lý

`HttpServletRequest` và `HttpServletResponse` do Servlet container tạo cho từng request. Chúng cung cấp header, parameter, body, cookie, địa chỉ client và khả năng ghi response. Khi request kết thúc, container có thể tái sử dụng hoặc giải phóng các cấu trúc nội bộ. Không được coi request/response là object dữ liệu có thể giữ lại để sử dụng trong request sau.

Ví dụ sai:

```java
@PostMapping("/remember-request")
public void rememberRequest(HttpServletRequest request) {
    request.getSession().setAttribute("lastRequest", request);
}
```

Ví dụ này đưa một object gắn với container vào session. Repository có thể thất bại khi serialize; nếu một cơ chế tùy biến giữ được tham chiếu trong bộ nhớ, request tiếp theo vẫn không có quyền dùng request cũ như request hiện hành.

Hãy trích xuất giá trị cần giữ thành dữ liệu đơn giản:

```java
@PostMapping("/remember-search")
public String rememberSearch(@RequestParam String keyword,
                              HttpSession session) {
    session.setAttribute("lastSearchKeyword", keyword);
    return "redirect:/search";
}
```

Nếu cần giữ thông tin về request để xử lý sau, chỉ lưu các trường đã được chọn lọc và chuẩn hóa, chẳng hạn mã correlation, URI nội bộ đã kiểm tra hoặc tham số tìm kiếm. Không lưu toàn bộ header, cookie, request body hoặc thông tin xác thực vào session. Những dữ liệu này có thể chứa bí mật, dữ liệu cá nhân hoặc nội dung lớn.

Đối với xử lý bất đồng bộ, không đưa request/response vào tác vụ chạy nền rồi lưu chúng trong session. Hãy sao chép các giá trị cần thiết sang command/DTO bất biến, sau đó truyền DTO cho tác vụ. Nếu cần tiếp tục một quy trình sau khi request kết thúc, lưu trạng thái công việc và mã công việc trong database hoặc job store; request sau tra cứu trạng thái theo mã đó.

## 4. Không lưu connection, transaction hoặc EntityManager

Một JDBC `Connection` thường được cấp phát từ pool trong phạm vi transaction hoặc thao tác dữ liệu. Khi hoàn tất, ứng dụng trả connection về pool. Đối tượng connection không phải dữ liệu; nó là handle tới tài nguyên đang hoạt động trong một process. Lưu nó vào session có thể khiến connection bị giữ qua nhiều request, gây cạn pool, deadlock hoặc lỗi serialize.

Tương tự, `EntityManager` và Hibernate `Session` quản lý persistence context: entity được theo dõi, trạng thái dirty, cache cấp một và quan hệ lazy. Persistence context được thiết kế theo phạm vi giao dịch/unit of work, không phải vòng đời người dùng đăng nhập. Giữ nó trong session có thể làm entity stale, giữ tham chiếu lớn và vi phạm ranh giới transaction.

Ví dụ sai:

```java
@Transactional
public void saveContextInHttpSession(HttpSession httpSession) {
    EntityManager entityManager = ...;
    httpSession.setAttribute("entityManager", entityManager);
}
```

Ngay cả khi đoạn mã có thể lấy được `EntityManager`, việc lưu nó vào session là sai vòng đời. Hãy để Spring quản lý transaction và persistence context thông qua `@Transactional` và dependency injection.

Ví dụ đúng: lưu ID của đối tượng cần tiếp tục làm việc, rồi nạp entity trong transaction mới:

```java
@Service
class OrderQueryService {

    private final OrderRepository orderRepository;

    OrderQueryService(OrderRepository orderRepository) {
        this.orderRepository = orderRepository;
    }

    @Transactional(readOnly = true)
    OrderSummary loadSummary(Long orderId) {
        OrderEntity order = orderRepository.findById(orderId)
                .orElseThrow(() -> new OrderNotFoundException(orderId));

        return new OrderSummary(
                order.getId(),
                order.getStatus().name(),
                order.getTotal());
    }
}
```

Session chỉ cần lưu `orderId` nếu người dùng cần quay lại đơn hàng đó. Mỗi request gọi service, service mở transaction phù hợp, nạp entity và chuyển thành `OrderSummary`. Transaction kết thúc sau khi dữ liệu cần thiết đã được chuyển thành DTO.

## 5. Entity ORM và lazy proxy

JPA entity có thể triển khai `Serializable`, nhưng điều đó không biến entity thành session DTO tốt. Entity thường mô tả mô hình persistence, có thể chứa:

- Quan hệ `@OneToMany`, `@ManyToOne`, `@ManyToMany` tạo object graph lớn hoặc vòng tham chiếu.
- Lazy proxy phụ thuộc provider và persistence context.
- Trạng thái dirty hoặc snapshot do Hibernate theo dõi.
- Collection wrapper đặc thù của ORM.
- Thuộc tính nhạy cảm hoặc trường nội bộ không cần gửi qua session.

Nếu serialize entity, có thể phát sinh lỗi khi proxy không serialize được, dữ liệu bị tải ngoài ý muốn hoặc session phình to. Nếu deserialize thành công, entity vẫn là dữ liệu tách rời khỏi persistence context cũ. Thay đổi object đó không tự động được JPA ghi xuống database; ứng dụng phải nạp entity trong transaction hiện tại và cập nhật thông qua repository/service.

Ví dụ không nên làm:

```java
OrderEntity order = orderRepository.findById(orderId).orElseThrow();
session.setAttribute("currentOrder", order);
```

Thay bằng một trong hai cách:

```java
session.setAttribute("currentOrderId", orderId);
```

Hoặc nếu giao diện cần snapshot nhỏ và không nhạy cảm:

```java
OrderSummary summary = orderQueryService.loadSummary(orderId);
session.setAttribute("currentOrderSummary", summary);
```

DTO snapshot chỉ nên dùng cho thông tin cần hiển thị tạm thời. Khi cần cập nhật đơn hàng, nạp lại entity theo ID trong transaction để xác minh quyền sở hữu, trạng thái hiện tại và điều kiện nghiệp vụ. Không tin một snapshot cũ trong session làm nguồn chân lý cho giá, số lượng tồn kho, trạng thái thanh toán hoặc quyền truy cập.

## 6. Tài nguyên mở phải có chủ sở hữu và điểm kết thúc rõ ràng

Các tài nguyên như stream, socket, file handle và lock có vòng đời riêng. Chúng thường phải được mở, sử dụng và đóng trong cùng một luồng công việc hoặc một phạm vi quản lý xác định. Session có thể tồn tại hàng phút hoặc hàng giờ; tài nguyên mở không nên bị giữ lâu như vậy.

Ví dụ đọc file nên dùng try-with-resources:

```java
byte[] preview;
try (InputStream input = fileStorage.open(documentId)) {
    preview = input.readNBytes(4096);
}

session.setAttribute("documentPreview", preview);
```

Ở đây chỉ dữ liệu preview nhỏ được giữ lại; `InputStream` được đóng trước khi request kết thúc. Với file lớn, tốt hơn nên lưu `documentId` hoặc object key và đọc lại từ storage khi cần, thay vì lưu cả byte array vào session.

Không lưu `Socket` để tiếp tục giao tiếp ở request sau. Dùng dịch vụ messaging hoặc connection manager có vòng đời và cơ chế reconnect riêng. Không lưu `Lock` hoặc `Semaphore` trong session để đồng bộ giữa các instance; các primitive đồng bộ trong JVM không tạo ra khóa phân tán. Nếu nghiệp vụ cần lock phân tán, dùng cơ chế chuyên trách có lease, timeout và xử lý mất kết nối.

## 7. Chọn giữa ID, DTO và trạng thái nhỏ

Khi quyết định một thuộc tính có nên nằm trong session hay không, hãy xác định chính xác request tiếp theo cần biết điều gì.

| Dữ liệu cần giữ | Cách lưu phù hợp | Cách dùng ở request sau |
| --- | --- | --- |
| Đơn hàng đang xem | `orderId` | Nạp đơn hàng và kiểm tra quyền sở hữu |
| Giỏ hàng nhỏ cần tiếp tục chỉnh sửa | Danh sách product ID và quantity | Xác minh sản phẩm/giá/tồn kho từ database trước khi thanh toán |
| Bộ lọc tìm kiếm | DTO nhỏ gồm keyword, sort, page | Xây dựng truy vấn mới theo điều kiện đã lưu |
| Tệp đang xử lý | Storage key hoặc job ID | Mở lại tệp hoặc tra cứu trạng thái job |
| Kết quả hiển thị tạm thời | DTO snapshot nhỏ | Hiển thị như snapshot; nạp lại nguồn chính khi cần hành động |
| JDBC connection | Không lưu | Lấy từ datasource trong transaction mới |
| `HttpServletRequest` | Không lưu | Đọc request hiện tại; chỉ trích xuất trường cần thiết |
| JPA entity/proxy | Không lưu trực tiếp | Nạp lại entity theo ID trong transaction |

Một DTO session tốt thường có các đặc điểm:

- Chỉ chứa dữ liệu thực sự cần giữa các request.
- Có kích thước nhỏ, không giữ object graph lớn.
- Không chứa handle tới tài nguyên hoặc đối tượng framework có vòng đời ngắn.
- Có cấu trúc ổn định và tương thích với serializer đang dùng.
- Không chứa bí mật hoặc dữ liệu nhạy cảm không cần thiết.
- Có thể được đọc bởi các instance khác trong cùng phiên bản hoặc giai đoạn rolling deployment.

## 8. Ví dụ: lưu trạng thái giỏ hàng nhỏ thay vì entity và resource

Ví dụ sau dùng DTO đơn giản cho session. Các kiểu được đánh dấu `Serializable` để phù hợp với những cấu hình serializer dựa trên Java serialization; nếu ứng dụng dùng JSON hoặc serializer khác, cần bảo đảm các kiểu này tương thích với serializer đó.

```java
import java.io.Serializable;
import java.util.List;

public record CartLineState(Long productId, int quantity)
        implements Serializable {
}

public record CartState(List<CartLineState> lines)
        implements Serializable {
    public CartState {
        lines = List.copyOf(lines);
    }
}
```

Controller lưu trạng thái nhỏ:

```java
@PostMapping("/cart/items")
public String addItem(@RequestParam Long productId,
                      @RequestParam int quantity,
                      HttpSession session) {
    CartState current = (CartState) session.getAttribute("cartState");
    if (current == null) {
        current = new CartState(List.of());
    }

    List<CartLineState> updated = new ArrayList<>(current.lines());
    updated.add(new CartLineState(productId, quantity));
    session.setAttribute("cartState", new CartState(updated));

    return "redirect:/cart";
}
```

Khi hiển thị hoặc thanh toán, service phải nạp lại dữ liệu sản phẩm từ database để xác minh sản phẩm còn tồn tại, giá hiện tại và số lượng hợp lệ. Không lấy giá do trình duyệt gửi hoặc snapshot trong session làm nguồn quyết định thanh toán.

Trong ví dụ thực tế, cần gộp dòng sản phẩm trùng ID, giới hạn số dòng và quantity, kiểm tra input và tránh session quá lớn. Đối với giỏ hàng có ý nghĩa nghiệp vụ hoặc cần tồn tại qua nhiều thiết bị, nên lưu giỏ hàng trong database theo user/cart ID; session chỉ giữ cart ID hoặc thông tin tham chiếu.

## 9. Phạm vi request, session-scoped bean và các annotation MVC

Spring MVC có một số cơ chế tiện lợi có thể đưa dữ liệu vào session. Ví dụ `@SessionAttributes` giữ các model attribute được chỉ định giữa nhiều request trong một controller flow; `@SessionAttribute` đọc một thuộc tính đã có trong session. Các cơ chế này không làm object trở nên an toàn để serialize. Nếu model attribute là entity, request, stream hoặc connection, vấn đề vẫn tồn tại.

Ví dụ:

```java
@Controller
@SessionAttributes("checkoutState")
class CheckoutController {

    @ModelAttribute("checkoutState")
    CheckoutState checkoutState() {
        return new CheckoutState();
    }
}
```

`CheckoutState` cần là DTO nhỏ, chứa các giá trị như bước checkout, lựa chọn giao hàng hoặc ID tham chiếu. Không thêm `EntityManager`, `OrderEntity` với lazy relations hoặc request hiện tại vào object này.

Tương tự, bean có scope `session` có vòng đời dài hơn request và có thể được giữ trong session context. Các field của bean không nên giữ request, response, transaction hoặc tài nguyên mở. Nếu cần dùng request-scoped dependency, hãy để Spring giải quyết dependency theo đúng scope trong request hiện tại; không sao chép target object của request scope vào session-scoped bean.

Khi quy trình kết thúc, dùng cơ chế phù hợp như `SessionStatus#setComplete()` cho `@SessionAttributes`, hoặc xóa thuộc tính session không còn cần thiết. Dọn trạng thái giúp giảm kích thước session và hạn chế dữ liệu cũ tồn tại lâu hơn cần thiết.

## 10. Serialization, rolling deployment và nhiều instance

Với Redis/JDBC, một instance ghi session và instance khác có thể đọc lại. Vì vậy, session attributes cần tương thích qua ranh giới process. Một object chỉ hoạt động vì còn class hoặc resource trong heap của instance A sẽ không có ý nghĩa với instance B.

Các lỗi thường gặp gồm:

- `NotSerializableException` khi serializer Java gặp object hoặc field không serialize được.
- Lỗi serialize do object graph chứa proxy, connection, stream hoặc tham chiếu vòng phức tạp.
- Lỗi deserialize sau deploy vì class đổi package, cấu trúc hoặc serializer format.
- `LazyInitializationException` khi code truy cập lazy relation sau khi persistence context đã đóng.
- Dữ liệu session quá lớn làm tăng latency, Redis memory hoặc kích thước bản ghi JDBC.

Trong rolling deployment, instance phiên bản mới và cũ có thể cùng đọc session được ghi bởi nhau. Dùng DTO phiên bản hóa nếu cấu trúc cần thay đổi, giữ khả năng đọc dữ liệu cũ trong giai đoạn chuyển tiếp và không lưu class nội bộ dễ thay đổi. Khi buộc phải thay đổi format, có thể đặt version trong DTO, chuyển đổi khi đọc hoặc chủ động vô hiệu hóa session cũ theo kế hoạch đã thông báo.

Không giả định Redis serialization tự động làm object tương thích giữa mọi phiên bản. Serializer JSON cũng cần quản lý type metadata, field rename, enum value và schema evolution. Test round-trip với dữ liệu được tạo bởi phiên bản trước trước khi triển khai.

## 11. Xử lý lỗi và quan sát

Khi lỗi xuất hiện lúc lưu session, phân biệt lỗi kết nối kho dữ liệu với lỗi serialize thuộc tính. Redis có thể trả timeout trong khi object hoàn toàn hợp lệ; ngược lại, Redis vẫn hoạt động nhưng serializer có thể thất bại vì một thuộc tính không tương thích.

Quy trình điều tra:

1. Xác định request nào tạo hoặc cập nhật thuộc tính gây lỗi.
2. Xem stack trace để phân biệt lỗi serialize, deserialize, lazy loading và kết nối Redis/JDBC.
3. Liệt kê các session attribute được ghi trong request đó; tìm object framework, entity/proxy hoặc resource.
4. Kiểm tra kích thước object graph và serializer đang cấu hình.
5. Thay object không phù hợp bằng ID hoặc DTO nhỏ, rồi kiểm thử đọc lại ở request mới.
6. Nếu lỗi xuất hiện sau deploy, kiểm tra tương thích class/schema giữa các phiên bản đang chạy.

Không log toàn bộ session attributes để tìm object gây lỗi. Log tên thuộc tính, loại class ở mức cần thiết, mã correlation và loại lỗi; tránh in nội dung nhạy cảm, cookie hoặc session ID đầy đủ.

## 12. Kiểm thử session attributes an toàn

Kiểm thử nên xác minh rằng dữ liệu được lưu và khôi phục qua một request mới, thay vì chỉ kiểm tra object trong cùng một method.

| Kịch bản | Kết quả cần xác minh |
| --- | --- |
| Lưu DTO nhỏ vào session | Request tiếp theo đọc lại đúng dữ liệu |
| Lưu ID của entity | Request mới nạp entity trong transaction mới và kiểm tra quyền |
| Thử lưu request/response | Thiết kế hoặc kiểm thử phát hiện việc lưu object không phù hợp; không để vào production |
| Thử lưu JDBC connection hoặc stream | Không lưu tài nguyên đang mở; tài nguyên được đóng đúng phạm vi |
| Lưu entity có lazy relation | Ứng dụng không phụ thuộc proxy/persistence context cũ |
| Đọc session ở instance khác | DTO được deserialize đúng và không cần heap của instance ban đầu |
| Rolling deployment | Phiên bản mới đọc được dữ liệu cũ hoặc có migration/invalidation rõ ràng |
| Kết thúc quy trình | Thuộc tính tạm được xóa để giảm dữ liệu tồn đọng |

Với Redis/JDBC thật hoặc Testcontainers, tạo session qua HTTP, lưu cookie từ response, gửi request tiếp theo và xác minh trạng thái. Để kiểm tra nhiều instance, tạo session ở instance A rồi dùng cookie đó ở instance B. Thêm test cho serializer round-trip và dữ liệu được tạo bởi phiên bản ứng dụng trước nếu hệ thống hỗ trợ rolling deployment.

## 13. Checklist trước khi lưu một thuộc tính vào session

- Đây có thực sự là dữ liệu cần tồn tại qua nhiều request không?
- Nó có phải dữ liệu nhỏ, ổn định và có thể serialize bằng serializer đang dùng không?
- Nó có giữ tham chiếu tới request, response, thread, transaction, connection, stream, socket, file handle hoặc lock không?
- Nó có phải entity/proxy phụ thuộc persistence context hoặc chứa object graph lớn không?
- Có thể lưu ID hoặc DTO thay thế không?
- Request tiếp theo có thể nạp lại dữ liệu từ database/storage trong transaction riêng không?
- Các instance và phiên bản ứng dụng khác nhau có thể deserialize dữ liệu không?
- Dữ liệu có nhạy cảm hoặc cần được xóa khi quy trình kết thúc không?
- Kích thước và thời hạn của thuộc tính có phù hợp với giới hạn session không?

Đối với Spring Session, session là nơi lưu trạng thái nhỏ giữa các request. Connection, request, tài nguyên mở và persistence context thuộc các vòng đời khác, nên cần được tạo và giải phóng trong đúng phạm vi. Lưu ID hoặc DTO ổn định rồi nạp lại dữ liệu ở request tiếp theo giúp session có thể serialize, chia sẻ giữa nhiều instance và vận hành an toàn với Redis hoặc JDBC.
