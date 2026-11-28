# Quan hệ giữa rollback nghiệp vụ với giao dịch lưu phiên độc lập

Trong ứng dụng Spring Session JDBC, dữ liệu phiên và dữ liệu nghiệp vụ có thể cùng nằm trong một database nhưng không nhất thiết thuộc cùng một giao dịch. Đây là khác biệt quan trọng khi một request vừa cập nhật đơn hàng, thanh toán hoặc hồ sơ, vừa thay đổi thuộc tính `HttpSession`.

Spring Session JDBC quản lý việc ghi session thông qua cơ chế giao dịch của repository. Ở cấu hình phổ biến, thao tác lưu session được thực hiện trong một transaction độc lập với transaction nghiệp vụ, thường theo propagation `REQUIRES_NEW`. Vì vậy, rollback của transaction nghiệp vụ không tự động rollback thay đổi session đã được repository commit. Ngoài ra, trong luồng Servlet thông thường, Spring Session thường lưu session khi response được hoàn tất, tức là sau khi một service method có `@Transactional` đã trả về và transaction nghiệp vụ của nó đã commit hoặc rollback.

Hiểu đúng ranh giới này giúp tránh trạng thái khó giải thích, chẳng hạn đơn hàng đã rollback nhưng session vẫn chứa thông báo hoặc cờ trạng thái cho biết thao tác đã hoàn tất.

## Mục tiêu

Sau bài học, bạn có thể:

- Phân biệt transaction nghiệp vụ với transaction lưu session.
- Giải thích vì sao thay đổi session có thể tồn tại sau khi transaction nghiệp vụ rollback.
- Hiểu tác động của `REQUIRES_NEW` và thời điểm Spring Session JDBC ghi dữ liệu.
- Thiết kế thuộc tính session sao cho không trở thành nguồn dữ liệu nghiệp vụ có thẩm quyền.
- Nhận biết rủi ro khi lưu session và cập nhật dữ liệu nghiệp vụ trong cùng request.
- Kiểm thử commit, rollback, lỗi lưu session và request đồng thời.

## 1. Hai loại dữ liệu, hai mục đích

Transaction nghiệp vụ bảo vệ tính nhất quán của dữ liệu như đơn hàng, số dư, thanh toán, tồn kho hoặc hồ sơ khách hàng. Transaction lưu session bảo vệ trạng thái truy cập tạm thời cần được dùng giữa các request, ví dụ thông tin điều hướng, ngôn ngữ, mã giỏ hàng hoặc thông báo flash.

| Nội dung | Transaction nghiệp vụ | Transaction lưu session |
|---|---|---|
| Dữ liệu | Đơn hàng, thanh toán, tồn kho, hồ sơ | Metadata và thuộc tính `HttpSession` |
| Mục đích | Bảo đảm quy tắc nghiệp vụ và tính nguyên tử | Lưu trạng thái phiên để request tiếp theo sử dụng |
| Thành phần quản lý | Service/repository nghiệp vụ và transaction manager | Spring Session JDBC và `JdbcIndexedSessionRepository` |
| Phạm vi rollback | Các thao tác thuộc transaction nghiệp vụ | Các thao tác lưu/xóa session trong transaction repository |
| Vòng đời | Theo quy tắc lưu trữ nghiệp vụ | Thường ngắn hạn, có timeout và cleanup |

Dù hai nhóm dữ liệu có thể nằm trong cùng database, điều đó không tự động khiến chúng dùng chung một transaction. Database chỉ là nơi lưu; ranh giới transaction do transaction manager và cách gọi repository quyết định.

Ví dụ một request xác nhận thanh toán:

1. Service tạo bản ghi thanh toán và cập nhật đơn hàng trong transaction nghiệp vụ.
2. Service phát hiện lỗi và transaction nghiệp vụ rollback.
3. Request vẫn cần hiển thị thông báo lỗi cho người dùng.
4. Spring Session lưu thuộc tính flash hoặc trạng thái giao diện ở giai đoạn hoàn tất response.

Trong trường hợp này, việc transaction session commit trong khi transaction nghiệp vụ rollback là hành vi có chủ đích: thông báo lỗi vẫn cần tồn tại để hiển thị ở request kế tiếp. Điều quan trọng là session chỉ lưu thông tin giao diện như “thanh toán thất bại”, không lưu sự thật thay thế cho trạng thái thanh toán trong database.

## 2. Spring Session JDBC lưu phiên ở ranh giới nào?

Trong ứng dụng Servlet, `SessionRepositoryFilter` bọc request và response để ánh xạ API `HttpSession` sang repository của Spring Session. Controller và service có thể gọi `getAttribute`, `setAttribute` hoặc `invalidate` như bình thường.

Ở chế độ lưu theo request, thay đổi session thường được gom lại và ghi khi request kết thúc hoặc response được commit. Do đó, lời gọi:

~~~java
session.setAttribute("checkoutMessage", "Thanh toán chưa thành công");
~~~

chủ yếu thay đổi đối tượng session đang được request sử dụng. Lệnh SQL có thể chỉ được thực hiện sau khi controller và các service đã hoàn tất. Thời điểm gọi `setAttribute` và thời điểm dữ liệu được commit vào database là hai mốc khác nhau.

Luồng tổng quát:

~~~mermaid
sequenceDiagram
    participant C as Client
    participant F as SessionRepositoryFilter
    participant S as Business Service
    participant DB as Database
    participant R as Spring Session JDBC
    C->>F: HTTP request
    F->>R: Tải session nếu có
    R->>DB: Đọc session
    DB-->>R: Session attributes
    R-->>F: HttpSession
    F->>S: Gọi service nghiệp vụ
    S->>DB: Bắt đầu transaction nghiệp vụ
    S->>DB: Cập nhật đơn hàng
    S-->>F: Thành công hoặc exception
    Note over S,DB: Transaction nghiệp vụ commit hoặc rollback
    F->>R: Lưu thay đổi session khi hoàn tất response
    R->>DB: Transaction lưu session
    DB-->>R: Commit hoặc lỗi
    R-->>F: Kết quả lưu phiên
    F-->>C: HTTP response
~~~

Sơ đồ mô tả luồng Servlet thông thường với session flush khi hoàn tất request. Nếu ứng dụng dùng `FlushMode.IMMEDIATE`, tự quản lý transaction bao quanh toàn request hoặc có cấu hình repository tùy chỉnh, thời điểm ghi có thể khác. Hãy kiểm tra cấu hình thực tế thay vì suy luận chỉ từ vị trí gọi `setAttribute`.

## 3. Transaction lưu session độc lập

Spring Session JDBC sử dụng cơ chế `TransactionOperations` để quản lý transaction của thao tác lưu repository. Cấu hình mặc định trong các dòng Spring Session JDBC phổ biến dùng propagation `REQUIRES_NEW` cho transaction lưu session. Propagation này yêu cầu tạo transaction mới, tạm treo transaction đang tồn tại nếu cùng transaction manager quản lý.

Ý nghĩa:

- Transaction nghiệp vụ có thể đang hoạt động.
- Khi repository bắt đầu transaction lưu session với `REQUIRES_NEW`, transaction nghiệp vụ hiện tại được suspend.
- Transaction lưu session chạy và commit/rollback độc lập.
- Sau đó transaction nghiệp vụ được resume nếu nó vẫn còn trong phạm vi thực thi.

Trong luồng Servlet phổ biến, việc lưu session có thể diễn ra sau khi transaction của service method đã kết thúc, nên không còn transaction nghiệp vụ để suspend. Dù vậy, ranh giới độc lập vẫn quan trọng khi session được lưu trong lúc có transaction khác đang hoạt động hoặc khi ứng dụng tùy chỉnh ranh giới request.

Ví dụ minh họa propagation:

~~~text
Transaction nghiệp vụ (REQUIRED)
  BEGIN
  UPDATE ORDERS ...
  |
  +-- Session repository (REQUIRES_NEW)
        BEGIN
        UPDATE SPRING_SESSION ...
        COMMIT
  |
  ROLLBACK transaction nghiệp vụ

Kết quả:
  - Thay đổi ORDERS bị rollback.
  - Thay đổi SPRING_SESSION đã commit vẫn tồn tại.
~~~

`REQUIRES_NEW` không có nghĩa session luôn được lưu thành công. Transaction session vẫn có thể rollback do lỗi SQL, constraint, timeout, mất kết nối hoặc lỗi serializer trước khi ghi. Nó chỉ tách kết quả transaction session khỏi transaction đang bị suspend.

### 3.1. Phạm vi của transaction manager

Propagation chỉ có thể phối hợp với transaction đang hoạt động nếu transaction manager quản lý cùng tài nguyên và có thể nhận biết transaction đó. Nếu ứng dụng có nhiều `DataSource` hoặc nhiều transaction manager, hãy xác định rõ repository session dùng manager nào.

Ví dụ, transaction nghiệp vụ dùng `JpaTransactionManager` cho một datasource còn session repository dùng một datasource/manager khác. Khi đó, không nên giả định transaction session sẽ suspend hoặc tham gia transaction nghiệp vụ theo cùng cách như khi cả hai cùng dùng một manager tương thích.

Kiểm tra cấu hình `DataSource`, transaction manager và transaction operations của repository. Không chỉ dựa vào việc hai bảng nằm trong cùng database server để kết luận chúng cùng transaction.

## 4. Ví dụ: nghiệp vụ rollback nhưng thông báo session vẫn được lưu

Giả sử checkout có thể thất bại vì tồn kho thay đổi. Service chạy trong transaction nghiệp vụ:

~~~java
@Service
public class CheckoutService {

    private final OrderRepository orderRepository;
    private final InventoryService inventoryService;

    public CheckoutService(
            OrderRepository orderRepository,
            InventoryService inventoryService) {
        this.orderRepository = orderRepository;
        this.inventoryService = inventoryService;
    }

    @Transactional
    public void confirm(long orderId) {
        Order order = orderRepository.findById(orderId)
                .orElseThrow();

        inventoryService.reserve(order);
        order.markConfirmed();
        orderRepository.save(order);
    }
}
~~~

Controller bắt lỗi nghiệp vụ và đặt thông báo giao diện vào session:

~~~java
@PostMapping("/checkout/confirm")
public String confirm(
        @RequestParam long orderId,
        HttpServletRequest request,
        RedirectAttributes redirectAttributes) {

    try {
        checkoutService.confirm(orderId);
        redirectAttributes.addFlashAttribute(
                "message", "Đơn hàng đã được xác nhận");
    } catch (InsufficientStockException ex) {
        request.getSession().setAttribute(
                "checkoutMessage",
                "Không đủ hàng để xác nhận đơn hàng");
    }

    return "redirect:/checkout";
}
~~~

Nếu `checkoutService.confirm` ném `InsufficientStockException` làm transaction trong service rollback, dữ liệu đơn hàng và tồn kho được hoàn tác. Thông báo được đặt sau khi exception đã thoát khỏi service proxy và controller bắt được lỗi; Spring Session có thể lưu thông báo đó khi response hoàn tất.

Ở request tiếp theo, trang checkout đọc `checkoutMessage` rồi xóa nó sau khi hiển thị:

~~~java
@GetMapping("/checkout")
public String checkout(
        HttpServletRequest request,
        Model model) {

    HttpSession session = request.getSession(false);
    if (session != null) {
        Object message = session.getAttribute("checkoutMessage");
        if (message != null) {
            model.addAttribute("message", message);
            session.removeAttribute("checkoutMessage");
        }
    }

    return "checkout";
}
~~~

Thông báo giao diện có thể tồn tại dù transaction nghiệp vụ rollback. Đây là một use case hợp lý vì session lưu thông tin hiển thị, không lưu kết quả xác nhận đơn hàng làm nguồn dữ liệu chính.

Lưu ý: nếu controller hoặc service đặt thuộc tính session trước khi transaction nghiệp vụ rollback, thuộc tính đó cũng có thể được lưu. Không dựa vào thứ tự code trong cùng method để giả định rollback sẽ tự hoàn tác session.

## 5. Ví dụ nguy hiểm: session tuyên bố nghiệp vụ đã thành công

Xem đoạn code:

~~~java
@PostMapping("/checkout/confirm")
public String confirm(
        @RequestParam long orderId,
        HttpServletRequest request) {

    HttpSession session = request.getSession();
    session.setAttribute("checkoutStatus", "COMPLETED");

    checkoutService.confirm(orderId);
    return "redirect:/checkout";
}
~~~

Nếu `checkoutService.confirm` ném exception và transaction nghiệp vụ rollback, thuộc tính `checkoutStatus=COMPLETED` vẫn có thể được Spring Session ghi khi request kết thúc. Giao diện có thể hiển thị trạng thái sai dù database không có đơn hàng đã xác nhận.

Cách thiết kế tốt hơn:

- Không đặt trạng thái thành công trước khi service xác nhận thành công.
- Lấy trạng thái đơn hàng từ database khi render trang.
- Dùng session chỉ cho thông báo hoặc trạng thái giao diện tạm thời.
- Nếu cần ghi nhận kết quả xử lý bền vững, lưu trong bảng nghiệp vụ và cập nhật cùng transaction phù hợp.

Ví dụ:

~~~java
@PostMapping("/checkout/confirm")
public String confirm(
        @RequestParam long orderId,
        HttpServletRequest request) {

    checkoutService.confirm(orderId);

    HttpSession session = request.getSession();
    session.setAttribute("lastConfirmedOrderId", orderId);
    return "redirect:/checkout";
}
~~~

Ngay cả ở ví dụ này, `lastConfirmedOrderId` chỉ là gợi ý giao diện. Khi trang hiển thị đơn hàng, service vẫn phải tải đơn hàng từ database và kiểm tra quyền truy cập. Không dùng thuộc tính session làm bằng chứng duy nhất rằng thanh toán đã thành công.

## 6. Khi nào cần transaction nghiệp vụ và session cùng commit?

Một số thiết kế có thể muốn trạng thái session chỉ thay đổi nếu transaction nghiệp vụ commit, hoặc muốn session và dữ liệu nghiệp vụ cùng rollback. Cần xác định yêu cầu trước khi thay đổi transaction policy.

### 6.1. Không lưu dữ liệu nghiệp vụ có thẩm quyền trong session

Đây thường là giải pháp đơn giản và bền vững nhất. Nếu trạng thái phải tuân theo transaction nghiệp vụ, hãy lưu nó trong database nghiệp vụ cùng transaction. Session chỉ giữ ID tham chiếu hoặc thông tin giao diện có thể tái tạo.

Ví dụ:

- Trạng thái đơn hàng: lưu trong bảng `ORDERS`.
- Trạng thái thanh toán: lưu trong bảng payment/ledger.
- Tồn kho: cập nhật trong transaction nghiệp vụ với cơ chế khóa/version.
- Thông báo lỗi tạm thời: có thể lưu flash attribute hoặc session.

### 6.2. Chỉ đặt session attribute sau khi nghiệp vụ thành công

Đặt thuộc tính sau khi lời gọi service đã trả về thành công giúp tránh một số trạng thái sai:

~~~java
checkoutService.confirm(orderId);
request.getSession().setAttribute("lastAction", "checkout-confirmed");
~~~

Tuy nhiên, đây vẫn không phải một transaction nguyên tử giữa dữ liệu nghiệp vụ và session. Service transaction có thể commit xong, sau đó việc lưu session thất bại. Khi đó nghiệp vụ đã thành công nhưng session không có cờ giao diện. Vì vậy, cờ session phải có thể tái tạo và không được quyết định tính đúng đắn của nghiệp vụ.

### 6.3. Thay đổi transaction policy của repository

Nếu có yêu cầu đặc biệt, cần kiểm tra API cấu hình của đúng phiên bản Spring Session JDBC để tùy chỉnh `TransactionOperations` hoặc transaction manager mà repository sử dụng. Không giả định một property Boot tiêu chuẩn có thể đổi propagation của transaction lưu session.

Muốn transaction session tham gia transaction nghiệp vụ thường cần propagation `REQUIRED` và cùng transaction manager/tài nguyên. Tuy nhiên, nếu Spring Session flush ở cuối request sau khi service transaction đã kết thúc, việc đổi propagation không tự làm cho session và service trở thành một transaction chung. Phải thay đổi và kiểm soát ranh giới transaction/request một cách rõ ràng, đồng thời đánh giá filter lifecycle.

Không nên tùy chỉnh repository transaction chỉ để đạt atomicity nếu không có integration test chứng minh. Kết hợp transaction nghiệp vụ và session có thể làm tăng thời gian giữ connection/lock, ảnh hưởng response và làm logout hoặc cập nhật session phụ thuộc vào kết quả giao dịch nghiệp vụ.

## 7. Sự khác biệt giữa REQUIRED và REQUIRES_NEW

Hai propagation thường được nhắc tới:

| Propagation | Khi đã có transaction hiện tại | Kết quả nếu transaction bên ngoài rollback |
|---|---|---|
| `REQUIRED` | Tham gia transaction hiện tại | Công việc tham gia cũng rollback |
| `REQUIRES_NEW` | Suspend transaction hiện tại và tạo transaction mới | Transaction mới đã commit vẫn giữ kết quả |

Ví dụ khái niệm với `TransactionTemplate`:

~~~java
TransactionTemplate required = new TransactionTemplate(transactionManager);
required.setPropagationBehavior(
        TransactionDefinition.PROPAGATION_REQUIRED);

TransactionTemplate requiresNew = new TransactionTemplate(transactionManager);
requiresNew.setPropagationBehavior(
        TransactionDefinition.PROPAGATION_REQUIRES_NEW);
~~~

Đây là minh họa semantics của Spring transaction, không phải đoạn cấu hình để thay thế transaction operations của `JdbcIndexedSessionRepository`. Repository có thể nhận `TransactionOperations` theo constructor hoặc cơ chế cấu hình riêng của phiên bản; hãy dùng API đúng phiên bản và không tự tạo repository thứ hai nếu Boot đã quản lý repository.

`REQUIRES_NEW` cần một transaction mới thực sự. Khi transaction ngoài đang giữ connection, transaction mới có thể cần connection khác. Nếu connection pool quá nhỏ, nhiều request đồng thời có transaction ngoài rồi gọi `REQUIRES_NEW` có thể chờ connection, dẫn tới nghẽn hoặc timeout. Hãy đo pool và tải thực tế.

## 8. Lỗi lưu session sau khi nghiệp vụ đã commit

Vì session có thể được lưu sau khi service transaction hoàn tất, có thể xảy ra tình huống:

1. Transaction nghiệp vụ commit đơn hàng thành công.
2. Controller trả về và response bắt đầu hoàn tất.
3. Spring Session ghi session vào JDBC.
4. Database session gặp lỗi kết nối hoặc constraint.
5. Response có thể gặp lỗi trong giai đoạn commit hoặc hoàn tất.

Khi đó, đơn hàng có thể đã được lưu thành công nhưng session không được cập nhật. Ứng dụng không nên cố rollback đơn hàng đã commit chỉ vì session write thất bại; transaction đã hoàn tất và không còn nằm trong phạm vi rollback.

Thiết kế cần bảo đảm:

- Dữ liệu nghiệp vụ có thể được đọc lại từ nguồn có thẩm quyền.
- Thuộc tính session chỉ là dữ liệu phụ trợ và có thể tái tạo.
- Lỗi session được ghi log/metric mà không lộ session ID hoặc nội dung nhạy cảm.
- Client có thể tải lại trạng thái nghiệp vụ sau khi nhận lỗi hoặc thử lại request theo idempotency key.
- API không báo giao dịch thất bại nếu thực tế transaction nghiệp vụ đã commit; cần xác định rõ lỗi thuộc giai đoạn nghiệp vụ hay giai đoạn lưu session.

## 9. Rollback không tự hoàn tác side effect bên ngoài transaction

Rollback chỉ hoàn tác các thao tác tham gia transaction đang rollback. Nó không tự động:

- Xóa thuộc tính session đã được repository commit bằng transaction độc lập.
- Hoàn tác email đã gửi hoặc message đã publish ra broker.
- Hủy HTTP request khác đã được gửi.
- Dừng background job đang chạy.
- Hoàn tác thay đổi đã commit trong transaction `REQUIRES_NEW`.

Nguyên tắc này rộng hơn Spring Session. Khi thiết kế service, hãy phân loại side effect theo ranh giới transaction và dùng outbox, after-commit event hoặc cơ chế bù trừ cho các hệ thống bên ngoài khi cần.

Đối với session, hãy xem việc lưu thuộc tính là một side effect độc lập. Không đưa các thuộc tính quyết định tính đúng đắn của giao dịch vào session.

## 10. Kiểm thử quan hệ giữa hai transaction

Nên kiểm thử trên database cùng loại với production hoặc môi trường tích hợp tương đương. Mock `HttpSession` không thể chứng minh transaction lưu session được commit độc lập.

### 10.1. Kiểm thử rollback nghiệp vụ nhưng session vẫn tồn tại

Thiết kế test:

1. Gửi request tạo session và ghi thuộc tính ban đầu.
2. Gọi service `@Transactional` cập nhật bảng nghiệp vụ rồi chủ động ném exception runtime.
3. Controller bắt exception và đặt thông báo session sau khi service transaction rollback.
4. Để request hoàn tất để Spring Session flush dữ liệu.
5. Gửi request tiếp theo kèm session cookie.
6. Xác minh bản ghi nghiệp vụ đã rollback nhưng thông báo session vẫn đọc được.

Test cần kiểm tra cả hai nguồn dữ liệu: bảng nghiệp vụ và repository session. Không chỉ assert response body của request đầu tiên.

### 10.2. Kiểm thử nghiệp vụ commit nhưng session write thất bại

Trong môi trường kiểm thử có kiểm soát:

1. Cho service commit thay đổi nghiệp vụ.
2. Làm cho thao tác ghi session thất bại, ví dụ dùng test double cho repository hoặc database fault injection.
3. Xác minh dữ liệu nghiệp vụ vẫn được commit.
4. Xác minh lỗi session được quan sát và xử lý theo chính sách.
5. Kiểm tra request tiếp theo có thể tải lại trạng thái nghiệp vụ từ database.

Không tạo lỗi bằng cách phá schema production. Dùng database test riêng hoặc test double ở đúng ranh giới.

### 10.3. Kiểm thử transaction propagation

Nếu repository được cấu hình transaction operations tùy chỉnh, hãy kiểm tra:

- Transaction session dùng đúng transaction manager.
- `REQUIRES_NEW` thực sự suspend transaction ngoài khi cùng manager.
- Rollback transaction ngoài không rollback session transaction đã commit.
- Nếu dùng `REQUIRED`, session write tham gia transaction ngoài khi transaction đó còn hoạt động.
- Trường hợp flush diễn ra sau service transaction được mô phỏng đúng trong test.
- Connection pool đủ cho số transaction lồng nhau trong tải dự kiến.

## 11. Quan sát trong production

Theo dõi riêng hai nhóm transaction:

| Nhóm chỉ số | Gợi ý quan sát |
|---|---|
| Nghiệp vụ | Số transaction commit/rollback, thời gian xử lý service, lỗi domain |
| Session JDBC | Số lần insert/update/delete session, độ trễ SQL, lỗi connection, lỗi serialization |
| Tài nguyên | Connection pool active/idle, thời gian chờ connection, lock wait |
| HTTP | Response lỗi sau khi nghiệp vụ đã commit, request hoàn tất chậm |

Log nên có correlation ID để liên kết request, transaction nghiệp vụ và thao tác lưu session. Không ghi session ID thô, cookie, token hoặc toàn bộ session attributes.

Khi điều tra một request lỗi, hãy xác định:

1. Transaction nghiệp vụ đã commit hay rollback?
2. Session repository đã bắt đầu ghi chưa?
3. Transaction lưu session commit hay rollback?
4. Response lỗi trước hay sau khi transaction nghiệp vụ hoàn tất?
5. Trạng thái cuối cùng trong database nghiệp vụ và session repository là gì?

Việc tách hai kết quả này giúp tránh kết luận sai rằng “request lỗi” đồng nghĩa “nghiệp vụ đã rollback”.

## 12. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Service rollback nhưng session vẫn có thuộc tính mới | Session được ghi trong transaction độc lập hoặc ở cuối request | Chỉ lưu thông tin giao diện; không đặt trạng thái nghiệp vụ có thẩm quyền trong session |
| Đơn hàng đã commit nhưng response báo lỗi | Session write thất bại sau khi transaction nghiệp vụ kết thúc | Phân biệt lỗi nghiệp vụ với lỗi session; hỗ trợ tải lại trạng thái và idempotency |
| Session không rollback cùng transaction service | Repository dùng `REQUIRES_NEW` hoặc flush sau service transaction | Hiểu ranh giới transaction; chỉ tùy chỉnh propagation khi có yêu cầu atomicity rõ ràng |
| `REQUIRES_NEW` gây cạn connection pool | Transaction ngoài giữ connection trong khi transaction mới cần connection khác | Đánh giá kích thước pool, thời gian giữ transaction và tải đồng thời |
| Trạng thái giao diện báo thành công nhưng database rollback | Session attribute được đặt trước khi nghiệp vụ commit | Đặt thông báo sau khi service thành công và đọc trạng thái chính từ database |
| Hai bảng cùng database nhưng rollback không đồng bộ | Hai repository dùng transaction manager hoặc transaction boundary khác nhau | Kiểm tra transaction manager, datasource và propagation thực tế |

## 13. Checklist thiết kế

- [ ] Phân biệt dữ liệu nghiệp vụ với dữ liệu giao diện trong session.
- [ ] Hiểu thời điểm Spring Session JDBC flush session trong vòng đời request.
- [ ] Xác định transaction manager và transaction operations của repository.
- [ ] Không giả định rollback nghiệp vụ tự động rollback session.
- [ ] Không dùng session làm nguồn sự thật cho đơn hàng, thanh toán, tồn kho hoặc quyền.
- [ ] Đặt thuộc tính thông báo sau khi biết kết quả nghiệp vụ.
- [ ] Xử lý trường hợp nghiệp vụ commit nhưng session write thất bại.
- [ ] Đánh giá connection pool khi dùng `REQUIRES_NEW`.
- [ ] Chỉ thay propagation khi có yêu cầu nhất quán và test chứng minh.
- [ ] Kiểm thử cả trạng thái database nghiệp vụ và session repository.

Transaction lưu session và transaction nghiệp vụ có mục đích, thời điểm và phạm vi rollback riêng. Với Spring Session JDBC, thao tác lưu session thường được quản lý độc lập, phổ biến là `REQUIRES_NEW`, và trong ứng dụng Servlet còn có thể diễn ra khi response hoàn tất sau transaction service. Vì vậy, session có thể giữ thông báo hoặc trạng thái giao diện dù nghiệp vụ rollback; ngược lại, nghiệp vụ có thể đã commit dù session write gặp lỗi. Hãy lưu sự thật nghiệp vụ trong database nghiệp vụ, giữ session cho trạng thái tạm thời và kiểm thử riêng kết quả của cả hai transaction.
