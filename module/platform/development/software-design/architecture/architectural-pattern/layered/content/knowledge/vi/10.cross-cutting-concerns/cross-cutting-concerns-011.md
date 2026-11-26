# Các mối quan tâm xuyên tầng

## Tránh che giấu quy tắc nghiệp vụ trong cơ chế tự động xuyên tầng

Trong module `SOFTWARE_DESIGN_ARCHITECTURE_ARCHITECTURAL_PATTERN_LAYERED` — **Học tổ chức phần mềm theo kiến trúc phân tầng** — một số hành vi kỹ thuật xuất hiện ở nhiều nơi: transaction, bảo mật, ghi log, đo thời gian, xử lý lỗi và kiểm tra đầu vào. Các cơ chế xuyên tầng như Spring AOP, interceptor, filter, annotation hoặc callback giúp áp dụng những hành vi đó nhất quán mà không phải lặp lại mã ở mọi phương thức.

Tuy nhiên, cơ chế tự động cũng có thể làm một quyết định nghiệp vụ biến mất khỏi luồng xử lý mà người đọc nhìn thấy. Ví dụ, một aspect tự chặn hủy đơn sau thời hạn, một entity listener tự đổi trạng thái đơn khi cập nhật database, hoặc một annotation khiến một thao tác bị từ chối theo điều kiện kinh doanh không được thể hiện trong application service hay domain model. Khi đó, hành vi quan trọng trở nên khó tìm, khó giải thích và khó kiểm thử đúng ngữ cảnh.

Bài học này giúp phân biệt **cơ chế thực thi xuyên tầng** với **quy tắc quyết định nghiệp vụ**, nhận diện dấu hiệu che giấu và đặt mỗi trách nhiệm vào nơi phù hợp. Ví dụ dùng Java/Spring với quy trình hủy đơn hàng.

## 1. Cơ chế xuyên tầng và quy tắc nghiệp vụ là hai việc khác nhau

**Mối quan tâm xuyên tầng (cross-cutting concern)** là trách nhiệm cần được áp dụng ở nhiều thành phần hoặc nhiều ca sử dụng, thường vì một yêu cầu kỹ thuật chung. Ví dụ:

- Mở, commit hoặc rollback transaction.
- Xác thực danh tính và kiểm tra quyền truy cập ở ranh giới.
- Ghi log, trace và đo thời gian thực thi.
- Chuyển đổi lỗi kỹ thuật thành phản hồi phù hợp.
- Áp dụng retry, giới hạn tốc độ hoặc kiểm tra chữ ký request.

**Quy tắc nghiệp vụ (business rule)** mô tả điều kiện, giới hạn hoặc quyết định chi phối kết quả của hoạt động nghiệp vụ. Ví dụ:

- Đơn chỉ được hủy trước khi giao cho đơn vị vận chuyển.
- Khách hàng chỉ được hủy đơn của chính mình.
- Yêu cầu hoàn tiền phải nằm trong thời hạn do chính sách bán hàng quy định.
- Tổng giá trị đơn không được vượt hạn mức tín dụng còn lại.
- Không được xác nhận đặt chỗ nếu số chỗ còn lại không đủ.

Một cách phân biệt hữu ích là hỏi: **cơ chế này đang giúp một hành động được thực thi như thế nào, hay đang quyết định hành động đó có được phép xảy ra và kết quả nghiệp vụ là gì?**

| Nội dung | Cơ chế xuyên tầng thường phù hợp | Quy tắc nghiệp vụ thường phù hợp |
| --- | --- | --- |
| Transaction | Bắt đầu, commit, rollback theo ranh giới use case | Điều kiện nào phải đúng trước khi chuyển trạng thái |
| Bảo mật | Xác thực token, kiểm tra quyền truy cập thô ở endpoint | Người này có được hủy chính đơn hàng này trong trạng thái hiện tại không |
| Logging/audit | Ghi nhận ai gọi, lúc nào, correlation ID và kết quả kỹ thuật | Sự kiện nghiệp vụ nào có ý nghĩa phải được lưu trong lịch sử đơn |
| Retry | Thử lại lỗi tạm thời theo chính sách kỹ thuật | Có được lặp lại thao tác nghiệp vụ hay phải yêu cầu xác nhận mới |
| Validation | Kiểm tra request đúng định dạng, giới hạn kích thước | Đơn có đủ điều kiện được duyệt theo chính sách hay không |

Ranh giới không phải lúc nào cũng tuyệt đối. Một số chính sách bảo mật hoặc tuân thủ có thể là quy tắc nghiệp vụ và cần được biểu diễn rõ trong application/domain. Một số thao tác audit có ý nghĩa nghiệp vụ, trong khi log chẩn đoán chỉ phục vụ vận hành. Hãy phân loại theo ý nghĩa và người chịu trách nhiệm thay đổi, không chỉ theo tên thư viện.

## 2. Những cơ chế tự động thường gặp

Trong Java/Spring, các cơ chế sau có thể chạy mà không xuất hiện trực tiếp trong thân phương thức:

| Cơ chế | Cách hoạt động | Ví dụ phù hợp |
| --- | --- | --- |
| AOP / method interceptor | Bao quanh lời gọi phương thức dựa trên pointcut hoặc annotation | Đo thời gian, ghi log, áp dụng transaction |
| Servlet filter / HandlerInterceptor | Chạy trước hoặc sau xử lý HTTP | Kiểm tra request ID, xác thực, CORS |
| Method security | Kiểm tra quyền trước khi gọi method | Chặn người không có authority gọi một nhóm chức năng |
| ORM lifecycle callback / entity listener | Chạy khi entity được persist, update hoặc load | Gán timestamp kỹ thuật, đồng bộ trường audit |
| Event listener | Phản ứng khi có event được phát | Gửi thông báo sau khi đơn đã được hủy thành công |
| Bean validation | Kiểm tra constraint khai báo trên dữ liệu | Tên request không rỗng, số lượng có định dạng hợp lệ |

Những cơ chế này hữu ích khi hành vi có tính tổng quát, áp dụng nhất quán và không làm người đọc mất dấu quyết định nghiệp vụ. Vấn đề bắt đầu khi annotation, pointcut hoặc callback trở thành nơi duy nhất chứa chính sách quan trọng.

## 3. Dấu hiệu quy tắc nghiệp vụ đang bị che giấu

Hãy xem xét lại thiết kế nếu gặp một hoặc nhiều dấu hiệu sau:

- Một annotation tự định nghĩa như `@CancelAllowedUntil(...)` quyết định thời hạn hủy đơn nhưng không có domain policy hoặc use case nào thể hiện điều kiện đó.
- Một aspect dựa vào tên phương thức, package hoặc tham số để suy ra loại nghiệp vụ rồi âm thầm chặn hoặc sửa dữ liệu.
- Một entity listener tự đổi trạng thái `PAID`, `CANCELLED` hoặc `SHIPPED` khi ORM lưu entity.
- Một thao tác gọi `orderService.cancel(id)` nhưng kết quả phụ thuộc vào cấu hình pointcut, thứ tự aspect hoặc listener mà người đọc không dễ tìm thấy.
- Quy tắc chỉ được kiểm thử gián tiếp bằng cách khởi động toàn bộ Spring context; không thể kiểm thử điều kiện nghiệp vụ độc lập.
- Thay đổi chính sách kinh doanh buộc nhóm phải sửa annotation, biểu thức AOP hoặc cấu hình framework mà không thấy được nơi quyết định trạng thái miền.
- Cùng một quy tắc xuất hiện trong nhiều aspect, listener hoặc interceptor nên hành vi giữa các luồng không nhất quán.

Không phải cứ có annotation là thiết kế sai. `@Transactional` ở application service có thể làm ranh giới giao dịch dễ nhận biết; `@PreAuthorize` cho quyền thô ở endpoint có thể làm chính sách truy cập rõ ràng. Cần xem annotation đang khai báo một cơ chế chung hay đang giấu một quyết định nghiệp vụ có ngữ cảnh.

## 4. Ví dụ: không giấu chính sách hủy đơn trong AOP

Giả sử doanh nghiệp quy định: khách hàng chỉ được hủy đơn của mình khi đơn đang ở trạng thái `PLACED` và chưa quá 30 phút từ lúc đặt. Đây là quyết định nghiệp vụ vì nó phụ thuộc chủ sở hữu, trạng thái và thời điểm tạo đơn.

Một cách thiết kế khó hiểu là dùng aspect tự kiểm tra điều kiện trước mọi phương thức có tên `cancel`:

```java
@Aspect
@Component
class CancellationPolicyAspect {

    @Around("execution(* *.cancel(..))")
    Object checkWindow(ProceedingJoinPoint joinPoint) throws Throwable {
        // Tìm orderId từ tham số, tải đơn và kiểm tra thời hạn.
        // Từ chối lời gọi nếu quá 30 phút hoặc đơn không ở trạng thái phù hợp.
        return joinPoint.proceed();
    }
}
```

Đoạn mã là ví dụ về một cách làm nên tránh. Pointcut có thể bắt nhầm phương thức `cancel` không liên quan đến đơn hàng; người đọc không biết chính sách nằm ở đâu; aspect phải tự tìm dữ liệu nghiệp vụ và có thể tạo thêm transaction hoặc truy vấn ngầm. Nếu một luồng gọi không đi qua Spring proxy, hành vi có thể không được áp dụng như dự kiến.

Đưa điều kiện vào mô hình miền để quyết định chuyển trạng thái được thể hiện ngay tại nơi sở hữu đơn hàng:

```java
public class Order {
    private final OrderId id;
    private final CustomerId customerId;
    private final Instant placedAt;
    private OrderStatus status;

    public void cancelBy(CustomerId actor, Instant now) {
        if (!customerId.equals(actor)) {
            throw new OrderAccessDeniedException(id);
        }
        if (status != OrderStatus.PLACED) {
            throw new OrderCannotBeCancelledException(id, status);
        }
        if (now.isAfter(placedAt.plus(Duration.ofMinutes(30)))) {
            throw new CancellationWindowExpiredException(id);
        }
        status = OrderStatus.CANCELLED;
    }
}
```

Application service điều phối việc tải đơn, gọi quyết định miền và lưu kết quả:

```java
@Service
class CancelOrderService {
    private final OrderRepository orders;
    private final Clock clock;

    CancelOrderService(OrderRepository orders, Clock clock) {
        this.orders = orders;
        this.clock = clock;
    }

    @Transactional
    public void handle(CancelOrderCommand command) {
        Order order = orders.findById(command.orderId())
            .orElseThrow(OrderNotFoundException::new);

        order.cancelBy(command.customerId(), clock.instant());
        orders.save(order);
    }
}
```

Trong ví dụ này, `Order` sở hữu điều kiện về chủ sở hữu, trạng thái và thời hạn; application service điều phối ca sử dụng; `@Transactional` khai báo ranh giới giao dịch. Đồng hồ được truyền vào để thời gian có thể kiểm soát trong kiểm thử. Mã minh họa lược bỏ constructor, getter và chi tiết repository; trong dự án thật, kiểu lỗi và chính sách thời hạn cần khớp với ngôn ngữ nghiệp vụ.

Nếu thời hạn 30 phút có thể thay đổi theo loại khách hàng hoặc chiến dịch, không nên cố định nó trong aspect. Có thể đưa chính sách vào một domain policy/service có tên rõ ràng, được application service gọi với dữ liệu cần thiết. Điều quan trọng là luồng use case cho thấy quyết định đó đang diễn ra.

## 5. Đặt các cơ chế xuyên tầng vào đúng vai trò

### Transaction: cơ chế tự động bao quanh use case

`@Transactional` là ví dụ tốt về khai báo xuyên tầng. Nó cho Spring biết cách mở và kết thúc transaction quanh một phương thức. Nó không nên tự quyết định một đơn có được hủy hay không.

```java
@Transactional
public void cancel(CancelOrderCommand command) {
    // Tải đơn, gọi order.cancelBy(...), lưu thay đổi.
}
```

Ranh giới transaction thường thuộc application service vì service biết những bước nào của use case cần cùng commit hoặc rollback. Quy tắc trạng thái vẫn nằm trong domain model hoặc policy được gọi rõ ràng.

### Bảo mật: phân biệt quyền truy cập thô và quyền theo ngữ cảnh

Method security có thể chặn một nhóm chức năng theo authority:

```java
@PreAuthorize("hasAuthority('ORDER_CANCEL')")
public void cancel(CancelOrderCommand command) {
    // Kiểm tra quyền chức năng ở ranh giới method.
    // Sau đó domain vẫn kiểm tra đơn có thể hủy trong ngữ cảnh cụ thể.
}
```

Điều kiện `ORDER_CANCEL` có thể là quyền chức năng chung. Nhưng điều kiện “người này chỉ hủy đơn của chính họ khi đơn chưa được giao” phụ thuộc dữ liệu và trạng thái của đơn; nên được kiểm tra trong use case/domain. Một annotation không thay thế kiểm tra quyền theo tài nguyên nếu nó không có đủ ngữ cảnh hoặc không làm rõ chính sách.

### Logging và audit: ghi nhận khác với quyết định

Aspect ghi log method, thời gian, correlation ID và lỗi kỹ thuật là phù hợp nếu không làm lộ dữ liệu nhạy cảm. Nhưng lịch sử nghiệp vụ như “đơn đã bị khách hàng hủy” nên được biểu diễn bằng sự kiện/domain record có nội dung và tác nhân rõ ràng. Log một dòng `cancel() called` không thay thế bản ghi nghiệp vụ có thể truy vấn và kiểm toán.

### ORM callback: giữ cho callback đơn giản và kỹ thuật

Entity listener có thể gán `createdAt`, `updatedAt` hoặc trường kỹ thuật trước khi persist/update. Không nên để `@PreUpdate` tự kiểm tra thời hạn hoàn tiền, tự đổi trạng thái đơn hoặc gọi dịch vụ thanh toán. Callback ORM có thể chạy trong các thao tác lưu không thể hiện rõ trong luồng use case; nó cũng không phải nơi phù hợp để điều phối nhiều hệ thống.

### Event listener: phản ứng sau quyết định, không thay thế quyết định

Sau khi `Order.cancelBy` thành công, ứng dụng có thể phát `OrderCancelled` để gửi email hoặc cập nhật một read model. Listener phản ứng với sự kiện đã xảy ra; nó không nên là nơi quyết định đơn có đủ điều kiện hủy hay không. Nếu cần bảo đảm sự kiện được phát cùng thay đổi dữ liệu, cân nhắc transactional outbox thay vì phát thông điệp không thể thu hồi trước commit.

## 6. Quy tắc nào nên đặt ở đâu?

| Loại quyết định/hành vi | Vị trí thường phù hợp | Ví dụ |
| --- | --- | --- |
| Quy tắc bất biến của một đối tượng miền | Entity/value object/domain service | Đơn chỉ chuyển từ `PLACED` sang `CANCELLED` khi đủ điều kiện |
| Điều phối một ca sử dụng | Application service | Tải đơn, kiểm tra quyền theo ngữ cảnh, gọi domain, lưu và phát sự kiện |
| Ranh giới transaction | Application service kết hợp `@Transactional` | Commit hoặc rollback toàn bộ thao tác dữ liệu của ca sử dụng |
| Xác thực và quyền chức năng chung | Security filter/method security | Request phải có danh tính và authority `ORDER_CANCEL` |
| Ghi log, trace, metrics | Filter, interceptor hoặc aspect | Ghi thời gian và correlation ID |
| Mapping HTTP và persistence | Controller/mapper và repository adapter | Request DTO sang command; domain sang entity lưu trữ |
| Phản ứng với sự kiện đã xảy ra | Event handler/listener | Gửi thông báo sau khi đơn được hủy |

Đôi khi một quy tắc không thuộc riêng một entity, chẳng hạn chính sách giá phụ thuộc nhiều aggregate. Có thể đặt nó trong domain service hoặc policy object có tên rõ ràng. Application service gọi policy đó một cách tường minh. Tránh chuyển nó thành aspect chỉ vì muốn dùng ở nhiều nơi; tái sử dụng chính sách không đòi hỏi che giấu điểm gọi.

## 7. Làm cho hành vi tự động dễ nhìn thấy và kiểm thử

Khi dùng cơ chế xuyên tầng, người đọc cần biết nó áp dụng ở đâu, thứ tự ra sao và có tác dụng phụ nào. Một số thực hành hữu ích:

- Dùng annotation chuẩn của framework cho hành vi có ngữ nghĩa kỹ thuật rõ, chẳng hạn `@Transactional`, `@Cacheable` hoặc `@PreAuthorize` cho quyền chức năng.
- Đặt aspect theo annotation có tên mô tả đúng cơ chế, thay vì pointcut rộng dựa vào tên method như `*Service.*(..)` hoặc `execution(* *.save(..))`.
- Giữ aspect mỏng: nhận diện điểm cắt, gọi cơ chế kỹ thuật và ghi nhận kết quả; không tải aggregate rồi áp dụng chính sách nghiệp vụ.
- Tài liệu hóa thứ tự khi nhiều interceptor/aspect cùng tác động, nhất là transaction, security, retry và logging.
- Tránh để listener âm thầm thay đổi trạng thái miền; nếu listener làm thay đổi dữ liệu nghiệp vụ, hãy xem đó có phải một use case khác cần điểm vào rõ ràng không.
- Không để cơ chế tự động phụ thuộc vào tên package hoặc quy ước đặt tên mong manh nếu có thể dùng interface/annotation rõ ràng.

Kiểm thử nên phản ánh hai loại trách nhiệm:

1. **Kiểm thử quy tắc nghiệp vụ:** kiểm thử `Order.cancelBy` với đơn đúng chủ sở hữu, sai chủ sở hữu, đúng thời hạn, quá thời hạn và trạng thái không cho phép hủy. Dùng `Instant` cố định để kiểm thử không phụ thuộc đồng hồ thật.
2. **Kiểm thử điều phối use case:** kiểm tra application service tải đúng đơn, gọi domain, lưu khi thành công và không lưu khi quy tắc ném lỗi.
3. **Kiểm thử cơ chế xuyên tầng:** kiểm tra `@Transactional` tạo rollback khi lỗi, method security từ chối người thiếu authority, aspect logging không làm thay đổi kết quả nghiệp vụ.
4. **Kiểm thử tích hợp:** khởi động Spring context khi cần xác nhận proxy, listener, transaction và thứ tự interceptor hoạt động đúng trong môi trường thật.

Nếu một quy tắc chỉ có thể được xác nhận bằng cách chạy toàn bộ ứng dụng, hãy xem xét đưa quyết định về một đối tượng hoặc policy có thể kiểm thử độc lập. Nếu một aspect chỉ làm nhiệm vụ kỹ thuật, kiểm thử tích hợp cơ chế là phù hợp.

## 8. Checklist khi review một annotation, aspect hoặc listener

Trước khi thêm cơ chế tự động, hãy tự hỏi:

1. Nó đang áp dụng chính sách kỹ thuật hay đang quyết định kết quả nghiệp vụ?
2. Nếu chính sách thay đổi, nhóm phát triển sẽ tìm và sửa ở đâu?
3. Người đọc một use case có thể nhận ra các điều kiện làm thay đổi trạng thái không?
4. Cơ chế có cần tải dữ liệu nghiệp vụ, gọi repository hoặc phối hợp dịch vụ khác không?
5. Hành vi có chạy trong mọi đường gọi cần thiết, kể cả gọi nội bộ, job nền và test không?
6. Có thể kiểm thử quy tắc độc lập khỏi Spring proxy hoặc ORM lifecycle không?
7. Có thứ tự thực thi, transaction hoặc tác dụng phụ ngầm nào cần công khai không?

Một cơ chế xuyên tầng tốt giúp hành vi kỹ thuật nhất quán và giảm lặp lại. Một quy tắc nghiệp vụ tốt có tên, ngữ cảnh và điểm gọi dễ tìm. Khi giữ hai phần này rõ ràng, kiến trúc phân tầng dễ đọc hơn, chính sách dễ thay đổi hơn và kiểm thử có thể tập trung đúng vào quyết định cần bảo vệ.

## Tự kiểm tra

1. Vì sao điều kiện “đơn chỉ được hủy trong 30 phút và bởi chủ sở hữu” nên được thể hiện trong domain/use case thay vì một aspect chung?
2. `@Transactional` có thể tự động hóa điều gì và không nên quyết định điều gì?
3. `@PreAuthorize` kiểm tra authority chức năng có thay thế được quy tắc “chỉ chủ đơn được hủy đơn chưa giao” không? Vì sao?
4. Entity listener phù hợp với việc gán `updatedAt` nhưng có rủi ro gì nếu tự đổi trạng thái đơn?
5. Sự khác nhau giữa log kỹ thuật `cancel()` và sự kiện nghiệp vụ `OrderCancelled` là gì?
6. Làm thế nào để kiểm thử chính sách thời hạn hủy đơn mà không phụ thuộc thời gian thực hoặc Spring AOP?

