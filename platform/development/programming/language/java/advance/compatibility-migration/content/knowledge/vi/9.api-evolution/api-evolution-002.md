# Thêm API thay thế trước khi ngừng hỗ trợ API cũ

Khi phát triển một thư viện Java hoặc một nền tảng dùng chung, nhu cầu thay đổi API là điều không tránh khỏi. Có thể một phương thức cũ trả về giá trị khó diễn đạt trạng thái lỗi, một interface không còn phản ánh nghiệp vụ, hoặc một API dựa trên thư viện không được hỗ trợ ở JDK mới. Nếu thay đổi trực tiếp chữ ký hoặc xóa API cũ, những ứng dụng đang phụ thuộc vào nó có thể không biên dịch được, không liên kết được khi chạy, hoặc thay đổi hành vi.

Một chiến lược tiến hóa API thường hiệu quả là **đưa API thay thế vào trước**, duy trì API cũ trong một giai đoạn chuyển tiếp, cung cấp hướng dẫn nâng cấp và chỉ ngừng hỗ trợ API cũ sau khi đánh giá được tác động. Cách làm này cho phép nhà cung cấp và consumer chuyển đổi theo nhịp độ khác nhau, đồng thời giữ khả năng phát hành những bản sửa lỗi trong thời gian migration.

Bài học tập trung vào cách thiết kế API thay thế, quản lý deprecation và chuyển đổi consumer trong bối cảnh **Java Advance Compatibility Migration**. Nguyên tắc cũng có thể áp dụng cho API framework, plugin và giao thức bên ngoài, nhưng cần đánh giá hợp đồng của từng loại API riêng biệt.

## 1. Vì sao nên thêm API thay thế trước?

Giả sử phiên bản 1 của thư viện có phương thức:

~~~java
Customer findCustomer(String customerId)
        throws CustomerNotFoundException;
~~~

Ứng dụng A dùng phương thức này trong giao diện quản trị, ứng dụng B dùng trong một batch job, và ứng dụng C chỉ được triển khai vài tháng một lần. Nhà cung cấp muốn giới thiệu một API mới trả về Optional để biểu diễn tình huống không tìm thấy khách hàng.

Nếu nhà cung cấp thay trực tiếp phương thức cũ bằng:

~~~java
Optional<Customer> findById(String customerId);
~~~

thì source code đang gọi findCustomer sẽ không còn biên dịch. Consumer đã biên dịch sẵn cũng có thể gặp NoSuchMethodError khi chạy với phiên bản thư viện mới, vì method cũ đã biến mất. Ngoài ra, người dùng còn phải thay cách xử lý tình huống không tìm thấy khách hàng.

Thay vào đó, nhà cung cấp có thể xuất bản một phiên bản chứa **cả hai phương thức**:

~~~java
Customer findCustomer(String customerId)
        throws CustomerNotFoundException;

Optional<Customer> findById(String customerId);
~~~

Các consumer cũ tiếp tục sử dụng hợp đồng hiện hành. Consumer mới và consumer đang được nâng cấp có thể chọn findById. Trong thời gian chuyển tiếp, thư viện có cơ hội thu thập phản hồi, kiểm tra tương thích và giải quyết những trường hợp mà API mới chưa đáp ứng.

Chiến lược này thường được gọi là **additive evolution** hoặc một phần của quy trình **expand–migrate–contract**:

1. **Expand:** bổ sung API mới, giữ API cũ hoạt động.
2. **Migrate:** hướng dẫn và chuyển dần các consumer sang API mới.
3. **Contract:** sau khi đáp ứng chính sách hỗ trợ, loại bỏ API cũ hoặc ngừng cam kết hỗ trợ cho nó theo một phiên bản được công bố.

Giai đoạn expand không tự động bảo đảm tương thích hoàn toàn. Việc thêm method vào interface, thêm overload hoặc thay dependency vẫn có thể ảnh hưởng consumer. Cần đánh giá hình thức thay đổi cụ thể trước khi phát hành.

## 2. Phân biệt API cũ, API mới và hợp đồng được hỗ trợ

Không phải mọi lớp hay method tồn tại trong một artifact đều được nhà cung cấp cam kết ổn định. Trước khi thiết kế API thay thế, cần xác định:

- **API được hỗ trợ:** phương thức, class, interface, SPI, cấu hình hoặc hành vi mà consumer được phép phụ thuộc theo hợp đồng đã công bố.
- **API deprecated:** API vẫn tồn tại nhưng nhà cung cấp khuyến nghị chuyển sang giải pháp khác; trong thời gian hỗ trợ, hợp đồng của nó vẫn cần được tôn trọng.
- **API nội bộ:** chi tiết triển khai không được công bố là bề mặt ổn định cho consumer.
- **API experimental:** API được cung cấp để thử nghiệm nhưng có chính sách ổn định khác API chính thức.

Deprecation là tín hiệu về **tương lai của API**, không phải thông báo rằng API đã lập tức ngừng hoạt động. Khi một method đang được hỗ trợ được đánh dấu deprecated, những consumer chưa thể nâng cấp thường vẫn mong đợi nó hoạt động đúng trong khoảng thời gian hỗ trợ đã công bố.

Ngoài chữ ký method, hợp đồng API có thể bao gồm điều kiện đầu vào, quy tắc null, exception, thứ tự kết quả, transaction boundary, thread-safety, serialization, cấu hình và hiệu ứng phụ. Muốn thêm API thay thế an toàn, phải biết chính xác các ràng buộc này.

## 3. Chốt mục đích của API thay thế

Không nên tạo một API mới chỉ để đổi tên method nếu không có lợi ích rõ ràng. Trước hết, xác định vấn đề của API cũ và tiêu chí giải quyết.

| Vấn đề của API cũ | Hướng thay thế có thể phù hợp | Điều cần đánh giá |
|---|---|---|
| Trả về null để biểu diễn không tìm thấy | Dùng Optional hoặc kết quả domain rõ nghĩa | Phân biệt không tồn tại với lỗi hệ thống |
| Nhận nhiều tham số cùng kiểu dễ truyền sai | Dùng parameter object hoặc kiểu domain | Chi phí tạo object và tác động tới callers |
| Rò rỉ exception của implementation | Định nghĩa exception ổn định ở ranh giới module | Giữ cause và khả năng phân loại lỗi |
| Method có quá nhiều trách nhiệm | Tách thành những thao tác có ngữ nghĩa rõ | Tránh phá vỡ transaction hoặc atomicity |
| Phụ thuộc API nội bộ của JDK | Dùng API Java SE công khai phù hợp | Hành vi, hiệu năng và baseline Java |
| Dùng tên cấu hình gây nhầm lẫn | Bổ sung tên mới và cơ chế alias | Thứ tự ưu tiên khi cả tên cũ và mới được khai báo |
| API trả về kiểu mutable không có quy tắc ownership | Cung cấp kiểu kết quả hoặc abstraction ổn định | Tương thích dữ liệu và chi phí sao chép |

Kết quả của bước này nên là một mô tả ngắn gọn: consumer nào được hưởng lợi, hành vi mới có gì khác và những phần của hợp đồng cũ bắt buộc giữ trong giai đoạn chuyển tiếp.

## 4. Ví dụ Java: thêm API mới và giữ API cũ

Giả sử CustomerService trước đây trả về Customer hoặc ném CustomerNotFoundException. API mới muốn trả về Optional khi không tìm thấy khách hàng. Một thiết kế có thể là:

~~~java
import java.util.Objects;
import java.util.Optional;

public final class CustomerService {
    private final CustomerRepository repository;

    public CustomerService(CustomerRepository repository) {
        this.repository = Objects.requireNonNull(repository);
    }

    /**
     * Returns a customer when one exists for the identifier.
     *
     * @param customerId the identifier to look up
     * @return a customer, or an empty Optional when not found
     */
    public Optional<Customer> findById(String customerId) {
        Objects.requireNonNull(customerId, "customerId");
        return repository.findById(customerId);
    }

    /**
     * Looks up a customer using the legacy exception contract.
     *
     * @deprecated Since 2.1, use {@link #findById(String)} and
     *             handle the empty Optional explicitly.
     */
    @Deprecated(since = "2.1", forRemoval = false)
    public Customer findCustomer(String customerId)
            throws CustomerNotFoundException {
        return findById(customerId)
                .orElseThrow(
                    () -> new CustomerNotFoundException(customerId));
    }
}
~~~

Trong ví dụ này, CustomerRepository có phương thức findById trả về Optional<Customer>, còn CustomerNotFoundException là checked exception thuộc API cũ. Những kiểu này là thành phần minh họa của thư viện.

Điểm quan trọng là **cả hai API dùng chung một luồng tra cứu**. Khi thay logic repository, cache hoặc chính sách tìm kiếm, nhóm không phải duy trì hai implementation nghiệp vụ độc lập. API cũ chuyển kết quả Optional thành exception để giữ hợp đồng ban đầu.

Ví dụ sử dụng API cũ:

~~~java
try {
    Customer customer = service.findCustomer("C-42");
    render(customer);
} catch (CustomerNotFoundException exception) {
    showNotFound();
}
~~~

Ví dụ consumer chuyển sang API mới:

~~~java
Optional<Customer> result = service.findById("C-42");

if (result.isPresent()) {
    render(result.get());
} else {
    showNotFound();
}
~~~

Vì Optional không truyền checked exception cho trường hợp “không tìm thấy”, caller mới cần xử lý kết quả trống một cách rõ ràng. Những lỗi I/O hoặc lỗi backend thật sự vẫn phải có hợp đồng riêng; không nên biến mọi exception thành Optional.empty(), vì như vậy sẽ che giấu sự cố.

### 4.1. Điều kiện để adapter giữ tương thích

Trong ví dụ, phương thức cũ chỉ nên gọi API mới nếu adapter duy trì được hành vi đã cam kết:

- Giữ nguyên quy tắc xử lý customerId không hợp lệ.
- Giữ loại exception và thông tin cần thiết khi customer không tồn tại.
- Không tự thêm lần truy vấn hoặc side effect ngoài dự kiến.
- Giữ điều kiện đồng bộ, tính thread-safe và transaction nếu đã cam kết.
- Duy trì thông tin nguyên nhân lỗi backend; không chuyển lỗi backend thành “không tìm thấy”.
- Không thay đổi quyền truy cập, cách ghi log hay dữ liệu quan sát được ngoài phạm vi được công bố.

Nếu hợp đồng cũ dùng null thay vì exception, adapter phải tái hiện đúng quy tắc null trong thời gian chuyển tiếp. Không được tự ý đổi “không tìm thấy trả null” thành “ném exception” chỉ vì API mới được thiết kế theo cách khác.

### 4.2. Chiều ủy quyền ngược lại cũng có thể phù hợp

Trong một số hệ thống, implementation cũ đã ổn định và phức tạp. API mới có thể tạm thời gọi API cũ và chuyển đổi kết quả:

~~~java
public Optional<Customer> findById(String customerId) {
    try {
        return Optional.of(findCustomer(customerId));
    } catch (CustomerNotFoundException exception) {
        return Optional.empty();
    }
}
~~~

Cách này hữu ích khi muốn phát hành API mới với rủi ro thấp. Tuy nhiên, nếu findCustomer từng có khả năng trả null, Optional.of sẽ ném NullPointerException; khi đó cần xử lý theo hợp đồng thực tế. Ngoài ra, khi định hướng loại bỏ API cũ, đội phát triển có thể muốn chuyển implementation về một hàm nội bộ chung để tránh API mới phụ thuộc lâu dài vào một phương thức sắp bị xóa.

Không tạo vòng gọi trực tiếp giữa hai method. Nếu findById gọi findCustomer mà findCustomer lại gọi findById, ứng dụng sẽ rơi vào đệ quy vô hạn.

## 5. Bảo đảm tương thích khi thêm API

Thêm mới có vẻ ít rủi ro hơn xóa hay sửa API hiện hữu, nhưng cần phân biệt ba chiều tương thích.

**Tương thích mã nguồn (source compatibility)** nghĩa là mã nguồn consumer cũ vẫn biên dịch khi dùng phiên bản thư viện mới. **Tương thích nhị phân (binary compatibility)** nghĩa là bytecode consumer đã biên dịch vẫn liên kết được với artifact mới. **Tương thích hành vi (behavioral compatibility)** nghĩa là consumer vẫn quan sát được kết quả và quy tắc vận hành phù hợp với hợp đồng trước đó.

| Thay đổi | Rủi ro cần kiểm tra |
|---|---|
| Thêm method mới vào một class công khai | Trùng tên/overload, ambiguity khi gọi với null hoặc lambda, tác động tới lớp kế thừa |
| Thêm abstract method vào interface | Lớp implementor có thể không biên dịch lại; invocation trên implementation cũ có thể gây AbstractMethodError |
| Thêm default method vào interface | Có thể tạo xung đột giữa các interface kế thừa, hoặc thay đổi cách resolve method |
| Thêm overload cùng tên | Compiler có thể chọn overload khác hoặc báo ambiguous đối với các lời gọi cũ |
| Thêm kiểu trả về mới ở một method khác tên | Tương đối độc lập nhưng cần kiểm tra exposure của dependency và baseline JDK |
| Thêm API mới nhưng chỉnh sửa logic dùng chung | API cũ có thể thay đổi hành vi dù chữ ký giữ nguyên |
| Thêm method với tên trùng ở superclass | Có thể ảnh hưởng dispatch, kế thừa hoặc override ở các consumer |

Ví dụ, nếu trước đây có method accept(String) và thêm accept(Integer), lời gọi accept(null) có thể trở thành ambiguous. Đây là source incompatibility dù không thay đổi method cũ.

~~~java
public void accept(String value) { /* legacy */ }
public void accept(Integer value) { /* new */ }

// Với hai overload, lệnh sau có thể gây lỗi ambiguous:
accept(null);
~~~

Vì vậy, đặt tên method mới rõ nghĩa đôi khi ít rủi ro hơn thêm overload chỉ khác kiểu tham số.

## 6. Thêm method mới vào interface cần đặc biệt thận trọng

Interface là hợp đồng dành cho cả **caller** lẫn **implementor**. Một thư viện có thể biết mọi nơi gọi API nhưng không biết hết những dự án tự triển khai interface đó.

Giả sử:

~~~java
public interface DocumentStore {
    Document load(String id);
}
~~~

Thêm method trừu tượng:

~~~java
public interface DocumentStore {
    Document load(String id);

    Optional<Document> findById(String id);
}
~~~

sẽ yêu cầu những implementation được biên dịch lại phải bổ sung findById, trừ khi class trừu tượng hoặc có cơ chế khác phù hợp. Bytecode implementation cũ có thể nạp được trong một số tình huống, nhưng khi method mới được gọi qua interface mà không có implementation, có thể phát sinh AbstractMethodError.

Một default method có thể giảm yêu cầu sửa implementation:

~~~java
public interface DocumentStore {
    Document load(String id);

    default Optional<Document> findById(String id) {
        return Optional.ofNullable(load(id));
    }
}
~~~

Dù vậy, default method không tự động an toàn cho mọi tình huống. Nếu implementation hiện có có method cùng tên nhưng không tương thích kiểu trả về, hoặc một class kế thừa nhiều interface cung cấp default method xung đột, consumer vẫn có thể gặp lỗi biên dịch. Đặc biệt, default implementation phải giữ đúng ngữ nghĩa khi load ném exception hoặc trả null.

Khi nhà cung cấp không kiểm soát toàn bộ implementor, có thể cân nhắc:

- Thêm interface mới để mở rộng khả năng thay vì bổ sung abstract method vào interface cũ.
- Cung cấp adapter hoặc abstract base class có implementation mặc định.
- Dùng default method khi ngữ nghĩa và tương thích được kiểm tra.
- Đưa API mới lên service/facade riêng.
- Công bố hướng dẫn rõ cho các nhóm tự implement SPI.

Cần kiểm tra consumer tự triển khai interface, anonymous class, mock và proxy, không chỉ consumer gọi method.

## 7. Deprecation trong Java: công bố ý định thay thế

Java cung cấp annotation Deprecated và thẻ Javadoc deprecated để giúp IDE, compiler và người dùng nhận biết API cũ.

~~~java
/**
 * @deprecated Since 2.1, use {@link #findById(String)}.
 *             The legacy method will be supported during the migration window.
 */
@Deprecated(since = "2.1", forRemoval = false)
public Customer findCustomer(String id)
        throws CustomerNotFoundException {
    // Legacy behavior remains supported.
}
~~~

Hai cơ chế có vai trò bổ trợ:

- **@Deprecated:** metadata trong Java, cho phép compiler và công cụ cảnh báo khi code sử dụng API deprecated.
- **Javadoc @deprecated:** nội dung hướng dẫn, giải thích vì sao API cũ không được khuyến nghị và consumer nên chuyển sang đâu.

Thuộc tính since và forRemoval được thêm vào annotation Deprecated từ Java 9. Nếu dự án phải biên dịch source bằng JDK 8, cần dùng dạng annotation tương thích với JDK đó, đồng thời diễn đạt thông tin phiên bản và kế hoạch trong Javadoc hoặc tài liệu riêng.

**since** cho biết nhãn deprecation được áp dụng từ phiên bản nào theo cách đánh phiên bản của thư viện. **forRemoval = true** biểu thị ý định loại bỏ API trong tương lai; nó không tự động xóa API và không quy định ngày loại bỏ cụ thể. Vì vậy, cần có chính sách versioning, release notes hoặc lịch ngừng hỗ trợ được công bố riêng.

### 7.1. Một deprecation notice hữu ích cần nói rõ

Thông báo tốt nên trả lời:

1. API cũ có vấn đề gì hoặc không còn phù hợp vì sao?
2. API nào là đường thay thế chính thức?
3. Cách chuyển đổi có cần thay đổi kiểu dữ liệu, exception hoặc hành vi không?
4. Có cần nâng baseline Java, Gradle, framework hoặc dependency không?
5. Phiên bản nào bắt đầu deprecated và phạm vi hỗ trợ còn lại là gì?
6. Có mốc dự kiến ngừng hỗ trợ hoặc loại bỏ không, nếu đã được quyết định?
7. Có ví dụ trước/sau, tài liệu migration và test nào để consumer tự kiểm tra không?

Chỉ ghi “Deprecated, use new API” thường chưa đủ nếu kiểu trả về, lỗi hoặc ngữ nghĩa khác nhau.

## 8. Giai đoạn chuyển tiếp và chính sách phiên bản

Không có một khoảng thời gian deprecation phù hợp cho mọi thư viện. Thời gian chuyển tiếp phụ thuộc vào số lượng consumer, lịch triển khai, độ quan trọng của API, yêu cầu bảo mật và cam kết hỗ trợ.

Ví dụ về lộ trình minh họa:

| Giai đoạn | Phiên bản giả định | Hành động của nhà cung cấp | Hành động của consumer |
|---|---|---|---|
| Chuẩn bị | 2.0 | Ghi nhận hợp đồng cũ, thiết kế và kiểm thử API mới | Cung cấp use case và ràng buộc thực tế |
| Expand | 2.1 | Phát hành API mới, giữ API cũ, bắt đầu deprecation | Có thể nâng thư viện mà chưa đổi source |
| Migrate | 2.2–2.x | Bổ sung hướng dẫn, xử lý feedback, báo tiến độ | Chuyển từng module và kiểm thử lại |
| Quyết định loại bỏ | Trước bản phát hành phá vỡ tương thích | Kiểm kê consumer, xác nhận chính sách và cảnh báo | Hoàn thành migration hoặc xin ngoại lệ |
| Contract | Một phiên bản major hoặc mốc được công bố | Loại bỏ API cũ theo chính sách hỗ trợ | Sử dụng API mới, cập nhật dependency và build |

Các con số phiên bản trên chỉ để minh họa. Việc xóa API cũ trong phiên bản major thường phù hợp với Semantic Versioning, nhưng không phải mọi dự án đều sử dụng SemVer, và việc tăng major không tự động khiến một thay đổi phá vỡ tương thích trở nên an toàn. Cần dựa vào chính sách phiên bản đã công bố, khả năng nâng cấp của consumer và hợp đồng hỗ trợ.

Có thể cần duy trì một nhánh bảo trì cho các consumer chưa nâng cấp, nhưng điều đó tạo thêm chi phí sửa lỗi và bảo mật. Phạm vi bảo trì cần rõ ràng về thời hạn, người phụ trách và loại bản vá được cung cấp.

## 9. Migration guide cần đưa ra phép thay thế cụ thể

Tài liệu migration tốt nhất cho người sử dụng là một chỉ dẫn có thể áp dụng ngay vào code hiện tại.

Ví dụ với API cũ:

~~~java
Customer customer = service.findCustomer(id);
process(customer);
~~~

Trong phương thức có thể ném CustomerNotFoundException, consumer có thể đang xử lý exception ở tầng gọi phía trên.

Cách chuyển dùng API mới:

~~~java
Optional<Customer> customer = service.findById(id);
if (customer.isEmpty()) {
    handleMissingCustomer(id);
    return;
}

process(customer.get());
~~~

Khi di chuyển, cần ghi rõ rằng trường hợp “không tìm thấy” đã chuyển từ checked exception sang Optional.empty. Điều này thay đổi trách nhiệm xử lý lỗi của consumer. Nếu consumer trước đây bắt exception ở một exception handler dùng chung, việc chuyển sang Optional có thể đòi hỏi cập nhật flow điều khiển ở tầng service hoặc controller.

Một bảng mapping có thể hữu ích:

| Hành vi của API cũ | Hành vi của API mới | Việc consumer cần làm |
|---|---|---|
| Trả về Customer khi tìm thấy | Optional chứa Customer | Lấy giá trị sau khi kiểm tra trạng thái |
| Ném CustomerNotFoundException khi thiếu | Optional.empty | Xử lý nhánh không tìm thấy |
| Ném lỗi backend khác | Giữ nguyên hoặc dùng lỗi domain được tài liệu hóa | Kiểm tra cơ chế catch, retry và logging |
| Nhận customerId theo quy tắc đã công bố | Giữ nguyên hoặc có quy tắc rõ hơn | Kiểm tra case null/blank và ký tự đặc biệt |

Nếu API mới thay đổi đơn vị đo, thứ tự phần tử, transaction hoặc khả năng bất đồng bộ, cần bổ sung ví dụ cho từng thay đổi ấy. Không nên ngụ ý thay thế 1:1 nếu hai API có hợp đồng hành vi khác nhau.

### 9.1. Công cụ hỗ trợ migration

Tùy quy mô dự án, có thể dùng:

- IDE quick fixes hoặc refactoring để đổi method và import.
- Static analysis để liệt kê nơi gọi API cũ.
- OpenRewrite hoặc công cụ rewrite tương tự cho thay đổi có quy tắc rõ và nhiều module.
- Consumer compile test để xác nhận code mới biên dịch.
- Integration test và contract test để kiểm tra ngữ nghĩa mới.

Automated refactoring thường xử lý tốt phép đổi tên hoặc đổi chữ ký đơn giản. Với thay đổi từ exception sang Optional, từ callback sang CompletableFuture hoặc thay đổi logic retry, cần kiểm tra luồng xử lý nghiệp vụ thay vì áp dụng rewrite máy móc.

## 10. Điều phối consumer chuyển đổi

Nhà cung cấp cần biết ai đang sử dụng API cũ. Với thư viện nội bộ, có thể dựa vào dependency graph, tìm kiếm source, báo cáo build và danh sách artifact đang triển khai. Với thư viện được phát hành bên ngoài, danh sách consumer có thể không đầy đủ.

Một danh sách consumer nên ghi:

| Trường | Ý nghĩa |
|---|---|
| Consumer | Repository, module hoặc ứng dụng đang sử dụng |
| Phiên bản thư viện | Đang dùng API cũ trong artifact nào |
| API cũ | Method, class hoặc cấu hình cần chuyển |
| Chủ sở hữu | Nhóm có quyền thay đổi consumer |
| Ràng buộc | JDK, framework, thời gian triển khai hoặc dependency |
| Trạng thái | Chưa bắt đầu, đang chuyển, đã kiểm thử, đã triển khai |
| Bằng chứng | Commit, build, test hoặc release xác nhận |
| Ngoại lệ | Lý do chưa nâng và thời hạn xử lý |

Trong giai đoạn chuyển tiếp, nên ưu tiên consumer quan trọng, consumer có lịch phát hành chậm và consumer tự implement SPI. Việc chuyển toàn bộ consumer nội bộ trước khi xóa API cũ giúp giảm rủi ro, nhưng vẫn phải tính đến consumer bên ngoài mà nhóm chưa quan sát được.

Nếu có đo lường mức sử dụng API cũ, cần chọn cách phù hợp: static usage analysis, build warnings, telemetry có kiểm soát hoặc thông tin phiên bản từ consumer. Không nên đưa logging vào mọi lần gọi API trong đường nóng gây giảm hiệu năng hoặc thu thập dữ liệu không cần thiết. Số lượt gọi runtime cũng không chứng minh đã tìm được mọi consumer, vì nhiều code path chỉ chạy theo sự kiện hiếm.

## 11. Tạo tín hiệu để consumer tự nhận biết API cũ

Sau khi đánh dấu Deprecated, IDE và compiler có thể hiển thị cảnh báo khi consumer sử dụng API. Trong dự án Java, có thể yêu cầu javac hiển thị thêm chi tiết deprecation:

~~~bash
javac -Xlint:deprecation -cp library.jar Consumer.java
~~~

Với Gradle JavaCompile, có thể thêm cấu hình:

~~~kotlin
tasks.withType<JavaCompile>().configureEach {
    options.compilerArgs.add("-Xlint:deprecation")
}
~~~

Đây là ví dụ Kotlin DSL. Compiler có thể phát ra warning tại những vị trí gọi API deprecated. Nếu nhóm muốn dùng warning làm quality gate, cần quy định rõ phạm vi và thời gian áp dụng. Không nên bật chế độ coi mọi warning là lỗi ngay khi deprecate API nếu consumer chưa có khả năng chuyển đổi theo chính sách hỗ trợ đã công bố.

Một số ngoại lệ tạm thời có thể cần @SuppressWarnings("deprecation") trong adapter hoặc mã chuyển tiếp. Nếu sử dụng suppression, nên giới hạn phạm vi, kèm lý do, owner và thời gian rà soát để nó không che khuất các lời gọi API cũ mới phát sinh ở nơi khác.

## 12. Kiểm thử trong thời gian hai API cùng tồn tại

Có hai API thì nhà cung cấp cần bảo vệ cả hai hợp đồng cho đến khi ngừng hỗ trợ API cũ. Không đủ để chỉ kiểm tra API mới.

### 12.1. Kiểm thử hành vi của API cũ

Các test nên xác minh những hành vi đã công bố:

- Dữ liệu hợp lệ vẫn trả kết quả đúng.
- Trường hợp không tìm thấy vẫn trả null hoặc ném exception đúng loại như trước.
- Input null, blank hoặc invalid vẫn tuân theo hợp đồng.
- Lỗi backend vẫn được truyền hoặc wrap theo cách đã cam kết.
- Side effect, transaction và concurrency không thay đổi ngoài dự kiến.

### 12.2. Kiểm thử hành vi của API mới

Test cần bao phủ cả kết quả có dữ liệu và không có dữ liệu, lỗi backend, điều kiện biên và quy tắc xử lý mới được công bố.

### 12.3. Kiểm thử tương ứng giữa hai API

Với những phần hành vi được kỳ vọng tương đương, dùng cùng bộ dữ liệu để xác nhận:

~~~java
@Test
void bothApisReturnSameExistingCustomer() throws Exception {
    Customer legacy = service.findCustomer("C-42");
    Customer current = service.findById("C-42").orElseThrow();

    assertEquals(legacy.getId(), current.getId());
}
~~~

Ví dụ trên giả định môi trường test dùng JUnit và Optional.orElseThrow() được hỗ trợ ở baseline Java của dự án. Các class và fixture là minh họa. Khi không tìm thấy, test riêng cần kiểm tra API cũ ném CustomerNotFoundException và API mới trả Optional.empty.

Không nên yêu cầu hai API giống nhau ở mọi điểm nếu API mới được thiết kế để thay đổi ngữ nghĩa; thay vào đó, mô tả rõ phần nào tương đương và phần nào thay đổi có chủ đích.

### 12.4. Kiểm thử consumer cũ

Một trường hợp quan trọng là dùng consumer đã biên dịch với thư viện cũ rồi chạy nó với bản thư viện mới. Điều này giúp phát hiện linkage error, thay đổi bytecode, dependency hoặc hành vi mà việc chỉ biên dịch test mới không nhìn thấy.

Đồng thời cần biên dịch lại một số consumer cũ trên thư viện mới để phát hiện source incompatibility do overload, default method, interface hoặc generic type.

## 13. Những yếu tố có thể làm API mới không sử dụng được

API mới chỉ hữu ích khi consumer mục tiêu có thể tiếp cận và chạy nó. Trước khi công bố, cần xác định:

**Baseline Java:** Optional có từ Java 8; dạng @Deprecated(since=..., forRemoval=...) có từ Java 9. Nếu thư viện hỗ trợ Java 8, cú pháp và API được dùng trong implementation cần tương thích với môi trường biên dịch đó hoặc có cấu hình --release phù hợp.

**Dependency exposure:** nếu method mới trả về kiểu từ một thư viện ngoài, consumer có thể phải nhận dependency đó trên compile classpath. Điều này tăng coupling và có thể tạo xung đột phiên bản.

**Module boundary:** nếu sử dụng JPMS, kiểu và package của API mới phải được export phù hợp. Một method public trong package không được export chưa chắc là API có thể dùng từ module khác.

**Serialization và giao thức:** nếu API mới đổi DTO, enum, record, JSON field hoặc tên cấu hình, cần kiểm tra khả năng trao đổi dữ liệu với consumer cũ. Tương thích Java source không bảo đảm tương thích wire format.

**Reflection và code generation:** framework, mapper, dependency injection, annotation processor hoặc proxy có thể phụ thuộc vào constructor, annotation hoặc tên method cũ. Các consumer kiểu này không nhất thiết xuất hiện như lời gọi trực tiếp trong source.

**Tên và overload:** tên API mới cần rõ nghĩa; tránh overload mơ hồ hoặc tên tạo xung đột với method mà subclass của consumer đã khai báo.

**API phụ thuộc trạng thái:** nếu phiên bản mới chỉ chạy được khi dữ liệu đã migration, phải phối hợp schema và rollout. Không thể chỉ thêm method rồi cho rằng consumer có thể nâng cấp độc lập.

## 14. Mở rộng quy tắc cho cấu hình và API dịch vụ

Nguyên tắc thêm trước, bỏ sau không chỉ dùng với method Java.

### 14.1. Cấu hình

Giả sử ứng dụng đang dùng thuộc tính:

~~~yaml
client:
  timeout-ms: 3000
~~~

Nhóm muốn dùng dạng thời lượng rõ ràng:

~~~yaml
client:
  timeout: 3s
~~~

Trong giai đoạn chuyển tiếp, có thể hỗ trợ cả hai tên, định nghĩa thứ tự ưu tiên khi cả hai cùng tồn tại, và cảnh báo khi cấu hình cũ được dùng. Nếu không quy định precedence, những deployment có cả timeout-ms và timeout có thể có hành vi khó dự đoán.

Khi ngừng hỗ trợ timeout-ms, cần cập nhật tài liệu, cấu hình mẫu và các consumer trước khi xóa parser alias.

### 14.2. REST API

Một endpoint mới có thể được triển khai song song với endpoint cũ. Ví dụ, thay /v1/customers/{id} bằng /v2/customers/{id} khi schema và semantics thay đổi đáng kể. Cần giữ route cũ theo chính sách hỗ trợ, công bố chuyển đổi client và kiểm thử cả hai phiên bản.

Không nên chỉ tạo đường dẫn mới rồi dùng một controller nội bộ để trả dữ liệu khác hợp đồng của endpoint cũ. Nếu cả hai API dựa trên cùng service, adapter ở mỗi endpoint vẫn phải đảm bảo status code, header, schema và error response riêng.

### 14.3. Event và schema dữ liệu

Với producer/consumer bất đồng bộ, việc bổ sung trường mới thường cần đánh giá compatibility rules của schema và mức chấp nhận của consumer. Producer, consumer cũ và mới có thể chạy cùng lúc. Tùy hệ thống, có thể cần dual-read, dual-write hoặc event version mới; không nên xóa trường cũ trước khi consumer đã sẵn sàng.

Những ví dụ này cho thấy “thêm API mới” thực chất là quản lý hai hợp đồng trong giai đoạn chuyển tiếp.

## 15. Khi nào được ngừng hỗ trợ API cũ?

Một API cũ chỉ nên được đưa ra khỏi phạm vi hỗ trợ khi đã có quyết định phù hợp với chính sách phát hành và rủi ro consumer.

Các câu hỏi cần được trả lời:

1. API thay thế có đủ tính năng và tài liệu cho những use case đã được hỗ trợ không?
2. Các consumer thuộc quyền kiểm soát đã nâng cấp và triển khai thành công chưa?
3. Có consumer bên ngoài hoặc downstream library nào vẫn dùng API cũ không?
4. Mốc deprecation đã được công bố và thời gian chuyển tiếp đã phù hợp cam kết chưa?
5. Có phương án rollback hoặc nhánh bảo trì nếu consumer chưa thể nâng cấp không?
6. Bản phát hành loại bỏ sẽ làm thay đổi source, binary, behavior, cấu hình hoặc data như thế nào?
7. Test compatibility có bao phủ các consumer quan trọng và trường hợp lỗi chưa?

Ngừng hỗ trợ có thể có nhiều hình thức: dừng phát triển tính năng mới cho API cũ, chỉ sửa lỗi bảo mật, tuyên bố hết hạn hỗ trợ, hoặc xóa API khỏi artifact. Cần nói rõ từng mốc, vì **deprecated**, **unsupported** và **removed** là những trạng thái khác nhau.

Khi thật sự xóa một method hoặc class công khai, consumer chưa chuyển đổi có thể bị lỗi biên dịch hoặc NoSuchMethodError/NoClassDefFoundError ở runtime. Mốc loại bỏ phải được thể hiện trong release notes và migration guide của phiên bản phát hành tương ứng.

## 16. Các sai lầm thường gặp

**Xóa API ngay khi thêm API mới.** Không cho consumer thời gian chuyển đổi, đặc biệt khi nhiều ứng dụng có lịch phát hành khác nhau.

**Giữ API cũ nhưng thay đổi hành vi.** Adapter trả kết quả khác, đổi exception, bỏ transaction hoặc thay đổi xử lý null sẽ phá vỡ hợp đồng cũ dù method vẫn tồn tại.

**Chỉ thêm method trừu tượng vào interface.** Người tự implement interface có thể bị buộc sửa source hoặc gặp lỗi runtime; cần chọn vị trí mở rộng phù hợp.

**Đánh dấu Deprecated mà không có hướng dẫn.** Compiler warning không giải thích logic chuyển đổi hoặc khác biệt hành vi cho consumer.

**Dùng forRemoval=true như một lịch xóa.** Annotation thể hiện ý định, không nói rõ phiên bản hay ngày; thông báo phải có chính sách phát hành riêng.

**Giữ hai implementation nghiệp vụ độc lập.** Hai nhánh logic có thể sai lệch theo thời gian. Nên dùng implementation chung khi hai hợp đồng cho phép.

**Đổi exception thành Optional.empty cho mọi trường hợp.** Lỗi hạ tầng và “không tìm thấy” có ngữ nghĩa khác nhau; gộp chúng làm mất tín hiệu vận hành.

**Chỉ thử nghiệm API mới.** Trong giai đoạn chuyển tiếp, consumer cũ vẫn cần được bảo vệ.

**Cho rằng một phiên bản major đủ để xóa tùy ý.** Chính sách hỗ trợ, downstream và khả năng thực tế của consumer vẫn phải được đánh giá.

## 17. Quy trình thực hiện trong một đợt Java compatibility migration

Có thể tổ chức công việc theo các bước sau:

### Bước 1: Kiểm kê hợp đồng và consumer

Xác định API cũ, các cách sử dụng thực tế và phiên bản Java/Gradle/framework mà consumer đang dùng. Phân biệt caller, implementor và những consumer sử dụng reflection hoặc cấu hình.

### Bước 2: Thiết kế API thay thế

Mô tả mục tiêu, kiểu dữ liệu, input, output, exception, tính bất biến, hiệu ứng phụ và semantic differences. Chọn tên mới rõ ràng, tránh overload mơ hồ và dependency không cần thiết.

### Bước 3: Thêm API mới theo cách tương thích

Xuất bản API mới, giữ API cũ và thiết kế adapter/implementation chung. Với interface hoặc SPI, đánh giá source và binary compatibility riêng cho implementor.

### Bước 4: Công bố deprecation có hướng dẫn

Dùng annotation và Javadoc phù hợp baseline Java; ghi version bắt đầu deprecated, API thay thế, ví dụ trước/sau và thời hạn hỗ trợ nếu đã có quyết định.

### Bước 5: Xác minh hai hợp đồng

Biên dịch consumer mới và cũ, chạy test trên JDK tối thiểu được hỗ trợ, kiểm tra bytecode consumer cũ với artifact mới và kiểm tra hành vi lỗi/edge case.

### Bước 6: Chuyển đổi consumer theo lộ trình

Ưu tiên consumer quan trọng, cập nhật dependency và source, theo dõi trạng thái triển khai. Ghi nhận ngoại lệ, chủ sở hữu và bước xử lý khi chưa thể chuyển.

### Bước 7: Đánh giá điều kiện ngừng hỗ trợ

Xác nhận chính sách versioning, cam kết bảo trì và bằng chứng consumer migration. Thông báo phiên bản cuối còn hỗ trợ API cũ và phiên bản dự kiến loại bỏ nếu được quyết định.

### Bước 8: Loại bỏ có kiểm soát và giám sát

Thực hiện xóa API chỉ tại mốc phát hành phù hợp; chạy test và kiểm tra hướng dẫn migration, dependency, release notes. Theo dõi lỗi compile/runtime từ consumer sau phát hành và duy trì kênh xử lý sự cố phù hợp.

## 18. Checklist cho người phát hành thư viện

- [ ] Đã mô tả vấn đề của API cũ và lợi ích của API thay thế.
- [ ] Đã phân biệt hợp đồng được hỗ trợ với chi tiết triển khai.
- [ ] Đã giữ hành vi của API cũ trong thời gian cam kết hỗ trợ.
- [ ] Đã xét source, binary và behavioral compatibility khi bổ sung API.
- [ ] Đã kiểm tra interface implementor, overload, generic type, subclass và reflection.
- [ ] Đã chọn baseline Java và bảo đảm API mới sử dụng được trên các JDK được hỗ trợ.
- [ ] Đã bổ sung Javadoc deprecated, annotation và migration guide.
- [ ] Đã kiểm thử API mới, API cũ và consumer đã biên dịch trước đó.
- [ ] Đã thông báo lộ trình chuyển đổi, owner và chính sách phiên bản.
- [ ] Đã xác định điều kiện thực tế trước khi ngừng hỗ trợ hoặc xóa API cũ.

## Kết luận

Thêm API thay thế trước khi ngừng hỗ trợ API cũ là cách tiến hóa hợp đồng có kiểm soát. Nhà cung cấp mở đường cho consumer dùng thiết kế mới, vẫn giữ hợp đồng cũ trong giai đoạn chuyển tiếp, sau đó hướng dẫn nâng cấp và xác minh mức độ sẵn sàng trước khi loại bỏ. Cốt lõi của chiến lược không nằm ở annotation Deprecated, mà ở việc hiểu rõ consumer, giữ tương thích có cam kết, xây dựng adapter đúng hành vi, kiểm thử cả phiên bản cũ và mới, và công bố một lộ trình phù hợp với vòng đời hỗ trợ của thư viện.
