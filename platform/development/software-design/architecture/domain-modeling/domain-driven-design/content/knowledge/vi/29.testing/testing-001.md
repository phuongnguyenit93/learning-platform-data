# Biến ví dụ nghiệp vụ thành tiêu chí chấp nhận có thể thực thi

Trong Domain-Driven Design (DDD), mô hình miền được hình thành qua trao đổi liên tục giữa chuyên gia nghiệp vụ và đội phát triển. Những câu như “đơn hợp lệ thì có thể xác nhận” hoặc “khách hàng thân thiết được ưu đãi” thường là điểm bắt đầu, chưa phải quy tắc đủ rõ để triển khai. Muốn biến hiểu biết đó thành phần mềm đáng tin cậy, đội ngũ cần làm rõ ví dụ cụ thể, xác định điều kiện và kết quả mong đợi, rồi chuyển chúng thành tiêu chí chấp nhận có thể kiểm tra tự động.

Tiêu chí chấp nhận (acceptance criteria) mô tả hành vi mà một chức năng phải thể hiện để được xem là đáp ứng nhu cầu nghiệp vụ. Khi các tiêu chí được viết bằng ví dụ rõ ràng và có thể thực thi, chúng trở thành một đặc tả sống: chuyên gia có thể đọc để xác nhận ý nghĩa, lập trình viên có thể dùng để định hướng thiết kế, và hệ thống kiểm thử có thể chạy để phát hiện sai lệch.

Bài học này trình bày cách khám phá ví dụ với chuyên gia, tổ chức quy tắc bằng Example Mapping và decision table, diễn đạt bằng Given–When–Then, rồi triển khai thành domain test và executable acceptance test. Ví dụ xuyên suốt là xác nhận đơn hàng trong Sales Context. Các chính sách trong ví dụ được giả định để minh họa; khi áp dụng vào một miền thật, đội ngũ phải xác nhận lại với người có thẩm quyền nghiệp vụ.

## 1. Tiêu chí chấp nhận là gì?

### 1.1. Mô tả kết quả có thể quan sát

Tiêu chí chấp nhận mô tả điều người dùng hoặc hệ thống liên quan có thể quan sát khi một hành động xảy ra.

Ví dụ còn mơ hồ:

> Người mua có thể xác nhận đơn hợp lệ.

Câu này chưa giải thích:
- Đơn hợp lệ cần có những dữ liệu nào?
- Đơn không có dòng hàng được xử lý ra sao?
- Giá trị đơn được tính theo giá hiện tại hay giá đã chốt?
- Có cho phép xác nhận lại đơn đã xác nhận không?
- Nếu xác nhận thất bại, trạng thái có thay đổi không?

Một tiêu chí rõ hơn:

> Với một đơn ở trạng thái Draft có người mua và ít nhất một dòng hàng hợp lệ, khi người mua xác nhận đơn, hệ thống chuyển đơn sang Confirmed, giữ nguyên các snapshot giá đã chốt và ghi nhận sự kiện SalesOrderConfirmed.

Tiêu chí này xác định được điều kiện trước, hành động và kết quả. Nó có thể được chuyển thành một test tự động.

### 1.2. Phân biệt yêu cầu, quy tắc và tiêu chí chấp nhận

| Khái niệm | Vai trò | Ví dụ |
|---|---|---|
| Yêu cầu (requirement) | Nhu cầu hoặc mục tiêu cần đạt | Người mua cần xác nhận đơn hàng |
| Business rule | Quy tắc quyết định điều gì được phép hoặc phải xảy ra | Chỉ đơn Draft mới được xác nhận |
| Acceptance criterion | Điều kiện cụ thể để chứng minh chức năng đáp ứng quy tắc | Khi xác nhận đơn Draft có ít nhất một dòng hợp lệ, trạng thái chuyển thành Confirmed |
| Acceptance test | Kiểm thử thực thi một hoặc nhiều tiêu chí | Test gọi use case và xác minh trạng thái cùng event được ghi nhận |

Một yêu cầu có thể có nhiều business rule. Mỗi rule có thể cần nhiều ví dụ và tiêu chí chấp nhận. Một acceptance test có thể kiểm tra một tiêu chí hoặc một nhóm tiêu chí liên quan.

### 1.3. Tiêu chí tốt phải rõ và có thể kiểm chứng

Một tiêu chí chấp nhận hữu ích thường có các đặc điểm:

- Có điều kiện đầu vào cụ thể.
- Nêu hành động hoặc sự kiện kích hoạt.
- Nêu kết quả quan sát được.
- Không dùng từ mơ hồ như “hợp lý”, “nhanh”, “đầy đủ” nếu chưa có định nghĩa.
- Có thể phân biệt trường hợp đạt và không đạt.
- Dùng thuật ngữ đã thống nhất trong ngôn ngữ miền.
- Không quy định chi tiết triển khai nếu đó không phải yêu cầu nghiệp vụ.

Tiêu chí chấp nhận không nên yêu cầu hệ thống phải gọi một private method cụ thể, dùng một framework cụ thể hoặc tạo đúng số lượng object nội bộ. Đó là quyết định thiết kế, trừ khi chúng tạo ra một cam kết vận hành có ý nghĩa.

## 2. Khám phá ví dụ cùng chuyên gia nghiệp vụ

### 2.1. Bắt đầu bằng một tình huống cụ thể

Thay vì hỏi “quy trình xác nhận đơn hoạt động thế nào?”, hãy hỏi một ví dụ gần với thực tế:

- Một đơn hàng bình thường được xác nhận ra sao?
- Dữ liệu nào đã có trước khi xác nhận?
- Ai có quyền thực hiện?
- Hệ thống thay đổi điều gì sau khi xác nhận?
- Có trường hợp nào trông giống bình thường nhưng phải xử lý khác?

Ví dụ cụ thể khiến các giả định ẩn xuất hiện. Chuyên gia có thể nói rằng đơn không có dòng hàng không thể xác nhận, hoặc đơn đã xác nhận không được sửa giá. Những điều này có thể không xuất hiện trong mô tả tổng quát ban đầu.

### 2.2. Hỏi về trường hợp ngoại lệ

Sau happy path, hãy tìm các trường hợp biên:

- Đơn không có dòng hàng thì sao?
- Một dòng có số lượng bằng 0 thì sao?
- Người mua chưa được gán thì sao?
- Giá của một dòng không cùng tiền tệ với tổng đơn thì sao?
- Hai yêu cầu xác nhận đến gần như đồng thời thì sao?
- Người dùng gửi lại yêu cầu vì không nhận được phản hồi thì sao?

Không phải mọi ngoại lệ đều cần được giải quyết ngay, nhưng câu hỏi chưa có lời giải cần được ghi nhận. Đừng tự biến suy đoán của đội phát triển thành chính sách chính thức.

### 2.3. Phân biệt ví dụ với quy tắc

Một ví dụ cho thấy điều gì xảy ra trong một tình huống. Quy tắc giải thích vì sao kết quả đó đúng và áp dụng cho những trường hợp nào.

Ví dụ:
- Ví dụ: đơn có hai dòng hàng và tổng tiền 250.000 đồng được xác nhận.
- Quy tắc có thể là: đơn Draft có ít nhất một dòng hàng hợp lệ được xác nhận, tổng tiền được tính từ số lượng nhân đơn giá đã chốt.

Nếu chỉ ghi ví dụ 250.000 đồng mà không rút ra quy tắc, đội phát triển dễ hard-code một trường hợp cụ thể. Ngược lại, nếu chỉ ghi quy tắc chung mà không có ví dụ, các bên có thể hiểu khác nhau về cách áp dụng.

### 2.4. Dùng ví dụ phản chứng để kiểm tra cách hiểu

Một ví dụ phản chứng là tình huống cho thấy giả định hiện tại có thể sai.

Nếu nhóm cho rằng “đơn đã xác nhận thì không thay đổi”, hãy hỏi:
- Có cho phép thay đổi địa chỉ giao hàng không?
- Có cho phép thêm ghi chú không?
- Có cho phép thay đổi người nhận nhưng giữ nguyên cam kết thương mại không?
- Có quy trình sửa đổi đơn riêng không?

Câu trả lời có thể cho thấy cần phân biệt dữ liệu bất biến của giao dịch với thông tin vận hành có thể cập nhật. Ví dụ phản chứng giúp mô hình không bị đơn giản hóa quá mức.

## 3. Tổ chức buổi làm rõ bằng Example Mapping

### 3.1. Example Mapping là gì?

Example Mapping là một kỹ thuật cộng tác để khám phá yêu cầu bằng bốn nhóm thông tin:

- **Story**: câu chuyện hoặc chức năng đang thảo luận.
- **Rules**: các quy tắc chi phối chức năng.
- **Examples**: ví dụ cụ thể minh họa từng quy tắc.
- **Questions**: câu hỏi chưa được trả lời.

Cách tổ chức này giúp buổi trao đổi tập trung vào hành vi và những điểm chưa rõ, thay vì bắt đầu bằng thiết kế class hoặc database.

### 3.2. Ví dụ Example Mapping cho xác nhận đơn

~~~text
STORY
Người mua xác nhận một Sales Order

RULE 1
Chỉ đơn Draft mới được xác nhận
  EXAMPLE: Đơn Draft có dòng hàng hợp lệ -> Confirmed
  EXAMPLE: Đơn đã Confirmed -> không xác nhận lần nữa

RULE 2
Đơn phải có ít nhất một dòng hàng hợp lệ
  EXAMPLE: Đơn rỗng -> từ chối
  EXAMPLE: Dòng có quantity = 0 -> từ chối

RULE 3
Tổng tiền dùng số lượng và đơn giá đã chốt
  EXAMPLE: 2 x 100.000 + 1 x 50.000 -> 250.000

QUESTIONS
Nếu người mua bị khóa thì có được xác nhận không?
Có cần kiểm tra tồn kho ngay ở Sales Context không?
Nếu hai lệnh xác nhận đến đồng thời thì kết quả nào được trả?
~~~

Các câu hỏi ở cuối không nên bị lấp bằng giả định. Cần người có thẩm quyền trả lời trước khi đưa chúng thành rule chính thức.

### 3.3. Khi nào cần chia nhỏ story?

Nếu một story có quá nhiều rule hoặc quá nhiều câu hỏi, nó có thể đang mô tả nhiều hành vi khác nhau.

Ví dụ “xác nhận đơn và giao hàng” có thể bao gồm:
- Xác nhận cam kết bán hàng.
- Yêu cầu giữ hàng.
- Phân bổ kho.
- Tạo đợt giao.
- Theo dõi giao hàng.

Các hành vi này có thể thuộc nhiều Bounded Context và có vòng đời khác nhau. Hãy chia thành các story có kết quả quan sát được và người sở hữu nghiệp vụ rõ ràng.

### 3.4. Ghi lại câu hỏi chưa được giải quyết

Mỗi câu hỏi nên có người chịu trách nhiệm và thời điểm cần trả lời. Không biến câu hỏi thành một điều kiện ngầm trong code.

Nếu câu hỏi chưa ảnh hưởng đến phần đang triển khai, có thể tách ra khỏi phạm vi hiện tại. Nếu nó quyết định hành vi cốt lõi, cần làm rõ trước khi chốt acceptance criteria.

## 4. Chuyển quy tắc thành decision table

### 4.1. Liệt kê điều kiện và kết quả

Decision table giúp nhìn thấy các tổ hợp điều kiện và hành động tương ứng. Với ví dụ xác nhận đơn, giả định chính sách như sau:

- Chỉ đơn Draft mới được xác nhận.
- Đơn phải có người mua.
- Đơn phải có ít nhất một dòng hàng.
- Mỗi dòng phải có quantity dương và đơn giá không âm.
- Các khoản tiền phải cùng currency.

| Trạng thái | Có người mua | Có dòng hàng | Dữ liệu dòng hợp lệ | Kết quả |
|---|---|---|---|---|
| Draft | Có | Có | Có | Xác nhận |
| Draft | Không | Có | Có | Từ chối: thiếu người mua |
| Draft | Có | Không | — | Từ chối: đơn rỗng |
| Draft | Có | Có | Không | Từ chối: dòng hàng không hợp lệ |
| Confirmed | Có | Có | Có | Từ chối: trạng thái không cho phép |

Dấu gạch ngang biểu thị điều kiện không còn ảnh hưởng vì một điều kiện trước đó đã quyết định kết quả. Thứ tự ưu tiên giữa các lỗi cần được thống nhất nếu API chỉ trả về một lỗi đầu tiên.

### 4.2. Kiểm tra tính đầy đủ của bảng

Với mỗi điều kiện, hỏi:
- Điều kiện này có thể đúng hoặc sai trong thực tế không?
- Có tổ hợp nào chưa được bao phủ?
- Hai rule có thể cùng thất bại không?
- Nếu cùng thất bại, kết quả nào được ưu tiên?
- Có trường hợp ngoại lệ được phép không?

Không nhất thiết phải tạo mọi tổ hợp nếu số lượng quá lớn. Có thể dùng phân tích rủi ro, decision table hoặc pairwise testing để chọn tập trường hợp phù hợp.

### 4.3. Phân biệt rule nghiệp vụ và validation kỹ thuật

Một chuỗi ID sai định dạng có thể là lỗi validation ở API boundary. Một đơn Draft không có dòng hàng là vi phạm điều kiện nghiệp vụ khi xác nhận.

Hai loại lỗi có thể được trình bày khác nhau:
- Lỗi giao thức hoặc dữ liệu đầu vào không hợp lệ.
- Từ chối nghiệp vụ vì trạng thái hoặc điều kiện không cho phép.

Tách rõ giúp caller biết có nên sửa request, hiển thị lý do nghiệp vụ hay thử lại.

## 5. Viết tiêu chí theo Given–When–Then

### 5.1. Cấu trúc cơ bản

Given–When–Then gồm:

- **Given**: bối cảnh và điều kiện ban đầu.
- **When**: hành động hoặc sự kiện được kích hoạt.
- **Then**: kết quả mong đợi có thể quan sát.

Ví dụ:

~~~text
Given một Sales Order ở trạng thái Draft
And đơn có người mua và ít nhất một dòng hàng hợp lệ
When người mua xác nhận đơn
Then trạng thái đơn chuyển thành Confirmed
And tổng tiền bằng tổng giá trị các dòng hàng
~~~

Cấu trúc này giúp cả chuyên gia và lập trình viên đọc cùng một kịch bản.

### 5.2. Một scenario nên tập trung vào một hành vi

Tránh viết một scenario vừa xác nhận đơn, vừa thanh toán, vừa phân bổ kho, vừa gửi email. Nếu có nhiều kết quả độc lập, hãy chia thành các scenario hoặc feature riêng.

Một scenario có thể kiểm tra nhiều kết quả cùng thuộc một hành vi, chẳng hạn trạng thái được cập nhật và event được ghi nhận khi xác nhận đơn.

### 5.3. Given phải mô tả trạng thái nghiệp vụ

Given nên diễn đạt bối cảnh bằng ngôn ngữ miền, ví dụ:
- Một đơn Draft có người mua.
- Một hợp đồng đang có hiệu lực.
- Một tài khoản có đủ số dư khả dụng.

Tránh mô tả chi tiết cách dựng dữ liệu kỹ thuật như “insert một row vào bảng orders” trong đặc tả nghiệp vụ. Chi tiết đó thuộc test fixture hoặc test setup.

### 5.4. When nên mô tả một hành động rõ ràng

When thường có một hành động chính:
- Người mua xác nhận đơn.
- Nhân viên phê duyệt hoàn tiền.
- Hệ thống ghi nhận giao hàng.
- Khách gửi yêu cầu hủy.

Nếu một scenario có nhiều When độc lập, hãy xem xét chia nhỏ hoặc mô tả một quy trình nhiều bước với các trạng thái trung gian rõ ràng.

### 5.5. Then phải kiểm tra kết quả, không lặp lại hành động

Then không nên viết “đơn được xác nhận thành công” nếu điều đó chỉ lặp lại When. Hãy nêu dấu hiệu chứng minh:
- Status là Confirmed.
- Tổng tiền được tính đúng.
- Event có định danh đơn và thời điểm phù hợp được ghi nhận.
- Một thao tác không hợp lệ bị từ chối và trạng thái không đổi.

## 6. Từ tiêu chí chấp nhận đến executable specification

### 6.1. Đặc tả sống là gì?

Executable specification là tập ví dụ hoặc tiêu chí có thể chạy tự động để kiểm tra hệ thống. Khi code thay đổi, bộ kiểm thử chạy lại và cho biết hành vi có còn phù hợp với ví dụ đã thống nhất hay không.

Một đặc tả sống cần:
- Được viết bằng ngôn ngữ mà chuyên gia hiểu.
- Có dữ liệu đầu vào và kết quả rõ.
- Chạy được trong pipeline kiểm thử.
- Có người chịu trách nhiệm cập nhật khi chính sách thay đổi.
- Không phụ thuộc quá mức vào chi tiết nội bộ.

### 6.2. BDD là cách cộng tác, không chỉ là cú pháp Gherkin

Behavior-Driven Development (BDD) tập trung vào việc khám phá hành vi thông qua ví dụ và ngôn ngữ chung. Gherkin, Cucumber hoặc SpecFlow chỉ là công cụ có thể hỗ trợ tự động hóa.

Chỉ viết file Feature mà không trao đổi với chuyên gia không tự động tạo ra BDD. Giá trị nằm ở việc các bên thống nhất ý nghĩa của từng ví dụ trước khi code.

### 6.3. Không phải mọi acceptance criterion đều cần Cucumber

Có thể thực thi tiêu chí bằng:
- Unit test cho Value Object và Aggregate.
- Application service test.
- Integration test qua database và message broker.
- API acceptance test.
- Cucumber hoặc framework BDD.

Chọn công cụ theo ranh giới hành vi cần kiểm tra. Một rule thuần túy của Money không cần chạy qua HTTP chỉ để có nhãn acceptance test.

## 7. Xây dựng mô hình miền cho ví dụ

Các chính sách dưới đây là giả định của bài học:
- Sales Order mới ở trạng thái Draft.
- Chỉ đơn Draft có Buyer và ít nhất một dòng hợp lệ mới được xác nhận.
- Mỗi dòng có quantity dương và unit price không âm.
- Tổng tiền được tính từ quantity nhân unit price đã chốt.
- Xác nhận thành công làm đơn chuyển sang Confirmed và ghi nhận Domain Event.
- Đơn đã Confirmed không thể xác nhận lại.

### 7.1. Kiểu định danh và tiền

~~~java
public record SalesOrderId(UUID value) {
    public SalesOrderId {
        Objects.requireNonNull(value);
    }
}

public record BuyerId(String value) {
    public BuyerId {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(
                "Buyer id is required"
            );
        }
    }
}

public record Money(
    BigDecimal amount,
    Currency currency
) {
    public Money {
        Objects.requireNonNull(amount);
        Objects.requireNonNull(currency);

        if (amount.signum() < 0) {
            throw new IllegalArgumentException(
                "Money cannot be negative"
            );
        }
    }

    public Money add(Money other) {
        requireSameCurrency(other);
        return new Money(
            amount.add(other.amount),
            currency
        );
    }

    public Money multiply(int quantity) {
        if (quantity <= 0) {
            throw new IllegalArgumentException(
                "Quantity must be positive"
            );
        }

        return new Money(
            amount.multiply(BigDecimal.valueOf(quantity)),
            currency
        );
    }

    private void requireSameCurrency(Money other) {
        if (!currency.equals(other.currency)) {
            throw new IllegalArgumentException(
                "Currencies must match"
            );
        }
    }
}
~~~

Money bảo vệ quy tắc tiền tệ. Trong hệ thống thực tế, cần xác nhận scale, rounding mode, precision và quy tắc thuế/chiết khấu với nghiệp vụ.

### 7.2. Dòng hàng giữ snapshot đơn giá

~~~java
public record SalesOrderLine(
    ProductId productId,
    int quantity,
    Money unitPrice
) {
    public SalesOrderLine {
        Objects.requireNonNull(productId);
        Objects.requireNonNull(unitPrice);

        if (quantity <= 0) {
            throw new IllegalArgumentException(
                "Quantity must be positive"
            );
        }
    }

    public Money lineTotal() {
        return unitPrice.multiply(quantity);
    }
}
~~~

Đơn giá được chốt khi dòng hàng được thêm hoặc khi đơn được tạo theo chính sách đã chọn. Không nên để một thay đổi giá trong Product Catalog tự động làm thay đổi tổng tiền của đơn đã xác nhận.

### 7.3. Kết quả xác nhận và Domain Event

~~~java
public enum SalesOrderStatus {
    DRAFT,
    CONFIRMED
}

public record SalesOrderConfirmed(
    SalesOrderId salesOrderId,
    Money total,
    Instant occurredAt
) {
}
~~~

Event biểu diễn sự kiện nghiệp vụ. Trong hệ thống thật, có thể bổ sung eventId, schemaVersion và metadata cần thiết cho outbox hoặc integration event.

### 7.4. Aggregate Root bảo vệ quy tắc

~~~java
public final class SalesOrder {

    private final SalesOrderId id;
    private BuyerId buyerId;
    private final List<SalesOrderLine> lines =
        new ArrayList<>();
    private SalesOrderStatus status =
        SalesOrderStatus.DRAFT;
    private final List<SalesOrderConfirmed> events =
        new ArrayList<>();

    public SalesOrder(SalesOrderId id, BuyerId buyerId) {
        this.id = Objects.requireNonNull(id);
        this.buyerId = buyerId;
    }

    public void addLine(SalesOrderLine line) {
        ensureDraft();
        lines.add(Objects.requireNonNull(line));
    }

    public void confirm(Instant now) {
        ensureDraft();

        if (buyerId == null) {
            throw new IllegalStateException(
                "A buyer is required"
            );
        }

        if (lines.isEmpty()) {
            throw new IllegalStateException(
                "An order must contain at least one line"
            );
        }

        Money total = total();

        status = SalesOrderStatus.CONFIRMED;
        events.add(new SalesOrderConfirmed(id, total, now));
    }

    public Money total() {
        if (lines.isEmpty()) {
            throw new IllegalStateException(
                "An empty order has no total"
            );
        }

        Money result = lines.get(0).lineTotal();

        for (int i = 1; i < lines.size(); i++) {
            result = result.add(lines.get(i).lineTotal());
        }

        return result;
    }

    private void ensureDraft() {
        if (status != SalesOrderStatus.DRAFT) {
            throw new IllegalStateException(
                "Only a draft order can be changed"
            );
        }
    }

    public SalesOrderStatus status() {
        return status;
    }

    public List<SalesOrderConfirmed> domainEvents() {
        return List.copyOf(events);
    }

    public SalesOrderId id() {
        return id;
    }
}
~~~

Đoạn code là mô hình minh họa; constructor, cách quản lý event và các kiểu ProductId cần được hoàn thiện theo dự án. Việc ghi event vào outbox nên được thực hiện cùng transaction lưu Aggregate để không phát thông điệp khi thay đổi chưa commit.

## 8. Viết domain test cho từng quy tắc

### 8.1. Test xác nhận đơn hợp lệ

~~~java
@Test
void confirmsDraftOrderWithValidLines() {
    SalesOrder order = newDraftOrderWithBuyer();

    order.addLine(line("PRODUCT-1", 2, "100000"));
    order.addLine(line("PRODUCT-2", 1, "50000"));

    order.confirm(Instant.parse("2026-11-18T03:00:00Z"));

    assertEquals(
        SalesOrderStatus.CONFIRMED,
        order.status()
    );

    assertEquals(
        new BigDecimal("250000"),
        order.total().amount()
    );

    assertEquals(1, order.domainEvents().size());
}
~~~

Test xác nhận hành vi chính và kết quả có thể quan sát. Factory newDraftOrderWithBuyer và line được giả định là fixture test; currency được giữ nhất quán trong ví dụ.

### 8.2. Test đơn rỗng bị từ chối

~~~java
@Test
void rejectsConfirmationWhenOrderHasNoLines() {
    SalesOrder order = newDraftOrderWithBuyer();

    assertThrows(
        IllegalStateException.class,
        () -> order.confirm(Instant.parse("2026-11-18T03:00:00Z"))
    );

    assertEquals(SalesOrderStatus.DRAFT, order.status());
    assertTrue(order.domainEvents().isEmpty());
}
~~~

Test không chỉ kiểm tra exception. Nó còn xác nhận trạng thái không thay đổi và không có event được ghi nhận khi hành động thất bại.

### 8.3. Test không cho xác nhận lần thứ hai

~~~java
@Test
void rejectsConfirmationOfAlreadyConfirmedOrder() {
    SalesOrder order = newDraftOrderWithBuyer();
    order.addLine(line("PRODUCT-1", 1, "100000"));
    order.confirm(NOW);

    assertThrows(
        IllegalStateException.class,
        () -> order.confirm(NOW.plusSeconds(1))
    );

    assertEquals(SalesOrderStatus.CONFIRMED, order.status());
    assertEquals(1, order.domainEvents().size());
}
~~~

Đây là một ví dụ về state transition. Một hành động không hợp lệ không được tạo thêm event hoặc làm thay đổi trạng thái đã xác nhận.

### 8.4. Test Value Object và dòng hàng

Các test độc lập nên kiểm tra:
- Quantity bằng 0 hoặc âm bị từ chối.
- Money âm bị từ chối.
- Cộng hai Money khác currency bị từ chối.
- Line total bằng unit price nhân quantity.
- Giá trị tiền giữ đúng precision và rounding theo chính sách.

Những test này giúp tìm lỗi gần nơi quy tắc được định nghĩa và chạy rất nhanh.

## 9. Viết acceptance criteria cho use case

### 9.1. Tiêu chí AC-01: xác nhận thành công

**Given**
- Một Sales Order ở trạng thái Draft.
- Đơn có Buyer.
- Đơn có hai dòng hợp lệ: 2 sản phẩm A giá 100.000 đồng và 1 sản phẩm B giá 50.000 đồng.

**When**
- Người mua xác nhận đơn.

**Then**
- Đơn chuyển sang Confirmed.
- Tổng tiền là 250.000 đồng.
- Một sự kiện SalesOrderConfirmed được ghi nhận cho đúng SalesOrderId.

### 9.2. Tiêu chí AC-02: từ chối đơn không có dòng hàng

**Given**
- Một Sales Order ở trạng thái Draft.
- Đơn có Buyer nhưng không có dòng hàng.

**When**
- Người mua xác nhận đơn.

**Then**
- Hành động bị từ chối với lý do đơn cần ít nhất một dòng hàng.
- Trạng thái vẫn là Draft.
- Không có SalesOrderConfirmed event được ghi nhận.

### 9.3. Tiêu chí AC-03: từ chối xác nhận lại

**Given**
- Một Sales Order đã ở trạng thái Confirmed.

**When**
- Người mua gửi lại lệnh xác nhận.

**Then**
- Hệ thống từ chối vì trạng thái hiện tại không cho phép xác nhận.
- Không tạo thêm sự kiện xác nhận.
- Dữ liệu đơn không thay đổi.

### 9.4. Tiêu chí AC-04: dữ liệu đầu vào không hợp lệ

**Given**
- Một yêu cầu tạo dòng hàng có quantity bằng 0.

**When**
- Hệ thống tiếp nhận yêu cầu.

**Then**
- Yêu cầu bị từ chối với lỗi validation phù hợp.
- Dòng hàng không được thêm vào đơn.

Tiêu chí này có thể được kiểm tra ở domain boundary hoặc API tùy cách hệ thống phân chia trách nhiệm. Điều quan trọng là không để một dòng hàng không hợp lệ đi vào Aggregate.

## 10. Viết Gherkin để chuyên gia và đội phát triển cùng đọc

### 10.1. Feature cho xác nhận đơn

Một file Feature có thể mô tả các ví dụ:

~~~gherkin
Feature: Xác nhận Sales Order

  Rule: Chỉ đơn Draft có dữ liệu hợp lệ mới được xác nhận

    Scenario: Xác nhận đơn có hai dòng hàng hợp lệ
      Given một Sales Order Draft của buyer "BUYER-1"
      And đơn có dòng hàng "PRODUCT-A" số lượng 2 đơn giá 100000 VND
      And đơn có dòng hàng "PRODUCT-B" số lượng 1 đơn giá 50000 VND
      When buyer "BUYER-1" xác nhận đơn
      Then trạng thái đơn là "CONFIRMED"
      And tổng tiền đơn là 250000 VND
      And có một sự kiện "SalesOrderConfirmed"

    Scenario: Không xác nhận đơn chưa có dòng hàng
      Given một Sales Order Draft của buyer "BUYER-1"
      When buyer "BUYER-1" xác nhận đơn
      Then yêu cầu bị từ chối với lý do "ORDER_HAS_NO_LINES"
      And trạng thái đơn vẫn là "DRAFT"
      And không có sự kiện "SalesOrderConfirmed"

    Scenario: Không xác nhận lại đơn đã xác nhận
      Given một Sales Order đã ở trạng thái "CONFIRMED"
      When buyer "BUYER-1" xác nhận đơn
      Then yêu cầu bị từ chối với lý do "ORDER_NOT_DRAFT"
      And chỉ có một sự kiện "SalesOrderConfirmed"
~~~

Tên trạng thái và mã lý do là một phần hợp đồng ví dụ. Dự án thật nên dùng thuật ngữ mà chuyên gia hiểu, đồng thời giữ mapping rõ ràng sang error code kỹ thuật.

### 10.2. Scenario Outline cho nhiều trường hợp dữ liệu

Khi cùng một quy tắc cần kiểm tra với nhiều dữ liệu, dùng Scenario Outline:

~~~gherkin
Scenario Outline: Từ chối dòng hàng có quantity không hợp lệ
  Given một Sales Order Draft của buyer "BUYER-1"
  When thêm dòng hàng "PRODUCT-A" với quantity <quantity>
  Then dòng hàng bị từ chối

  Examples:
    | quantity |
    | 0        |
    | -1       |
~~~

Không dùng Scenario Outline chỉ để rút ngắn file. Nếu mỗi ví dụ có ý nghĩa hoặc kết quả khác nhau, scenario riêng thường dễ đọc hơn.

### 10.3. Gắn rule với nguồn quyết định

Mỗi Feature hoặc Scenario có thể tham chiếu mã yêu cầu hoặc ticket. Tuy nhiên, không nên biến file Gherkin thành bản sao của hệ thống quản lý công việc. Hãy giữ nội dung tập trung vào hành vi và liên kết đến nguồn quyết định ở metadata hoặc tài liệu liên quan.

## 11. Kết nối Gherkin với code kiểm thử

### 11.1. Step definition chuyển ngôn ngữ nghiệp vụ thành thao tác test

Một step definition có thể gọi test fixture hoặc application boundary:

~~~java
@Given("một Sales Order Draft của buyer {string}")
public void createDraftOrder(String buyerCode) {
    testContext.order = testContext.orderFixture
        .draftFor(new BuyerId(buyerCode));
}

@When("buyer {string} xác nhận đơn")
public void confirmOrder(String buyerCode) {
    testContext.result = testContext.confirmOrderUseCase
        .execute(testContext.order.id(), new BuyerId(buyerCode));
}

@Then("trạng thái đơn là {string}")
public void assertOrderStatus(String expectedStatus) {
    SalesOrder reloaded =
        testContext.orderRepository.get(testContext.order.id());

    assertEquals(
        SalesOrderStatus.valueOf(expectedStatus),
        reloaded.status()
    );
}
~~~

Đây là khung minh họa. Step definition cần có test context, fixture và cách ánh xạ kết quả phù hợp với framework đang dùng. Không nên để mỗi step tự tạo database connection hoặc chứa toàn bộ logic nghiệp vụ.

### 11.2. Step definition nên mỏng

Step definition nên:
- Chuyển dữ liệu từ Gherkin sang kiểu miền.
- Gọi use case hoặc API.
- Lưu kết quả để bước Then xác minh.
- Không tự thực hiện quy tắc mà hệ thống cần kiểm thử.

Nếu step definition tự tính tổng tiền hoặc tự kiểm tra trạng thái theo cùng thuật toán production, test có thể xác nhận chính logic test thay vì logic ứng dụng.

### 11.3. Chọn ranh giới thực thi

Một acceptance test có thể chạy:
- Qua HTTP API để kiểm tra toàn bộ request/response boundary.
- Qua application use case để kiểm tra điều phối và persistence.
- Qua message consumer để kiểm tra integration flow.
- Qua UI khi hành vi giao diện là một phần tiêu chí.

Không phải mọi scenario đều cần chạy qua browser. Hãy chọn ranh giới thấp nhất vẫn chứng minh được hành vi mà tiêu chí yêu cầu.

## 12. Kiểm tra sự kiện và tác động phụ

### 12.1. Phân biệt event được ghi nhận với event đã giao

Khi Aggregate xác nhận đơn, nó có thể ghi nhận Domain Event trong bộ nhớ. Application layer lưu Aggregate và event/outbox trong cùng transaction. Một publisher khác giao message sau đó.

Do đó, tiêu chí cần nói rõ điều gì được cam kết:
- Domain Event được tạo trong mô hình.
- Outbox record được lưu cùng transaction.
- Message được broker nhận.
- Consumer hoàn thành xử lý.

Đây là các mốc khác nhau. Không viết Then “event đã được xử lý” nếu acceptance test chỉ xác nhận một outbox row tồn tại.

### 12.2. Test transactional outbox

Với yêu cầu event chỉ được công bố sau khi đơn được lưu thành công, integration test có thể xác nhận:
- Khi xác nhận thành công, Order và Outbox record cùng commit.
- Khi transaction rollback, không có Outbox record.
- Publisher có thể gửi lại message mà không làm consumer áp dụng hành vi hai lần.

Không cần khởi động toàn bộ hệ thống production nếu test database và broker test đủ kiểm tra ranh giới đang quan tâm.

### 12.3. Idempotency của command

Nếu client gửi lại command do timeout, hệ thống cần quy tắc riêng về idempotency. Việc đơn đã Confirmed không nhất thiết có nghĩa lần gửi lại phải tạo lỗi; API có thể trả kết quả đã xác nhận trước đó nếu cùng idempotency key và cùng request.

Tiêu chí cần phân biệt:
- Cùng command và cùng idempotency key.
- Cùng command nhưng key khác.
- Cùng key nhưng payload khác.
- Command mới trên đơn đã xác nhận.

Đây là các tình huống khác nhau, không nên gộp thành một scenario “xác nhận hai lần”.

## 13. Kiểm thử ranh giới và trường hợp biên

### 13.1. Kiểm tra giá trị ở ngưỡng

Với quantity, kiểm tra:
- Giá trị nhỏ hơn 1.
- Đúng 1.
- Giá trị lớn hơn 1.

Với Money, kiểm tra:
- Giá trị âm.
- Bằng 0 nếu được phép.
- Giá trị dương.
- Currency không khớp.
- Precision và rounding theo chính sách.

### 13.2. Kiểm tra trạng thái trước và sau hành động

Một state transition nên có:
- Trạng thái được phép.
- Hành động hợp lệ.
- Trạng thái đích.
- Trạng thái không được phép.
- Kết quả khi hành động thất bại.

Ví dụ Draft -> Confirmed là chuyển đổi hợp lệ. Confirmed -> Confirmed qua lệnh xác nhận lại có thể bị từ chối hoặc trả lại kết quả idempotent tùy hợp đồng. Quyết định này phải được chuyên gia và product owner xác nhận.

### 13.3. Kiểm tra dữ liệu thiếu và sai phạm vi

Một ID có định dạng hợp lệ nhưng không thuộc tenant hiện tại không đồng nghĩa người gọi có quyền truy cập. Acceptance test bảo mật cần kiểm tra quyền truy cập và tenant scope nếu chúng là tiêu chí của chức năng.

Tương tự, một BuyerId tồn tại ở Customer Context không tự động có nghĩa Buyer được phép đặt đơn trong Sales Context. Quy tắc này cần được làm rõ và kiểm tra qua integration boundary phù hợp.

### 13.4. Kiểm tra cạnh tranh khi có invariant dùng chung

Nếu hai yêu cầu cùng xác nhận một đơn, hoặc cùng tiêu thụ một tài nguyên có giới hạn, test unit đơn luồng không chứng minh được concurrency safety.

Nếu đây là rủi ro nghiệp vụ, acceptance/integration test cần chạy nhiều request đồng thời với persistence thật và xác minh invariant sau commit. Không nên tạo test đồng thời phức tạp cho một quy tắc không có shared mutable state.

## 14. Chọn đúng loại kiểm thử cho từng tiêu chí

| Loại kiểm thử | Ranh giới | Điều nên xác minh |
|---|---|---|
| Unit/domain test | Value Object, Entity, Aggregate | Invariant và hành vi miền |
| Application service test | Use case | Điều phối, quyền gọi và kết quả |
| Integration test | Database, repository, outbox | Mapping, transaction, persistence |
| Contract test | API hoặc message schema | Producer/consumer tương thích |
| Acceptance test | Ranh giới chức năng đã chọn | Tiêu chí người dùng/nghiệp vụ |
| UI test | Giao diện | Hành vi tương tác cần thiết |

### 14.1. Kim tự tháp kiểm thử

~~~text
             /\
            /  \
           / UI \          Ít, chậm, qua giao diện
          /------\
         /Acceptance\      Một số luồng nghiệp vụ trọng yếu
        /------------\
       / Integration  \    Adapter, database, message
      /----------------\
     / Domain / Unit    \  Nhiều, nhanh, kiểm tra rule
    /____________________\
~~~

Phần lớn quy tắc miền nên được kiểm tra bằng unit/domain test nhanh. Acceptance test nên tập trung vào các luồng quan trọng và ranh giới thực tế. Nếu mọi rule đều chạy qua UI, bộ test sẽ chậm và khó chẩn đoán.

### 14.2. Một tiêu chí có thể được kiểm tra ở nhiều lớp

Ví dụ “đơn rỗng không thể xác nhận” có thể có:
- Domain test chứng minh Aggregate từ chối.
- Acceptance test chứng minh API trả response đúng và dữ liệu không đổi.

Hai test có mục đích khác nhau. Domain test kiểm tra quy tắc; acceptance test kiểm tra hành vi được cung cấp cho caller.

## 15. Duy trì chất lượng của executable acceptance criteria

### 15.1. Dùng dữ liệu có ý nghĩa

Ưu tiên fixture dễ đọc:
- Buyer có mã rõ ràng.
- Đơn có dòng hàng và giá cụ thể.
- Trạng thái được nêu trong Given.
- Kết quả được kiểm tra bằng business term.

Tránh fixture ngẫu nhiên hoặc phụ thuộc vào dữ liệu dùng chung giữa các test. Mỗi scenario nên tự thiết lập bối cảnh cần thiết.

### 15.2. Không lặp logic production trong test

Nếu test tự tính tổng tiền bằng cùng đoạn code với production, nó có thể lặp lại cùng lỗi. Hãy dùng kết quả mong đợi được tính độc lập từ ví dụ cụ thể.

Ví dụ 2 x 100.000 + 1 x 50.000 = 250.000 là một oracle dễ kiểm tra. Không gọi chính phương thức total() để tính expected value.

### 15.3. Giữ scenario độc lập và có thể chạy riêng

Một scenario không nên phụ thuộc scenario trước đã tạo dữ liệu. Mỗi test phải thiết lập Given của chính nó và dọn dẹp dữ liệu theo chiến lược cô lập.

Nếu dùng database, có thể dùng transaction rollback, schema riêng hoặc dữ liệu có namespace. Với message broker, cần topic hoặc correlation riêng và chờ điều kiện cụ thể thay vì sleep tùy tiện.

### 15.4. Tránh test phụ thuộc thứ tự hoặc thời gian thực

Dùng Clock cố định nếu quy tắc phụ thuộc thời gian. Không dùng Thread.sleep để chờ một trạng thái có thể kiểm tra bằng polling có timeout hoặc cơ chế đồng bộ của test framework.

Không dùng ngày hiện tại trong ví dụ nếu nó làm kết quả thay đổi theo thời gian.

### 15.5. Tránh Gherkin dài và trừu tượng

Một Feature nên phản ánh một năng lực nghiệp vụ. Nếu scenario có quá nhiều bước kỹ thuật, nhiều đối tượng không liên quan hoặc Then khó hiểu với chuyên gia, hãy chia nhỏ.

Step phrase dùng chung cần có ý nghĩa ổn định. Đừng tạo một step chung như “hệ thống xử lý dữ liệu” có thể làm bất cứ điều gì.

### 15.6. Cập nhật tiêu chí khi quy tắc thay đổi

Khi chuyên gia xác nhận chính sách mới:
1. Cập nhật rule và ví dụ.
2. Cập nhật acceptance criteria.
3. Điều chỉnh test bị ảnh hưởng.
4. Cập nhật mô hình và code.
5. Chạy bộ test liên quan và toàn bộ kiểm tra cần thiết.

Nếu test thất bại vì chính sách đã thay đổi, đừng xóa test ngay. Xác nhận thay đổi với người sở hữu nghiệp vụ rồi cập nhật đặc tả để giữ lịch sử quyết định nếu cần.

## 16. Những sai lầm thường gặp

### Viết tiêu chí bằng từ mơ hồ

“Đơn hợp lệ”, “xử lý nhanh” hoặc “khách đủ điều kiện” không thể kiểm thử nếu không định nghĩa. Hãy chuyển thành điều kiện cụ thể và kết quả đo được.

### Chỉ viết happy path

Nếu chỉ kiểm tra trường hợp thành công, các rule về trạng thái, dữ liệu thiếu và biên thường bị bỏ sót. Bổ sung ví dụ từ chối và trường hợp ngoại lệ.

### Đưa giải pháp kỹ thuật vào tiêu chí nghiệp vụ

“Dùng Redis cache trong 5 phút” là quyết định kỹ thuật nếu người dùng không yêu cầu cam kết đó. Acceptance criteria nên mô tả hành vi và chất lượng dịch vụ có ý nghĩa.

### Viết Gherkin sau khi code xong để hợp thức hóa

Khi ví dụ chỉ được viết sau implementation, chúng có thể chỉ mô tả cách code hiện tại hoạt động. Hãy dùng ví dụ để làm rõ và kiểm tra hiểu biết trước khi triển khai.

### Để step definition tự thực hiện quy tắc

Test có thể xanh dù production sai nếu step definition tính kết quả riêng. Step nên gọi hệ thống và xác minh kết quả.

### Chạy tất cả test qua UI

Điều này làm suite chậm, khó tìm nguyên nhân và dễ flaky. Dùng domain test cho rule, integration test cho adapter và acceptance test cho luồng trọng yếu.

### Kiểm tra implementation thay vì hành vi

Assert số lần gọi private helper hoặc thứ tự method nội bộ làm test dễ vỡ khi refactor. Kiểm tra kết quả nghiệp vụ và side effect có ý nghĩa.

### Không ghi nhận câu hỏi chưa được giải quyết

Giả định không được xác nhận có thể trở thành rule sai. Giữ danh sách Questions và giao người chịu trách nhiệm trả lời.

### Dùng chung dữ liệu giữa các scenario

Scenario phụ thuộc nhau gây lỗi khó tái hiện khi chạy riêng hoặc song song. Tạo dữ liệu độc lập và kiểm soát side effect.

### Nhầm event được tạo với event được xử lý

Một outbox row chưa chứng minh consumer đã xử lý. Tiêu chí phải xác định chính xác ranh giới và trạng thái cần kiểm tra.

## 17. Bài tập thực hành: làm rõ quy tắc hủy đơn

Một nền tảng thương mại điện tử cho phép người mua yêu cầu hủy đơn. Nhóm nghiệp vụ cung cấp thông tin ban đầu:

- Đơn Draft có thể hủy.
- Đơn Confirmed có thể hủy nếu Fulfillment chưa bắt đầu xử lý.
- Nếu Fulfillment đã bắt đầu picking, cần một quy trình yêu cầu hủy riêng.
- Nếu hàng đã được bàn giao cho đơn vị vận chuyển, người mua cần dùng quy trình trả hàng.
- Khi hủy thành công, Sales phải phát sự kiện để các context liên quan xử lý.

Hãy thực hiện:

1. Tổ chức Example Mapping với Story, Rules, Examples và Questions.
2. Hỏi chuyên gia định nghĩa chính xác “Fulfillment đã bắt đầu”.
3. Làm rõ trạng thái của đơn nếu yêu cầu hủy đang chờ phản hồi.
4. Viết decision table cho Draft, Confirmed, Picking, Dispatched và Delivered.
5. Viết Given–When–Then cho trường hợp hủy thành công và bị từ chối.
6. Xác định Aggregate nào sở hữu quyết định hủy.
7. Thiết kế integration event hoặc command để phối hợp với Fulfillment.
8. Viết domain test cho state transition và acceptance test qua use case.
9. Kiểm tra message lặp và phản hồi đến muộn.
10. Xác nhận các tiêu chí với chuyên gia trước khi coi chúng là đặc tả chính thức.

### 17.1. Mẫu bảng quyết định

| Trạng thái Sales | Trạng thái Fulfillment | Kết quả cần làm rõ |
|---|---|---|
| Draft | Chưa tạo | Có thể hủy trực tiếp |
| Confirmed | Chưa bắt đầu | Có thể yêu cầu hủy |
| Confirmed | Picking | Chuyển quy trình yêu cầu hủy |
| Confirmed | Dispatched | Dùng quy trình trả hàng |
| Confirmed | Delivered | Dùng quy trình trả hàng/hoàn tiền |

Bảng này là giả thuyết ban đầu. Chuyên gia cần xác nhận trạng thái nào thực sự tồn tại và điều kiện chuyển giữa chúng. Không tự giả định mọi trạng thái Fulfillment đều có thể được đọc đồng bộ từ Sales.

## 18. Checklist biến ví dụ thành tiêu chí chấp nhận thực thi được

Trước khi đưa một chức năng vào phát triển hoặc nghiệm thu, hãy kiểm tra:

- Story mô tả đúng nhu cầu và người sử dụng.
- Thuật ngữ được thống nhất với chuyên gia nghiệp vụ.
- Rule được tách khỏi ví dụ cụ thể.
- Có happy path, negative path và trường hợp biên.
- Câu hỏi chưa giải quyết được ghi nhận rõ.
- Decision table bao phủ các điều kiện quan trọng.
- Given mô tả bối cảnh nghiệp vụ cụ thể.
- When có hành động hoặc sự kiện rõ ràng.
- Then mô tả kết quả quan sát được.
- Mỗi scenario tập trung vào một hành vi chính.
- Tiêu chí không áp đặt chi tiết nội bộ không cần thiết.
- Test gọi hệ thống thật qua ranh giới phù hợp.
- Step definition không lặp logic production.
- Domain invariant được kiểm tra gần mô hình.
- Persistence, outbox và message được kiểm tra ở integration boundary.
- Dữ liệu test độc lập và kết quả lặp lại được.
- Clock, timezone và concurrency được kiểm soát khi có liên quan.
- Event được tạo, được giao và được consumer xử lý được phân biệt.
- Tiêu chí có người sở hữu và được cập nhật khi rule đổi.

## Kết luận

Biến ví dụ nghiệp vụ thành tiêu chí chấp nhận có thể thực thi bắt đầu bằng việc hiểu đúng tình huống, không phải bằng việc viết test framework. Example Mapping giúp đội ngũ làm rõ Story, Rules, Examples và Questions. Decision table giúp nhìn thấy các tổ hợp điều kiện. Given–When–Then diễn đạt bối cảnh, hành động và kết quả bằng ngôn ngữ chung.

Khi các tiêu chí được tự động hóa ở ranh giới phù hợp, chúng trở thành đặc tả sống của mô hình miền. Domain test bảo vệ invariant, integration test xác nhận persistence và message, còn acceptance test chứng minh luồng nghiệp vụ mà người dùng quan tâm. Cách làm này giúp chuyên gia, lập trình viên và kiểm thử viên cùng hiểu một hành vi, phát hiện giả định sai sớm và giữ cho mô hình DDD phản ánh đúng quy tắc của tổ chức.

