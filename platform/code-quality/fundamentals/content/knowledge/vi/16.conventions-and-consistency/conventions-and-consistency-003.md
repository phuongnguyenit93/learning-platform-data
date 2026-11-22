# Tính nhất quán trong một tệp, mô-đun và nhóm

> **Chương:** Quy ước và nhất quán  
> **Học phần:** Code Quality Fundamentals (`CODE_QUALITY_FUNDAMENTALS`) — hiểu những thuộc tính quyết định mã nguồn có đáng tin cậy, dễ hiểu và dễ thay đổi hay không.

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích **tính nhất quán (consistency)** giúp người đọc dự đoán cấu trúc và hành vi của mã nguồn như thế nào, đồng thời phân biệt nó với việc ép mọi đoạn mã phải giống hệt nhau.
2. Nhận diện sự nhất quán ở ba phạm vi: **trong một tệp**, **giữa các thành phần của mô-đun** và **trong quy trình làm việc của nhóm**.
3. Phân biệt quy ước **hình thức** (format, tên gọi, thứ tự sắp xếp) với quy ước **ngữ nghĩa** (đơn vị dữ liệu, xử lý lỗi, trạng thái vắng mặt, hành vi API).
4. Áp dụng các quy tắc Java để làm rõ kiểu dữ liệu, tên phương thức, hợp đồng trả về, tác dụng phụ và bài kiểm thử mà không vô tình thay đổi nghiệp vụ.
5. Đề xuất cơ chế thiết lập, thực thi và cải tiến quy ước bằng **ví dụ chuẩn, công cụ tự động, code review và quyết định có ghi nhận**.
6. Lập kế hoạch xử lý khu vực mã thiếu nhất quán theo thứ tự ưu tiên, nhận diện khi nào “đồng bộ phong cách” lại gây rủi ro tương thích hoặc làm giảm khả năng đọc.

## 1. Vì sao nhất quán là một thuộc tính của chất lượng mã?

Hãy tưởng tượng bạn mới tiếp nhận một dự án Java. Trong cùng mô-đun đặt hàng:

- Hàm `findOrder` trả `null` nếu không thấy dữ liệu.
- Hàm `getCustomer` trả `Optional.empty()` trong tình huống tương tự.
- Hàm `loadInvoice` ném exception khi bản ghi không tồn tại.
- Có nơi biểu diễn tiền bằng `long amountVnd`, nơi khác bằng `double amount`, và nơi thứ ba dùng chuỗi `"250000"` mà không giải thích đơn vị.
- Một controller trả lỗi theo `{"code":"..."}`, controller khác trả chuỗi tự do.
- Có file đặt tên method bằng động từ rõ ràng, file khác dùng `process()` hoặc `handle()` cho nhiều hành vi không liên quan.

Mỗi lựa chọn riêng lẻ có thể có lý do. Nhưng khi không có **quy tắc giải thích vì sao khác nhau**, người đọc phải suy lại hợp đồng của từng hàm. Một thay đổi nhỏ đòi hỏi nhiều lần kiểm tra, tăng nguy cơ đưa vào cách xử lý không tương thích.

**Tính nhất quán** nghĩa là những trường hợp giống nhau về mục đích và ngữ cảnh được biểu diễn, xử lý và kiểm chứng theo cách **có thể dự đoán**, còn sự khác biệt có ý nghĩa được diễn đạt **tường minh**.

Nhất quán có giá trị vì giúp giảm chi phí nhận thức:

- **Dễ đọc:** người mới biết tên, vị trí và cấu trúc dự kiến của phần cần tìm.
- **Dễ thay đổi:** thay một quy tắc ở đúng chỗ, không phải đoán từng phương thức dùng quy ước nào.
- **Đáng tin cậy:** hợp đồng lỗi, dữ liệu và quyền không bị diễn giải khác nhau do thói quen viết mã.
- **Dễ kiểm thử:** nhóm thống nhất nên kiểm tra ranh giới, trường hợp biên và cách đặt tên test ra sao.
- **Dễ cộng tác:** code review tập trung vào hành vi và thiết kế thay vì tranh luận lặp lại về dấu cách, import hay cách viết tên.

Điều quan trọng: **nhất quán không tự đồng nghĩa với đúng**. Nếu cả dự án cùng bỏ qua `InterruptedException` hoặc cùng trả `null` khi database lỗi, đó là một sự nhất quán **sai** cần thay đổi. Quy ước tốt phải phục vụ tính đúng đắn, khả năng đọc và khả năng tiến hóa, không chỉ tạo vẻ đồng đều.

## 2. Ba phạm vi: tệp, mô-đun và nhóm

| Phạm vi | Câu hỏi quan trọng | Ví dụ quy ước | Rủi ro khi thiếu nhất quán |
| --- | --- | --- | --- |
| **Một tệp** | Những phần gần nhau có cùng cách biểu diễn ý nghĩa và tổ chức không? | Tên biến, độ dài biểu thức, nhánh lỗi, thứ tự hàm, sử dụng bất biến | Người đọc phải đổi cách hiểu giữa các đoạn trong cùng lớp |
| **Một mô-đun** | Các thành phần cùng phục vụ một năng lực có tuân hợp đồng và ranh giới chung không? | Tiền/đơn vị, lỗi, `Optional`, package, DTO, transaction, chính sách truy vấn | Tích hợp sai, dữ liệu không tương thích, quy tắc rải rác |
| **Một nhóm** | Mọi người biết quy tắc đang áp dụng, lý do, công cụ và cách thay đổi nó không? | Formatter, review checklist, quyết định thiết kế, test conventions, kế hoạch migration | PR tranh luận lại chuyện cũ, mỗi người sửa theo ý riêng |

Ba phạm vi liên quan nhưng **không đồng nhất**. Một lớp có thể được format hoàn hảo mà vẫn trả lỗi trái hợp đồng của mô-đun. Một mô-đun có API nhất quán nhưng cách review của nhóm thiếu rõ ràng khiến lỗi mới tiếp tục lọt vào.

### Nhất quán không có nghĩa đồng phục tuyệt đối

Một DTO bất biến, một adapter JDBC, một state machine và một lớp điều phối HTTP có **trách nhiệm khác nhau**. Không nên ép tất cả chúng có cùng số phương thức, cấu trúc constructor hay cách dùng exception. Thay vào đó, hãy hỏi:

> “Khi hai phần làm **cùng loại trách nhiệm**, người đọc có thể dự đoán cách chúng được viết và hoạt động không? Khi chúng khác loại, ranh giới khác biệt có dễ nhận biết không?”

Nếu hai quy ước khác nhau tồn tại do **hai hợp đồng khác nhau**, hãy ghi rõ phạm vi áp dụng. Sự khác biệt có chủ đích không phải là thiếu nhất quán.

## 3. Nhất quán trong một tệp: xây dựng cách đọc có thể dự đoán

Một tệp Java thường gồm package/import, khai báo kiểu, các trường, constructor, phương thức công khai, hàm phụ trợ. Thứ tự cụ thể nên theo chuẩn đã chọn, nhưng quan trọng là người đọc nhận ra **cấu trúc và trách nhiệm**.

### 3.1. Tên có cùng cách biểu diễn ý nghĩa

Ví dụ trong một lớp tính giá:

~~~java
long totalVnd = 0L;
long taxVnd = 0L;
long discountVnd = 0L;
long amountDueVnd = totalVnd + taxVnd - discountVnd;
~~~

Các tên cùng đơn vị `Vnd` giúp người đọc không phải đoán giữa `total`, `price` và `money`. Nếu một biến khác là phần trăm thuế, nên đặt `taxRate` thay vì `taxVnd` vì **ý nghĩa khác nhau**.

Với tên phương thức, nên có quy tắc về **động từ và mức tác dụng phụ**. Ví dụ:

- `calculateAmountDue(...)`: gợi ý trả giá trị được tính, không tự gửi thanh toán.
- `saveOrder(...)`: thể hiện hành động ghi dữ liệu.
- `findById(...)`: cần hợp đồng rõ về kết quả vắng mặt.
- `requireOrder(...)`: có thể dùng cho truy xuất bắt buộc và ném lỗi nếu không có, nếu đó là quy ước đã được định nghĩa.

Tên không phải bằng chứng tuyệt đối về hành vi; chúng cần **khớp implementation và hợp đồng**. Tránh thay tên chỉ để trông đẹp khi API công khai hoặc mã phía ngoài đã phụ thuộc tên cũ.

### 3.2. Thống nhất cách xử lý đầu vào và đường lỗi

Xét hai phương thức trong cùng một lớp:

~~~java
String displayName(Customer customer) {
    if (customer == null) {
        return "";
    }
    return customer.name();
}

String email(Customer customer) {
    return customer.email(); // Có thể NPE nếu customer null.
}
~~~

Nếu `customer` là đầu vào bắt buộc ở cả hai, hành vi khác nhau với `null` khiến caller phải nhớ từng ngoại lệ. Nếu khác biệt thật sự được yêu cầu (ví dụ tên dùng để hiển thị dự phòng, email bắt buộc để gửi thông báo), hãy tách mục đích và ghi rõ:

~~~java
import java.util.Objects;

static String displayNameOrFallback(Customer customer) {
    if (customer == null || customer.name() == null) {
        return "Khách hàng";
    }
    return customer.name();
}

static String requiredEmail(Customer customer) {
    Objects.requireNonNull(customer, "customer");
    return Objects.requireNonNull(
            customer.email(), "customer email");
}
~~~

Đoạn trên giả định `Customer` có `name()` và `email()` trả `String`. Đây là **hai hợp đồng khác nhau có tên rõ ràng**, không phải lý do để dùng một chính sách null cho mọi trường.

### 3.3. Một biến không nên đổi ý nghĩa ngầm giữa các dòng

~~~java
long amount = subtotalVnd;
amount = amount * 90 / 100; // Sau giảm VIP?
amount -= couponVnd;       // Sau mã?
~~~

Mã có thể chạy đúng theo một chính sách, nhưng tên `amount` không giúp nhận biết bước nào đã áp dụng. Các giá trị trung gian có tên phản ánh giai đoạn thường dễ đọc hơn:

~~~java
long subtotalVnd = sumLines(lines);
long afterVipVnd = applyVipDiscount(subtotalVnd, isVip);
long amountDueVnd = applyCoupon(afterVipVnd, couponVnd);
~~~

`sumLines`, `applyVipDiscount` và `applyCoupon` là các hàm minh họa chưa được định nghĩa ở đây. Chúng thể hiện cách diễn đạt **các bước khác nhau bằng tên nhất quán theo đơn vị**. Việc tách nhỏ chỉ có ích nếu mỗi hàm có trách nhiệm, hợp đồng và test đủ rõ, không làm người đọc phải nhảy qua quá nhiều lớp.

### 3.4. Format hỗ trợ đọc, không thay thế ý nghĩa

Dấu cách, xuống dòng, import và vị trí dấu ngoặc giúp mã dễ quét mắt. Nên dùng một formatter được chọn chung; tránh mỗi người tự viết lại style toàn file khi chỉ sửa một điều kiện.

Nhưng một phương thức được format chuẩn vẫn có thể sai về quyền, tràn số hoặc đơn vị tiền. **Format thống nhất là nền tảng để dễ đọc và review, không phải chứng chỉ về tính đúng đắn.**

## 4. Nhất quán trong một mô-đun: hợp đồng hành vi quan trọng hơn vẻ ngoài

Trong mô-đun, những lựa chọn quan trọng nhất thường là **đơn vị dữ liệu, lỗi, vắng mặt, trạng thái và ranh giới tác dụng phụ**. Chúng quyết định các thành phần có hiểu nhau hay không.

### 4.1. Quy ước đơn vị và kiểu dữ liệu

Một service dùng `long amountDueVnd`, service khác dùng `double amount`, controller gửi `"amount":"250.00"`: khác biệt này không thể giải quyết chỉ bằng formatter.

Nếu mô-đun xử lý VND nguyên, có thể quy định:

- Biến và field giữ số nguyên bằng `long` mang hậu tố `Vnd`.
- Các phép cộng/nhân có thể tràn phải có cách kiểm soát.
- Các mức giảm và quy tắc làm tròn phải được mô tả riêng, không tự suy từ kiểu dữ liệu.
- DTO công khai phải nêu rõ đơn vị và phạm vi số; không tự chuyển sang chuỗi khi gặp số lớn mà không đổi hợp đồng.

Nếu mô-đun nhiều tiền tệ, có thể cần một kiểu `Money` chứa currency, số lượng và quy tắc số thập phân thích hợp. **Không nên cưỡng ép `long Vnd` lên tính năng nhiều currency chỉ để đồng nhất cú pháp**.

### 4.2. Quy ước khi không có dữ liệu hoặc có lỗi

Một hợp đồng có thể định nghĩa:

| Tình huống | Hướng biểu diễn trong mô-đun giả định | Vì sao |
| --- | --- | --- |
| Tra cứu thành công nhưng không có bản ghi | `Optional.empty()` ở repository query | Vắng dữ liệu là kết quả hợp lệ |
| Không kết nối được DB | Exception hoặc kiểu thất bại rõ | Không được giả vờ “không tìm thấy” |
| Danh sách hợp lệ không có phần tử | `List.of()` | Có kết quả danh sách rỗng |
| Dữ liệu bắt buộc bị thiếu | Lỗi validation rõ ràng | `null` không phải dữ liệu hợp lệ |
| API nhận PATCH không gửi trường | Giữ nguyên (nếu hợp đồng định nghĩa) | Khác với gửi `null` để xóa |

Đây là một **quy ước minh họa**, cần điều chỉnh theo module và framework thực. Quan trọng là các hàm cùng loại không trả `null`, empty và exception một cách ngẫu nhiên cho cùng tình huống.

### 4.3. Quy ước lỗi qua các tầng

Một mô-đun có thể phân biệt:

- **Lỗi dữ liệu vào:** yêu cầu vi phạm hợp đồng.
- **Không tìm thấy:** tra cứu thành công nhưng tài nguyên không tồn tại.
- **Không có quyền:** chủ thể không được phép thực hiện hành động trên tài nguyên.
- **Xung đột trạng thái:** thao tác không hợp lệ với trạng thái hiện tại hoặc có thay đổi đồng thời.
- **Sự cố phụ thuộc:** database, mạng hoặc dịch vụ ngoài không sẵn sàng.

Tầng domain nên diễn đạt lỗi nghiệp vụ; ranh giới HTTP ánh xạ chúng sang status/error schema đã được công bố. Không nên rải điều kiện `return null` ở service này và `throw RuntimeException("bad")` ở service khác chỉ vì tác giả khác nhau.

**Lưu ý:** HTTP 401, 403, 404, 409, 422 và 5xx có ý nghĩa khác nhau; việc dùng chính xác mã nào phải theo hợp đồng công khai và chính sách không tiết lộ thông tin. “Nhất quán” không đồng nghĩa biến tất cả lỗi thành một mã HTTP.

### 4.4. Quy ước về transaction và tác dụng phụ

Trong cùng mô-đun đặt hàng, nếu có phương thức `createOrder` ghi DB rồi gửi email, và `updateOrder` gửi email trước khi commit DB, đội ngũ cần hiểu tại sao thứ tự khác nhau.

Những câu hỏi cần thống nhất:

1. Ai sở hữu transaction; trường hợp nào được rollback?
2. Thao tác ngoài DB (thanh toán, gửi email, phát event) có retry/idempotency không?
3. Khi hệ thống ngoài timeout nhưng đã xử lý, trạng thái nghiệp vụ được đối soát thế nào?
4. Log và audit ghi theo chính sách chung nào?
5. Tác vụ chạy nền có cùng quy tắc ownership và kiểm tra quyền không?

Dùng cùng thứ tự thao tác chỉ vì đồng đều có thể **sai nghiệp vụ**. Cần ghi **lý do khác biệt** nếu các workflow có ranh giới commit hoặc tính nhất quán khác nhau.

## 5. Ví dụ Java: cùng một ý nghĩa, ba hợp đồng trái nhau

Giả sử trong cùng mô-đun có ba phương thức truy vấn đơn hàng:

~~~java
// Cả ba cùng muốn tìm một đơn hàng theo ID, nhưng hợp đồng mơ hồ.
Order getOrder(long id) {
    return repository.find(id).orElse(null);
}

Order loadOrder(long id) {
    return repository.find(id)
            .orElseThrow(() -> new RuntimeException("missing"));
}

Optional<Order> lookupOrder(long id) {
    try {
        return repository.find(id);
    } catch (RuntimeException ignored) {
        return Optional.empty(); // Lỗi bị giấu thành "không thấy".
    }
}
~~~

`repository`, `Order` và các import chưa được định nghĩa trong đoạn phản ví dụ; mục tiêu là so sánh **ba cách truyền thông tin**. Đặc biệt, phương thức thứ ba có thể khiến timeout database bị hiểu thành bản ghi không tồn tại.

### 5.1. Chọn hợp đồng nhất quán ở ranh giới mô-đun

Giả định mô-đun quy định: `findById` dùng `Optional` khi truy vấn thành công nhưng không có dữ liệu; sự cố DB được truyền bằng lỗi tương ứng; `requireById` dùng cho ca cần bản ghi bắt buộc.

~~~java
import java.util.Objects;
import java.util.Optional;

record Order(long id, String customerId) {}

interface OrderRepository {
    Optional<Order> findById(long id);
}

final class OrderQueries {
    private final OrderRepository repository;

    OrderQueries(OrderRepository repository) {
        this.repository = Objects.requireNonNull(repository);
    }

    Optional<Order> findById(long id) {
        return repository.findById(id);
    }

    Order requireById(long id) {
        return findById(id)
                .orElseThrow(() -> new OrderNotFoundException(id));
    }
}

final class OrderNotFoundException extends RuntimeException {
    OrderNotFoundException(long id) {
        super("Order not found: " + id);
    }
}
~~~

Trong ví dụ này:

- Cùng một tình huống không thấy dữ liệu được thể hiện **nhất quán** bằng `Optional.empty()` tại API truy vấn tùy chọn.
- Tình huống “bắt buộc phải có” có **tên và exception riêng**, thay vì mỗi caller tự `get()` rồi gặp `NoSuchElementException` thiếu ngữ cảnh.
- Lỗi database không bị biến thành empty. Hợp đồng repository phải được thực thi đúng ở implementation.
- Hai phương thức khác nhau vì **mục đích caller khác nhau**, không phải sự tùy tiện về style.

Khi xuất exception ra API công khai, không nên tự lộ chi tiết nhận diện, dữ liệu nhạy cảm hoặc thông tin DB trong error response. Tầng HTTP nên ánh xạ lỗi theo chính sách phân quyền/không tiết lộ sự tồn tại tài nguyên.

### 5.2. Thống nhất hành vi không đồng nghĩa gộp mọi method

Một hàm `searchOrders` trả danh sách rỗng nếu không có kết quả là hợp lý; không cần ép nó trả `Optional<List<Order>>` nếu không có trạng thái vắng mặt riêng cần phân biệt.

Một hàm `createOrder` có thể trả `OrderCreated` hoặc ID mới, đồng thời ném lỗi nghiệp vụ khi dữ liệu không hợp lệ. Cố khiến tất cả method trả `Optional` chỉ để cùng kiểu sẽ làm mã **kém rõ nghĩa**.

**Nguyên tắc:** các lựa chọn giống nhau cho **trường hợp giống nhau**, sự khác biệt cho **ngữ nghĩa khác nhau** được làm rõ bằng kiểu và tên.

## 6. Tên, package và ranh giới sở hữu ở cấp mô-đun

Nhất quán về tên và vị trí giúp người mới biết tìm code ở đâu:

~~~text
orders/
  domain/
    Order.java
    OrderPricing.java
  application/
    CheckoutService.java
    OrderQueries.java
  infrastructure/
    JdbcOrderRepository.java
  api/
    OrderController.java
    OrderResponse.java
~~~

Đây là **một sơ đồ minh họa**, không phải cấu trúc bắt buộc. Một mô-đun nhỏ có thể đơn giản hơn; mô-đun lớn có thể tổ chức theo feature dọc thay vì theo layer. Mục tiêu là **trách nhiệm có chỗ ở nhất quán**.

Đặt câu hỏi:

- DTO HTTP nằm gần controller hay domain? Có quy ước chuyển đổi rõ không?
- Repository interface biểu diễn nhu cầu domain/application hay bị lộ mọi chi tiết của DB?
- Chính sách tính giá được tái sử dụng từ một nơi hay sao chép trong nhiều handler?
- Những package tên `common`, `helpers` có mục đích đủ hẹp không?
- Nơi định nghĩa lỗi, logging và validation có được người mới tìm thấy nhanh không?

Không nên tạo hàng loạt package rỗng chỉ để trông giống kiến trúc mẫu. **Cấu trúc nhất quán phải đi cùng độ gắn kết và quan hệ phụ thuộc hợp lý.**

## 7. Nhất quán trong hợp đồng API và dữ liệu bên ngoài

Sự nhất quán nội bộ có thể thay đổi dần; hợp đồng công khai có **consumer độc lập** nên cần thận trọng hơn.

Giả sử API v1 trả:

~~~json
{
  "orderId": "OD-42",
  "totalVnd": 250000,
  "status": "PAID"
}
~~~

Nhóm muốn thống nhất tên `amountDueVnd` ở các endpoint mới. **Không được đổi tên JSON rồi xóa `totalVnd` ngay** chỉ vì chuẩn đặt tên mới đẹp hơn. Client cũ có thể dựa vào trường này.

Một lộ trình có thể là:

1. Xác định `totalVnd` đang có **ý nghĩa chính xác** gì (trước hay sau giảm, đơn vị ra sao).
2. Thêm `amountDueVnd` trong giai đoạn mở rộng, giữ `totalVnd` cùng giá trị theo hợp đồng.
3. Cập nhật tài liệu và contract tests, thông báo tên mới và lộ trình ngừng hỗ trợ tên cũ.
4. Di chuyển consumer, kiểm tra cả provider mới/client cũ và provider cũ/client mới khi rollout song song.
5. Chỉ bỏ trường cũ theo chính sách phiên bản/deprecation đã được thống nhất.

**Tính nhất quán nội bộ không được phá vỡ tương thích bên ngoài một cách âm thầm.** Nhiều khi một adapter chấp nhận tên cũ là lựa chọn thực tế tốt hơn việc buộc mọi client nâng cấp cùng ngày.

### “Thống nhất” không có nghĩa tự đổi đơn vị

Hai API dùng `amount` nhưng một bên là VND nguyên và một bên là cent của USD **không phải cùng một kiểu nghĩa**. Thay đổi tên mà không làm rõ currency/scale chỉ che vấn đề. Trước khi thống nhất format, hãy thống nhất **khái niệm nghiệp vụ**.

## 8. Quy ước kiểm thử cũng là một phần của thiết kế

Mã sản phẩm cùng một kiểu hợp đồng nhưng bài test có quy tắc tùy tiện có thể khiến lỗi khó chẩn đoán.

Các quy ước hữu ích ở mô-đun hoặc nhóm:

- Tên test nêu **điều kiện và hành vi**, không chỉ `testMethod1`.
- Arrange/Act/Assert hoặc cách viết tương đương được dùng nhất quán khi giúp đọc.
- Fake/mock dùng tại ranh giới có lý do; test không verify mọi lời gọi nội bộ không thuộc hợp đồng.
- Test có dữ liệu cụ thể, giới hạn, và thông báo thất bại rõ; không phụ thuộc ngẫu nhiên vào thứ tự chạy.
- Clock, nguồn ID hoặc các dependency thời gian được điều khiển khi muốn test lặp lại.
- Các trường hợp lỗi/người dùng không có quyền được kiểm tra phù hợp với rủi ro.
- Cấp unit/integration/contract/E2E được lựa chọn theo **khả năng phát hiện loại lỗi**, không phải theo tên class.

Ví dụ JUnit 5 cho hợp đồng truy vấn trong phần 5:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;
import java.util.Optional;

class OrderQueriesTest {
    @Test
    void missingOrderIsEmptyForOptionalLookup() {
        OrderRepository repository = id -> Optional.empty();
        OrderQueries queries = new OrderQueries(repository);

        assertTrue(queries.findById(42L).isEmpty());
    }

    @Test
    void missingOrderThrowsForRequiredLookup() {
        OrderRepository repository = id -> Optional.empty();
        OrderQueries queries = new OrderQueries(repository);

        assertThrows(OrderNotFoundException.class,
                () -> queries.requireById(42L));
    }

    @Test
    void infrastructureFailureIsNotConvertedToEmpty() {
        OrderRepository repository = id -> {
            throw new IllegalStateException("DB unavailable");
        };
        OrderQueries queries = new OrderQueries(repository);

        assertThrows(IllegalStateException.class,
                () -> queries.findById(42L));
    }

    @Test
    void existingOrderIsPreserved() {
        OrderRepository repository = id ->
                Optional.of(new Order(id, "C-17"));
        OrderQueries queries = new OrderQueries(repository);

        assertEquals(new Order(42L, "C-17"),
                queries.requireById(42L));
    }
}
~~~

Bài test này xác minh **hợp đồng Java ở cấp component** với repository thay thế, chưa chứng minh cách SQL/ORM xử lý hàng không tồn tại và lỗi DB thật. Cần kiểm thử tích hợp tại ranh giới dữ liệu nếu đó là nguồn rủi ro.

Khi test khác nhau về tên hoặc cấu trúc do framework/kiểu kiểm thử khác nhau, hãy giữ các nguyên tắc chung **ở cấp mục tiêu và bằng chứng**, không ép mọi bài test thành cùng số dòng.

## 9. Quy ước nhóm: giúp các quyết định không phụ thuộc trí nhớ cá nhân

Ở cấp nhóm, quy ước tốt cần đáp ứng:

1. **Có thể tìm thấy:** người mới biết tài liệu/điểm bắt đầu nào mô tả chuẩn.
2. **Có ví dụ tích cực và tiêu cực:** không chỉ “viết code sạch”, mà nêu trường hợp cùng phạm vi nên làm gì.
3. **Có lý do:** giải thích chuẩn bảo vệ readability, compatibility, correctness hay security nào.
4. **Có công cụ phù hợp:** format và lint được tự động hóa khi có thể; không bắt reviewer làm máy kiểm tra khoảng trắng.
5. **Có người và quy trình sửa:** chuẩn lỗi thời được đề xuất thay đổi thế nào, ai quyết định, đường migration ra sao.
6. **Có chỗ cho ngoại lệ có chủ đích:** kèm phạm vi, lý do và bài kiểm thử, không biến ngoại lệ thành cách làm mặc định.

### Một bảng quyết định nhóm minh họa

| Quyết định | Quy ước đề xuất | Lý do | Ngoại lệ cần ghi rõ |
| --- | --- | --- | --- |
| Format Java | Dùng cùng formatter trên file thay đổi | Giảm diff hình thức | Generated code do tool sở hữu |
| Tên tiền VND | `amountDueVnd`, `subtotalVnd` | Không mơ hồ đơn vị | Domain hỗ trợ nhiều currency dùng kiểu Money |
| Tra cứu tùy chọn | `Optional<T>` | Không nhầm với lỗi | API thư viện có hợp đồng khác phải adapter |
| Lỗi cơ sở dữ liệu | Truyền/làm rõ lỗi, không trả empty | Giữ tín hiệu thất bại | Fallback có mô tả nghiệp vụ và quan sát rõ |
| Thời gian hiện tại | Truyền `Clock` ở logic cần kiểm thử | Test có thể lặp lại | Mã ứng dụng nhỏ không có chính sách thời gian phức tạp |
| Response API | DTO riêng, không xuất entity toàn bộ | Kiểm soát hợp đồng và dữ liệu | API nội bộ có hợp đồng riêng được duyệt |
| Cấu trúc PR | Tách thay đổi format lớn khỏi sửa hành vi khi hợp lý | Giữ lịch sử dễ review | Thay đổi bắt buộc đi cùng migration |

Bảng là **ví dụ**, không phải quy ước đã được xác nhận cho repository hiện tại. Một nhóm có thể chọn quyết định khác, miễn là có lý do, phạm vi rõ và được thực thi nhất quán.

## 10. Dùng công cụ để tự động hóa phần có thể tự động hóa

Quy ước format và một số loại lỗi có thể được kiểm tra tự động, giúp code review tập trung vào thiết kế và nghiệp vụ.

| Loại quy tắc | Công cụ/biện pháp thường dùng | Giới hạn |
| --- | --- | --- |
| Thụt lề, cuối dòng, khoảng trắng | `.editorconfig`, IDE formatter | Không thể chứng minh API đúng |
| Java formatting/import | Spotless, formatter được nhóm chọn | Có thể tạo diff lớn; cần thống nhất phiên bản/cấu hình |
| Quy tắc tên, style và một số lỗi tĩnh | Checkstyle, PMD, static analysis | Cần chọn rule và quản lý false positive |
| Lỗi mẫu trong Java | Error Prone, SpotBugs hoặc công cụ phù hợp | Không thay thế test nghiệp vụ hay review kiến trúc |
| Hợp đồng API | Schema/contract test, OpenAPI validation | Chưa phát hiện hết thay đổi nghĩa |
| Quy ước dependency và kiến trúc | Architecture tests/static rules khi phù hợp | Không đo được toàn bộ lý do nghiệp vụ |
| Test và khả năng chạy lại | Unit/integration tests, pipeline CI | Chỉ chứng minh những trường hợp và môi trường đã kiểm tra |

Một ví dụ `.editorconfig` mang tính minh họa:

~~~ini
root = true

[*]
charset = utf-8
end_of_line = lf
insert_final_newline = true

[*.java]
indent_style = space
indent_size = 4
trim_trailing_whitespace = true
~~~

**Không cần copy nguyên xi cấu hình này vào mọi dự án.** Nếu repository đã chọn tab hoặc formatter khác, phải xem xét ràng buộc hiện có và thống nhất trước. Mục tiêu của cấu hình là **giảm quyết định lặp lại của con người**, không thay thế quyết định thiết kế.

### Khi chạy formatter tự động

- Dùng **một phiên bản/cấu hình** thống nhất giữa IDE và CI để tránh việc định dạng thay đổi qua lại.
- Ưu tiên kiểm tra định dạng trong PR; nếu cần format toàn bộ codebase, làm riêng hoặc theo kế hoạch để lịch sử diff dễ đọc.
- Không sửa generated file thủ công nếu nguồn sinh mới là nơi phải thay.
- Với repository tồn tại lâu, có thể giới hạn thay đổi ban đầu ở file mới hoặc file đang sửa, sau đó có kế hoạch mở rộng.
- Đừng coi hết cảnh báo lint là bằng chứng không còn lỗi bảo mật, race condition hoặc hợp đồng mơ hồ.

## 11. Thứ tự ưu tiên khi có nhiều quy ước xung đột

Thực tế có thể xuất hiện:

- Mã cũ trong file dùng dấu ngoặc và tên theo một cách.
- Chuẩn mô-đun mới quy định cách khác.
- Một thư viện bên ngoài có tên API bắt buộc không theo chuẩn nội bộ.
- API v1 cần giữ tên cũ để bảo vệ consumer.

Không thể giải quyết mọi trường hợp bằng “hãy theo file đang có”. Có thể dùng **trật tự cân nhắc** sau:

1. **Tính đúng đắn, bảo mật và hợp đồng công khai:** không được hy sinh để đồng nhất style.
2. **Ràng buộc của ngôn ngữ/framework/giao thức:** tuân theo những phần bắt buộc để tích hợp đúng.
3. **Quy ước đã công bố cho khu vực đang sửa:** chọn chuẩn đang áp dụng thay vì tự đưa ra sở thích riêng.
4. **Nhất quán cục bộ có lý do:** khi chưa có chuẩn cao hơn, ưu tiên cách viết đang được dùng cho trách nhiệm tương tự.
5. **Cải tiến có kiểm chứng:** nếu chuẩn hiện tại rõ ràng gây lỗi hoặc khó thay đổi, đề xuất đổi kèm phạm vi và kế hoạch.

Đây là **thứ tự ra quyết định gợi ý**, không phải thứ bậc bất biến của mọi tổ chức. Khi ràng buộc mâu thuẫn, cần ghi lại lựa chọn có chủ đích để người sau không phải suy đoán.

### Ví dụ ngoại lệ chính đáng

Một API công khai dùng JSON field `totalVnd` còn client cũ. Trong nội bộ, chuẩn mới là `amountDueVnd`. Giải pháp có thể là một mapper xuất **cả hai field** trong giai đoạn chuyển đổi; không đổi ngay hợp đồng cũ. Như vậy **nội bộ nhất quán với tên mới**, còn ranh giới giữ tương thích.

Không nên cố “xóa ngoại lệ” bằng cách thay đổi dữ liệu công khai ngay cả khi mọi bài unit test nội bộ vẫn xanh.

## 12. Nhất quán khác với đồng nhất máy móc

Có nhiều trường hợp cùng một mẫu code **không nên** được sao chép:

### 12.1. Dùng exception và Optional

`findById` trả `Optional.empty()` khi không có dữ liệu; `requireById` ném lỗi trong tình huống ấy. Hai hành vi khác nhau vì **hợp đồng sử dụng khác nhau**, không phải vi phạm consistency.

### 12.2. Số thực và tiền

Dùng `double` cho số đo vật lý có dung sai và `BigDecimal`/số nguyên đơn vị nhỏ nhất cho tiền không phải thiếu nhất quán. Đó là **chọn kiểu theo ý nghĩa**.

### 12.3. Phân quyền

Endpoint chỉ đọc dữ liệu công khai và endpoint hoàn tiền có thể cần các lớp kiểm soát khác nhau. Cố ép cả hai dùng chung một cờ `isLoggedIn` để “thống nhất” có thể tạo lỗi bảo mật.

### 12.4. Đồng bộ và bất đồng bộ

Một phép tính CPU rất nhỏ có thể trả kết quả trực tiếp; một tác vụ báo cáo dài có thể cần job ID, trạng thái và cơ chế hủy. Tính nhất quán ở đây là **quy tắc lựa chọn và định nghĩa trạng thái**, không phải ép tất cả API đều đồng bộ.

### 12.5. Cấu trúc khác nhau theo trách nhiệm

Một DTO bất biến, repository adapter, domain aggregate và HTTP controller không nhất thiết có cùng cấu trúc class. Mỗi nhóm trách nhiệm có thể có convention riêng. Điều cần tránh là **cùng một loại trách nhiệm nhưng được giải quyết tùy tiện theo sở thích cá nhân**.

## 13. Khi nào nên đổi quy ước của một mô-đun?

Có những dấu hiệu quy ước hiện tại không còn phù hợp:

- Nhóm liên tục gặp lỗi từ việc hiểu nhầm `null`, đơn vị, thời gian hoặc mã lỗi.
- Mỗi thay đổi API phải sửa nhiều chỗ do dữ liệu bị biểu diễn theo nhiều cách khác nhau.
- Code review lặp lại cùng một loại nhận xét dù đã có tài liệu nhưng không có kiểm tra tự động.
- Một quyết định cũ gây chi phí bảo trì đáng kể khi công nghệ hoặc yêu cầu đã đổi.
- Test khó viết vì quy ước vô tình trộn logic nghiệp vụ và phụ thuộc bên ngoài.
- Người mới thường xuyên phải hỏi “hàm này khác hàm kia ở chỗ nào?” mà không có lý do nghiệp vụ.

Tuy nhiên, **khác chuẩn mới không đồng nghĩa có lợi ích khi sửa ngay**. Trước khi thay, phải cân nhắc:

| Câu hỏi | Vì sao quan trọng? |
| --- | --- |
| Vấn đề nào đã được quan sát? | Tránh đổi theo sở thích không mang lại lợi ích |
| Phạm vi tác động đến đâu? | Mã nội bộ, API công khai, dữ liệu lưu, migration, SDK |
| Có thể bảo toàn hành vi không? | Refactor khác với thay đổi hợp đồng hoặc sửa lỗi nghiệp vụ |
| Chi phí churn/diff là bao nhiêu? | Review, merge conflict, mất khả năng `git blame` hữu ích |
| Có test cho hành vi cũ và mới không? | Đảm bảo không thay lỗi này bằng lỗi khác |
| Cần duy trì hai cách trong giai đoạn chuyển đổi không? | Client hoặc dữ liệu cũ có thể cần tương thích |
| Có công cụ giữ quy ước mới không? | Nếu không, sai khác dễ xuất hiện trở lại |

Không nên đồng loạt đổi hàng nghìn tên chỉ để báo cáo “100% nhất quán” trong khi chưa xác định được ảnh hưởng API hoặc build.

## 14. Quy trình chuyển đổi quy ước an toàn

Một cách tiếp cận theo bước:

~~~mermaid
flowchart TD
    A["Quan sát thiếu nhất quán"] --> B["Xác định hậu quả và phạm vi"]
    B --> C["Chọn quy ước + ngoại lệ có lý do"]
    C --> D["Bổ sung test/hợp đồng bảo vệ hành vi"]
    D --> E["Thay đổi nhỏ theo khu vực"]
    E --> F["Đối chiếu kết quả và ranh giới"]
    F --> G["Tự động hóa và ghi nhận quy ước"]
    G --> H["Theo dõi việc áp dụng trong PR"]
~~~

### Bước 1 — Chọn một vấn đề có chi phí thực

Ví dụ: trong mô-đun orders, các query trả `null` và empty khác nhau khiến service nhiều lần xử lý sai “không tìm thấy”. Mục tiêu cụ thể hơn “cả repo phải dùng Optional”.

### Bước 2 — Viết hợp đồng và phạm vi trước khi sửa

Định nghĩa: với phương thức tra cứu thành công, `Optional.empty()` là không tìm thấy; lỗi DB phải được giữ riêng. Xác định những API cũ phải được giữ bằng adapter hoặc tạm hỗ trợ song song.

### Bước 3 — Tạo bằng chứng hồi quy

Test ít nhất ba tình huống: tìm thấy, không tìm thấy và lỗi hạ tầng. Nếu chuyển đổi qua HTTP/JSON hoặc DB, thêm test tại ranh giới thật. Không dựa vào “compile thành công” để chứng minh tương thích.

### Bước 4 — Chuyển đổi từng lớp có chủ sở hữu

Có thể đổi API nội bộ ở một lớp, sửa các caller tương ứng và kiểm tra kết quả trước khi di chuyển nhóm khác. Với public API, dùng mở rộng/di chuyển/thu hẹp để không phá consumer đang chạy.

### Bước 5 — Chuẩn hóa công cụ

Formatter xử lý style, static analysis xử lý một số lỗi mẫu, contract test bảo vệ hợp đồng. Không tự phát triển lint rule phức tạp nếu chi phí duy trì vượt lợi ích của quy tắc.

### Bước 6 — Ghi nhận những ngoại lệ và cập nhật cách review

Thay đổi thành chuẩn mới nên có **ví dụ đúng/sai**, người phụ trách và cách xử lý khi gặp mã cũ. Reviewer cần phân biệt “chưa chuyển đổi theo lộ trình” với “code mới vi phạm quy ước”.

### Bước 7 — Đánh giá sau khi áp dụng

Theo dõi những tín hiệu thực tế: lỗi hiểu nhầm dữ liệu giảm hay không, PR có ít tranh luận style hơn không, thời gian onboarding, số hồi quy do migration và độ ổn định CI. Không suy giá trị chỉ từ số file đã format.

## 15. Tình huống xuyên suốt: thống nhất contract trong nhóm phát triển đơn hàng

Một nhóm có ba ứng dụng cùng dùng mô-đun orders: backend, công cụ quản trị và báo cáo. Những khác biệt hiện tại:

| Vấn đề | Hành vi đang có | Rủi ro |
| --- | --- | --- |
| Tên tiền | `amount`, `total`, `totalVnd` | Nhầm đơn vị/ý nghĩa |
| Tra cứu đơn | Trả `null`, empty hoặc exception | Caller xử lý thiếu trường hợp |
| Thời gian | Có nơi dùng `LocalDateTime` không zone, nơi dùng `Instant` | Sai thời điểm khi deploy ở vùng khác |
| HTTP lỗi | Lúc JSON error code, lúc chuỗi tự do | Client không xử lý ổn định |
| Quyền | Controller kiểm tra role, service khác bỏ qua owner | Truy cập sai đơn |
| Test | Có test happy path, ít test âm tính và biên | Hồi quy khó phát hiện |

Nhóm thống nhất một **bộ quyết định có phạm vi**:

- Trong mã nội bộ, tiền đơn hàng là `amountDueVnd` kiểu số nguyên VND khi nghiệp vụ áp dụng; không thay trường API cũ mà chưa có lộ trình tương thích.
- Query tùy chọn dùng `Optional<Order>`, tìm bắt buộc có API tên rõ; lỗi hạ tầng không thành empty.
- Thời điểm tuyệt đối dùng `Instant`; ngày theo lịch dùng `LocalDate` kèm vùng khi chuyển sang thời điểm.
- API lỗi có schema/mã ổn định; không đưa exception nội bộ thẳng ra ngoài.
- Kiểm tra quyền theo đối tượng/tenant ở đường thực thi, không dựa vào UI hay role chung.
- Test bao phủ thành công, không tìm thấy, lỗi, sai quyền và các giá trị biên theo rủi ro.

### Hai thay đổi cần xử lý khác nhau

**Thay đổi A — format và tên biến cục bộ:** đổi tên `x` thành `amountDueVnd` ở một phương thức không công khai và không đổi hành vi. Có thể được review như refactor nhỏ sau khi xác nhận phạm vi.

**Thay đổi B — hợp đồng API:** đổi JSON `totalVnd` thành `amountDueVnd`. Đây là **thay đổi có thể phá consumer**, cần lộ trình mở rộng và kiểm thử tương thích, không được gộp lẫn vào PR format.

Một quy ước tốt giúp reviewer nhận ra **hai loại rủi ro** này ngay từ đầu.

### Bản ghi quyết định mẫu

~~~text
Decision: Giá trị tiền trong nội bộ module orders
Status: Đã thống nhất cho code mới; mã cũ chuyển đổi dần
Scope: Application/domain trong module orders
Rule: Tên có hậu tố Vnd cho số tiền nguyên theo nghiệp vụ hiện tại
Reason: Tránh nhầm với tỉ lệ, phần trăm hoặc đơn vị ngoại tệ
Exceptions: API v1 còn trường totalVnd được giữ để tương thích
Verification: Unit test tính tiền, contract test JSON, kiểm tra static khi phù hợp
Migration: Ưu tiên code đang thay đổi; không đổi API công khai ngoài lộ trình
Owner: Nhóm sở hữu module orders
~~~

Đây là **mẫu minh họa**, không phải quyết định thực sự đã có trong dự án. Giá trị của bản ghi nằm ở việc nêu *quy tắc, lý do, phạm vi, ngoại lệ và phương pháp kiểm chứng*.

## 16. Code review: nhận xét có bằng chứng thay vì sở thích

Một nhận xét kém hữu ích:

> “Tớ thích `get()` hơn `find()`, sửa cho giống nhé.”

Một nhận xét rõ hơn:

> “Các phương thức `findById` của mô-đun hiện trả `Optional.empty()` khi tra cứu thành công nhưng không có bản ghi. Phương thức này trả `null` nên caller phải kiểm tra riêng, dễ bỏ sót nhánh. Có thể giữ cùng hợp đồng `Optional<Order>` và bổ sung test tìm thấy/không tìm thấy/lỗi DB không?”

Nhận xét thứ hai nêu **quy ước đã tồn tại trong phạm vi**, **rủi ro**, **đề xuất** và **cách kiểm chứng**. Nó cũng tạo cơ hội phản biện nếu method mới thật sự có ý nghĩa khác.

### Khi chuẩn hiện tại chưa có câu trả lời

Reviewer không nên áp đặt một sở thích riêng rồi gọi đó là “team convention”. Có thể:

1. Hỏi loại hành vi nào đang được triển khai và nó giống trường hợp nào đã có.
2. So sánh các lựa chọn theo readability, correctness, compatibility và chi phí thay đổi.
3. Chọn quyết định trong phạm vi nhỏ nhất đủ dùng.
4. Ghi lại để lần sau không cần tranh luận lại.
5. Tự động hóa nếu quy tắc đủ ổn định và kiểm tra được bằng máy.

Cách này giúp **tính nhất quán được hình thành từ quyết định chung**, không phải từ người review mạnh tiếng nhất.

## 17. Checklist khi đọc và sửa một đoạn mã

### Trong một tệp

- [ ] Tên biến/phương thức phản ánh cùng quy tắc đơn vị và ý nghĩa.
- [ ] Các hàm cùng loại thể hiện đường thành công, đường lỗi và nullability dễ dự đoán.
- [ ] Biến không đổi ý nghĩa ngầm khiến người đọc phải lần ngược lịch sử gán.
- [ ] Quy tắc format/import được áp dụng bằng công cụ hoặc cấu hình đã chọn.
- [ ] Tác dụng phụ, thời điểm đọc dữ liệu và ranh giới trách nhiệm có thể nhận biết.
- [ ] Nếu có ngoại lệ với pattern cục bộ, lý do nghiệp vụ được giải thích.

### Trong mô-đun

- [ ] Kiểu tiền, thời gian, ID và trạng thái có ý nghĩa thống nhất tại các ranh giới.
- [ ] Không tìm thấy, dữ liệu rỗng, dữ liệu thiếu và lỗi được phân biệt theo hợp đồng.
- [ ] Mapping giữa domain, DB và API không tự đổi đơn vị hoặc làm mất trạng thái.
- [ ] Package và tên lớp giúp tìm đúng chủ sở hữu của một quy tắc.
- [ ] Transaction, retry và idempotency có người chịu trách nhiệm rõ.
- [ ] Phân quyền theo hành động/tài nguyên được áp dụng nhất quán ở các đường truy cập.
- [ ] Kiểm thử phản ánh rủi ro tại cả logic thuần và ranh giới tích hợp quan trọng.

### Trong nhóm

- [ ] Quy ước đang áp dụng có thể tìm thấy, có lý do và ví dụ.
- [ ] Formatter/linter/CI kiểm tra những việc máy có thể làm ổn định.
- [ ] Review tập trung vào hành vi, không ép sở thích riêng khi chưa có chuẩn.
- [ ] Có đường đề xuất thay đổi và ngoại lệ có thời hạn/phạm vi.
- [ ] Migration không gộp lặng lẽ thay đổi format với breaking API/business behavior.
- [ ] Người mới có thể xác định chuẩn cần áp dụng mà không phải hỏi từng tác giả.

## 18. Những ngộ nhận thường gặp

**“Nhất quán nghĩa là mọi lớp trông giống nhau.”** DTO, domain aggregate, adapter và controller có mục đích khác nhau. Nhất quán là **cùng ngữ nghĩa thì cùng cách thể hiện**.

**“Cứ theo code cũ là đúng.”** Code cũ có thể chứa anti-pattern hoặc lỗi. Phải cân nhắc tính đúng đắn và lộ trình cải thiện.

**“Một formatter là đủ.”** Formatter không quyết định có được trả null khi lỗi DB, đơn vị tiền là gì hoặc ai có quyền xem dữ liệu.

**“Tên giống nhau là hành vi giống nhau.”** Hai field `amount` có thể khác currency/scale; hợp đồng phải diễn đạt điều đó.

**“Một quy ước tốt phải có càng nhiều luật càng tốt.”** Quá nhiều luật không mang giá trị làm code review và CI tốn kém. Ưu tiên luật bảo vệ rủi ro thực.

**“Đổi tên public field để thống nhất là refactor an toàn.”** API/JSON, DB hoặc SDK có consumer; đổi tên có thể là breaking change.

**“Sử dụng `Optional` cho mọi thứ sẽ nhất quán hơn.”** Không nên ép thao tác ghi, lỗi hạ tầng và danh sách rỗng vào cùng biểu diễn.

**“Không đồng ý style là lỗi của người mới.”** Nếu quy ước không được mô tả và áp dụng bằng công cụ, hệ thống đang phụ thuộc trí nhớ cá nhân.

**“Mọi file phải được format lại trong cùng một PR.”** Diff lớn dễ che lỗi và gây xung đột; cần cân nhắc tách migration style.

**“Đã có lint xanh thì code chắc chắn đáng tin cậy.”** Còn cần test nghiệp vụ, kiểm tra quyền, lỗi tích hợp và review thiết kế.

## 19. Bài tập thực hành

### Bài tập A — tìm những khác biệt có ý nghĩa

Bạn thấy trong một module:

~~~java
Order find(long id);             // Trả null khi không có dữ liệu.
Optional<Order> lookup(long id); // Trả empty khi không có dữ liệu.
List<Order> search(String term); // Trả danh sách rỗng khi không có kết quả.
~~~

Hãy trả lời:

1. Hai phương thức đầu có cùng loại trách nhiệm không?
2. Có nên đổi tất cả thành `Optional` không? Tại sao?
3. Lỗi DB nên xuất hiện qua kiểu trả về nào hoặc cơ chế nào?
4. Bạn sẽ viết những test nào để tránh làm thay đổi hành vi không mong đợi?
5. Nếu `find` là public API đã có consumer, lộ trình cải thiện cần điều gì?

### Bài tập B — cân nhắc tính nhất quán và tính đúng đắn

Trong mô-đun thanh toán, tất cả phép tính đang dùng `double`. Một người đề xuất giữ `double` vì “cả nhóm đang nhất quán”; người khác đề xuất chuyển sang cách biểu diễn tiền chính xác hơn.

Hãy so sánh rủi ro số học, phạm vi data/API, test hồi quy, chi phí migration và cách ghi quyết định. Vì sao **nhất quán với một lỗi** không phải mục tiêu cần bảo vệ?

### Bài tập C — review một pull request

Một PR vừa đổi formatter trên 1.000 file, vừa đổi tên JSON field và sửa quy tắc chiết khấu. Hãy đề xuất cách tách thay đổi, những contract test cần có và chiến lược tránh để style diff che mất thay đổi hành vi.

### Bài tập D — thiết kế quy ước nhóm

Viết một quyết định ngắn cho: cách biểu diễn “không tìm thấy dữ liệu”; cách ghi log lỗi DB; và cách đặt tên field tiền. Mỗi quyết định phải có **scope, rule, reason, exception và verification**.

## 20. Câu hỏi tự kiểm tra

1. Vì sao tính nhất quán cải thiện khả năng đọc dù nó không tự sửa mọi lỗi?
2. Phân biệt ba cấp nhất quán trong **tệp**, **mô-đun** và **nhóm**, kèm một ví dụ mỗi cấp.
3. Hai method khác nhau dùng `Optional` và exception có nhất thiết thiếu nhất quán không? Khi nào sự khác biệt là đúng?
4. Quy ước về tiền hoặc thời gian khác quy ước thụt lề ở điểm nào?
5. Vì sao kết quả lint xanh không chứng minh hợp đồng API đúng?
6. Một module có hai định nghĩa của “không tìm thấy”. Những rủi ro nào có thể xảy ra nếu người đọc nhầm?
7. Tại sao không nên đổi JSON field của API công khai chỉ vì chuẩn tên nội bộ mới?
8. Khi thay một quy ước cũ, cần có những bằng chứng nào để phân biệt refactor với thay đổi hành vi?
9. Vì sao generated code hoặc library integration có thể là ngoại lệ hợp lý đối với quy ước nhóm?
10. Khi một file chưa theo chuẩn mới, bạn sẽ ưu tiên “thống nhất với file” hay “thống nhất với module” theo những điều kiện nào?
11. Một review comment tốt về thiếu nhất quán nên có những phần nào?
12. Hãy nêu hai cách giảm tranh luận style nhưng vẫn giữ quyền thay đổi quy ước khi có lý do chính đáng.

## Ghi nhớ

**Tính nhất quán không phải là làm mọi đoạn mã trông giống nhau; đó là giúp người đọc dự đoán được cách những trường hợp cùng ý nghĩa được biểu diễn và xử lý.** Trong một tệp, hãy giữ tên gọi, luồng dữ liệu và đường lỗi dễ theo dõi. Trong mô-đun, bảo vệ hợp đồng về đơn vị, trạng thái, lỗi, quyền và tác dụng phụ. Trong nhóm, ghi lại quy ước có lý do, tự động hóa phần máy kiểm tra được và chuyển đổi theo lộ trình an toàn. Một chuẩn tốt luôn phải phục vụ tính đúng đắn, khả năng đọc và khả năng thay đổi — không được đặt sự đồng đều bề ngoài cao hơn những mục tiêu đó.
