# Đề xuất hướng sửa nhưng giữ quyền giải thích của tác giả

> **Chương:** Rà soát mã  
> **Học phần:** CODE_QUALITY_FUNDAMENTALS — hiểu những thuộc tính quyết định mã nguồn có đáng tin cậy, dễ hiểu và dễ thay đổi hay không.

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích code review là hoạt động cộng tác để kiểm tra hành vi, rủi ro và khả năng bảo trì, không phải cuộc thi tìm lỗi hoặc áp đặt phong cách cá nhân.
2. Viết nhận xét có **quan sát cụ thể, tác động, lý do và hướng xử lý có thể hành động**, đồng thời để tác giả có cơ hội giải thích bối cảnh.
3. Phân biệt yêu cầu bắt buộc, đề xuất cải thiện, câu hỏi làm rõ và nhận xét hình thức; nêu rõ mức độ ưu tiên để tác giả biết điều gì đang chặn merge.
4. Đề xuất hướng sửa mà không biến cách triển khai ưa thích của reviewer thành yêu cầu duy nhất khi có nhiều phương án hợp lệ.
5. Phản hồi phù hợp khi tác giả giải thích một quyết định, cung cấp bằng chứng hoặc không đồng ý với đề xuất.
6. Xử lý bất đồng dựa trên hợp đồng, rủi ro, tiêu chí chất lượng và quy ước nhóm; biết khi nào cần thêm test, trao đổi trực tiếp hoặc nhờ người sở hữu quyết định.
7. Giữ trách nhiệm của reviewer đối với rủi ro đã nhận diện, đồng thời tôn trọng quyền tác giả cung cấp ngữ cảnh và lựa chọn cách sửa phù hợp.
8. Viết và xử lý review comment sao cho cuộc trao đổi tập trung vào mã và hành vi, không đánh giá con người.

## 1. Code review là cuộc trao đổi về chất lượng và rủi ro

Một pull request thay đổi cách tính tiền VIP. Reviewer thấy điều kiện dùng toán tử lớn hơn và cho rằng phải là lớn hơn hoặc bằng. Nếu chỉ viết:

> “Sai rồi. Sửa thành lớn hơn hoặc bằng.”

tác giả có thể không biết reviewer đang dựa trên chính sách nào. Có thể đặc tả thực sự là “lớn hơn ngưỡng”, hoặc có quy tắc riêng cho một chương trình khác. Reviewer có thể đúng, nhưng comment chưa tạo đủ cơ hội để xác nhận ngữ cảnh.

Một nhận xét tốt hơn:

> “Theo chính sách VIP hiện được mô tả là áp dụng từ 1.000.000 VND trở lên, điều kiện lớn hơn sẽ bỏ sót đơn đúng ngưỡng. Đây có phải là chủ ý của chương trình này không? Nếu vẫn theo chính sách chung, mình đề xuất đổi thành lớn hơn hoặc bằng và thêm test ở đúng ngưỡng.”

Nhận xét thứ hai làm rõ:

- **Quan sát:** điều kiện đang dùng toán tử lớn hơn.
- **Tác động:** bỏ sót trường hợp đúng bằng ngưỡng.
- **Cơ sở:** chính sách đang được hiểu là “từ ... trở lên”.
- **Câu hỏi:** tác giả có ngữ cảnh khác không?
- **Hướng xử lý:** đổi điều kiện và thêm test nếu cùng chính sách.

Reviewer đã nêu rủi ro, nhưng chưa giả định rằng mình biết toàn bộ bối cảnh. Tác giả có thể xác nhận đặc tả, chỉ ra ngoại lệ hoặc cung cấp bằng chứng để cả hai thống nhất cách xử lý.

**Code review tốt vừa bảo vệ chất lượng, vừa giữ không gian cho tri thức của người trực tiếp thực hiện thay đổi.** Tác giả thường biết lý do sản phẩm, lịch sử quyết định, giới hạn hệ thống hoặc điều kiện triển khai mà reviewer chưa thấy trong diff. Reviewer có trách nhiệm đặt câu hỏi và kiểm tra rủi ro; tác giả có trách nhiệm giải thích và xử lý những vấn đề đã được xác minh.

### Hai vai trò bổ sung nhau

| Vai trò | Trách nhiệm chính |
| --- | --- |
| **Tác giả (author)** | Giải thích mục tiêu, bối cảnh, lựa chọn thiết kế, test và tác động của thay đổi; phản hồi các rủi ro được nêu |
| **Reviewer** | Kiểm tra tính đúng đắn, bảo mật, hợp đồng, khả năng đọc, test và rủi ro; trình bày nhận xét có căn cứ |
| **Người sở hữu module/maintainer** | Giúp giải quyết quyết định về kiến trúc, quy ước và ranh giới sở hữu khi nhóm chưa thống nhất |
| **Nhóm** | Duy trì quy ước review, mức độ chặn, cách xử lý ngoại lệ và tiêu chí merge |

Tôn trọng quyền giải thích của tác giả **không có nghĩa reviewer phải chấp nhận mọi lựa chọn**. Nếu có lỗi bảo mật, dữ liệu sai hoặc vi phạm hợp đồng đã xác nhận, reviewer cần nói rõ điều kiện phải được giải quyết trước khi merge. Tôn trọng ở đây là yêu cầu bằng chứng và trao đổi công bằng, không phải bỏ qua rủi ro.

## 2. Bắt đầu từ mục tiêu thay đổi, không chỉ từ từng dòng diff

Một diff chỉ cho biết những dòng đã đổi. Nó không tự giải thích **vì sao** thay đổi cần thiết hoặc điều gì phải được giữ nguyên.

Trước khi nhận xét, reviewer nên tìm câu trả lời cho các câu hỏi:

1. PR giải quyết vấn đề hoặc nhu cầu nào?
2. Hành vi nào thay đổi, hành vi nào phải giữ nguyên?
3. Những module, API, dữ liệu hoặc người dùng nào bị ảnh hưởng?
4. Tác giả đã chọn giải pháp này vì giới hạn hay quyết định nào?
5. Có test hoặc bằng chứng nào bảo vệ hợp đồng?
6. Có rủi ro nào không được thể hiện trong diff, ví dụ migration, cấu hình, quyền, retry hoặc rollout?

Nếu mô tả PR chưa đủ, hãy hỏi trước khi phán đoán:

> “Mình chưa thấy lý do thay đổi cách retry ở đây. Bạn có thể mô tả tình huống lỗi mà PR muốn xử lý và hành vi mong đợi sau timeout không?”

Câu hỏi này không buộc tác giả chọn sẵn một cách cài đặt. Nó yêu cầu làm rõ **hợp đồng và vấn đề** để reviewer đánh giá được giải pháp.

### Đọc diff theo bốn lớp

| Lớp | Điều cần xem | Ví dụ |
| --- | --- | --- |
| **Ý định** | Vấn đề và hành vi cần thay đổi | Hỗ trợ hoàn tiền một phần |
| **Hợp đồng** | Đầu vào, đầu ra, lỗi, quyền, trạng thái | Chỉ hoàn tiền đơn đã thanh toán |
| **Cài đặt** | Cấu trúc, thuật toán, dependency, transaction | Tạo lệnh hoàn tiền có idempotency key |
| **Bằng chứng** | Test, log, migration, tài liệu, rollout | Test timeout sau khi provider đã nhận lệnh |

Một nhận xét chỉ ở lớp cài đặt như “dùng stream cho gọn” có thể bỏ lỡ lỗi ở hợp đồng. Ngược lại, không phải mọi PR đều cần review kiến trúc toàn hệ thống; hãy tập trung vào các lớp liên quan đến rủi ro của thay đổi.

## 3. Một review comment hữu ích có cấu trúc rõ

Không cần mọi comment đều dài. Nhưng với nhận xét có ảnh hưởng đến hành vi, nên làm rõ bốn thành phần:

1. **Vị trí/quan sát:** đoạn mã hoặc điều kiện cụ thể nào đang được nói tới?
2. **Tác động:** điều gì có thể xảy ra, ai hoặc phần nào bị ảnh hưởng?
3. **Lý do/cơ sở:** hợp đồng, dữ liệu, quy ước hay bằng chứng nào khiến vấn đề đáng quan tâm?
4. **Đề xuất hoặc câu hỏi:** tác giả có thể kiểm tra, thay đổi hoặc giải thích điều gì?

### Ví dụ ngắn

**Thiếu hữu ích:**

> “Code này không ổn.”

**Hữu ích hơn:**

> “Nếu thao tác lưu repository thất bại sau khi gateway đã nhận lệnh thanh toán, request retry có thể tạo giao dịch thứ hai. Mình chưa thấy idempotency key được giữ qua lần retry. Bạn có thể xác nhận gateway xử lý key này ở đâu và bổ sung test cho timeout sau khi provider đã nhận request không?”

Nhận xét thứ hai nêu một failure mode có thể tái hiện, chỉ rõ điều chưa biết và yêu cầu bằng chứng phù hợp. Nó không áp đặt một cấu trúc class cụ thể nếu tác giả có một cơ chế tương đương.

### Đề xuất nên nói rõ mục tiêu, không chỉ cách viết

Thay vì:

> “Tách hàm này ra.”

Có thể viết:

> “Đoạn này đang vừa kiểm tra quyền sở hữu vừa cập nhật trạng thái. Tách phần quyết định quyền thành một policy có tên có thể giúp test trường hợp khác tenant độc lập. Bạn thấy có phù hợp với ranh giới hiện tại của service không?”

Tác giả vẫn có thể chọn cách khác, miễn giải quyết được vấn đề mà comment chỉ ra.

## 4. Phân loại nhận xét để tác giả biết điều gì thực sự chặn merge

Một comment có thể đúng nhưng gây khó xử nếu không nói rõ mức độ quan trọng. Nhóm nên thống nhất cách gắn nhãn. Ví dụ:

| Loại nhận xét | Ý nghĩa | Cách tác giả xử lý |
| --- | --- | --- |
| **Blocking / Required** | Rủi ro hoặc yêu cầu phải giải quyết trước khi merge | Sửa, cung cấp bằng chứng rằng không có vấn đề, hoặc thống nhất phương án thay thế |
| **Suggestion** | Đề xuất cải thiện, không phải điều kiện bắt buộc | Cân nhắc lợi ích và chi phí; có thể nhận hoặc giải thích lý do chưa làm |
| **Question** | Reviewer cần hiểu bối cảnh hoặc hành vi | Trả lời, bổ sung tài liệu/test hoặc điều chỉnh code nếu phát hiện vấn đề |
| **Nit** | Chi tiết nhỏ về trình bày hoặc cách diễn đạt | Sửa nếu hợp lý; không nên làm chậm thay đổi quan trọng |
| **Praise / Observation** | Ghi nhận một lựa chọn tốt hoặc một đặc điểm đáng chú ý | Giúp chia sẻ cách làm có ích, không yêu cầu sửa |

Tên nhãn cụ thể có thể khác nhau giữa các nhóm. Điều quan trọng là **một suggestion không bị diễn giải thành blocker**, và một blocker không bị che dưới giọng điệu mơ hồ như “có lẽ nên xem lại”.

### Khi nào cần blocker?

Nên chặn merge khi có bằng chứng đáng tin rằng thay đổi:

- Vi phạm yêu cầu hoặc bất biến nghiệp vụ đã xác nhận.
- Tạo nguy cơ bảo mật hoặc truy cập dữ liệu trái quyền.
- Làm hỏng hợp đồng API, schema hoặc dữ liệu được consumer sử dụng.
- Có thể làm mất, nhân đôi hoặc ghi sai giao dịch.
- Thiếu bằng chứng bắt buộc theo chính sách của repository/nhóm.
- Gây hồi quy nghiêm trọng về độ tin cậy hoặc hiệu năng theo tiêu chí đã thống nhất.

Không nên dùng blocker chỉ vì reviewer thích một tên biến, thư viện hoặc mẫu thiết kế khác. Nếu có nhiều cách triển khai hợp lệ, hãy nói rõ tiêu chí nào khiến lựa chọn hiện tại không đáp ứng yêu cầu.

### Cách ghi mức độ trong comment

~~~text
[BLOCKER] Request retry có thể gửi lệnh hoàn tiền lần hai.
[QUESTION] Trường hợp gateway timeout sau khi xử lý được phân biệt thế nào?
[SUGGESTION] Có thể đặt tên biến kèm đơn vị Vnd để tránh nhầm scale.
[NIT] Có thể bỏ dòng trống thừa giữa hai import.
~~~

Đây là quy ước minh họa. Nếu nhóm đã có nhãn hoặc mức ưu tiên khác, hãy dùng một cách nhất quán.

## 5. Đề xuất hướng sửa mà không áp đặt một implementation duy nhất

Reviewer thường thấy một cách giải quyết quen thuộc và muốn tác giả dùng đúng cách ấy. Nhưng **cách reviewer từng dùng thành công không tự trở thành tiêu chuẩn duy nhất**.

Ví dụ có ba lựa chọn để ngăn đọc đơn hàng ngoài tenant:

- Repository luôn truy vấn theo mã đơn và tenant.
- Service tải đối tượng trong phạm vi rồi kiểm tra policy.
- Database dùng Row-Level Security (RLS) với ngữ cảnh tenant được thiết lập an toàn.

Mỗi cách có điều kiện và giới hạn riêng. Reviewer nên tập trung vào yêu cầu:

> “Mọi đường đọc phải giới hạn theo tenant đã được xác minh, kể cả query list và export. Phương án hiện tại bảo đảm điều đó ở những ranh giới nào?”

Nếu tác giả đưa ra bằng chứng rằng RLS được cấu hình đúng, connection pool không rò rỉ ngữ cảnh và các query đi qua transaction phù hợp, reviewer cần đánh giá bằng chứng ấy. Không nên buộc tác giả sao chép giải pháp repository mà reviewer quen dùng nếu phương án hiện tại đáp ứng hợp đồng.

### Ba cấp đề xuất

| Cấp | Cách viết | Khi nên dùng |
| --- | --- | --- |
| **Nêu kết quả cần đạt** | “Không được trả dữ liệu của tenant khác.” | Khi nhiều implementation hợp lệ |
| **Gợi ý hướng giải quyết** | “Có thể giới hạn tenant ngay trong query để tránh tải dữ liệu ngoài phạm vi.” | Khi có một hướng đáng cân nhắc |
| **Đề xuất implementation cụ thể** | “Dùng phương thức truy vấn theo mã đơn và tenant, rồi test hai tenant.” | Khi giải pháp phù hợp với kiến trúc hiện có và có thể giải thích |

Càng đi xuống, đề xuất càng cụ thể. Nhưng mức độ cụ thể nên tương xứng với **độ chắc chắn về bối cảnh**. Nếu reviewer chưa biết schema hoặc policy, bắt đầu bằng câu hỏi về hợp đồng sẽ tốt hơn.

## 6. Ví dụ Java: nhận xét về quyền truy cập theo đối tượng

Giả sử một endpoint trả đơn hàng:

~~~java
OrderResponse getOrder(String actorId, long orderId) {
    Order order = repository.findById(orderId).orElseThrow();
    return mapper.toResponse(order);
}
~~~

Reviewer thấy hàm nhận mã người gọi nhưng không dùng. Chỉ nhìn đoạn này, chưa thể biết kiểm tra quyền đã xảy ra ở filter, service phía trước hay database policy. Tuy nhiên, việc tham số không được sử dụng là tín hiệu cần làm rõ.

**Comment chưa tốt:**

> “Thêm điều kiện so sánh actor với owner vào đây.”

Cách viết này giả định chỉ chủ sở hữu được đọc đơn. Có thể nhân viên hỗ trợ cùng tenant cũng được quyền xem, hoặc policy được kiểm tra ở một lớp khác.

**Comment tốt hơn:**

> “Mình thấy mã người gọi chưa được dùng trong phương thức này. Quyền đọc đơn được kiểm tra ở lớp nào? Nếu chưa có kiểm tra theo đối tượng/tenant, người dùng biết mã đơn có thể đọc đơn ngoài phạm vi. Bạn có thể chỉ ra policy đang áp dụng và test trường hợp hai tài khoản truy cập chéo không?”

Tác giả có thể trả lời:

> “Controller có annotation kiểm tra scope đọc đơn, nhưng đúng là scope chỉ xác nhận quyền gọi chức năng, chưa kiểm tra owner hoặc tenant. Mình sẽ bổ sung policy ở service và test hai tenant.”

Hoặc tác giả có thể giải thích:

> “Repository này chỉ được gọi từ một handler đã kiểm tra quyền trong transaction; mã người gọi được truyền để ghi audit nhưng chưa cần trong method. Tuy vậy, tham số hiện đặt sai chỗ, mình sẽ chuyển audit context sang interceptor.”

Cả hai câu trả lời đều giúp review tiến lên. Reviewer không cần bảo vệ đề xuất ban đầu bằng mọi giá; điều cần bảo vệ là **hợp đồng phân quyền thực sự được thực thi**.

### Một hướng sửa có thể kiểm chứng

Nếu chính sách được xác nhận là chủ sở hữu hoặc nhân viên có quyền trong cùng tenant được đọc, có thể dùng một service như sau:

~~~java
import java.util.Objects;
import java.util.Optional;
import java.util.Set;

record Actor(String userId, String tenantId, Set<String> permissions) {
    Actor {
        Objects.requireNonNull(userId);
        Objects.requireNonNull(tenantId);
        permissions = Set.copyOf(permissions);
    }
}

record Order(long id, String tenantId, String ownerId) {}

interface OrderRepository {
    Optional<Order> findByIdAndTenant(long orderId, String tenantId);
}

final class OrderReader {
    private final OrderRepository repository;

    OrderReader(OrderRepository repository) {
        this.repository = Objects.requireNonNull(repository);
    }

    Optional<Order> findReadableOrder(Actor actor, long orderId) {
        return repository.findByIdAndTenant(orderId, actor.tenantId())
                .filter(order ->
                        actor.userId().equals(order.ownerId())
                        || actor.permissions().contains("orders:read:tenant"));
    }
}
~~~

Đây chỉ là một **implementation minh họa**. Actor phải được dựng từ danh tính và quyền đã được server xác minh, không lấy trực tiếp từ body do client gửi. API thật còn phải quy định 403/404, DTO, audit và hành vi khi policy service không khả dụng.

Test có thể kiểm tra cả trường hợp được và bị từ chối:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;
import java.util.List;
import java.util.Optional;
import java.util.Set;

class OrderReaderTest {
    private final List<Order> orders = List.of(
            new Order(42L, "shop-a", "alice"),
            new Order(43L, "shop-a", "bob"),
            new Order(42L, "shop-b", "carol")
    );

    private final OrderRepository repository = (id, tenantId) ->
            orders.stream()
                    .filter(order -> order.id() == id)
                    .filter(order -> order.tenantId().equals(tenantId))
                    .findFirst();

    private final OrderReader reader = new OrderReader(repository);

    @Test
    void ownerCanReadOwnOrder() {
        Actor alice = new Actor("alice", "shop-a", Set.of());

        assertTrue(reader.findReadableOrder(alice, 42L).isPresent());
    }

    @Test
    void anotherCustomerCannotReadOwnersOrder() {
        Actor bob = new Actor("bob", "shop-a", Set.of());

        assertTrue(reader.findReadableOrder(bob, 42L).isEmpty());
    }

    @Test
    void tenantPermissionDoesNotCrossTenant() {
        Actor support = new Actor(
                "support", "shop-b", Set.of("orders:read:tenant"));

        assertTrue(reader.findReadableOrder(support, 42L).isPresent());
        assertTrue(reader.findReadableOrder(support, 43L).isEmpty());
    }
}
~~~

Một comment review nên hướng tác giả tới **bằng chứng cần có** như test hai tenant. Reviewer không nhất thiết phải viết toàn bộ implementation thay tác giả.

## 7. Hỏi để hiểu trước khi đề nghị thay đổi

Câu hỏi có giá trị khi reviewer thật sự chưa biết câu trả lời và sẵn sàng cập nhật nhận định sau khi nghe giải thích.

### Câu hỏi tốt thường nhắm tới điều chưa rõ

- “Đầu vào này có thể null từ client hay đã được validate ở boundary?”
- “Trường hợp timeout sau khi gateway đã xử lý được biểu diễn như thế nào?”
- “Mốc thời gian ở đây là UTC hay ngày địa phương của cửa hàng?”
- “Hai field này có cùng ý nghĩa, hay một field là giá trước giảm?”
- “Đoạn code này được gọi từ job nền nào ngoài controller?”
- “Có lý do giữ thứ tự cập nhật này để tương thích dữ liệu cũ không?”
- “Test hiện tại xác nhận trạng thái sau commit hay chỉ xác nhận method được gọi?”

### Tránh câu hỏi mang tính kết tội

| Không nên viết | Nên viết |
| --- | --- |
| “Tại sao lại viết như thế này?” | “Bạn có thể chia sẻ giả định hoặc ràng buộc dẫn tới cách này không?” |
| “Bạn có đọc đặc tả không?” | “Mình đang hiểu đặc tả yêu cầu X; phần này có chủ ý khác không?” |
| “Sao không dùng cách đơn giản hơn?” | “Có ràng buộc nào khiến cách hiện tại cần thiết? Mình muốn hiểu trade-off trước khi đề xuất phương án khác.” |
| “Đây là bug rõ ràng.” | “Với input X, mình dự đoán kết quả Y; code hiện có vẻ trả Z. Bạn có thể xác nhận kỳ vọng không?” |
| “Cái này phải viết lại.” | “Phần này đang có hai trách nhiệm thay đổi độc lập; liệu tách ranh giới có giúp kiểm tra và bảo trì tốt hơn không?” |

Giọng điệu lịch sự không có nghĩa làm nhạt mức độ nghiêm trọng. Nếu một đường truy cập có thể làm lộ dữ liệu, hãy nói rõ đó là blocker và vì sao. Chỉ tránh gắn vấn đề kỹ thuật với phẩm chất cá nhân.

## 8. Tác giả có thể giải thích khác với giả định ban đầu

Một reviewer có trách nhiệm **thay đổi kết luận khi có bằng chứng mới**. Điều đó không làm reviewer yếu đi; nó cho thấy mục tiêu là hiểu đúng hệ thống.

Ví dụ:

1. Reviewer thấy nhánh bắt timeout rồi trả kết quả rỗng, nghi ngờ lỗi hạ tầng bị biến thành không tìm thấy.
2. Tác giả giải thích timeout ở đây chỉ áp dụng cho cache lookup tùy chọn; database fallback vẫn chạy và test tích hợp chứng minh hợp đồng.
3. Reviewer xem code fallback và test, xác nhận trường hợp này không vi phạm hợp đồng.
4. Reviewer rút lại blocker, có thể đề nghị đổi tên hoặc thêm log để người đọc hiểu rõ hơn nếu còn mơ hồ.

Nếu bằng chứng chưa đủ, reviewer có thể giữ câu hỏi hoặc yêu cầu test cụ thể. **Không cần giữ một nhận xét chỉ để bảo vệ thể diện**.

### Phân biệt giải thích với bằng chứng

Một lời giải thích có thể làm rõ ý định nhưng chưa chứng minh hành vi. Ví dụ:

> “Gateway luôn chống gửi trùng.”

Đây là thông tin hữu ích, nhưng với thanh toán, reviewer có thể cần hợp đồng provider, cách gửi idempotency key và test timeout/retry. Ngược lại, không phải mọi comment đều cần tài liệu ngoài; một giải thích về tên biến hoặc lý do chọn cấu trúc có thể đã đủ.

Hãy yêu cầu **mức bằng chứng tương xứng với hậu quả**.

## 9. Khi tác giả không đồng ý với đề xuất

Không đồng ý không đồng nghĩa thiếu hợp tác. Có thể reviewer đang ưu tiên readability, tác giả đang ưu tiên tương thích; hoặc reviewer chưa biết một constraint production.

Một cách xử lý:

1. **Tóm tắt điểm bất đồng:** hai bên đang hiểu khác nhau ở yêu cầu hay cách triển khai?
2. **Tách mục tiêu khỏi giải pháp:** mục tiêu là gì, implementation nào đang được tranh luận?
3. **Đưa ra bằng chứng:** đặc tả, test, trace, benchmark, schema hoặc lịch sử tương thích.
4. **Xem phương án thay thế:** có cách nào đáp ứng mục tiêu với chi phí/rủi ro thấp hơn?
5. **Xác định người quyết định:** nếu là quy ước module, nhờ maintainer; nếu là chính sách nghiệp vụ, hỏi chủ sở hữu nghiệp vụ.
6. **Ghi lại kết luận:** lý do chọn phương án và điều kiện xem lại khi phù hợp.

### Ví dụ bất đồng về abstraction

Reviewer đề nghị trích xuất một lớp PricingPolicy. Tác giả phản hồi rằng hai đoạn code hiện giống nhau nhưng một bên là giá báo trước, bên kia là giá giao dịch đã chốt; chúng có vòng đời khác nhau.

Reviewer nên kiểm tra:

- Báo giá có được phép thay đổi khi policy mới có hiệu lực không?
- Giao dịch đã chốt có phải giữ nguyên giá lịch sử không?
- Hai đoạn có dùng cùng công thức nhưng **khác thời điểm áp dụng**?
- Có thể chia sẻ phép toán thấp hơn nhưng giữ policy/contract riêng không?

Nếu khác biệt được xác nhận, giữ tách có thể là lựa chọn tốt hơn. Review không nên biến DRY thành yêu cầu gộp mọi đoạn code tương tự.

### Khi vẫn chưa thống nhất

Không nên kéo dài hàng chục comment lặp lại. Có thể chuyển sang cuộc trao đổi ngắn có agenda:

- Tình huống cần giải quyết.
- Các lựa chọn và trade-off.
- Ràng buộc bắt buộc.
- Bằng chứng còn thiếu.
- Người chịu trách nhiệm ra quyết định.

Sau cuộc trao đổi, ghi kết luận vào PR hoặc tài liệu phù hợp để lần sau không phải tranh luận lại từ đầu.

## 10. Phản hồi review từ phía tác giả

Tác giả cũng có vai trò chủ động giúp reviewer hiểu thay đổi. Một phản hồi tốt thường:

- Trả lời đúng câu hỏi.
- Nêu giả định hoặc constraint liên quan.
- Dẫn tới test, tài liệu hoặc đoạn code chứng minh khi cần.
- Nói rõ đã sửa ở commit nào.
- Nếu không làm theo đề xuất, giải thích lý do và cách khác đang bảo vệ cùng mục tiêu.

### Ví dụ phản hồi

**Reviewer:**

> “amount ở đây là tổng trước hay sau giảm? Tên hiện tại có thể khiến caller gửi sai số tiền.”

**Tác giả:**

> “Đây là số tiền sau giảm và trước phí vận chuyển. Mình sẽ đổi tên thành amountDueBeforeShippingVnd để phản ánh đúng phạm vi, đồng thời thêm assertion trong test checkout.”

Hoặc:

> “Tên amount là một phần của interface thư viện bên ngoài nên mình không thể đổi trực tiếp. Adapter nội bộ đã ánh xạ sang amountDueBeforeShippingVnd; mình sẽ liên kết test mapping trong PR.”

Câu trả lời thứ hai giữ nguyên interface bên ngoài nhưng cung cấp cách bảo vệ hợp đồng nội bộ. Reviewer nên đánh giá **kết quả và bằng chứng**, không chỉ đếm số đề xuất của mình được áp dụng.

### Không trả lời bằng cách chỉ đóng thread

Đánh dấu thread đã resolved nên đi kèm thay đổi hoặc lời giải thích có thể kiểm tra. Nếu tác giả chưa đồng ý hoặc câu hỏi còn mở, nên tiếp tục trao đổi hoặc ghi rõ ai sẽ theo dõi. Mục tiêu là **giải quyết vấn đề**, không phải làm cho giao diện PR hết comment.

## 11. Cách xử lý comment theo từng mức độ

| Mức | Reviewer nên làm | Tác giả nên làm |
| --- | --- | --- |
| Blocker có bằng chứng | Nêu failure mode, tác động và điều kiện chấp nhận | Sửa hoặc cung cấp bằng chứng thuyết phục rằng không vi phạm |
| Required theo quy ước | Trích dẫn quy ước và phạm vi áp dụng | Tuân thủ hoặc đề xuất ngoại lệ qua người có thẩm quyền |
| Suggestion | Nêu lợi ích và chi phí dự kiến | Cân nhắc; có thể từ chối với lý do hợp lý |
| Question | Hỏi điều chưa rõ, chưa kết luận sớm | Giải thích và bổ sung bằng chứng nếu cần |
| Nit | Ghi rõ không chặn merge | Sửa nếu thuận tiện, không làm lệch ưu tiên |
| Praise | Nêu cụ thể điều gì tốt và vì sao | Có thể giữ pattern hoặc chia sẻ cho nhóm |

Một số nhóm dùng priority như P0/P1/P2 hoặc nhãn blocking/non-blocking. Dù dùng tên nào, hãy tránh để **mức độ phải được đoán từ giọng điệu**.

### Không lạm dụng blocker

Nếu reviewer đặt blocker cho mọi sở thích, tác giả sẽ khó phân biệt nguy cơ thực với ý kiến cá nhân. Điều đó làm giảm niềm tin và kéo dài review.

### Không làm nhẹ blocker thực sự

Nếu có nguy cơ mất dữ liệu hoặc lộ thông tin, đừng viết “có thể cân nhắc xem lại”. Hãy nói rõ mức độ, đường tái hiện và yêu cầu phải đáp ứng trước merge. **Sự tôn trọng thể hiện ở cách trao đổi, không ở việc che giấu mức rủi ro.**

## 12. Đưa ra đề xuất có nhiều lựa chọn khi trade-off là thật

Một số vấn đề không có một đáp án duy nhất. Ví dụ một API cần tránh trả dữ liệu ngoài quyền:

- Cách A: lọc theo tenant trong repository.
- Cách B: policy service kiểm tra object-level sau khi truy vấn trong phạm vi an toàn.
- Cách C: database RLS.

Thay vì yêu cầu một cách duy nhất, reviewer có thể viết:

> “Mục tiêu là không tải hoặc trả dữ liệu ngoài tenant đã xác thực. Repository scoping có thể làm phạm vi rõ ngay tại query; RLS có thể thêm lớp bảo vệ nếu connection context được quản lý an toàn. Bạn đang chọn cách nào trong kiến trúc hiện tại, và test nào chứng minh list/export cũng được giới hạn?”

Câu hỏi giúp tác giả trình bày lựa chọn. Reviewer vẫn có thể yêu cầu **bằng chứng ở các đường truy cập cụ thể**, thay vì chấp nhận một mô tả chung.

### Khi nào chỉ nên đưa một phương án?

- Hợp đồng hoặc tiêu chuẩn đã quy định rõ.
- Một lựa chọn khác tạo lỗi đã biết.
- Có giới hạn kỹ thuật khiến phương án còn lại không khả thi.
- Rủi ro cao cần một điều kiện bắt buộc, dù implementation cụ thể vẫn linh hoạt.

Ngay cả khi chỉ có một hướng đáp ứng yêu cầu, hãy giải thích **vì sao**. “Làm theo cách tôi nói” không phải cơ sở review.

## 13. Tập trung vào hành vi, không phán xét tác giả

Ngôn ngữ review có thể vô tình chuyển từ đánh giá code sang đánh giá người.

| Cách diễn đạt gây phòng thủ | Cách diễn đạt tập trung vào vấn đề |
| --- | --- |
| “Bạn không hiểu transaction à?” | “Nếu exception xảy ra sau lần ghi đầu, transaction hiện tại có rollback cả hai thao tác không?” |
| “Bạn luôn quên test.” | “PR này chưa có test cho trường hợp timeout; mình cần bằng chứng cho đường lỗi đó.” |
| “Cách này lười và khó bảo trì.” | “Phương thức đang xử lý validation, persistence và gửi event; thay đổi một phần có thể ảnh hưởng hai trách nhiệm còn lại.” |
| “Code này ngớ ngẩn.” | “Với input rỗng, vòng lặp trả kết quả khác hợp đồng được mô tả. Ta có thể bổ sung test và xử lý trường hợp này không?” |
| “Tôi đã nói phải dùng X.” | “Điều kiện cần bảo vệ là Y. Phương án hiện tại chưa chứng minh Y; bạn có thể đề xuất cách khác đáp ứng nó không?” |

Từ “luôn”, “không bao giờ”, “rõ ràng” thường khái quát quá mức. Hãy nói về **đoạn mã và trường hợp cụ thể**.

### Khen ngợi cũng nên cụ thể

Thay vì “Good job”, có thể viết:

> “Test ở đúng ngưỡng này rất hữu ích: nó bắt được khác biệt giữa toán tử lớn hơn và lớn hơn hoặc bằng mà happy path không phát hiện.”

Nhận xét cụ thể giúp tác giả và người đọc sau biết **pattern nào đáng giữ**.

## 14. Phạm vi review: không yêu cầu tác giả sửa mọi vấn đề nhìn thấy

Trong một PR sửa lỗi thanh toán, reviewer phát hiện thêm:

- Một tên biến có thể rõ hơn.
- Một lớp cũ dài.
- Một module khác có nhiều duplicate code.
- Một vấn đề bảo mật đang ảnh hưởng tới route khác.

Không nên gom tất cả thành cùng một mức yêu cầu. Cần phân biệt:

1. **Vấn đề do PR tạo ra hoặc làm lộ:** xử lý trong thay đổi hiện tại nếu cần để bảo vệ correctness.
2. **Vấn đề cũ có liên quan trực tiếp:** cân nhắc sửa cùng nếu phạm vi và rủi ro phù hợp.
3. **Vấn đề ngoài phạm vi:** ghi nhận riêng với vị trí, tác động và người sở hữu; không làm PR thành một cuộc viết lại không giới hạn.
4. **Rủi ro nghiêm trọng đang tồn tại:** báo đúng quy trình/owner ngay cả khi không phải tác giả PR tạo ra.

Giữ phạm vi review rõ giúp tránh cả hai cực: bỏ qua vấn đề nghiêm trọng vì “không thuộc PR”, hoặc bắt tác giả sửa toàn bộ codebase trước khi merge một thay đổi nhỏ.

### Đề xuất follow-up có thể hành động

Một comment ngoài phạm vi nên nêu:

- File/module hoặc vị trí.
- Hậu quả đã quan sát hoặc rủi ro cần xác minh.
- Lý do không sửa trong PR hiện tại.
- Việc tiếp theo và người/nhóm sở hữu nếu đã biết.

Không cần tạo issue cho mọi nit. Chỉ tách việc khi có giá trị theo dõi thật.

## 15. Review test và bằng chứng, không chỉ review implementation

Một đoạn code có thể trông hợp lý nhưng test chưa bảo vệ hành vi. Reviewer nên xem:

- Test có phản ánh **đặc tả độc lập** hay chỉ sao chép công thức implementation?
- Có test ở ngưỡng, dữ liệu rỗng, giá trị biên và lỗi phụ thuộc không?
- Test có kiểm tra kết quả quan sát được, không chỉ verify lời gọi nội bộ?
- Các phụ thuộc được mock có che đúng ranh giới đang cần kiểm tra không?
- Có test âm tính cho phân quyền, tenant, trạng thái hoặc retry không?
- Có integration/contract test nếu thay đổi schema, transaction hoặc API?
- Test có ổn định, dữ liệu độc lập và dễ chẩn đoán không?

### Ví dụ comment

> “Test hiện xác nhận calculate được gọi, nhưng chưa kiểm tra số tiền cuối. Nếu implementation truyền subtotal thay vì amount sau giảm, test vẫn xanh. Bạn có thể assert giá trị gateway nhận ở trường hợp VIP đúng ngưỡng không?”

Đây là một yêu cầu có căn cứ. Tác giả có thể chọn unit/component/integration test phù hợp, miễn **đúng ranh giới rủi ro** được kiểm tra.

## 16. Review thay đổi cấu trúc và quy ước

Khi PR đổi tên, tách lớp hoặc hợp nhất code, reviewer cần phân biệt:

- **Refactor bảo toàn hành vi:** cấu trúc thay đổi, contract giữ nguyên.
- **Sửa defect:** kết quả sai được sửa theo đặc tả.
- **Thay đổi nghiệp vụ:** quy tắc hoặc hành vi được điều chỉnh.
- **Thay đổi tương thích:** API, schema, dữ liệu hoặc event thay đổi với consumer.
- **Thay đổi vận hành:** config, rollout, migration, monitoring hoặc quyền triển khai.

Nếu nhiều loại bị trộn trong một PR, có thể hỏi:

> “PR đang vừa chuyển logic tính giá, vừa đổi ngưỡng VIP. Có thể tách phần bảo toàn hành vi khỏi phần thay đổi chính sách không? Nếu cần đi cùng nhau, hãy nêu rõ test nào bảo vệ từng quyết định.”

Không bắt buộc phải tách mọi thứ thành nhiều PR; đôi khi migration và code cần phát hành cùng nhau. Điều cần có là **mô tả rõ phần nào thay đổi hành vi và bằng chứng nào bảo vệ nó**.

### Với thay đổi lớn

Có thể yêu cầu:

- Tóm tắt mục tiêu và phương án đã cân nhắc.
- Sơ đồ luồng hoặc ranh giới module khi cần.
- Kế hoạch migration/rollback.
- Contract tests cho client.
- Tác động bảo mật, hiệu năng và dữ liệu.
- Phần nào chưa làm và lý do.

Review nên tăng độ sâu theo **mức rủi ro và phạm vi**, không chỉ theo số dòng diff.

## 17. Khi reviewer đề xuất sai: cách sửa nhận xét

Reviewer cũng có thể hiểu nhầm code. Khi tác giả cung cấp bằng chứng phản bác:

1. Đọc lại câu trả lời và xác định giả định nào ban đầu không đúng.
2. Kiểm tra test/tài liệu/luồng thực tế được dẫn.
3. Nếu nhận xét không còn phù hợp, nói rõ đã hiểu và resolve.
4. Nếu một phần rủi ro vẫn còn, giữ lại đúng phần chưa được giải quyết.
5. Cập nhật kết luận về blocker/approval cho nhất quán.

Ví dụ:

> “Cảm ơn bạn đã chỉ ra rằng OrderReader chỉ được gọi sau middleware tenant. Mình đã xem test tích hợp và xác nhận phạm vi được áp dụng cả cho endpoint này. Mình rút lại blocker ban đầu. Mình vẫn đề nghị đổi tên tham số tenant thành verifiedTenant để thể hiện nguồn tin cậy.”

Không nên để một comment đã bị phản biện tiếp tục như blocker chỉ vì reviewer không muốn đổi ý.

### Tác giả không phải lúc nào cũng đúng

Nếu giải thích không có bằng chứng, hoặc test không bao phủ failure mode đã nêu, reviewer có thể giữ yêu cầu. Khi đó nên nói rõ **bằng chứng nào còn thiếu** và tiêu chí nào sẽ làm blocker được giải quyết.

## 18. Review bất đồng về style và sở thích cá nhân

Nhiều comment không phải về chất lượng thực mà là khác biệt phong cách:

- Dùng vòng lặp hay stream.
- Đặt tên load hay find.
- Chọn một lớp helper hay phương thức private.
- Đặt thứ tự method theo visibility hay theo use case.
- Dùng early return hay một nhánh else.

Nếu repository đã có quy ước rõ, hãy dẫn quy ước và phạm vi. Nếu chưa có, đừng tự tạo blocker từ sở thích cá nhân.

### Ví dụ

**Comment áp đặt:**

> “Dùng stream đi, Java hiện đại rồi.”

**Comment có căn cứ hơn:**

> “Ở đây stream không làm luồng biến đổi rõ hơn vì có hai nhánh side effect. Vòng lặp hiện tại có thể dễ debug hơn. Mình không thấy cần đổi; nếu nhóm có convention cụ thể thì mình sẽ theo convention đó.”

Hoặc nếu có vấn đề readability thật:

> “Chuỗi filter/map/peek này có side effect ở peek, nên người đọc khó biết lúc nào dữ liệu được ghi. Có thể chuyển side effect thành bước rõ ràng sau khi lọc không?”

Khác biệt là comment thứ hai nêu **tác động tới cách hiểu và hành vi**, không chỉ yêu cầu dùng cú pháp ưa thích.

## 19. Kết thúc review: xác nhận vấn đề đã được giải quyết

Một PR có thể có nhiều comment đã trả lời nhưng chưa rõ trạng thái cuối. Trước khi approve hoặc merge, cần kiểm tra:

- Các blocker đã được sửa hoặc có bằng chứng giải quyết.
- Những câu hỏi ảnh hưởng đến hợp đồng đã được trả lời.
- Test phù hợp đã chạy trên commit cuối.
- Các suggestion không bắt buộc được chấp nhận hoặc từ chối có lý do khi cần.
- Không có thay đổi mới làm mất hiệu lực của review trước.
- Người có trách nhiệm phê duyệt đã xem đúng diff cuối cùng.

### Approve không có nghĩa bảo đảm tuyệt đối

Một approval có nghĩa reviewer đã xem thay đổi trong **phạm vi và mức độ hiểu biết tại thời điểm review**, thấy đủ điều kiện theo quy trình nhóm. Nó không chứng minh không còn bug. Với thay đổi rủi ro cao, có thể cần reviewer chuyên môn, kiểm thử bổ sung, rollout có giám sát hoặc kế hoạch rollback.

### Sau khi merge

Nếu lỗi xuất hiện sau merge, review nên là một phần của quá trình học:

- Có tín hiệu nào trong diff/test mà nhóm đã bỏ qua?
- Tiêu chí hoặc checklist có thiếu?
- Comment đã không rõ mức độ?
- Tác giả/reviewer thiếu bối cảnh nào?
- Cần bổ sung test, telemetry hoặc quy ước để lỗi khó lặp lại?

Không dùng incident để hồi tố kết luận rằng một cá nhân “đáng lẽ phải biết”. Tập trung vào **cải thiện vòng phản hồi và lớp phòng vệ**.

## 20. Checklist cho reviewer và tác giả

### Reviewer

- [ ] Tôi hiểu mục tiêu PR và hành vi cần giữ/thay đổi.
- [ ] Tôi phân biệt điều đã xác minh với giả định của mình.
- [ ] Comment chỉ rõ vị trí, tác động và cơ sở.
- [ ] Tôi hỏi khi thiếu bối cảnh thay vì khẳng định sớm.
- [ ] Tôi ghi rõ blocker, suggestion, question hay nit.
- [ ] Tôi đề xuất mục tiêu và tiêu chí chấp nhận, không áp đặt sở thích nếu có nhiều cách hợp lệ.
- [ ] Tôi xem test ở ranh giới rủi ro và không chỉ dựa vào coverage.
- [ ] Tôi cân nhắc API, DB, quyền, transaction, dữ liệu lịch sử và rollout nếu bị tác động.
- [ ] Tôi sẵn sàng rút lại hoặc sửa comment khi có bằng chứng mới.
- [ ] Tôi tập trung vào code và hành vi, không gán nhãn con người.
- [ ] Tôi giữ phạm vi review phù hợp nhưng không bỏ qua rủi ro nghiêm trọng.
- [ ] Tôi kiểm tra lại diff cuối trước khi approve.

### Tác giả

- [ ] PR mô tả mục tiêu, phạm vi và hành vi thay đổi.
- [ ] Tôi giải thích các constraint không hiển thị trong diff.
- [ ] Tôi phản hồi câu hỏi bằng thông tin hoặc bằng chứng cụ thể.
- [ ] Tôi không coi mọi suggestion là blocker.
- [ ] Nếu không làm theo đề xuất, tôi giải thích cách khác bảo vệ cùng tiêu chí.
- [ ] Tôi bổ sung test phù hợp với rủi ro.
- [ ] Tôi chỉ resolve thread khi vấn đề đã được xử lý hoặc có kết luận rõ.
- [ ] Tôi tách refactor, sửa lỗi và thay đổi hợp đồng khi việc tách giúp review an toàn hơn.
- [ ] Tôi cập nhật mô tả PR nếu phạm vi thay đổi trong quá trình review.

## 21. Những ngộ nhận thường gặp

**“Reviewer phải đưa ra code sửa hoàn chỉnh.”** Reviewer cần chỉ rõ vấn đề và tiêu chí; tác giả có thể chọn implementation phù hợp hơn với bối cảnh.

**“Giữ quyền giải thích nghĩa là tác giả luôn có quyền quyết định cuối.”** Tác giả cung cấp bối cảnh và đề xuất; nhóm/maintainer vẫn chịu trách nhiệm về tiêu chuẩn merge và rủi ro hệ thống.

**“Comment càng trực tiếp càng tốt.”** Rõ ràng là cần thiết, nhưng kết luận không có cơ sở hoặc công kích cá nhân làm giảm chất lượng trao đổi.

**“Đặt câu hỏi là thiếu quyết đoán.”** Khi thiếu bối cảnh, câu hỏi cụ thể giúp tránh yêu cầu sửa sai hướng.

**“Mọi đề xuất của reviewer đều phải được thực hiện.”** Suggestion và sở thích không phải blocker; cần phân biệt mức độ.

**“Không đồng ý với reviewer là chống đối.”** Bất đồng có thể cung cấp thông tin quan trọng về constraint, lịch sử hoặc hợp đồng.

**“Reviewer phải giữ ý kiến ban đầu để nhất quán.”** Khi bằng chứng mới làm giả định cũ sai, cần cập nhật kết luận.

**“Tôn trọng tác giả nghĩa là nói nhẹ mọi rủi ro.”** Rủi ro nghiêm trọng phải được nêu rõ và chặn khi cần; điều chỉnh là cách nói và cơ sở, không phải che mức độ.

**“Code review chỉ xem các dòng đã thay.”** Thay đổi có thể tác động tới caller, schema, quyền, dữ liệu lịch sử, job nền và rollout.

**“Một test xanh là đủ nếu reviewer tin tác giả.”** Niềm tin không thay thế bằng chứng phù hợp; mức kiểm tra phải theo rủi ro.

**“Số comment nhiều chứng minh review kỹ.”** Một comment đúng trọng tâm có thể hữu ích hơn nhiều nit và trao đổi lặp lại.

**“Approve nghĩa là bảo đảm không có lỗi.”** Approval chỉ là đánh giá theo phạm vi, bằng chứng và quy trình hiện có.

## 22. Bài tập thực hành

### Bài tập A — viết lại comment áp đặt

Tình huống: một method dùng if/else thay vì stream. Reviewer viết:

> “Đổi sang stream cho hiện đại và gọn hơn.”

Hãy viết lại comment sao cho:
- Nếu chỉ là sở thích, nói rõ không chặn merge.
- Nếu có vấn đề readability thực sự, nêu tác động cụ thể.
- Cho tác giả cơ hội giải thích constraint hoặc giữ cách hiện tại.

### Bài tập B — hỏi về rủi ro quyền truy cập

Một endpoint tải hóa đơn chỉ kiểm tra token hợp lệ rồi gọi phương thức tìm theo mã hóa đơn. Hãy viết comment:
- Không khẳng định ngay rằng hệ thống chắc chắn có lỗ hổng nếu chưa xem các lớp khác.
- Nêu nguy cơ object-level authorization.
- Hỏi nơi policy được thực thi.
- Yêu cầu bằng chứng/test hai tài khoản hoặc hai tenant.

### Bài tập C — phân loại mức độ

Phân loại mỗi nhận xét là blocker, required, suggestion, question hoặc nit; giải thích lý do:

1. Thay đổi làm lộ dữ liệu của tenant khác.
2. Tên biến x trong một công thức tiền khiến đơn vị không rõ.
3. Reviewer thích switch hơn chuỗi if.
4. Test không có trường hợp đúng ngưỡng đã được đặc tả.
5. PR thiếu mô tả lý do thay đổi một public API.
6. Có dòng trống thừa giữa hai method.

### Bài tập D — tác giả giải thích hợp lý

Reviewer yêu cầu hợp nhất hai hàm vì công thức giống nhau. Tác giả giải thích một hàm tính báo giá hiện tại, hàm kia đọc giá đã chốt của giao dịch lịch sử. Hãy viết phản hồi tiếp theo:
- Thông tin nào xác nhận sự khác biệt?
- Còn rủi ro nào cần kiểm tra?
- Có thể chia sẻ phần nào mà không gộp hai chính sách?
- Khi nào nên rút lại comment ban đầu?

### Bài tập E — bất đồng về transaction

Reviewer cho rằng gửi event sau commit là bắt buộc. Tác giả nói hệ thống dùng transactional outbox và worker phát event sau đó. Hãy xác định bằng chứng cần xem (ghi outbox trong transaction, retry, idempotency, publish status, test crash/restart) trước khi giữ hoặc rút blocker.

### Bài tập F — review có phạm vi

Trong PR sửa lỗi hiển thị giá, reviewer phát hiện một module báo cáo cũ có nhiều duplicate code nhưng không liên quan tới lỗi. Hãy viết một comment follow-up ngắn có vị trí, tác động cần xác minh và đề xuất cách theo dõi, không biến việc ngoài phạm vi thành blocker tùy tiện.

## 23. Câu hỏi tự kiểm tra

1. Vì sao code review cần cả tri thức của tác giả và góc nhìn độc lập của reviewer?
2. Một comment tốt nên có những thành phần nào?
3. Phân biệt blocker, suggestion và question bằng ví dụ.
4. Khi nào nên hỏi để làm rõ thay vì đưa ra một implementation cụ thể?
5. Vì sao đề xuất hướng sửa nên tập trung vào hợp đồng và tác động?
6. Tôn trọng quyền giải thích của tác giả khác gì với chấp nhận mọi quyết định?
7. Khi nào reviewer nên rút lại một blocker?
8. Nếu tác giả giải thích bằng lời nhưng chưa có test cho failure mode quan trọng, reviewer nên làm gì?
9. Vì sao không nên dùng blocker cho sở thích về stream, tên hoặc số dòng?
10. Một rủi ro bảo mật thực sự nên được diễn đạt thế nào để rõ mức độ nhưng không công kích cá nhân?
11. Cách xử lý bất đồng khi hai implementation đều hợp lệ là gì?
12. Ai nên quyết định khi bất đồng liên quan tới quy ước module hoặc chính sách nghiệp vụ?
13. Làm sao tránh review trở thành cuộc trao đổi lặp lại trên hàng chục comment?
14. Vì sao phải xem caller, API contract, migration và job nền khi chỉ một method được sửa?
15. Một test so sánh hai implementation có thể bỏ sót điều gì nếu cả hai cùng sai?
16. Tại sao reviewer cần xem lại diff cuối trước khi approve?
17. Một PR có nhiều nit nhưng thiếu test rủi ro cao nên được đánh giá thế nào?
18. Sau incident, nhóm nên cải thiện điều gì trong review process thay vì tìm người để đổ lỗi?
19. Làm thế nào để phân biệt suggestion ngoài phạm vi với một rủi ro nghiêm trọng cần xử lý ngay?
20. Hãy viết một comment có đủ quan sát, tác động, cơ sở và hướng xử lý cho một lỗi bạn từng gặp.

## Ghi nhớ

**Đề xuất hướng sửa tốt giúp tác giả nhìn rõ rủi ro và tiêu chí cần bảo vệ, đồng thời để họ giải thích bối cảnh và lựa chọn cách triển khai phù hợp.** Reviewer cần nêu quan sát cụ thể, tác động, cơ sở và mức độ; tác giả cần trả lời bằng ngữ cảnh hoặc bằng chứng. Hãy phân biệt blocker với suggestion, hỏi khi chưa rõ, sẵn sàng cập nhật ý kiến và giữ bất đồng tập trung vào hợp đồng cùng hành vi. Tôn trọng tác giả không làm giảm trách nhiệm bảo vệ chất lượng; nó giúp nhóm đưa ra quyết định tốt hơn với đầy đủ thông tin, để mã **đáng tin cậy, dễ hiểu và dễ thay đổi**.
