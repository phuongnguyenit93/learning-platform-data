# Đánh giá cấu trúc mới bằng khả năng hiểu và thực hiện thay đổi

Trong chương **Tái cấu trúc** của module **CODE_QUALITY_FUNDAMENTALS**, chúng ta tập trung vào một câu hỏi quan trọng sau khi refactor: **cấu trúc mới có thật sự giúp người khác hiểu hệ thống và thực hiện những thay đổi tiếp theo an toàn hơn không?**

Mục tiêu của **CODE_QUALITY_FUNDAMENTALS** là hiểu những thuộc tính quyết định mã nguồn có **đáng tin cậy, dễ hiểu và dễ thay đổi** hay không. Một lần tái cấu trúc có thể khiến phương thức ngắn hơn, số cảnh báo của công cụ giảm và sơ đồ lớp trông cân đối hơn. Nhưng nếu người bảo trì phải lần qua nhiều interface không cần thiết, sửa ba nơi cho một quy tắc, hoặc không biết test nào bảo vệ hành vi, cấu trúc mới chưa chắc tốt hơn.

> **Đánh giá refactoring bằng những công việc mà mã cần phục vụ: người đọc có tìm đúng nơi chịu trách nhiệm, hiểu hợp đồng, sửa một yêu cầu thật và xác minh hành vi dễ hơn không?**

Bài học này đi từ việc xác định tiêu chí đánh giá, minh họa bằng mã Java trước–sau refactor, đến cách thử một tình huống thay đổi giả định và ra quyết định dựa trên bằng chứng. Tập trung là **chất lượng của cấu trúc mới**, không phải đếm số dòng được xóa.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

1. Phân biệt **refactor giữ nguyên hành vi** với **sửa lỗi** và **bổ sung tính năng**.
2. Xác định dấu hiệu cấu trúc hỗ trợ **khả năng hiểu**: trách nhiệm rõ, dữ liệu có tên, luồng điều khiển truy vết được, phụ thuộc tường minh và bất biến dễ thấy.
3. Xác định dấu hiệu hỗ trợ **khả năng thay đổi**: đúng chỗ cần sửa, ít điểm đồng bộ, tác động được giới hạn và có cách kiểm chứng.
4. Lập **tình huống thay đổi đại diện** để so sánh cấu trúc trước–sau, thay vì chỉ xem chỉ số tĩnh.
5. Sử dụng ví dụ Java/JUnit 5 để bảo vệ hành vi khi tập trung một quy tắc nghiệp vụ bị sao chép.
6. Phân biệt độ phức tạp giảm thật với độ phức tạp chỉ bị **dời sang nhiều lớp hoặc interface**.
7. Thiết kế phép quan sát về khả năng hiểu, thời gian tìm nơi sửa, phạm vi thay đổi và rủi ro hồi quy mà không đưa ra kết luận quá mức.
8. Viết nhận xét code review giải thích **vì sao cấu trúc mới tốt hơn hoặc chưa tốt hơn** bằng hành vi và tình huống cụ thể.

## 2. “Tốt hơn” phải được định nghĩa trước khi refactor

Tái cấu trúc (*refactoring*) thường nhằm cải thiện **thiết kế nội bộ trong khi giữ nguyên hành vi quan sát được theo hợp đồng hiện tại**. Trong phạm vi đó, một phép đổi tên, trích xuất phương thức hay di chuyển quy tắc nghiệp vụ không nên tự ý đổi số tiền được tính, điều kiện ném ngoại lệ hoặc tác dụng phụ.

Một thay đổi cấu trúc được kỳ vọng cải thiện một hoặc vài thuộc tính:

| Thuộc tính | Câu hỏi đánh giá | Bằng chứng nên tìm |
| --- | --- | --- |
| **Dễ hiểu** | Người mới có biết logic nào quyết định kết quả không? | Đọc được ý định, lần theo phụ thuộc hợp lý, giải thích đúng bất biến. |
| **Dễ thay đổi** | Một yêu cầu tương tự có cần sửa đúng trách nhiệm không? | Số nơi phải cập nhật, mối phụ thuộc, phạm vi diff và thời gian tìm đúng nơi. |
| **Dễ kiểm thử** | Có thể tạo đầu vào và quan sát kết quả mà không dựng cả hệ thống không? | Unit test ở ranh giới có ý nghĩa, khả năng fake phụ thuộc cần thiết. |
| **Đáng tin cậy** | Hợp đồng cũ có được bảo vệ trong refactor không? | Test hồi quy, kiểm thử tích hợp phù hợp, xác minh ngoại lệ và tác dụng phụ. |
| **Dễ vận hành** | Sự cố có dễ xác định nguyên nhân và khôi phục hơn không? | Trách nhiệm rõ, thông tin chẩn đoán phù hợp, ranh giới dữ liệu và tài nguyên. |
| **Chi phí hợp lý** | Lợi ích có xứng với lớp trừu tượng và cách quản lý mới không? | Số khái niệm phải hiểu, phụ thuộc mới, migration và chi phí cập nhật lâu dài. |

**Tính đúng đắn là ràng buộc**, không phải lợi ích có thể đánh đổi tùy ý. Nếu sau refactor tính phí sai nhưng thời gian đọc mã giảm, đó không phải một refactor hoàn thành an toàn.

### 2.1. Đặt mục tiêu theo người sử dụng mã

Đánh giá phải gắn với công việc thực:

- Người review muốn biết thay đổi có làm mất một nhánh nghiệp vụ không.
- Người bảo trì muốn sửa chính sách trong một chỗ rõ trách nhiệm.
- Người kiểm thử muốn tạo được ca ở đúng ngưỡng mà không gửi giao dịch thật.
- Người vận hành muốn biết nơi cấu hình, phiên bản chính sách và cách rollback.
- Người tích hợp muốn hợp đồng API không thay đổi ngoài chủ đích.

Một bản refactor có thể tốt cho người đọc logic, nhưng gây khó cho nhóm triển khai nếu đưa thêm bước cấu hình không được mô tả. Vì vậy cần xem **toàn bộ công việc liên quan**.

## 3. Đừng coi điểm số hình thức là câu trả lời cuối

Một số tín hiệu thường được dùng để tuyên bố refactor thành công:

- Số dòng giảm từ 300 xuống 100.
- Một phương thức được chia thành mười phương thức nhỏ.
- Cyclomatic complexity của hàm chính giảm.
- Không còn mã lặp theo công cụ.
- Nhiều interface được tạo “để dễ mở rộng”.
- Test coverage tăng.

Đây có thể là thông tin hữu ích, nhưng **không trực tiếp trả lời** liệu người khác hiểu hoặc thay đổi mã dễ hơn.

### 3.1. Độ phức tạp có thể chỉ được phân tán

Trước:

~~~java
long fee(Order order) {
    // Một phương thức lớn với nhiều quyết định rõ ngay tại đây.
    return computeFee(order);
}
~~~

Sau:

~~~java
long fee(Order order) {
    return resolver.resolve(contextFactory.create(order))
            .strategy()
            .execute();
}
~~~

Mã ở phương thức `fee` đã ngắn, nhưng việc hiểu kết quả đòi người đọc tìm tới `resolver`, `contextFactory`, `strategy` và `execute`. Nếu các thành phần này có nhiệm vụ độc lập, sự phân tách có thể hợp lý. Nếu chỉ có một chính sách cố định, nó có thể làm tăng **chi phí điều hướng**.

**Câu hỏi đúng:** có một khái niệm mới và một ranh giới trách nhiệm thật hay chỉ thêm tầng trung gian?

### 3.2. Loại bỏ lặp cú pháp không luôn loại bỏ chi phí

Hai phần mã giống nhau có thể biểu diễn **hai quy tắc độc lập**. Gộp chúng chỉ vì giống hình dạng có thể khiến hai nhóm sản phẩm phải thay đổi cùng một thư viện dù nhu cầu khác nhau.

Ngược lại, hai đoạn chỉ vài dòng nhưng cùng định nghĩa một chính sách phải luôn nhất quán có thể tạo rủi ro cập nhật thiếu. Cần đánh giá **tri thức bị nhân bản**, không chỉ tỷ lệ token lặp.

### 3.3. Một chỉ số tăng còn có thể che vấn đề khác

Độ bao phủ nhánh 100% không chứng minh quy tắc miễn phí ở đúng ngưỡng đã được test. Một class mới có ít phụ thuộc trực tiếp nhưng có thể vẫn truy cập singleton toàn cục. Một PR ít file sửa có thể chỉ chuyển logic sang một bộ cấu hình khó tìm.

Vì vậy, nên dùng metric để **gợi ý nơi cần xem**, rồi thử câu hỏi và nhiệm vụ cụ thể.

## 4. Xây dựng đường cơ sở: trước khi sửa, ai đang gặp khó gì?

Nếu không ghi lại vấn đề ban đầu, sau refactor ta thường chỉ có cảm giác “mã nhìn sạch hơn”. Một đánh giá có căn cứ nên xác định:

1. **Tình huống thay đổi:** lần tới cần thêm điều kiện, sửa công thức, thay provider hay thêm loại dữ liệu nào?
2. **Nơi người đọc phải tìm:** có bao nhiêu nơi chứa cùng quyết định; trách nhiệm có rõ không?
3. **Các điều kiện rủi ro:** dữ liệu âm, null, đúng ngưỡng, đồng thời, thất bại của phụ thuộc?
4. **Bằng chứng hiện có:** test, lịch sử PR, lỗi hồi quy hoặc nhận xét review?
5. **Ràng buộc không được phá:** API, thứ tự tác dụng phụ, tính nhất quán, định dạng dữ liệu, hiệu năng?
6. **Mục tiêu thực tế:** giảm số bản sao quy tắc, tăng khả năng cô lập test, giảm lần sửa thiếu hoặc làm rõ điểm sở hữu?

### 4.1. Mô tả bằng tình huống thay vì nhãn “mùi mã”

Không nên chỉ ghi:

> “Có duplicate code, cần trích xuất.”

Nên ghi:

> “Khi thêm một hạng khách hàng mới, hai màn hình báo phí dự tính đều phải cập nhật cùng một chính sách. Hiện tại chính sách nằm ở hai class và không có test chung cho cả hai. Refactor nên tạo một điểm sở hữu quy tắc, giúp lần thêm hạng tiếp theo không phải nhân bản điều kiện.”

Mô tả thứ hai cung cấp **tình huống tương lai, nguyên nhân và tiêu chí kiểm chứng**.

## 5. Ví dụ Java: hai đường báo giá đang nhân bản cùng chính sách

Giả sử ứng dụng có hai màn hình cho khách xem **phí vận chuyển dự tính hiện tại**:

- Checkout preview.
- Delivery estimate preview.

Cả hai phải dùng **cùng chính sách**:

- `STANDARD` miễn phí vận chuyển từ 500.000 đơn vị tiền nhỏ nhất.
- `PREMIUM` miễn phí từ 300.000.
- Thấp hơn ngưỡng tương ứng chịu phí 30.000.
- Ngưỡng áp dụng cho tổng tiền hàng **trước chiết khấu**.
- Tổng tiền hàng âm là dữ liệu không hợp lệ.
- Hạng khách hàng `null` là không hợp lệ.

**Giả định quan trọng:** đây là hai tính năng dự tính phí hiện hành, không phải xem lại hóa đơn đã chốt trong quá khứ. Hóa đơn lịch sử có thể cần đọc số tiền đã lưu thay vì tính lại theo chính sách mới.

### 5.1. Cấu trúc ban đầu

~~~java
import java.util.Objects;

enum CustomerTier {
    STANDARD, PREMIUM
}

final class CheckoutPreview {
    long shippingFee(long subtotalCents, CustomerTier tier) {
        if (subtotalCents < 0) {
            throw new IllegalArgumentException("Negative subtotal");
        }
        Objects.requireNonNull(tier, "tier");

        long threshold =
                tier == CustomerTier.PREMIUM ? 300_000 : 500_000;
        return subtotalCents >= threshold ? 0 : 30_000;
    }
}

final class DeliveryEstimatePreview {
    long shippingFee(long subtotalCents, CustomerTier tier) {
        if (subtotalCents < 0) {
            throw new IllegalArgumentException("Negative subtotal");
        }
        Objects.requireNonNull(tier, "tier");

        long threshold =
                tier == CustomerTier.PREMIUM ? 300_000 : 500_000;
        return subtotalCents >= threshold ? 0 : 30_000;
    }
}
~~~

Hai phương thức ngắn, dễ đọc và trả kết quả đúng với đặc tả hiện tại. Vấn đề không phải chúng “trông xấu”; vấn đề là **một quy tắc duy nhất có hai nơi có thể sửa độc lập**.

### 5.2. Thử tình huống thay đổi trước refactor

Yêu cầu giả định tiếp theo:

> “Thêm hạng `VIP`, miễn phí vận chuyển từ 200.000. Cả hai màn hình dự tính phải dùng cùng chính sách mới.”

Với thiết kế hiện tại, người bảo trì cần:

1. Thêm `VIP` vào `CustomerTier`.
2. Tìm tất cả nơi dùng biểu thức `tier == PREMIUM ? 300_000 : 500_000`.
3. Sửa điều kiện ở ít nhất hai class.
4. Xác minh không có nơi nào khác vẫn coi `VIP` là `STANDARD`.
5. Chạy test cho hai màn hình.

Đây là **kịch bản đánh giá**, chưa phải yêu cầu được triển khai trong bài. Nó cho ta một cách hỏi cụ thể: **“Cấu trúc sau refactor có làm yêu cầu thêm VIP dễ tìm, ít nơi sửa và an toàn hơn không?”**

### 5.3. Nguy cơ của nhánh mặc định

Trong mã ban đầu, `tier != PREMIUM` đều bị coi như STANDARD. Nếu chỉ thêm một enum `VIP` mà quên sửa một phương thức, test của STANDARD/PREMIUM vẫn có thể đỗ, trong khi VIP âm thầm nhận ngưỡng 500.000.

Đây là ví dụ quan trọng về **khả năng thay đổi**: ranh giới thiết kế nên giúp người sửa biết khi chính sách chưa định nghĩa hạng mới, thay vì lặng lẽ dùng một giá trị mặc định không có căn cứ.

## 6. Refactor để một thành phần sở hữu quyết định phí

Ta xác nhận một chính sách phục vụ cả hai màn hình. Một lựa chọn là đưa ngưỡng theo hạng vào đối tượng chính sách **bất biến**, có hợp đồng rõ. Ví dụ Java 17+:

~~~java
import java.util.Map;
import java.util.Objects;

final class ShippingPolicy {
    private final Map<CustomerTier, Long> freeFromCents;
    private final long flatFeeCents;

    ShippingPolicy(
            Map<CustomerTier, Long> freeFromCents,
            long flatFeeCents) {
        Objects.requireNonNull(freeFromCents, "freeFromCents");
        if (flatFeeCents < 0) {
            throw new IllegalArgumentException("Negative flat fee");
        }

        // Bản sao không thể sửa qua Map API.
        Map<CustomerTier, Long> snapshot = Map.copyOf(freeFromCents);

        // Mỗi hạng được hỗ trợ phải có ngưỡng rõ ràng.
        for (long threshold : snapshot.values()) {
            if (threshold < 0) {
                throw new IllegalArgumentException("Negative threshold");
            }
        }

        this.freeFromCents = snapshot;
        this.flatFeeCents = flatFeeCents;
    }

    long shippingFee(long subtotalCents, CustomerTier tier) {
        if (subtotalCents < 0) {
            throw new IllegalArgumentException("Negative subtotal");
        }
        Objects.requireNonNull(tier, "tier");

        Long threshold = freeFromCents.get(tier);
        if (threshold == null) {
            throw new IllegalArgumentException(
                    "No shipping policy for tier: " + tier);
        }

        return subtotalCents >= threshold ? 0 : flatFeeCents;
    }
}
~~~

Các thành phần giao diện chỉ còn vai trò gọi chính sách:

~~~java
final class CheckoutPreview {
    private final ShippingPolicy policy;

    CheckoutPreview(ShippingPolicy policy) {
        this.policy = java.util.Objects.requireNonNull(policy);
    }

    long shippingFee(long subtotalCents, CustomerTier tier) {
        return policy.shippingFee(subtotalCents, tier);
    }
}

final class DeliveryEstimatePreview {
    private final ShippingPolicy policy;

    DeliveryEstimatePreview(ShippingPolicy policy) {
        this.policy = java.util.Objects.requireNonNull(policy);
    }

    long shippingFee(long subtotalCents, CustomerTier tier) {
        return policy.shippingFee(subtotalCents, tier);
    }
}
~~~

Khởi tạo chính sách cho hai hạng ban đầu:

~~~java
ShippingPolicy policy = new ShippingPolicy(
        Map.of(
                CustomerTier.STANDARD, 500_000L,
                CustomerTier.PREMIUM, 300_000L),
        30_000L);

var checkout = new CheckoutPreview(policy);
var estimate = new DeliveryEstimatePreview(policy);

long feeA = checkout.shippingFee(400_000, CustomerTier.STANDARD); // 30_000
long feeB = estimate.shippingFee(400_000, CustomerTier.PREMIUM);   // 0
~~~

Để hiểu các đoạn mã, xem chúng như những phần của **một ví dụ hoàn chỉnh**, không đặt hai phiên bản `CheckoutPreview`/`DeliveryEstimatePreview` vào cùng một package và biên dịch đồng thời. Phiên bản trước và sau refactor được trình bày để so sánh thiết kế.

### 6.1. Cải thiện mong đợi là gì?

- **Một nơi quyết định phí:** `ShippingPolicy.shippingFee`.
- **Hợp đồng rõ:** tổng tiền âm, hạng null và hạng chưa được cấu hình được xử lý tường minh.
- **Ít nhân bản:** các màn hình không tự sao chép điều kiện.
- **Đầu vào điều khiển được:** test có thể tạo chính sách với ngưỡng riêng.
- **Không có state request:** đối tượng chính sách chỉ giữ cấu hình bất biến; mỗi lần tính dùng tham số riêng.

### 6.2. Đánh đổi và những gì chưa được giải quyết

Thiết kế mới thêm một class và một phép tra cứu Map. Nó cần nơi khởi tạo cấu hình và quy tắc quản lý phiên bản chính sách. Với một ứng dụng chỉ có một màn hình và hai hạng không bao giờ thay đổi, cách dùng Map có thể phức tạp hơn cần thiết.

`Map.copyOf` giữ một bản sao không thể sửa qua Map API; vì `CustomerTier` là enum và giá trị `Long` bất biến, dữ liệu ví dụ không có vấn đề đối tượng con mutable. Tuy nhiên, nó **không tự xác minh tất cả hạng enum đều được cấu hình**. Kiểm tra đó xảy ra khi gọi `shippingFee` hoặc cần bổ sung theo hợp đồng khởi tạo nếu hệ thống muốn fail-fast ngay lúc start.

Tập trung quy tắc không tự bảo đảm chính sách đúng với database, cấu hình production hay lịch sử đơn hàng. Đây là **lợi ích về cấu trúc và khả năng kiểm chứng**, không phải chứng minh toàn hệ thống đã đúng.

## 7. Refactor giữ hành vi: test những gì phải không đổi

Trước khi thêm VIP, cần xác minh phiên bản mới vẫn đáp ứng chính sách cho STANDARD/PREMIUM. Một số test minh họa với JUnit 5:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.Map;
import org.junit.jupiter.api.Test;

class ShippingPolicyTest {
    private final ShippingPolicy policy = new ShippingPolicy(
            Map.of(
                    CustomerTier.STANDARD, 500_000L,
                    CustomerTier.PREMIUM, 300_000L),
            30_000L);

    @Test
    void standardBelowThresholdPaysFlatFee() {
        assertEquals(30_000L,
                policy.shippingFee(499_999, CustomerTier.STANDARD));
    }

    @Test
    void standardAtThresholdGetsFreeShipping() {
        assertEquals(0L,
                policy.shippingFee(500_000, CustomerTier.STANDARD));
    }

    @Test
    void premiumBelowThresholdPaysFlatFee() {
        assertEquals(30_000L,
                policy.shippingFee(299_999, CustomerTier.PREMIUM));
    }

    @Test
    void premiumAtThresholdGetsFreeShipping() {
        assertEquals(0L,
                policy.shippingFee(300_000, CustomerTier.PREMIUM));
    }

    @Test
    void inputValidationRemainsExplicit() {
        assertThrows(IllegalArgumentException.class,
                () -> policy.shippingFee(-1, CustomerTier.STANDARD));
        assertThrows(NullPointerException.class,
                () -> policy.shippingFee(10_000, null));
    }

    @Test
    void bothEntryPointsUseTheSamePolicy() {
        var checkout = new CheckoutPreview(policy);
        var delivery = new DeliveryEstimatePreview(policy);

        assertEquals(
                checkout.shippingFee(400_000, CustomerTier.PREMIUM),
                delivery.shippingFee(400_000, CustomerTier.PREMIUM));
        assertEquals(0L,
                checkout.shippingFee(400_000, CustomerTier.PREMIUM));
    }
}
~~~

Test xác minh **một số trường hợp quan trọng** của hợp đồng, không chứng minh mọi giá trị `long` hoặc mọi tương tác với hệ thống ngoài. Có thể bổ sung property-based testing hoặc so sánh hai implementation trên một tập đầu vào nếu rủi ro đủ lớn.

### 7.1. Kiểm tra trường hợp cấu hình thiếu

~~~java
@Test
void missingTierPolicyFailsExplicitly() {
    ShippingPolicy incomplete = new ShippingPolicy(
            Map.of(CustomerTier.STANDARD, 500_000L),
            30_000L);

    assertThrows(IllegalArgumentException.class,
            () -> incomplete.shippingFee(
                    400_000, CustomerTier.PREMIUM));
}
~~~

Một hạng chưa có cấu hình sẽ bị từ chối thay vì vô tình dùng ngưỡng của STANDARD. Tuy nhiên, **đây là hành vi mới của một trường hợp cấu hình lỗi**, không thể tự coi mọi khía cạnh là refactor giữ nguyên hành vi tuyệt đối.

Trong một dự án thật, nếu chính sách cũ có hợp đồng đối với dữ liệu hạng lạ, cần xem việc đổi cách xử lý có phù hợp không. Có thể tách thành một quyết định sửa lỗi/validation rõ ràng thay vì lẫn vào thay đổi cấu trúc.

### 7.2. Test không nên kiểm tra tên helper private

Test tốt ở đây kiểm tra **phí, điều kiện biên, ngoại lệ và việc hai điểm nhập dùng cùng chính sách**. Không cần khẳng định “`ShippingPolicy` gọi đúng một phương thức private” hoặc “phải truy vấn Map đúng một lần”, nếu đó không phải hợp đồng.

Nhờ vậy, khi đổi Map thành một cách lưu khác nhưng vẫn đúng, test hành vi không phải sửa hàng loạt.

## 8. Thử một yêu cầu mới: thêm hạng VIP

Sau khi refactor và đã bảo vệ hành vi cũ, dùng lại **tình huống thay đổi** ở mục 5:

> “Thêm hạng VIP, miễn phí vận chuyển từ 200.000. Cả hai màn hình dự tính dùng chính sách mới, hai hạng cũ giữ nguyên.”

Đây là **feature change**, không còn là bước refactor giữ hành vi. Cần xử lý như một thay đổi hợp đồng có chủ đích.

### 8.1. Thay đổi ở mô hình hạng khách hàng

~~~java
enum CustomerTier {
    STANDARD, PREMIUM, VIP
}
~~~

### 8.2. Bổ sung cấu hình tại nơi tạo chính sách

~~~java
ShippingPolicy policy = new ShippingPolicy(
        Map.of(
                CustomerTier.STANDARD, 500_000L,
                CustomerTier.PREMIUM, 300_000L,
                CustomerTier.VIP, 200_000L),
        30_000L);
~~~

`CheckoutPreview` và `DeliveryEstimatePreview` **không cần thêm nhánh VIP**: cả hai vẫn gọi `policy.shippingFee`. Đây chính là hiệu quả kỳ vọng của việc tập trung một quy tắc dùng chung.

### 8.3. Kiểm tra tính năng mới và hành vi cũ

~~~java
@Test
void vipAtThresholdGetsFreeShipping() {
    ShippingPolicy policy = new ShippingPolicy(
            Map.of(
                    CustomerTier.STANDARD, 500_000L,
                    CustomerTier.PREMIUM, 300_000L,
                    CustomerTier.VIP, 200_000L),
            30_000L);

    assertEquals(30_000L,
            policy.shippingFee(199_999, CustomerTier.VIP));
    assertEquals(0L,
            policy.shippingFee(200_000, CustomerTier.VIP));
    assertEquals(0L,
            policy.shippingFee(200_001, CustomerTier.VIP));

    assertEquals(30_000L,
            policy.shippingFee(400_000, CustomerTier.STANDARD));
    assertEquals(0L,
            policy.shippingFee(400_000, CustomerTier.PREMIUM));
}
~~~

Code test trên minh họa một phương thức trong lớp test có import JUnit phù hợp. Đối với triển khai thật, cần kiểm tra mọi điểm tạo `ShippingPolicy`, nguồn cấu hình và hợp đồng bên ngoài: thêm giá trị enum có thể ảnh hưởng các đoạn `switch`, serialization, API schema hoặc hệ thống khác.

### 8.4. Kết luận nào có căn cứ?

Có thể nhận xét:

> “Để thêm VIP vào phép tính phí của hai màn hình đang xét, cấu trúc mới không đòi sửa hai thuật toán riêng. Thay đổi tập trung tại danh sách hạng được hỗ trợ và dữ liệu cấu hình; các màn hình giữ nguyên cách gọi. Các test giá trị biên cho ba hạng giúp xác minh yêu cầu.”

**Không nên khẳng định:** “Toàn bộ hệ thống thêm VIP chỉ cần sửa hai dòng.” Hệ thống thực có thể còn quyền lợi khách hàng, database, API, giao diện và tài liệu. Một bài đánh giá tốt luôn nêu **phạm vi được kiểm tra**.

## 9. Đánh giá khả năng hiểu bằng nhiệm vụ, không chỉ bằng cảm giác

“Nhìn sạch hơn” là nhận xét có thể đúng nhưng khó giúp đội ngũ quyết định. Một cách tốt hơn là yêu cầu người bảo trì thực hiện những nhiệm vụ cụ thể trên cấu trúc trước và sau refactor.

### 9.1. Những nhiệm vụ kiểm tra khả năng hiểu

Có thể đưa cho người chưa viết refactor:

1. **Tìm điểm quyết định:** “Hạng PREMIUM được miễn phí từ mức nào, và nơi nào quyết định kết quả?”
2. **Giải thích đầu vào:** “Phí dựa trên tiền hàng trước hay sau chiết khấu?”
3. **Nêu bất biến:** “Tổng tiền âm và hạng chưa có cấu hình được xử lý thế nào?”
4. **Truy dấu hành vi:** “Tại sao checkout và ước tính giao hàng cho cùng kết quả?”
5. **Chỉ ra nơi thêm VIP:** “Muốn thêm hạng mới, những file nào thực sự cần xem?”
6. **Chỉ ra giới hạn:** “Hóa đơn đã chốt trong quá khứ có được tính lại bằng chính sách hiện tại không?”

Một câu trả lời tốt không chỉ tìm đúng file mà còn **giải thích đúng yêu cầu và rủi ro**. Điều này giúp phát hiện trường hợp cấu trúc đã ngắn hơn nhưng cách hiểu trở nên khó hơn.

### 9.2. Ghi lại những gì quan sát được

Tùy mục tiêu, có thể quan sát:

- Người đọc có tìm đúng nơi sở hữu quy tắc không?
- Có hiểu đúng đơn vị tiền và ngưỡng “từ ... trở lên” không?
- Mất bao nhiêu bước điều hướng để tìm tất cả ảnh hưởng?
- Cần hỏi tác giả bao nhiêu câu để hiểu hợp đồng?
- Có mắc lỗi diễn giải hay bỏ sót một nơi sử dụng không?
- Có nêu đúng trường hợp chưa được hỗ trợ không?

**Không nên dùng một lần thử của một người để kết luận số giờ tiết kiệm được cho cả nhóm.** Người tham gia, độ quen thuộc và độ khó của nhiệm vụ đều ảnh hưởng mạnh đến kết quả.

## 10. Đánh giá khả năng thay đổi bằng “change exercise”

Một *change exercise* là bài thực hành thay đổi có phạm vi rõ, được dùng để so sánh tính dễ bảo trì của các cấu trúc.

### 10.1. Thiết kế bài tập công bằng

Chọn một thay đổi **khả thi và đại diện** với hướng phát triển hệ thống:

- Thêm hạng VIP.
- Đổi ngưỡng vận chuyển theo cấu hình.
- Thêm một trường hợp lỗi mà cả hai màn hình phải hiển thị nhất quán.
- Thay quy tắc làm tròn (nếu nghiệp vụ thật yêu cầu).
- Bổ sung loại khách hàng mà chưa có chính sách, cần xử lý rõ.

Giữ cùng yêu cầu, dữ liệu kiểm thử và tiêu chí chấp nhận giữa các phương án trước–sau.

### 10.2. Những bước quan sát

| Giai đoạn | Câu hỏi quan sát | Dấu hiệu tốt |
| --- | --- | --- |
| **Đọc yêu cầu** | Người sửa hiểu đầu vào, đầu ra và ràng buộc không? | Đề xuất đúng test biên trước khi sửa. |
| **Tìm vị trí** | Mất công sức gì để tìm tất cả nơi sở hữu logic? | Một ranh giới trách nhiệm rõ, có link test. |
| **Lập kế hoạch** | Có phải đoán thứ tự sửa hoặc chạm nhiều module không? | Dễ chỉ ra thay đổi cần thiết và phần không được đụng. |
| **Thực hiện** | Diff có tập trung vào chức năng cần thay không? | Ít điểm đồng bộ và không nhân bản logic. |
| **Xác minh** | Có test nhanh, phù hợp, phân biệt lỗi hợp đồng không? | Test nêu kết quả và điều kiện biên. |
| **Review** | Reviewer có dễ xác nhận phạm vi ảnh hưởng không? | Rõ vì sao các file đổi, ranh giới vẫn ổn. |
| **Vận hành** | Có bước cấu hình, migrate hoặc rollback mới không? | Bước mới được nêu rõ, có kiểm tra tương ứng. |

### 10.3. Tránh “thi đấu mã” thiếu kiểm soát

Nếu nhóm A đã hiểu code mới và nhóm B lần đầu xem code cũ, so sánh thời gian sẽ thiên lệch. Nếu người tạo refactor tự làm bài tập trên code mới, lợi thế quen thuộc cũng rất lớn.

Một cách đơn giản để giảm thiên lệch:

- Dùng các thay đổi tương đương về phạm vi và độ khó.
- Chia sẻ cùng tài liệu yêu cầu và tiêu chí xong.
- Cho người tham gia thời gian làm quen tương đối tương đồng.
- Xem thêm chất lượng kết quả, không chỉ thời gian.
- Nêu rõ cỡ mẫu, bối cảnh và giới hạn diễn giải.

Không nhất thiết tổ chức thí nghiệm lớn cho mỗi refactor. Một buổi walkthrough và một thay đổi mẫu được review kỹ có thể đủ để tìm ra vấn đề thiết kế quan trọng.

## 11. Các chỉ số hỗ trợ, nhưng không thay thế nhiệm vụ thực tế

Một số tín hiệu có thể hữu ích trong đánh giá:

| Tín hiệu | Hỗ trợ câu hỏi nào? | Giới hạn |
| --- | --- | --- |
| Số nơi phải sửa một chính sách | Quy tắc có một chủ sở hữu hay bị nhân bản? | Ít file chưa chắc ít coupling. |
| Số nơi gọi từ màn hình tới quyết định | Người đọc phải điều hướng qua bao nhiêu tầng? | Một tầng có thể là ranh giới có ích. |
| Cyclomatic/cognitive complexity | Luồng điều khiển có đáng điều tra không? | Điểm giảm có thể do chia nhỏ qua helper. |
| Số phụ thuộc giữa module | Refactor thêm/bớt quan hệ gì? | Đếm dependency không nói ngữ nghĩa phụ thuộc. |
| Test biên và test hồi quy | Hành vi quan trọng có bằng chứng không? | Coverage cao vẫn có thể thiếu oracle. |
| Thời gian review/thực hiện thay đổi | Chi phí bảo trì có dấu hiệu thay đổi không? | Chịu ảnh hưởng người làm, công cụ và độ khó. |
| Số lần sửa bổ sung do bỏ sót | Tính nhất quán của thay đổi đã được bảo vệ chưa? | Mẫu nhỏ, thay đổi quy trình có thể ảnh hưởng. |

Nếu metrics và trải nghiệm trái ngược, cần điều tra. Ví dụ complexity của phương thức chính giảm nhưng người review phải đi qua bảy lớp mới tìm ra ngưỡng, có thể đã **chuyển vị trí khó hiểu** chứ chưa xử lý nguyên nhân.

### 11.1. Mẫu quan sát minh họa, không phải số liệu thực

| Quan sát trong ví dụ hai màn hình | Trước refactor | Sau refactor |
| --- | --- | --- |
| Nơi chứa công thức tính phí hiện hành | 2 bản | 1 `ShippingPolicy` |
| Điểm vào nghiệp vụ vẫn tồn tại | Checkout và Delivery estimate | Checkout và Delivery estimate |
| Khi thêm VIP, cần sửa điều kiện ở bao nhiêu bản công thức? | Cần xem cả 2 | Không cần thêm nhánh vào 2 màn hình |
| Xử lý hạng thiếu cấu hình | Có thể rơi về ngưỡng mặc định | Ném lỗi tường minh |
| Bằng chứng tại ngưỡng | Phụ thuộc test ban đầu | Test cho STANDARD/PREMIUM và bài tập VIP |
| Chi phí thời gian thực tế của nhóm | Chưa đo | Chưa đo |

Bảng phản ánh **thuộc tính có thể quan sát từ thiết kế minh họa**. Nó không đủ để kết luận “giảm 50% thời gian phát triển” hoặc “giảm 80% bug”.

## 12. Ranh giới trách nhiệm và quyền sở hữu thay đổi

Một trong những yếu tố quan trọng nhất của cấu trúc dễ thay đổi là **một quyết định có nơi chịu trách nhiệm rõ**.

### 12.1. Tính gắn kết (*cohesion*)

Các phương thức và dữ liệu của một thành phần nên hỗ trợ một trách nhiệm có ý nghĩa. `ShippingPolicy` chứa thông tin ngưỡng và phép tính phí; nó không cần biết cách tạo email, ghi đơn hàng hay mở kết nối database.

Nếu muốn đổi phí, người bảo trì biết cần tìm ở đâu. Nếu muốn đổi giao diện hiển thị, không cần sửa chính sách.

### 12.2. Mức phụ thuộc (*coupling*)

Tập trung quy tắc tạo một phụ thuộc của hai màn hình vào `ShippingPolicy`. Đây không phải tự động xấu: **phụ thuộc vào một hợp đồng chung thực sự** có thể giảm nguy cơ các màn hình thực thi sai lệch.

Nhưng nếu hai màn hình thuộc hai hệ thống có vòng đời phiên bản và nghiệp vụ hoàn toàn độc lập, chia sẻ một thư viện hoặc dịch vụ có thể tạo chi phí phối hợp mới. Hãy xác định **điều gì phải thay đổi cùng nhau** và **điều gì cần độc lập**.

### 12.3. Tránh thay một “God Class” bằng nhiều “God Interface”

Thêm lớp trung gian chỉ hữu ích khi chúng biểu diễn ranh giới có ý nghĩa: policy, repository, clock, gateway hoặc cơ chế lưu trữ với hợp đồng rõ.

Một interface có duy nhất một triển khai vẫn có thể hợp lý khi ngăn logic nghiệp vụ phụ thuộc hạ tầng hoặc cần kiểm thử. Nhưng tạo interface cho mọi phép cộng, mọi helper, mọi cấu hình chỉ để “có thể thay thế về sau” dễ làm người đọc mất dấu hành vi.

**Một cấu trúc tốt không tối đa hóa số abstraction; nó làm nổi bật những trách nhiệm quan trọng.**

## 13. Kiểm thử là bằng chứng về tính đúng đắn và là tín hiệu của thiết kế

Một refactor tốt thường giúp test quan sát đúng kết quả với ít thiết lập không liên quan hơn.

### 13.1. Những dấu hiệu test dễ hơn

- Có thể khởi tạo đối tượng chính sách với dữ liệu kiểm thử cố định.
- Không cần chạy cả web server để tính một khoản phí.
- Không cần đọc clock thật hoặc database thật cho phép tính thuần túy.
- Lỗi được diễn đạt bằng kết quả/ngoại lệ có ý nghĩa.
- Test kiểm tra hành vi thay vì thao tác vào field private.
- Test biên được đặt gần quyết định nghiệp vụ.

### 13.2. Nhưng nhiều mock chưa chắc tốt

Một refactor có thể tạo nhiều interface khiến mỗi unit test phải dựng năm mock, xác minh mười lời gọi và có hàng loạt expectation phụ thuộc thứ tự. Những test như vậy có thể dễ vỡ khi đổi tổ chức helper dù kết quả không đổi.

Cần hỏi: test có xác minh **hợp đồng mà người dùng dựa vào** hay chỉ phản ánh chi tiết cài đặt?

### 13.3. Refactor không được làm mất bằng chứng tích hợp

Khi chuyển logic từ controller vào policy, unit test chính sách có thể nhanh hơn. Nhưng ranh giới tích hợp vẫn cần xác minh controller truyền đúng `CustomerTier`, số tiền đúng đơn vị và cùng phiên bản chính sách.

Bộ test thuần túy không tự bảo đảm cấu hình production hoặc serializer làm đúng. **Kiểm thử nhiều tầng phục vụ các câu hỏi khác nhau**, không phải tập trung mọi assertion ở một loại test.

## 14. Đánh giá những trường hợp refactor làm hành vi thay đổi ngoài ý muốn

Một thay đổi cấu trúc có thể vô tình chạm các chi tiết được người sử dụng coi là hợp đồng.

### 14.1. Thứ tự kiểm tra và ngoại lệ

Ví dụ:

~~~java
static long checkedFee(long subtotalCents, CustomerTier tier) {
    if (subtotalCents < 0) {
        throw new IllegalArgumentException("Negative subtotal");
    }
    java.util.Objects.requireNonNull(tier, "tier");
    return 0;
}
~~~

Ở đầu vào đồng thời `subtotalCents < 0` và `tier == null`, ví dụ trên ném `IllegalArgumentException` trước. Nếu refactor đổi thứ tự và ném `NullPointerException`, một client có thể quan sát khác biệt. Cần xem **loại và thứ tự lỗi có thuộc hợp đồng được cam kết không**, tránh thay đổi ngầm khi mục tiêu chỉ là tái cấu trúc.

Ví dụ này minh họa **thứ tự validation**, không phải hàm tính phí hoàn chỉnh.

### 14.2. Số học và làm tròn

~~~java
long byLine = item1Cents / 10 + item2Cents / 10;
long onSum = Math.addExact(item1Cents, item2Cents) / 10;
~~~

Với hai dòng có giá trị 9, `byLine` bằng 0 còn `onSum` bằng 1. Nếu quy tắc nghiệp vụ yêu cầu giảm giá theo từng dòng, đổi thành tính trên tổng không phải refactor giữ hành vi, dù có thể ít phép chia hơn.

### 14.3. Tác dụng phụ và thứ tự xử lý

Trong quy trình thanh toán, các hành động “giữ chỗ → thanh toán → xác nhận” có thể phải bảo vệ bất biến qua ranh giới giao dịch. Di chuyển chúng sang những helper chạy song song mà không xác định thứ tự, idempotency hay xử lý lỗi có thể tạo mất dữ liệu hoặc giao dịch trùng.

Một thiết kế đẹp hơn về dependency graph chưa đủ; cần xác minh **kết quả và tác dụng phụ quan sát được**.

### 14.4. Dữ liệu mutable và đồng thời

Thay tham số cục bộ bằng field `static` để “tái sử dụng” có thể khiến nhiều request ghi đè nhau. Ngược lại, chuyển state về đúng đối tượng sở hữu hoặc giá trị bất biến có thể làm test và lập luận đồng thời dễ hơn.

Phải xem tính đúng đắn trong **phạm vi thực của trạng thái**: một JVM, nhiều instance, database hay hàng đợi.

## 15. Đánh đổi: trích xuất chính sách hay giữ cách viết đơn giản?

Không phải lần refactor nào cũng cần một class riêng.

### 15.1. Trường hợp nên giữ một phương thức đơn giản

~~~java
static boolean isEligible(long points) {
    return points >= 100;
}
~~~

Nếu quy tắc chỉ dùng ở một nơi, ít thay đổi, không có phụ thuộc và test rõ, tạo `EligibilityFactory`, `EligibilityStrategy` và `EligibilityResolver` có thể làm mã khó hiểu hơn.

### 15.2. Trường hợp một policy có ý nghĩa

Một quy tắc:

- được dùng ở nhiều đường nghiệp vụ;
- có dữ liệu cấu hình và bất biến riêng;
- thay đổi theo một chủ sở hữu;
- cần test nhiều trường hợp biên;
- không nên phụ thuộc vào UI hay database cụ thể;

có thể là ứng viên hợp lý cho một đối tượng `Policy`.

### 15.3. Trường hợp hai quy tắc giống nhau nhưng phải giữ độc lập

Nếu báo giá hiện tại và hóa đơn lịch sử cùng hiển thị phí, nhưng **một bên tính phí dự kiến** và **bên kia phải giữ giá đã chốt**, không nên bắt cả hai gọi chính sách hiện tại chỉ vì muốn giảm duplicate code.

Một cấu trúc được đánh giá tốt khi **thay đổi đúng thứ cần thay, giữ độc lập thứ cần độc lập**.

## 16. Xem chi phí tìm hiểu trong cả quy trình, không chỉ một file

Người bảo trì thường phải đi qua nhiều nguồn tri thức:

~~~text
Yêu cầu thay đổi
      |
      v
Hợp đồng và ví dụ nghiệp vụ
      |
      v
Mã thực thi chính sách
      |
      v
Các điểm gọi và cấu hình
      |
      v
Test hồi quy / test tích hợp
      |
      v
Tài liệu và quy trình phát hành
~~~

Sau refactor, có thể mã ngắn hơn nhưng cấu hình nằm ở nơi khó tìm, test ở package không liên quan, JavaDoc còn mô tả chính sách cũ hoặc ví dụ tài liệu chưa phản ánh dữ liệu hạng mới.

Vì vậy, đánh giá khả năng thay đổi còn cần hỏi:

- Có biết **nguồn sự thật** của mỗi ngưỡng không?
- Có biết **phiên bản chính sách** đang áp dụng không?
- Cấu hình mới có cần rollout/migration không?
- Test nào bảo vệ đầu vào mới và đầu vào cũ?
- Tài liệu có cần cập nhật khi hợp đồng người dùng thay đổi không?
- Có cách rollback nếu refactor làm sai kết quả trong thực tế không?

Đây là phần bổ sung cho cấu trúc code, không phải lý do để biến bài đánh giá thành một đợt viết lại mọi tài liệu.

## 17. Mẫu đánh giá trước–sau có thể dùng trong pull request

Một báo cáo ngắn nên giữ cả **điều đã quan sát** lẫn **điều chưa xác nhận**:

~~~markdown
## Mục tiêu refactor
Giảm nguy cơ hai màn hình dự tính vận chuyển dùng hai bản quy tắc khác nhau.

## Vấn đề trước thay đổi
- Công thức phí xuất hiện trong CheckoutPreview và DeliveryEstimatePreview.
- Khi thêm hạng khách hàng, phải cập nhật cả hai công thức.
- Có nguy cơ hạng mới rơi vào nhánh mặc định.

## Phạm vi thay đổi
- Tạo ShippingPolicy sở hữu phép tính phí.
- Hai màn hình chuyển sang gọi cùng policy.
- Không đổi chính sách STANDARD/PREMIUM trong bước refactor.

## Hành vi phải giữ
- STANDARD: ngưỡng 500.000.
- PREMIUM: ngưỡng 300.000.
- Dưới ngưỡng: 30.000; đúng ngưỡng: miễn phí.
- Tiền âm, hạng null: bị từ chối theo hợp đồng.

## Bằng chứng
- Test ở sát dưới và đúng ngưỡng của hai hạng.
- Test hai màn hình dùng cùng một kết quả.
- Review số nơi định nghĩa công thức sau refactor.

## Tình huống thay đổi để đánh giá
Thêm VIP với ngưỡng 200.000.
Kỳ vọng chỉ cập nhật mô hình hạng và cấu hình chính sách,
không nhân bản logic ở hai màn hình.

## Đánh đổi
- Thêm một class chính sách và nơi quản lý cấu hình.
- Chưa chứng minh thời gian phát triển thực tế giảm.
- Cần kiểm tra API, serialization và cấu hình ngoài phạm vi ví dụ.

## Kết luận
Cấu trúc mới tập trung trách nhiệm phí và giúp bài tập thêm VIP rõ hơn.
Sẽ tiếp tục đánh giá khi có thay đổi nghiệp vụ thật.
~~~

Các giá trị trong mẫu là **thông tin minh họa từ ví dụ Java**, không phải số đo tại một repository cụ thể.

## 18. Thế nào là bằng chứng “thay đổi dễ hơn” đủ tin cậy?

Có nhiều mức bằng chứng:

### 18.1. Mức 1 — Lập luận cấu trúc

Ta thấy mã trùng đã được tập trung, dữ liệu đầu vào tường minh và các màn hình không còn chứa công thức. Đây là **bằng chứng về thiết kế**, nhưng chưa đo được chi phí làm việc của con người.

### 18.2. Mức 2 — Thử bài tập thay đổi

Người bảo trì thực hiện yêu cầu thêm VIP trên hai cấu trúc, đối chiếu kết quả, thời gian tìm vị trí, số nơi sửa và lỗi bị bỏ sót. Đây là bằng chứng gần với công việc hơn, nhưng vẫn phụ thuộc người thực hiện và bài tập được chọn.

### 18.3. Mức 3 — Theo dõi thay đổi thực tế

Sau một số chu kỳ, nhóm thấy những yêu cầu tương tự có ít lần sửa thiếu, test hồi quy rõ hơn hoặc reviewer tìm đúng nơi nhanh hơn. Đây là dữ liệu thực tế, nhưng cần kiểm tra **độ khó và phạm vi thay đổi có tương đương không**.

### 18.4. Kết luận phải tương xứng với mức bằng chứng

| Bằng chứng hiện có | Có thể nói | Không nên nói |
| --- | --- | --- |
| Chỉ xem diff | “Một công thức giờ có một nơi sở hữu.” | “Năng suất tăng 40%.” |
| Có test và change exercise | “Bài tập thêm VIP không cần sửa logic ở hai màn hình.” | “Mọi thay đổi tương lai đều chỉ sửa một file.” |
| Có vài PR sau refactor | “Các thay đổi được quan sát có ít bản sao phải sửa hơn.” | “Refactor là nguyên nhân duy nhất của mọi cải thiện.” |
| Có kết quả vận hành | “Trong tải và phiên bản được đo, hành vi liên quan ổn định.” | “Không thể có lỗi hồi quy ở bất kỳ môi trường nào.” |

Việc ghi giới hạn kết luận không làm yếu đánh giá; nó giúp người sau hiểu **khi nào cần kiểm tra lại**.

## 19. Khi cấu trúc mới thất bại trong bài đánh giá

Ví dụ một nhóm refactor thành:

~~~text
CheckoutPreview
    |
    v
PricingFacade
    |
    v
PolicyResolver
    |
    v
ShippingStrategyFactory
    |
    v
DefaultShippingStrategy
    |
    v
ThresholdRepository
~~~

Nếu việc thêm VIP vẫn cần sửa ba nhánh ở các tầng khác nhau, còn test phải mock từng tầng, có thể cấu trúc mới đã làm tăng công sức hiểu và thay đổi, dù mỗi class có ít dòng.

Hướng xem lại:

1. **Xác định ai thật sự sở hữu ngưỡng và lựa chọn hạng.**
2. **Loại abstraction không có trách nhiệm ổn định.**
3. **Đưa dữ liệu cấu hình về một ranh giới tìm được rõ ràng.**
4. **Kiểm tra cách test quy tắc mà không cần khởi tạo toàn bộ graph.**
5. **Xác minh phần phụ thuộc hạ tầng chỉ xuất hiện khi thật sự cần.**

Không nên tự động kết luận cần “quay lại mọi thứ một class”. Cần tìm một mức phân tách vừa đủ cho nhiệm vụ và hướng thay đổi thật.

### 19.1. Không cố cứu một refactor chỉ vì đã bỏ nhiều công sức

Nếu bài thử cho thấy đường đi khó theo dõi hơn và lợi ích chưa xuất hiện, nên điều chỉnh hoặc rollback phần kiến trúc chưa phù hợp. Chi phí đã bỏ ra không làm một lựa chọn trở nên đúng.

Việc chấp nhận sửa thiết kế sau khi có bằng chứng mới là một phần của **thực hành cải tiến có trách nhiệm**.

## 20. Quy trình review một refactor theo hướng thay đổi an toàn

**Bước 1 — Đọc lý do.** Mùi mã hoặc trở ngại nào thực sự cần xử lý? Có liên quan đến kế hoạch thay đổi gần không?

**Bước 2 — Phân biệt mục tiêu.** PR nhằm giữ hành vi và đổi cấu trúc, hay đồng thời sửa bug/thêm tính năng? Nếu có cả hai, từng phần phải được nêu rõ.

**Bước 3 — So sánh ownership.** Trước–sau, quy tắc nào có một nơi quyết định? Có tạo thêm phụ thuộc khó quản lý không?

**Bước 4 — Theo đường đi của một hành vi.** Từ đầu vào đến kết quả, người review phải qua bao nhiêu tầng và có hiểu vì sao nhánh được chọn không?

**Bước 5 — Kiểm tra bất biến và tác dụng phụ.** Các trường hợp null, âm, đúng ngưỡng, ngoại lệ, tính nguyên tử, thứ tự ghi và khả năng đồng thời có thay đổi không?

**Bước 6 — Xem test và hợp đồng.** Test có bảo vệ hành vi cũ không; có test mới chỉ phụ thuộc vào cấu trúc private không; ranh giới tích hợp có được kiểm tra phù hợp không?

**Bước 7 — Thử một change scenario.** Ví dụ thêm VIP, đổi ngưỡng hoặc thêm mã lỗi. Điều gì phải sửa và điều gì phải giữ nguyên?

**Bước 8 — Đánh giá chi phí mới.** Class, Map, factory, config, migration, monitoring và tài liệu thêm vào có xứng với lợi ích?

**Bước 9 — Ghi kết luận có phạm vi.** Nêu chính xác điều đã cải thiện, bằng chứng và điều chưa kiểm chứng. Đặt điều kiện xem lại nếu thiết kế tiếp tục phát triển.

### 20.1. Ví dụ nhận xét code review có giá trị

> “Sau khi đưa quy tắc phí vào `ShippingPolicy`, cả hai màn hình chỉ còn chuyển tiếp đầu vào và không chứa hai bản ngưỡng riêng. Điều này giải quyết trở ngại mỗi lần đổi chính sách phải cập nhật hai class. Test đã có ca sát dưới và đúng ngưỡng cho STANDARD/PREMIUM. Trước khi merge, đề nghị kiểm tra nguồn cấu hình production và cách xử lý hạng không có chính sách. Với tình huống thêm VIP, hai màn hình không cần thêm nhánh mới.”

Nhận xét nêu **điều gì tốt hơn, bằng chứng nào hỗ trợ và lỗ hổng nào còn cần xem**, không chỉ khen “clean code”.

## 21. Bài tập tự đánh giá

### Tình huống A — Phương thức được chia nhỏ rất nhiều

Một phương thức 180 dòng được trích thành 15 helper, tất cả đều nhận cùng đối tượng `MutableContext` chứa 25 field. Điểm complexity của phương thức gốc giảm; người review thường phải mở nhiều helper để biết field nào đang bị thay đổi.

**Câu hỏi:** nên đánh giá bằng nhiệm vụ gì và có thể cải thiện ở đâu?

**Gợi ý:** yêu cầu người mới truy vết “field nào được cập nhật trước khi gửi sự kiện” hoặc thử thêm một nhánh kiểm tra. Nếu phụ thuộc và thứ tự trạng thái vẫn ẩn, việc chia nhỏ mới chỉ phân tán độ phức tạp. Có thể dùng đầu vào–đầu ra rõ theo từng giai đoạn hoặc tách trách nhiệm thật, thay vì tăng số helper tiếp.

### Tình huống B — Mã trùng nhưng hai chính sách độc lập

Checkout dự tính phí vận chuyển hiện tại, còn chức năng in hóa đơn phải hiển thị **phí đã chốt khi tạo đơn**. Một PR đưa cả hai vào cùng `ShippingPolicy` dùng ngưỡng hiện tại để giảm duplicate code.

**Câu hỏi:** vì sao đây có thể là refactor nguy hiểm?

**Gợi ý:** hai hành vi có nguồn sự thật và vòng đời khác nhau. Hóa đơn cũ có thể bị tính lại khi chính sách đổi. Cần xác định hợp đồng trước; một bản sao của cú pháp không đồng nghĩa một trách nhiệm chung.

### Tình huống C — Test nhanh hơn nhưng thiếu tính đúng đắn

Sau refactor, unit test của phí vận chuyển chạy nhanh và coverage 100%. Tuy nhiên, API nhận `customerTier` từ client mà không xác minh quyền lợi hạng khách hàng trên server.

**Câu hỏi:** có thể coi refactor đã bảo đảm chất lượng hệ thống không?

**Gợi ý:** chưa. Test thuần túy chỉ xác minh phép tính với tier được cung cấp. Ranh giới xác thực/quyền lợi là câu hỏi bảo mật và tích hợp riêng, phải được kiểm chứng theo hợp đồng.

### Tình huống D — Thêm một biến thể mới

Hệ thống có ba phương án hoàn tiền với logic chung nhưng điều kiện khác nhau. Một nhóm muốn tạo rule engine tổng quát ngay để “dễ thay đổi”.

**Câu hỏi:** cần bằng chứng gì để quyết định dùng rule engine?

**Gợi ý:** những thay đổi dự kiến và ranh giới nào thật sự khác nhau, số lần thêm chính sách, cách test và cấu hình, số tầng tăng, khả năng người bảo trì tìm đúng luật. Nếu nhu cầu còn đơn giản, vài class policy rõ trách nhiệm có thể tốt hơn engine quá tổng quát.

### Tình huống E — Số file sửa giảm

Sau refactor, một thay đổi chỉ sửa hai file thay vì sáu. Nhưng thời gian triển khai tăng do phải cập nhật schema và migration tại database.

**Câu hỏi:** có thể kết luận cải thiện chi phí thay đổi chỉ từ số file không?

**Gợi ý:** không. Cần xem phạm vi trách nhiệm, độ phức tạp của migration, rủi ro và khả năng rollback. Ít file là tín hiệu, không đo toàn bộ công việc.

## 22. Checklist đánh giá cấu trúc sau refactor

- [ ] Mục tiêu refactor nêu **trở ngại hiểu hoặc thay đổi cụ thể**, không chỉ một cảnh báo.
- [ ] Tôi phân biệt bước giữ nguyên hành vi với bug fix hoặc feature change.
- [ ] Hợp đồng cũ được mô tả và bảo vệ bằng test phù hợp.
- [ ] Người đọc có thể tìm **một nơi chịu trách nhiệm** cho quyết định nghiệp vụ cần thay.
- [ ] Các đầu vào, giá trị biên, null và ngoại lệ vẫn rõ ràng.
- [ ] Trạng thái và tác dụng phụ quan trọng có chủ sở hữu và thứ tự xử lý phù hợp.
- [ ] Những class/interface mới có trách nhiệm có thể giải thích, không chỉ làm điểm complexity giảm.
- [ ] Tôi đã kiểm tra độ phức tạp có bị **chuyển sang nhiều tầng** hay không.
- [ ] Mã trùng được xử lý theo **tri thức chung**, không gộp nhầm hai quy tắc độc lập.
- [ ] Có một tình huống thay đổi đại diện để thử cấu trúc mới.
- [ ] Người bảo trì có thể xác định nơi sửa và test cần chạy mà không hỏi tác giả mọi chi tiết.
- [ ] Test tập trung vào kết quả/hợp đồng, không khóa chặt thứ tự gọi helper private.
- [ ] Cấu hình, API, schema và ranh giới tích hợp chịu tác động đã được nhận diện.
- [ ] Những chỉ số như LOC, complexity và số file được đặt trong đúng ngữ cảnh.
- [ ] Không tuyên bố cải thiện thời gian hoặc tỷ lệ lỗi khi chưa có dữ liệu tương ứng.
- [ ] Phần phức tạp tăng thêm có giá trị đo được hoặc lập luận vững chắc theo nhu cầu.
- [ ] Có cách xác minh và rollback khi refactor có rủi ro vận hành.
- [ ] Kết luận review nêu **bằng chứng, phạm vi và giới hạn** của nhận định.

## 23. Kết luận

**Đánh giá cấu trúc mới bằng khả năng hiểu và thực hiện thay đổi** giúp tránh một sai lầm phổ biến: coi việc xóa mã lặp, chia phương thức hoặc giảm điểm complexity là mục tiêu cuối cùng của refactoring.

Một cấu trúc đáng giữ phải giúp người bảo trì **biết một quyết định nằm ở đâu, hiểu vì sao nó đúng, sửa đúng nơi khi yêu cầu thay đổi và kiểm chứng hành vi với chi phí hợp lý**. Tình huống thay đổi đại diện — như thêm hạng VIP vào chính sách vận chuyển của hai màn hình dự tính — cung cấp một thước đo gần với công việc hơn cảm giác “mã đẹp hơn”.

Trong **CODE_QUALITY_FUNDAMENTALS**, refactor góp phần tạo mã nguồn **đáng tin cậy, dễ hiểu và dễ thay đổi** khi nó giữ hợp đồng hiện tại, làm rõ trách nhiệm và được kiểm nghiệm bằng nhiệm vụ cụ thể. Đừng chỉ hỏi **“cấu trúc có gọn hơn không?”**; hãy hỏi **“người tiếp theo có thể thay đổi yêu cầu một cách đúng đắn và tự tin hơn không?”**

