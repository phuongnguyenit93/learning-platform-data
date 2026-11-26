# Tránh giữ service, tài nguyên mở hoặc dữ liệu lớn trong mô hình

*Chương: Dữ liệu và scope · Module: SPRING_WEB_FLOW*

Một flow nhiều bước cần giữ lại một phần dữ liệu để người dùng có thể chuyển màn hình, quay lại hoặc tiếp tục sau một request. Tuy nhiên, không phải đối tượng nào ứng dụng đang sử dụng cũng nên được đưa vào model hoặc scope của flow. Service, kết nối cơ sở dữ liệu, luồng đọc file, socket, đối tượng request và tập dữ liệu lớn có vòng đời hoặc chi phí riêng. Nếu giữ chúng trong mô hình của flow quá lâu, ứng dụng có thể gặp lỗi vòng đời, khó khôi phục execution, tốn bộ nhớ và khó mở rộng khi chạy nhiều người dùng.

Module SPRING_WEB_FLOW hướng tới việc mô hình hóa hành trình web bằng state, event, transition và subflow, đồng thời thực hành form binding, validation, quản lý scope và phiên, tích hợp Spring MVC, kiểm thử và phục hồi lỗi. Bài học này tập trung vào một nguyên tắc thiết kế quan trọng: model và scope chỉ nên giữ dữ liệu nhỏ, cần thiết cho hành trình; các thao tác và tài nguyên có vòng đời ngắn phải được quản lý trong service hoặc tại request đang sử dụng chúng.

Sau bài học, bạn có thể:

- Phân biệt dữ liệu của form và flow với service, tài nguyên đang mở và đối tượng hạ tầng.
- Giải thích vì sao không nên giữ connection, stream, session ORM, request hoặc service instance trong model.
- Chọn scope phù hợp với vòng đời dữ liệu.
- Thiết kế DTO nhỏ thay cho việc đưa cả entity graph hoặc tập dữ liệu lớn vào flow.
- Dùng ID, tiêu chí tìm kiếm và thông tin phân trang để tải dữ liệu theo nhu cầu.
- Quản lý việc đóng tài nguyên, tính nhất quán dữ liệu và khả năng khôi phục flow execution.

## 1. Model của flow nên chứa gì?

Trong một hành trình Spring Web Flow, model là dữ liệu mà view cần để hiển thị và nhận input. Scope là nơi giữ những dữ liệu đó trong một khoảng thời gian nhất định. Ví dụ, quy trình checkout có thể cần tên người nhận, địa chỉ giao hàng, lựa chọn vận chuyển và mã đơn nháp. Đây là những giá trị nhỏ, có ý nghĩa đối với hành trình và có thể tiếp tục sử dụng sau nhiều request.

Model không phải là nơi chứa mọi thứ mà ứng dụng cần để thực hiện nghiệp vụ. Một đối tượng form có thể chứa dữ liệu người dùng nhập; service chịu trách nhiệm thực hiện nghiệp vụ; repository hoặc storage quản lý dữ liệu lâu dài; connection và stream được mở trong thời gian thao tác cần chúng.

| Loại đối tượng | Nơi quản lý phù hợp | Có nên đưa vào flow model/scope? |
|---|---|---|
| DTO hoặc dữ liệu nháp nhỏ của form | viewScope hoặc flowScope tùy vòng đời | Có, nếu cần cho view hoặc các bước tiếp theo |
| Tiêu chí tìm kiếm, trang hiện tại, ID bản ghi | viewScope hoặc flowScope | Có, thường là dữ liệu phù hợp |
| Spring service hoặc repository | Spring application context | Không; gọi bean qua cơ chế DI/expression |
| JDBC Connection, ResultSet, transaction đang mở | Bên trong thao tác service | Không |
| InputStream, OutputStream, socket, file handle | Phạm vi thao tác đang sử dụng tài nguyên | Không |
| EntityManager hoặc Hibernate Session | Cơ chế persistence context và transaction | Không |
| HttpServletRequest, response, RequestContext | Request hiện tại hoặc tầng tích hợp | Không |
| Danh sách hàng chục nghìn bản ghi hoặc nội dung nhị phân lớn | Database, object storage hoặc hệ thống lưu trữ chuyên dụng | Không; chỉ giữ trang dữ liệu nhỏ hoặc tham chiếu |

Một model tốt thường gồm dữ liệu có thể biểu diễn, kiểm tra, lưu tạm và khôi phục một cách rõ ràng. Nó không nên mang theo những đối tượng có trạng thái nội bộ phức tạp, phụ thuộc thread, giữ tài nguyên hệ thống hoặc chỉ hợp lệ trong một request.

## 2. Vì sao không giữ service trong model?

Spring service thường là bean do container quản lý. Service có thể được inject vào controller, component hoặc được gọi từ biểu thức trong flow definition. Nó có vòng đời và phạm vi chia sẻ do Spring quản lý; model của một người dùng không cần sở hữu một bản sao service.

Ví dụ không nên thiết kế form object như sau:

~~~java
public class CheckoutForm {
    private String recipient;
    private String address;

    // Không nên nhúng collaborator vào đối tượng dữ liệu của form.
    private CheckoutService checkoutService;
}
~~~

Nếu form object được đưa vào flowScope, flow execution sẽ giữ cả tham chiếu tới service. Điều này trộn lẫn dữ liệu người dùng với collaborator của ứng dụng. Service có thể là singleton dùng chung giữa nhiều request, có dependency không thể serialize, hoặc có trạng thái nội bộ không thuộc về một execution cụ thể. Việc gắn service vào model cũng khiến form object khó kiểm thử và khó tái sử dụng.

Hãy để service ở Spring context và giữ form object chỉ có dữ liệu:

~~~java
public class CheckoutForm {
    private String recipient;
    private String address;
    private String shippingMethod;

    public String getRecipient() {
        return recipient;
    }

    public void setRecipient(String recipient) {
        this.recipient = recipient;
    }

    public String getAddress() {
        return address;
    }

    public void setAddress(String address) {
        this.address = address;
    }

    public String getShippingMethod() {
        return shippingMethod;
    }

    public void setShippingMethod(String shippingMethod) {
        this.shippingMethod = shippingMethod;
    }
}
~~~

Flow gọi bean bằng tên đã đăng ký trong Spring application context:

~~~xml
<on-start>
    <evaluate expression="checkoutService.createForm()"
              result="flowScope.checkoutForm"/>
</on-start>

<view-state id="shipping" view="checkout/shipping">
    <transition on="continue" to="review">
        <evaluate expression="checkoutService.validateAndPrepare(
            flowScope.checkoutForm)"/>
    </transition>
</view-state>
~~~

Trong ví dụ, flowScope giữ dữ liệu của form. Bean checkoutService vẫn do Spring quản lý và được tìm qua expression evaluation. Service không trở thành thuộc tính của CheckoutForm hay một giá trị trong scope. Khi cần thay đổi nghiệp vụ, ta sửa service; khi cần thay đổi trường nhập liệu, ta sửa form object.

Quy tắc này cũng áp dụng cho repository, DataSource, client HTTP, message producer, application context và các collaborator khác. Hãy inject chúng vào service hoặc component có trách nhiệm phù hợp. Không đặt các dependency đó vào DTO, entity hoặc object được bind từ view.

## 3. Không giữ tài nguyên đang mở qua nhiều request

Connection, stream, socket và file handle đại diện cho tài nguyên đang được hệ điều hành, database hoặc một dịch vụ khác cấp phát. Chúng thường phải được đóng trong một khoảng thời gian xác định. Flow execution có thể tồn tại lâu hơn một request, thậm chí người dùng có thể rời trình duyệt rồi quay lại sau đó. Vì vậy, giữ tài nguyên mở trong flowScope hoặc conversationScope dễ làm cạn pool connection, rò rỉ file descriptor hoặc để lại trạng thái không thể khôi phục.

Những đối tượng không nên giữ trong model gồm:

- java.sql.Connection, Statement, PreparedStatement và ResultSet.
- InputStream, OutputStream, reader, writer và file handle.
- Socket, HTTP response body hoặc client response cần đóng.
- Hibernate Session, transaction đang mở hoặc persistence context.
- Lock, thread, executor task và các đối tượng phụ thuộc vào thread hiện tại.
- HttpServletRequest, HttpServletResponse, RequestContext và các đối tượng chỉ có ý nghĩa trong request.

Hãy mở và đóng tài nguyên ngay trong service thực hiện thao tác. Ví dụ, khi đọc file để tính thông tin tổng hợp, service xử lý stream trong cùng phương thức:

~~~java
public ReportSummary summarize(String storedFileId) {
    try (InputStream input = fileStorage.open(storedFileId)) {
        return reportParser.summarize(input);
    } catch (IOException ex) {
        throw new ReportReadException("Không thể đọc báo cáo", ex);
    }
}
~~~

try-with-resources bảo đảm stream được đóng khi phương thức kết thúc, kể cả khi việc đọc phát sinh exception. Flow chỉ nhận kết quả nhỏ như ReportSummary hoặc thông tin lỗi có thể hiển thị. Nó không giữ InputStream để sử dụng ở state tiếp theo.

Với JDBC, hãy để transaction và connection nằm trong ranh giới service/repository. Spring transaction manager có thể quản lý vòng đời connection trong transaction; không lấy connection rồi đưa vào flowScope để dùng lại ở request kế tiếp. Một HTTP request mới không nên tiếp tục sử dụng transaction hoặc ResultSet của request trước.

### Trường hợp upload và download file

Đối tượng upload gắn với request, ví dụ MultipartFile, có thể tham chiếu tới file tạm do framework quản lý. Không nên giữ chính đối tượng đó trong flow qua nhiều bước. Hãy kiểm tra và lưu nội dung vào nơi lưu trữ được quản lý, sau đó giữ một ID hoặc storage key cùng metadata cần thiết:

~~~java
public UploadedFileInfo storeUpload(MultipartFile file) {
    validateFile(file);
    String storageId = fileStorage.store(file);
    return new UploadedFileInfo(
            storageId,
            file.getOriginalFilename(),
            file.getSize(),
            file.getContentType());
}
~~~

Flow có thể giữ UploadedFileInfo hoặc chỉ giữ storageId. Khi cần xử lý ở bước sau, service mở lại file từ storage theo ID và đóng stream trong cùng thao tác.

Với download lớn, tránh đọc toàn bộ file thành byte[] trong flowScope. Dùng endpoint hoặc cơ chế streaming phù hợp để truyền dữ liệu tới response, đồng thời đóng stream đúng cách. Nếu cần cho phép người dùng tải sau, lưu file ở object storage hoặc vùng lưu trữ tạm có thời hạn, rồi giữ một token tham chiếu an toàn. Không giữ response object hoặc stream đang mở trong execution.

## 4. Tránh đưa dữ liệu lớn vào flow scope

Một flow có thể sống trong nhiều phút hoặc lâu hơn thời gian của một request. Nếu mỗi execution giữ một danh sách lớn, một object graph sâu hoặc một nội dung nhị phân, bộ nhớ tiêu thụ sẽ tăng theo số lượng người dùng và số flow đang hoạt động. Việc lưu snapshot, passivation hoặc sao chép session giữa các node cũng trở nên tốn kém hơn.

Các ví dụ nên tránh:

- Lưu toàn bộ kết quả tìm kiếm hàng chục nghìn dòng trong flowScope.
- Đưa entity có nhiều quan hệ lazy-loaded vào form model.
- Giữ một danh sách đầy đủ sản phẩm, khách hàng hoặc giao dịch chỉ để hiển thị một trang.
- Đưa file PDF, ảnh hoặc nội dung upload lớn vào byte array trong scope.
- Lưu toàn bộ lịch sử thao tác hoặc dữ liệu báo cáo chỉ để tính một vài con số.

Thay vào đó, giữ tiêu chí tìm kiếm, bộ lọc, số trang, kích thước trang và các ID cần thiết. Khi view cần hiển thị, service truy vấn một trang dữ liệu nhỏ. Ví dụ:

~~~java
public class OrderSearchCriteria {
    private String keyword;
    private String status;
    private int pageNumber = 0;
    private int pageSize = 20;

    // getters và setters
}

public class OrderSummary {
    private String orderId;
    private String customerName;
    private String status;
    private BigDecimal total;

    // getters và setters
}

public class OrderPageView {
    private List<OrderSummary> items;
    private int pageNumber;
    private int pageSize;
    private long totalItems;

    // getters và setters
}
~~~

OrderPageView chỉ chứa một trang nhỏ các summary đã được chọn trường cần thiết. Nó không giữ toàn bộ entity graph hay nội dung file. Service truy vấn dữ liệu theo trang:

~~~java
public OrderPageView findOrders(OrderSearchCriteria criteria) {
    int safePageSize = Math.min(Math.max(criteria.getPageSize(), 1), 50);
    int safePageNumber = Math.max(criteria.getPageNumber(), 0);

    return orderRepository.findSummaryPage(
            criteria.getKeyword(),
            criteria.getStatus(),
            safePageNumber,
            safePageSize);
}
~~~

Giới hạn page size ở phía server giúp tránh việc client yêu cầu một trang quá lớn. Repository nên truy vấn có phân trang ở database thay vì tải toàn bộ kết quả rồi cắt danh sách trong Java.

Trong flow, giữ tiêu chí và số trang trong flowScope, còn trang kết quả chỉ cần tồn tại trong view đang hiển thị:

~~~xml
<on-start>
    <evaluate expression="orderSearchService.createCriteria()"
              result="flowScope.criteria"/>
    <set name="flowScope.pageNumber" value="0"/>
</on-start>

<view-state id="results" view="orders/results">
    <on-entry>
        <evaluate expression="orderSearchService.findPage(
            flowScope.criteria, flowScope.pageNumber)"
            result="viewScope.page"/>
    </on-entry>
    <transition on="nextPage" to="nextPage"/>
</view-state>

<action-state id="nextPage">
    <set name="flowScope.pageNumber"
         value="flowScope.pageNumber + 1"/>
    <transition to="results"/>
</action-state>
~~~

Ví dụ này giữ tiêu chí tìm kiếm và số trang trong flowScope vì chúng cần qua nhiều lần hiển thị. Dữ liệu trang kết quả nằm trong viewScope vì nó chỉ phục vụ state results. Khi quay lại state này, trang được tải lại từ service theo tiêu chí và số trang. Cần bảo đảm view hiển thị đúng thuộc tính của OrderPageView và cấu hình view resolver phù hợp.

Với dữ liệu lớn hơn, có thể dùng cursor hoặc token phân trang thay cho số trang. Nếu dữ liệu thay đổi giữa các request, hãy quyết định rõ cách xử lý bản ghi đã bị xóa, thay đổi trạng thái hoặc không còn quyền truy cập.

## 5. Chọn scope theo vòng đời và kích thước dữ liệu

Không có một scope phù hợp cho mọi loại dữ liệu. Hãy chọn scope dựa trên thời gian sống cần thiết và lượng dữ liệu cần giữ.

| Scope | Vòng đời điển hình | Dữ liệu phù hợp |
|---|---|---|
| requestScope | Request hiện tại | Giá trị tạm chỉ dùng trong lần xử lý hiện tại |
| flashScope | Ngắn hạn qua lần chuyển tiếp/render kế tiếp | Thông báo thành công hoặc lỗi |
| viewScope | Khi view state hiện tại còn hoạt động | Model nhỏ và dữ liệu chỉ phục vụ màn hình đó |
| flowScope | Trong suốt flow execution | Form draft, tiêu chí tìm kiếm, ID và lựa chọn giữa nhiều bước |
| conversationScope | Trong conversation gốc cùng các subflow liên quan | Một ít dữ liệu cần chia sẻ giữa flow cha và flow con |
| applicationScope | Dùng chung trong application | Dữ liệu tham chiếu dùng chung, bất biến hoặc được quản lý đồng bộ |

Ví dụ, một địa chỉ giao hàng đang chỉnh sửa có thể nằm trong flowScope nếu người dùng cần quay lại nhiều bước. Kết quả tìm kiếm chỉ dùng cho một màn hình nên nằm trong viewScope. Thông báo “Đã lưu” chỉ cần tồn tại ngắn hạn có thể dùng flashScope.

Không nên chọn conversationScope chỉ vì muốn dữ liệu tồn tại lâu hơn flowScope. Conversation có thể bao phủ cả flow cha và các subflow, vì vậy dữ liệu được giữ lâu hơn và có thể được nhiều phần của quy trình nhìn thấy. Chỉ đưa dữ liệu vào đó khi có nhu cầu chia sẻ thực sự.

applicationScope không phải nơi lưu dữ liệu riêng của người dùng. Vì dữ liệu được chia sẻ giữa các execution, thay đổi mutable object ở đây có thể ảnh hưởng tới nhiều người dùng. Chỉ dùng cho dữ liệu dùng chung có chính sách đồng bộ, cập nhật và cache rõ ràng.

Scope của Spring Web Flow không đồng nghĩa với việc mọi object được lưu trong một HTTP session duy nhất. Cách execution được lưu, snapshot hoặc khôi phục phụ thuộc FlowExecutionRepository và cấu hình triển khai. Dù repository đang giữ execution trong bộ nhớ hay dùng cơ chế lưu trữ khác, việc giữ object nhỏ và có vòng đời rõ ràng vẫn giúp giảm rủi ro và chi phí.

## 6. Khả năng serialize, passivation và triển khai nhiều node

Một số môi trường cần serialize hoặc passivate trạng thái phiên, lưu snapshot flow execution hoặc chuyển session giữa các node. Khi đó, object trong scope có thể phải đáp ứng yêu cầu của cơ chế lưu trữ và môi trường triển khai. Service proxy, connection, stream, socket, thread hoặc entity graph phức tạp thường không phù hợp để serialize.

Không nên thêm Serializable vào mọi class rồi xem đó là cách xử lý. Một object có thể serialize về mặt kỹ thuật nhưng vẫn chứa quá nhiều dữ liệu, tham chiếu tới trạng thái lỗi thời hoặc kéo theo một object graph lớn. Điều quan trọng là chỉ lưu dữ liệu cần thiết và có thể khôi phục.

Với DTO nằm trong flowScope hoặc conversationScope, hãy cân nhắc:

- Chỉ giữ các trường cần cho những bước còn lại.
- Dùng kiểu dữ liệu đơn giản, ổn định và có ý nghĩa rõ ràng.
- Không giữ collaborator, request object hoặc tài nguyên đang mở.
- Nếu repository hoặc container yêu cầu serialization, kiểm tra đúng yêu cầu của cấu hình đó và kiểm thử đường lưu/khôi phục execution.
- Với entity, cân nhắc lưu ID rồi tải lại thay vì giữ một object graph gắn với persistence context đã đóng.

Không giả định một execution có thể được khôi phục ở node khác chỉ vì dữ liệu của nó đã nằm trong flowScope. Khả năng này phụ thuộc repository, session replication, cấu hình serialization, phiên bản thư viện và cách ứng dụng quản lý dữ liệu ngoài flow.

## 7. Lưu ID thay vì giữ entity và trạng thái hạ tầng

Trong flow dài, việc giữ entity ORM qua nhiều request có thể tạo ra những vấn đề khó thấy. Entity có thể chứa proxy lazy-loading, quan hệ hai chiều hoặc tham chiếu tới persistence context đã kết thúc. Khi view truy cập một quan hệ lazy, ứng dụng có thể gặp lỗi do session đã đóng. Nếu entity được chỉnh sửa ở nhiều bước, trạng thái trong bộ nhớ cũng có thể cũ so với dữ liệu trong database.

Một cách tiếp cận an toàn hơn là giữ ID và một DTO form nhỏ:

~~~java
public class EditOrderForm {
    private String orderId;
    private String deliveryNote;
    private String shippingMethod;

    // getters và setters
}
~~~

Khi người dùng xác nhận, service tải lại bản ghi theo ID, kiểm tra quyền truy cập và trạng thái hiện tại, áp dụng thay đổi được phép rồi lưu trong transaction:

~~~java
public void updateDelivery(EditOrderForm form, UserPrincipal user) {
    Order order = orderRepository.findById(form.getOrderId())
            .orElseThrow(OrderNotFoundException::new);

    authorizationService.checkCanEdit(order, user);
    order.updateDelivery(form.getDeliveryNote(), form.getShippingMethod());
    orderRepository.save(order);
}
~~~

ID do trình duyệt gửi lên không phải bằng chứng người dùng có quyền đọc hoặc sửa bản ghi. Service luôn phải kiểm tra quyền và điều kiện nghiệp vụ trên dữ liệu mới nhất trước khi thực hiện thay đổi. Nếu bản ghi đã thay đổi từ request trước, hãy áp dụng chính sách phát hiện xung đột hoặc yêu cầu người dùng tải lại dữ liệu.

Với dữ liệu nháp chưa lưu, có thể giữ DTO trong flowScope và chỉ ghi xuống database ở thời điểm phù hợp. Nếu draft cần tồn tại sau khi flow kết thúc hoặc người dùng có thể quay lại nhiều ngày sau, hãy lưu draft vào kho dữ liệu có thời hạn và chỉ giữ draft ID trong flow.

## 8. Đóng tài nguyên và dọn dữ liệu tạm đúng lúc

Việc tránh giữ tài nguyên trong scope cần đi cùng chính sách đóng và dọn dữ liệu. Hãy phân định rõ ai mở tài nguyên, ai sở hữu nó và thời điểm đóng:

| Tài nguyên | Cách quản lý |
|---|---|
| JDBC connection/statement/result set | Để transaction manager hoặc repository quản lý; đóng trong phạm vi thao tác |
| File stream | Dùng try-with-resources trong service |
| HTTP client response/body | Đọc hoặc stream trong phạm vi request, đóng response theo API client |
| File upload tạm | Chuyển vào storage có quản lý, chỉ giữ ID và metadata |
| File export tạm | Gắn thời hạn, xóa theo chính sách dọn rác hoặc job quản lý |
| Bản nháp trong flow | Xóa hoặc đánh dấu hết hạn khi flow kết thúc theo chính sách nghiệp vụ |
| Cache dữ liệu tham chiếu | Có TTL, giới hạn kích thước và cơ chế invalidation phù hợp |

Đừng dựa hoàn toàn vào việc người dùng đóng trình duyệt để dọn dữ liệu. Flow có thể hết hạn, trình duyệt có thể mất kết nối hoặc người dùng mở nhiều tab. Nếu có tài nguyên tạm bên ngoài như file đã upload hoặc reservation, cần có TTL hoặc cơ chế cleanup độc lập với vòng đời trình duyệt.

Nếu flow kết thúc ở nhiều end state, hãy xác định nơi thực hiện cleanup chung và các thao tác chỉ áp dụng cho một nhánh. Cleanup nên idempotent nếu có khả năng được gọi lại sau lỗi hoặc retry. Không xóa tài nguyên đã được chuyển quyền sở hữu cho một quy trình nghiệp vụ khác.

## 9. Bảo vệ dữ liệu và tránh tham chiếu nhạy cảm

Scope và model có thể được giữ trong bộ nhớ, lưu trong session hoặc được ghi thành snapshot tùy cấu hình. Vì vậy, không nên lưu mật khẩu, secret, access token dài hạn, thông tin thẻ thanh toán hoặc dữ liệu nhạy cảm không cần thiết chỉ để tiện sử dụng ở bước sau.

Với thông tin xác thực, hãy dùng cơ chế bảo mật chuyên dụng và chỉ truyền tham chiếu hoặc trạng thái tối thiểu cần thiết. Không đưa credential vào DTO hiển thị cho view, log, thông báo lỗi hoặc object được serialize. Với dữ liệu cá nhân, chỉ giữ trường thực sự cần cho quy trình và xóa khi hết mục đích sử dụng theo chính sách ứng dụng.

Khi lưu ID của file hoặc bản ghi, dùng ID khó đoán hoặc token có thời hạn nếu phù hợp, nhưng vẫn phải kiểm tra quyền ở service. Một ID khó đoán không thay thế authorization.

## 10. Dấu hiệu nhận biết model đang giữ quá nhiều

Các dấu hiệu sau thường cho thấy flow execution đang giữ sai loại dữ liệu:

- Dung lượng session hoặc snapshot tăng theo thời gian sử dụng.
- Số lượng flow đang hoạt động không lớn nhưng heap tăng nhanh.
- Database connection pool bị cạn sau khi người dùng rời một bước giữa chừng.
- Lỗi serialize hoặc passivation xuất hiện khi triển khai nhiều node.
- Lỗi lazy-loading xảy ra khi người dùng quay lại màn hình sau một request.
- Một flow tiếp tục sử dụng dữ liệu cũ dù bản ghi trong database đã thay đổi.
- File tạm không được xóa sau khi người dùng hủy quy trình.
- Nhiều execution cùng tham chiếu một mutable object và ảnh hưởng lẫn nhau.

Khi điều tra, hãy xem xét object nào đang nằm trong flowScope, conversationScope hoặc viewScope, kích thước object graph, vòng đời flow execution, cấu hình repository và số request đang giữ tài nguyên. Không chỉ nhìn vào heap; hãy kiểm tra cả connection pool, file descriptor, số file tạm và log của cơ chế session replication.

## 11. Ví dụ thiết kế trước và sau

Giả sử người dùng tìm kiếm đơn hàng, mở một đơn, chỉnh sửa ghi chú giao hàng rồi xác nhận. Cách thiết kế dễ gây vấn đề là đưa toàn bộ danh sách đơn, entity Order, repository và một connection đang mở vào model để các màn hình dùng chung.

Thiết kế phù hợp hơn chia dữ liệu theo trách nhiệm:

| Thành phần | Dữ liệu hoặc trách nhiệm |
|---|---|
| FlowScope | Tiêu chí tìm kiếm nhỏ, số trang, orderId, form draft |
| ViewScope | Một trang OrderSummary có giới hạn kích thước |
| Spring service | Tìm kiếm, kiểm tra quyền, tải entity, lưu thay đổi |
| Repository/transaction | Truy vấn và ghi dữ liệu trong transaction |
| Storage | Lưu file nếu quy trình có upload, trả về storageId |
| View | Hiển thị DTO và gửi event; không giữ connection hoặc entity graph |

Với thiết kế này, flow có thể tiếp tục qua nhiều request bằng các giá trị nhỏ. Khi người dùng mở một đơn, service tải dữ liệu mới nhất theo ID. Khi xác nhận, service kiểm tra quyền và trạng thái rồi lưu thay đổi trong transaction. Khi người dùng rời flow, không có connection hoặc stream nào bị bỏ lại trong scope.

## 12. Danh sách kiểm tra khi thiết kế model cho flow

Trước khi thêm một thuộc tính vào model hoặc scope, hãy tự hỏi:

1. View hoặc bước tiếp theo có thực sự cần giá trị này không?
2. Giá trị cần sống trong một request, một view state hay toàn flow?
3. Có thể lưu ID hoặc tiêu chí thay vì giữ cả object không?
4. Object có giữ service, repository, connection, stream, request hoặc collaborator nào không?
5. Object có chứa collection lớn, binary data hoặc entity graph không cần thiết không?
6. Dữ liệu có thể serialize/passivate theo cấu hình triển khai không?
7. Nếu dữ liệu thay đổi trong database, flow sẽ tải lại hoặc phát hiện xung đột như thế nào?
8. Ai chịu trách nhiệm đóng hoặc xóa tài nguyên tạm, và khi nào?
9. Có dữ liệu nhạy cảm nào cần loại khỏi model, log hoặc snapshot không?
10. Test có kiểm tra flow kết thúc, timeout, retry và khôi phục execution không?

Nếu một object không vượt qua các câu hỏi về vòng đời, kích thước hoặc khả năng khôi phục, hãy chuyển trách nhiệm của nó về service, repository hoặc storage và chỉ giữ tham chiếu nhỏ trong flow.

## Kết luận

Model của Spring Web Flow nên giữ dữ liệu cần thiết cho hành trình và có vòng đời phù hợp với scope. Service và repository thuộc Spring application context; connection, stream, socket và transaction thuộc phạm vi thao tác; tập dữ liệu lớn và nội dung nhị phân thuộc database hoặc storage. Flow thường chỉ cần DTO nhỏ, tiêu chí tìm kiếm, ID, trạng thái lựa chọn và một trang dữ liệu có giới hạn.

Khi giữ model nhẹ, đóng tài nguyên đúng lúc và tải lại dữ liệu theo nhu cầu, flow execution dễ khôi phục hơn, tiêu thụ ít bộ nhớ hơn và ít phụ thuộc vào trạng thái hạ tầng của request trước. Đây là nền tảng để xây dựng hành trình nhiều bước ổn định khi có nhiều người dùng, nhiều tab và các lần tiếp tục sau gián đoạn.
