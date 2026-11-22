# Kiểm tra mức bao phủ hành vi bằng kiểm thử

## Mục tiêu

Một bộ kiểm thử có thể đạt tỷ lệ bao phủ dòng lệnh cao nhưng vẫn bỏ sót những hành vi quan trọng mà người dùng và hệ thống phụ thuộc. Ví dụ, test có thể chạy qua một Controller và một application service mà chỉ kiểm tra response thành công; các trường hợp thiếu quyền, dữ liệu sai, trạng thái không hợp lệ hoặc tác dụng phụ bị lặp vẫn chưa được xác minh.

Kiểm tra mức bao phủ hành vi (behavior coverage) bắt đầu từ những điều hệ thống phải làm và những tình huống có thể xảy ra, sau đó đối chiếu chúng với các kiểm thử đã có. Cách tiếp cận này giúp đánh giá bộ test theo hợp đồng nghiệp vụ và HTTP, thay vì chỉ theo số dòng code đã chạy.

Trong ứng dụng Model–View–Controller, hành vi cần bao phủ trải dài từ request, Controller, application service và domain model đến persistence, View hoặc response body. Bài học này trình bày cách lập danh mục hành vi, xây dựng ma trận truy vết, chọn trường hợp kiểm thử, đo lường và phát hiện khoảng trống.

Sau khi học, người học có thể:

- Phân biệt behavior coverage với line coverage, branch coverage và requirement coverage.
- Chuyển yêu cầu và quy tắc nghiệp vụ thành các tình huống kiểm thử có thể quan sát.
- Xây dựng ma trận actor–action–state–result và liên kết test với hành vi.
- Chọn test bằng phân vùng tương đương, giá trị biên, decision table và state transition.
- Đánh giá bao phủ ở Controller, service, domain, persistence, View và security.
- Dùng unit test, MVC test, integration test và end-to-end test đúng tầng.
- Phát hiện test chỉ chạy code nhưng không kiểm tra kết quả hoặc tác dụng phụ.
- Dùng coverage report và mutation testing như tín hiệu bổ trợ.
- Đề xuất tiêu chí review và quality gate phù hợp với rủi ro.

## 1. Behavior coverage là gì?

Behavior coverage là mức độ mà bộ kiểm thử xác minh các hành vi đã xác định của hệ thống. Một hành vi mô tả cách ứng dụng phản ứng với một tình huống cụ thể, gồm tác nhân, điều kiện ban đầu, hành động và kết quả mong đợi.

Ví dụ, với chức năng hủy đơn hàng:

- Chủ đơn hàng được hủy đơn đang chờ.
- Người khác không được hủy đơn.
- Đơn đã giao không thể hủy.
- Đơn không tồn tại trả về kết quả phù hợp.
- Request bị từ chối không thay đổi dữ liệu.
- Hủy thành công tạo audit record hoặc event theo hợp đồng.

Một test chỉ gọi method cancel() và nhận về không có exception chưa chứng minh các hành vi này được bảo vệ. Test cần xác nhận trạng thái đơn hàng, quyền truy cập, response và side effect theo từng tình huống.

### Hành vi cần có thể quan sát

Một hành vi tốt để đưa vào danh mục phải có kết quả có thể xác nhận. Kết quả có thể là:

- HTTP status, header và response body.
- View được chọn và dữ liệu được đưa vào Spring Model.
- Trạng thái domain trước và sau thao tác.
- Bản ghi được tạo, cập nhật hoặc không thay đổi.
- Event, message hoặc audit record được phát ra.
- Hành động bị từ chối.
- Lỗi được chuyển thành response an toàn.
- Tương tác giữa các request hoặc giữa nhiều người dùng.

Behavior coverage không phải một con số chuẩn duy nhất do mọi công cụ tự động tính. Đây là cách đánh giá có hệ thống xem các hành vi quan trọng đã được kiểm tra đến đâu. Nhóm có thể định nghĩa chỉ số riêng, nhưng phải nói rõ mẫu số gồm những hành vi nào.

## 2. Phân biệt các loại coverage

Các loại coverage trả lời những câu hỏi khác nhau và bổ sung cho nhau.

| Loại coverage | Câu hỏi | Ví dụ |
|---|---|---|
| Line coverage | Dòng code nào đã được thực thi? | Dòng gọi repository đã chạy |
| Statement coverage | Câu lệnh nào đã được thực thi? | Lệnh cập nhật trạng thái đã chạy |
| Branch coverage | Các nhánh điều kiện nào đã được đi qua? | Nhánh owner và non-owner |
| Condition coverage | Các điều kiện Boolean riêng lẻ đã nhận true/false chưa? | isOwner và isAdmin |
| Method coverage | Method nào đã được gọi? | Controller method detail được gọi |
| Requirement coverage | Yêu cầu nào đã có test liên kết? | Yêu cầu hủy đơn có test |
| Behavior coverage | Tình huống và kết quả nghiệp vụ nào đã được xác minh? | Chủ đơn hủy được; người khác bị từ chối |
| Mutation testing | Test có phát hiện các thay đổi sai trong code không? | Bỏ điều kiện owner làm test thất bại |

### Vì sao line coverage cao vẫn có thể bỏ sót lỗi?

Giả sử code:

    if (order.isPending() && accessPolicy.isOwner(actor, order)) {
        order.cancel();
    }

Một test chỉ dùng đơn đang chờ và chủ sở hữu có thể chạy qua mọi dòng. Tuy nhiên, nó chưa chứng minh:

- Đơn đã giao bị từ chối.
- Người không sở hữu đơn bị từ chối.
- Khi một điều kiện sai, trạng thái không thay đổi.
- Hai điều kiện kết hợp đúng trong các trường hợp khác nhau.

Một test có thể đạt line coverage 100% mà vẫn thiếu các tổ hợp điều kiện hoặc hành vi quan trọng. Ngược lại, một số dòng code có thể không được thực thi trong test nhưng thuộc mã xử lý nền tảng hoặc trường hợp không thể xảy ra. Vì vậy, không nên dùng một tỷ lệ duy nhất làm đại diện cho chất lượng.

### Coverage không đồng nghĩa chất lượng test

Test cần có assertion đủ mạnh. Một test gọi endpoint rồi chỉ kiểm tra status 200 có thể không phát hiện response thiếu dữ liệu, sai owner hoặc ghi sai trạng thái. Coverage report cho biết code đã chạy; assertion và test design mới xác định điều gì đã được kiểm chứng.

## 3. Xác định đơn vị hành vi

Trước khi viết test, hãy chia chức năng thành các hành vi có phạm vi rõ ràng. Có thể dùng mẫu:

    Actor + Preconditions + Action + Expected outcome

Ví dụ:

| Thành phần | Giá trị |
|---|---|
| Actor | Alice, chủ đơn hàng |
| Preconditions | Đơn hàng đang ở trạng thái PENDING |
| Action | Gửi yêu cầu hủy đơn |
| Expected outcome | Đơn chuyển sang CANCELLED; response thành công; audit event được ghi |

Một tình huống khác:

| Thành phần | Giá trị |
|---|---|
| Actor | Bob, không phải chủ đơn |
| Preconditions | Đơn hàng của Alice đang PENDING |
| Action | Bob gửi yêu cầu hủy |
| Expected outcome | Request bị từ chối; trạng thái và audit log nghiệp vụ không thay đổi |

Mỗi hành vi cần làm rõ:

- Ai thực hiện?
- Tài nguyên nào bị tác động?
- Trạng thái ban đầu là gì?
- Điều kiện nào phải đúng?
- Hành động được yêu cầu là gì?
- Kết quả thành công hoặc thất bại ra sao?
- Có side effect nào được phép xảy ra?
- Kết quả được quan sát ở HTTP, domain hay persistence?

### Phân biệt hành vi chính và hành vi phụ

Hành vi chính là kết quả mà use case cam kết. Hành vi phụ có thể gồm log, metric, audit hoặc notification. Không phải mọi chi tiết nội bộ đều cần một test riêng; hãy kiểm tra side effect nếu nó ảnh hưởng đến tính đúng đắn, bảo mật, khả năng truy vết hoặc hợp đồng tích hợp.

## 4. Xây dựng danh mục hành vi

Danh mục hành vi là tập hợp các tình huống cần được kiểm thử cho một chức năng hoặc module. Có thể lấy thông tin từ:

- User story và acceptance criteria.
- Use case và business rule.
- API contract hoặc form contract.
- State machine và domain invariant.
- Security policy.
- Error handling policy.
- Event và integration contract.
- Incident đã xảy ra.
- Những thay đổi gần đây hoặc vùng code có rủi ro cao.

Đừng chỉ đọc Controller để tạo danh sách. Một endpoint có thể gọi nhiều use case; cùng một use case có thể được gọi từ API, form, job hoặc message handler.

### Ví dụ danh mục cho chức năng hủy đơn

| ID | Hành vi | Mức rủi ro |
|---|---|---|
| ORD-CAN-01 | Chủ đơn hủy đơn PENDING thành công | Cao |
| ORD-CAN-02 | Người khác không hủy được đơn | Rất cao |
| ORD-CAN-03 | Không hủy được đơn SHIPPED | Cao |
| ORD-CAN-04 | ID không tồn tại trả lỗi phù hợp | Trung bình |
| ORD-CAN-05 | Request thiếu CSRF token với session auth | Cao |
| ORD-CAN-06 | Request bị từ chối không cập nhật dữ liệu | Rất cao |
| ORD-CAN-07 | Hủy thành công ghi audit/event đúng semantics | Cao |
| ORD-CAN-08 | Gửi lại request không tạo side effect trùng | Cao |

Danh mục nên được review cùng người hiểu nghiệp vụ và người chịu trách nhiệm bảo mật. Một hành vi chưa được ghi nhận rất dễ bị bỏ khỏi test suite.

## 5. Ma trận truy vết yêu cầu – hành vi – test

Ma trận truy vết (traceability matrix) liên kết yêu cầu với hành vi và test thực thi. Nó giúp trả lời hai câu hỏi:

1. Mỗi yêu cầu quan trọng đã có test chưa?
2. Mỗi test đang bảo vệ hành vi hoặc rủi ro nào?

Ví dụ:

| Requirement | Behavior ID | Test | Tầng |
|---|---|---|---|
| Chủ đơn được hủy khi PENDING | ORD-CAN-01 | cancelPendingOrderByOwner | Application |
| Người khác không được hủy | ORD-CAN-02 | rejectsCancellationByNonOwner | Policy + MVC |
| Không hủy đơn đã giao | ORD-CAN-03 | rejectsCancellationAfterShipment | Domain |
| Đơn không tồn tại trả 404 | ORD-CAN-04 | missingOrderReturnsNotFound | MVC |
| CSRF bắt buộc | ORD-CAN-05 | postWithoutCsrfIsRejected | Security MVC |
| Request bị từ chối không ghi dữ liệu | ORD-CAN-06 | deniedCancelDoesNotPersist | Persistence integration |
| Audit event được ghi | ORD-CAN-07 | successfulCancelPublishesAudit | Application integration |
| Retry không lặp tác dụng phụ | ORD-CAN-08 | repeatedCancelIsIdempotent | Integration |

Có thể một hành vi cần nhiều test ở các tầng khác nhau. Ví dụ, policy test xác nhận người không sở hữu bị từ chối; MVC test xác nhận lỗi được chuyển thành status phù hợp; persistence test xác nhận dữ liệu không đổi.

### Đừng biến ma trận thành danh sách method

Một test method có thể xác minh nhiều assertion, nhưng tên method không tự chứng minh hành vi đã được kiểm tra. Hãy ghi rõ điều kiện và kết quả. Một hành vi có thể cần test parameterized hoặc test theo state transition.

### Trạng thái truy vết

Có thể dùng các trạng thái:

- Covered: có test chạy và assertion đủ để xác minh.
- Partial: có test nhưng thiếu một nhánh, actor hoặc kết quả quan trọng.
- Missing: chưa có test.
- Deferred: được hoãn có lý do và có người chịu trách nhiệm.
- Not applicable: không áp dụng, kèm lý do.

Không đánh dấu Covered chỉ vì có test trùng tên với yêu cầu.

## 6. Chọn test bằng phân vùng tương đương

Phân vùng tương đương (equivalence partitioning) chia đầu vào thành các nhóm mà hệ thống dự kiến xử lý theo cùng quy tắc. Thay vì thử mọi giá trị, chọn đại diện cho mỗi nhóm.

Ví dụ trường số lượng bản sách phải là số nguyên không âm:

| Phân vùng | Ví dụ | Kết quả |
|---|---:|---|
| Số âm | -1 | Từ chối |
| Số 0 | 0 | Chấp nhận |
| Số dương hợp lệ | 4 | Chấp nhận |
| Vượt giới hạn nghiệp vụ | 1000000 | Từ chối nếu có giới hạn |
| Không phải số nguyên | abc | Lỗi binding/conversion |
| Thiếu giá trị | Không gửi field | Lỗi binding/validation |

Một test đại diện cho mỗi phân vùng giúp phát hiện các nhóm lỗi khác nhau. Nếu quy tắc thay đổi theo loại actor hoặc trạng thái tài nguyên, cần chia phân vùng theo các điều kiện đó nữa.

### Không gộp các phân vùng chỉ vì chúng đều thất bại

Số âm, giá trị sai định dạng và giá trị vượt giới hạn đều có thể bị từ chối, nhưng tầng xử lý và response có thể khác nhau. Nếu contract yêu cầu lỗi validation theo field, test phải phân biệt đúng loại lỗi.

## 7. Chọn test bằng giá trị biên

Lỗi thường xuất hiện tại ranh giới giữa hợp lệ và không hợp lệ. Với một giới hạn từ 0 đến 100, các giá trị đáng kiểm tra gồm:

- -1: ngay dưới giới hạn dưới.
- 0: giới hạn dưới.
- 1: ngay trên giới hạn dưới.
- 99: ngay dưới giới hạn trên.
- 100: giới hạn trên.
- 101: ngay trên giới hạn trên.

Nếu có quy tắc ngày, thời gian, kích thước file hoặc số lần retry, hãy kiểm tra ngay trước, đúng tại và ngay sau ranh giới.

### Ví dụ với thời hạn hủy

Giả sử người dùng được hủy đơn trong vòng 15 phút kể từ khi đặt:

| Thời điểm | Kết quả theo chính sách giả định |
|---|---|
| 14 phút 59 giây | Được hủy |
| Đúng 15 phút | Xác định rõ chính sách inclusive/exclusive |
| 15 phút 1 giây | Bị từ chối |

Không tự suy đoán toán tử ở biên. Acceptance criteria phải xác định thời điểm đúng 15 phút thuộc phía nào, rồi test phải cố định semantics đó.

## 8. Dùng decision table cho nhiều điều kiện

Khi kết quả phụ thuộc nhiều điều kiện Boolean, decision table giúp liệt kê các tổ hợp có ý nghĩa.

Ví dụ chính sách hủy đơn:

- A: actor là chủ đơn hoặc có quyền quản trị.
- B: đơn ở trạng thái PENDING.
- C: request thỏa điều kiện thời hạn.

| A | B | C | Kết quả |
|---|---|---|---|
| Đúng | Đúng | Đúng | Cho phép hủy |
| Sai | Đúng | Đúng | Từ chối quyền |
| Đúng | Sai | Đúng | Từ chối trạng thái |
| Đúng | Đúng | Sai | Từ chối thời hạn |
| Sai | Sai | Đúng | Từ chối theo policy đã định |
| Sai | Đúng | Sai | Từ chối quyền/thời hạn |
| Đúng | Sai | Sai | Từ chối trạng thái/thời hạn |
| Sai | Sai | Sai | Từ chối |

Bảng trên minh họa các tổ hợp; response ưu tiên khi nhiều điều kiện cùng sai cần được định nghĩa theo chính sách bảo mật và error contract. Test không nhất thiết phải kiểm tra mọi tổ hợp nếu một số tổ hợp không thể xảy ra, nhưng cần giải thích lý do loại trừ.

### MC/DC và condition coverage

Với logic an toàn hoặc quyết định quan trọng, có thể dùng Modified Condition/Decision Coverage (MC/DC) để chứng minh mỗi điều kiện Boolean có thể độc lập làm thay đổi kết quả quyết định. Đây là kỹ thuật mạnh hơn branch coverage trong một số bối cảnh, nhưng không thay thế kiểm thử hành vi nghiệp vụ đầy đủ.

## 9. Dùng state transition để kiểm thử vòng đời nghiệp vụ

Nhiều domain object có trạng thái và chỉ cho phép một số chuyển đổi. Test cần xác minh chuyển đổi hợp lệ và chuyển đổi bị cấm.

Ví dụ đơn hàng:

    PENDING -> CONFIRMED -> SHIPPED -> DELIVERED
        |
        +----> CANCELLED

Một bảng chuyển đổi có thể là:

| Trạng thái hiện tại | Hành động | Trạng thái sau | Kết quả |
|---|---|---|---|
| PENDING | Confirm | CONFIRMED | Hợp lệ |
| PENDING | Cancel | CANCELLED | Hợp lệ nếu actor có quyền |
| CONFIRMED | Ship | SHIPPED | Hợp lệ |
| SHIPPED | Deliver | DELIVERED | Hợp lệ |
| SHIPPED | Cancel | Không đổi | Từ chối |
| DELIVERED | Cancel | Không đổi | Từ chối |
| CANCELLED | Ship | Không đổi | Từ chối |

Test state transition nên xác nhận:

- Trạng thái mới đúng.
- Trạng thái cũ không bị thay đổi khi transition thất bại.
- Event chỉ phát khi transition thành công.
- Transition không hợp lệ trả lỗi đúng.
- Request lặp hoặc đồng thời không làm trạng thái quay lui.

## 10. Áp dụng behavior coverage vào từng lớp MVC

Mỗi tầng có thể có hành vi riêng, nhưng không nên kiểm tra mọi thứ ở Controller test.

### Controller và HTTP boundary

Bao phủ:

- URL và HTTP method.
- Path variable, query parameter, header và body.
- Binding và validation.
- Authentication và authorization ở ranh giới web.
- Status, redirect, response body và content type.
- View name và model attributes.
- Error mapping.

### Application service

Bao phủ:

- Use case thành công.
- Các điều kiện từ chối.
- Trình tự phối hợp domain/repository.
- Transaction và side effect.
- Quy tắc idempotency.
- Các lỗi từ dependency.

### Domain model

Bao phủ:

- Invariant.
- State transition hợp lệ.
- State transition bị cấm.
- Boundary và decision rule.
- Kết quả tính toán.

### Persistence

Bao phủ:

- Lưu và đọc trạng thái đúng.
- Query giới hạn owner/tenant.
- Constraint và uniqueness.
- Transaction rollback khi lỗi.
- Optimistic locking hoặc concurrency behavior nếu có.

### View

Bao phủ:

- Dữ liệu cần thiết được render.
- Trạng thái empty, loading hoặc error nếu có.
- Validation message hiển thị đúng.
- Hành động chỉ hiện khi phù hợp với quyền.
- Nội dung không tin cậy được escape.
- Form gửi đúng field và token cần thiết.

Ẩn nút trong View không thay thế authorization ở server. Cần có test trực tiếp gọi endpoint với actor không có quyền.

## 11. Xây dựng ma trận behavior cho một endpoint MVC

Ví dụ endpoint POST /orders/{id}/cancel:

| Nhóm | Tình huống | Kết quả cần xác minh |
|---|---|---|
| Thành công | Chủ đơn, PENDING | Redirect hoặc response thành công; trạng thái CANCELLED |
| Authentication | Anonymous | Login redirect hoặc 401 theo client type |
| Authorization | User khác | 403/404 theo policy; không đổi dữ liệu |
| State | SHIPPED | Conflict; không đổi dữ liệu |
| Resource | ID không tồn tại | 404 theo contract |
| Input | ID sai định dạng | Binding/conversion error phù hợp |
| CSRF | Thiếu token với session auth | Bị security filter từ chối |
| Persistence | Lỗi khi lưu | Transaction rollback |
| Side effect | Hủy thành công | Audit/event theo hợp đồng |
| Retry | Gửi lại request | Không tạo side effect trùng ngoài semantics |

Từ ma trận này, nhóm có thể quyết định test ở tầng nào. Không cần một end-to-end test cho mọi tổ hợp; nhiều quy tắc nên được kiểm thử nhanh ở domain hoặc application layer, còn một số luồng đại diện được kiểm tra xuyên suốt MVC.

## 12. Chọn đúng tầng kiểm thử

Một chiến lược hợp lý thường có nhiều tầng:

| Tầng | Phạm vi | Loại hành vi phù hợp |
|---|---|---|
| Unit test | Method/domain/policy | Rule, boundary, transition, decision |
| Application test | Use case và dependency giả lập | Orchestration, quyền, side effect |
| MVC slice test | Controller và Spring MVC infrastructure | Mapping, binding, validation, response |
| Security integration test | Filter chain và security config | Authentication, authorization, CSRF |
| Persistence integration test | ORM và database | Query, constraint, transaction |
| End-to-end test | Browser/API đến hệ thống | Luồng người dùng quan trọng |

### Tránh dồn toàn bộ behavior coverage vào E2E

End-to-end test có chi phí cao, dễ chậm và dễ flaky. Nếu một domain rule có thể được kiểm tra bằng unit test, hãy kiểm tra ở đó. E2E nên xác nhận một số hành trình đại diện và tích hợp quan trọng.

### Không chỉ có unit test

Unit test không chứng minh route được map đúng, template render đúng, security filter được cấu hình hoặc transaction database hoạt động. Cần test ở ranh giới nơi hành vi được công bố.

## 13. Ví dụ unit test cho domain behavior

Giả sử Order có thể hủy khi ở trạng thái PENDING:

    public class Order {
        private final UUID id;
        private OrderStatus status;

        public Order(UUID id, OrderStatus status) {
            this.id = id;
            this.status = status;
        }

        public void cancel() {
            if (status != OrderStatus.PENDING) {
                throw new IllegalStateException(
                        "Only pending orders can be cancelled");
            }

            status = OrderStatus.CANCELLED;
        }

        public OrderStatus status() {
            return status;
        }
    }

Test hành vi hợp lệ:

    @Test
    void pendingOrderCanBeCancelled() {
        Order order = new Order(
                UUID.randomUUID(),
                OrderStatus.PENDING);

        order.cancel();

        assertEquals(OrderStatus.CANCELLED, order.status());
    }

Test hành vi bị cấm:

    @Test
    void shippedOrderCannotBeCancelled() {
        Order order = new Order(
                UUID.randomUUID(),
                OrderStatus.SHIPPED);

        assertThrows(
                IllegalStateException.class,
                order::cancel);

        assertEquals(OrderStatus.SHIPPED, order.status());
    }

Test thứ hai không chỉ xác nhận có exception mà còn xác nhận trạng thái không đổi. Đây là assertion về hành vi quan trọng.

## 14. Ví dụ application service test

Use case cần tải đơn, kiểm tra quyền và yêu cầu domain hủy. Khi quyền bị từ chối, repository không được lưu và event không được phát.

    @Test
    void nonOwnerCannotCancelOrder() {
        Order order = pendingOrderOwnedBy("alice");

        when(repository.findById(order.id()))
                .thenReturn(Optional.of(order));

        doThrow(new AccessDeniedException("Denied"))
                .when(accessPolicy)
                .checkCanCancel("bob", order);

        assertThrows(
                AccessDeniedException.class,
                () -> cancelOrder.execute(
                        new CancelOrderCommand("bob", order.id())));

        verify(repository, never()).save(any());
        verify(eventPublisher, never()).publish(any());
        assertEquals(OrderStatus.PENDING, order.status());
    }

Test này bao phủ một hành vi application: actor không có quyền bị từ chối trước khi ghi dữ liệu hoặc phát event. Nó không thay thế test cho access policy; policy cần test riêng các tổ hợp owner, admin, tenant và action.

## 15. Ví dụ MVC test với MockMvc

MockMvc giúp kiểm tra HTTP contract và Spring MVC mapping mà không cần khởi chạy server thật cho mỗi test.

    @WebMvcTest(OrderController.class)
    class OrderControllerTest {

        @Autowired
        MockMvc mockMvc;

        @MockBean
        CancelOrder cancelOrder;

        @Test
        @WithMockUser(username = "alice", roles = "USER")
        void successfulCancellationRedirectsToOrder() throws Exception {
            UUID orderId = UUID.randomUUID();

            mockMvc.perform(post("/orders/" + orderId + "/cancel")
                            .with(csrf()))
                    .andExpect(status().is3xxRedirection())
                    .andExpect(redirectedUrl("/orders/" + orderId));
        }
    }

Ví dụ giả định Controller dùng form login và Post/Redirect/Get. Nếu endpoint là REST API, response có thể là 200, 202 hoặc 204 theo contract. Nếu test chỉ dùng @WithMockUser, nó tạo security context giả và không kiểm tra quy trình login/session thật.

### Test request bị từ chối

Có thể kiểm tra anonymous và user thiếu quyền:

    @Test
    void anonymousRequestIsNotAllowed() throws Exception {
        mockMvc.perform(post("/orders/42/cancel")
                        .with(csrf()))
                .andExpect(status().is3xxRedirection());
    }

    @Test
    @WithMockUser(username = "viewer", roles = "VIEWER")
    void viewerCannotCancelOrder() throws Exception {
        mockMvc.perform(post("/orders/42/cancel")
                        .with(csrf()))
                .andExpect(status().isForbidden());
    }

Status cụ thể phụ thuộc cấu hình AuthenticationEntryPoint và AccessDeniedHandler. Hãy kiểm tra đúng contract của ứng dụng.

### Test CSRF riêng

    @Test
    @WithMockUser(username = "alice", roles = "USER")
    void missingCsrfTokenIsRejected() throws Exception {
        mockMvc.perform(post("/orders/42/cancel"))
                .andExpect(status().isForbidden());
    }

Test này xác nhận security filter chain từ chối request thiếu token. Nó không xác nhận object-level authorization; đó là hành vi cần test riêng.

## 16. Kiểm thử response và View behavior

Với server-rendered MVC, status 200 chưa đủ. Cần xác nhận đúng View và Model attributes:

    mockMvc.perform(get("/orders/42"))
            .andExpect(status().isOk())
            .andExpect(view().name("orders/detail"))
            .andExpect(model().attributeExists("order"))
            .andExpect(model().attribute("canCancel", true));

Có thể bổ sung template integration test để xác nhận:

- Tên đơn và trạng thái được render.
- Nút hủy xuất hiện khi canCancel là true.
- Nút không xuất hiện khi canCancel là false.
- Validation error được hiển thị cạnh field.
- Nội dung người dùng nhập được escape.

Nếu dùng Thymeleaf, test render template thực tế để phát hiện lỗi biểu thức hoặc fragment. Controller slice test có thể kiểm tra model và view name nhưng chưa chắc xác nhận mọi chi tiết HTML cuối cùng.

## 17. Kiểm thử persistence và transaction behavior

Các hành vi liên quan database cần test với repository hoặc database phù hợp.

Ví dụ:

- Hủy đơn thành công được lưu.
- Request bị từ chối không ghi dữ liệu.
- Exception trong transaction làm rollback.
- Unique constraint được thực thi.
- Query không trả dữ liệu của tenant khác.
- Optimistic lock phát hiện cập nhật đồng thời.
- Retry không tạo bản ghi audit hoặc event trùng.

Một unit test mock repository chỉ xác nhận code yêu cầu gọi save hoặc không gọi save. Nó không chứng minh SQL, mapping, transaction hoặc constraint hoạt động. Với những hành vi đó, dùng integration test với database thật hoặc Testcontainers phù hợp.

### Kiểm tra rollback

Có thể cố tình làm một dependency thất bại sau thao tác ghi trong cùng transaction, sau đó đọc lại database để xác nhận dữ liệu đã rollback. Test phải chạy qua Spring transaction proxy; tự tạo service bằng new sẽ không kiểm tra được annotation transaction.

## 18. Kiểm thử hành vi bảo mật

Security behavior thường có rủi ro cao và cần được đưa rõ vào danh mục.

Bao phủ:

- Anonymous và authenticated user.
- Role/authority đủ và thiếu.
- Owner và non-owner.
- Tenant đúng và tenant khác.
- Quyền đọc khác quyền sửa/xóa.
- Field nhạy cảm không thể bị mass assignment.
- CSRF token hợp lệ và thiếu.
- Session logout và timeout.
- Không lộ dữ liệu khi trả 403/404.
- Request bị từ chối không gây side effect.

Một ma trận actor–resource–action giúp tránh chỉ test role. Ví dụ hai user cùng role USER nhưng chỉ owner mới được sửa tài nguyên.

### Test không được dựa vào giao diện

Ẩn nút không có nghĩa endpoint an toàn. Hãy gọi trực tiếp endpoint bằng MockMvc hoặc API test với actor không có quyền. Đồng thời kiểm tra dữ liệu không đổi sau request bị từ chối.

## 19. Đo coverage tự động bằng JaCoCo

JaCoCo có thể tạo báo cáo coverage cho Java code. Với Maven, có thể thêm plugin JaCoCo vào build để thu thập execution data và tạo report.

Ví dụ cấu hình rút gọn:

    <plugin>
        <groupId>org.jacoco</groupId>
        <artifactId>jacoco-maven-plugin</artifactId>
        <version>0.8.12</version>
        <executions>
            <execution>
                <goals>
                    <goal>prepare-agent</goal>
                </goals>
            </execution>
            <execution>
                <id>report</id>
                <phase>verify</phase>
                <goals>
                    <goal>report</goal>
                </goals>
            </execution>
        </executions>
    </plugin>

Chạy:

    mvn clean verify

Báo cáo HTML thường nằm dưới target/site/jacoco/index.html. Đường dẫn có thể thay đổi theo module hoặc cấu hình build.

JaCoCo cung cấp thông tin về instruction, line, branch, complexity và các class/method chưa được thực thi. Nó không tự biết một acceptance criterion hoặc business behavior đã được kiểm chứng hay chưa.

### Dùng coverage làm tín hiệu

Có thể đặt ngưỡng cho branch hoặc line coverage ở module quan trọng, nhưng không nên chọn ngưỡng chỉ để đạt một con số đẹp. Đánh giá:

- Mã nghiệp vụ quan trọng có test chưa?
- Các nhánh từ chối có được xác minh không?
- Thay đổi mới có làm giảm coverage không?
- Test có assertion đủ mạnh không?
- Có phần code chưa test nhưng rủi ro thấp và có lý do rõ không?

Không loại bỏ test hoặc viết test vô nghĩa chỉ để làm report đạt ngưỡng.

## 20. Mutation testing để đánh giá sức mạnh của test

Mutation testing tạo ra các thay đổi nhỏ có chủ ý trong code, gọi là mutants. Ví dụ:

- Đổi toán tử lớn hơn thành lớn hơn hoặc bằng.
- Đổi AND thành OR.
- Bỏ điều kiện kiểm tra owner.
- Thay số lượng cộng thêm 1 thành cộng thêm 2.
- Bỏ lời gọi publish event.
- Thay status code hoặc nhánh xử lý lỗi.

Nếu test thất bại khi mutant được đưa vào, mutant bị killed. Nếu test vẫn xanh, mutant sống sót (survived) và có thể chỉ ra một khoảng trống trong test suite hoặc một thay đổi không ảnh hưởng hành vi.

Mutation score thường được tính:

    mutation score =
        killed mutants / (valid mutants - excluded mutants) * 100%

Cần loại trừ mutant tương đương (equivalent mutants) và phân tích các mutant bị timeout hoặc không chạy. Một mutation score cao không tự chứng minh mọi hành vi đã được bao phủ, nhưng giúp đánh giá test có phát hiện các lỗi nhỏ có ý nghĩa hay không.

### Ví dụ

Code:

    if (quantity > 0 && quantity <= stock) {
        reserve(quantity);
    }

Mutant có thể đổi quantity lớn hơn 0 thành quantity lớn hơn hoặc bằng 0. Nếu test chỉ kiểm tra quantity bằng 1, mutant vẫn sống. Bổ sung test quantity bằng 0 sẽ phát hiện sai lệch ở biên.

Mutation testing nên tập trung vào domain rule, authorization và logic có rủi ro cao trước khi áp dụng rộng cho toàn repository.

## 21. Phát hiện khoảng trống trong bộ test

Một cách review thực tế là đi từ hành vi đến test và từ test quay lại hành vi.

### Từ hành vi đến test

Với mỗi dòng trong behavior catalog, hỏi:

- Có test cụ thể không?
- Test chạy ở tầng nào?
- Có điều kiện ban đầu đúng không?
- Assertion xác nhận đúng kết quả không?
- Có xác nhận trạng thái hoặc side effect không?
- Test có thể thất bại nếu hành vi bị phá không?

### Từ test đến hành vi

Với mỗi test, hỏi:

- Nó bảo vệ yêu cầu nào?
- Nó có trùng với test khác không?
- Nó chỉ kiểm tra implementation detail hay hành vi?
- Nó có assertion có ý nghĩa không?
- Có thể loại bỏ test mà không mất bằng chứng nào không?

Test không truy được về hành vi hoặc rủi ro nào có thể là test thừa, nhưng cần xem xét trước khi xóa vì nó có thể bảo vệ một contract kỹ thuật quan trọng.

### Dấu hiệu của test yếu

- Chỉ assert response không null.
- Chỉ kiểm tra status 200 cho mọi tình huống.
- Không kiểm tra state sau thao tác.
- Không xác nhận side effect hoặc sự vắng mặt của side effect.
- Dùng cùng một actor cho cả positive và negative path.
- Không có dữ liệu ở trạng thái biên.
- Mock mọi dependency nên không kiểm tra integration cần thiết.
- Test phụ thuộc thứ tự chạy hoặc dùng dữ liệu dùng chung không được reset.
- Assertion không phân biệt được kết quả đúng và một số kết quả sai.

## 22. Ưu tiên coverage theo rủi ro

Không phải hành vi nào cũng có cùng mức độ quan trọng. Khi thời gian hạn chế, ưu tiên theo tác động và khả năng xảy ra.

Có thể đánh giá:

- Impact: Nếu sai, hậu quả là gì?
- Likelihood: Khả năng lỗi xuất hiện cao đến đâu?
- Exposure: Chức năng được dùng thường xuyên hoặc mở ra bên ngoài không?
- Change frequency: Code thay đổi thường xuyên không?
- Complexity: Có nhiều điều kiện, trạng thái hoặc tích hợp không?
- Detectability: Lỗi có dễ được phát hiện trước khi gây thiệt hại không?

Ví dụ:

| Hành vi | Rủi ro | Ưu tiên test |
|---|---|---|
| Authorization trên tài nguyên riêng tư | Rất cao | Bắt buộc |
| Tính tổng tiền hoặc tồn kho | Rất cao | Bắt buộc |
| Transaction và rollback | Cao | Cao |
| Validation form cơ bản | Trung bình–cao | Cao |
| Empty state của trang nội dung | Thấp–trung bình | Theo mức sử dụng |
| Căn lề một nhãn trang trí | Thấp | Visual test chọn lọc |

Không dùng risk score để bỏ qua yêu cầu pháp lý, bảo mật hoặc acceptance criteria bắt buộc. Risk-based testing giúp ưu tiên chiều sâu, không xóa trách nhiệm kiểm thử.

## 23. Coverage trong thay đổi và code review

Mỗi pull request có thể ghi rõ:

- Hành vi nào được thêm hoặc thay đổi?
- Behavior ID hoặc acceptance criteria nào liên quan?
- Test mới nằm ở tầng nào?
- Có test positive và negative path không?
- Có thay đổi contract HTTP, View hoặc event không?
- Có ảnh hưởng security, transaction hoặc data migration không?
- Coverage report có giảm ở vùng code quan trọng không?
- Có khoảng trống nào được chấp nhận và ai chịu trách nhiệm?

Reviewer nên kiểm tra test có thể phát hiện lỗi thực tế. Không chỉ đếm số test method hoặc nhìn tỷ lệ coverage tổng.

### Khi hành vi thay đổi

Nếu sản phẩm chủ ý đổi hành vi, hãy cập nhật:

1. Acceptance criteria hoặc behavior catalog.
2. Traceability matrix.
3. Test kỳ vọng cũ.
4. Test mới cho behavior mới.
5. Tài liệu API/View hoặc runbook liên quan.

Không sửa expected result chỉ để làm test xanh nếu chưa xác nhận thay đổi là đúng theo yêu cầu.

## 24. Giữ test ổn định và có thể lặp lại

Một bộ test behavior chỉ hữu ích nếu có thể chạy ổn định.

- Mỗi test tự chuẩn bị dữ liệu cần thiết.
- Không phụ thuộc thứ tự test.
- Reset repository hoặc database giữa test.
- Dùng clock giả lập cho quy tắc thời gian.
- Tránh sleep cố định để chờ async; dùng Awaitility hoặc cơ chế đồng bộ có timeout.
- Không gọi dịch vụ production thật trong test.
- Dùng fixture thể hiện rõ actor, resource và state.
- Kiểm tra race condition bằng test concurrency có đồng bộ.
- Ghi nhận lý do khi một test bị disabled hoặc flaky.

Với quy tắc thời gian, inject Clock giúp test thời điểm biên có tính xác định. Với ID ngẫu nhiên, giữ ID trong biến để assertion và trace rõ ràng.

## 25. Quy trình đánh giá behavior coverage

Có thể áp dụng quy trình sau trong design review:

1. Chọn use case hoặc thay đổi cần đánh giá.
2. Đọc acceptance criteria, business rule và API/View contract.
3. Liệt kê actor, resource, state và action.
4. Xác định positive, negative, boundary và error scenarios.
5. Bổ sung security, persistence và side effect behaviors.
6. Gán ID cho từng hành vi và mức rủi ro.
7. Liên kết mỗi hành vi với test hiện có hoặc test cần viết.
8. Xác định tầng test phù hợp cho từng hành vi.
9. Đọc assertion để xác nhận test thực sự chứng minh kết quả.
10. Xem line/branch coverage để tìm code chưa được thực thi.
11. Dùng mutation testing cho vùng logic quan trọng khi phù hợp.
12. Ghi rõ missing, partial hoặc deferred behaviors.
13. Đề xuất test bổ sung trước khi chấp nhận thay đổi có rủi ro cao.
14. Cập nhật ma trận khi contract hoặc nghiệp vụ thay đổi.

## 26. Ví dụ review tổng hợp

Một pull request thêm chức năng cập nhật số lượng sách trong ứng dụng MVC. Reviewer không nên chỉ xem Controller có test GET và POST hay chưa.

Danh mục hành vi có thể là:

| ID | Hành vi | Test phù hợp |
|---|---|---|
| BOOK-QTY-01 | Số lượng hợp lệ được cập nhật | Application + MVC |
| BOOK-QTY-02 | Số lượng bằng 0 được chấp nhận | Boundary unit + MVC |
| BOOK-QTY-03 | Số lượng âm bị từ chối | Validation + domain |
| BOOK-QTY-04 | ID không tồn tại trả 404 | MVC |
| BOOK-QTY-05 | User không có quyền không cập nhật được | Security + application |
| BOOK-QTY-06 | Dữ liệu không đổi khi validation thất bại | Persistence integration |
| BOOK-QTY-07 | Hai View hiển thị số lượng mới | MVC/template integration |
| BOOK-QTY-08 | Hai request cập nhật đồng thời không làm mất dữ liệu theo policy | Concurrency integration |

Reviewer kiểm tra test BOOK-QTY-07 phải tải cả hai View sau khi cập nhật và xác nhận nội dung phản ánh cùng nguồn dữ liệu. Chỉ assert hai endpoint trả 200 chưa chứng minh yêu cầu đó.

Nếu code có branch cho số lượng âm và dương nhưng test chỉ gửi số dương, branch report có thể phát hiện nhánh chưa chạy. Tuy nhiên, behavior catalog mới giải thích vì sao cần test số âm và kết quả dữ liệu không đổi.

## 27. Checklist đánh giá mức bao phủ hành vi

### Danh mục và truy vết

- Yêu cầu và business rule quan trọng đã được chuyển thành hành vi cụ thể.
- Mỗi hành vi có actor, precondition, action và expected outcome.
- Hành vi có ID hoặc cách tham chiếu ổn định.
- Mỗi hành vi được liên kết với test và tầng test.
- Missing/partial/deferred có lý do và owner.

### Thiết kế test

- Có positive và negative path.
- Có phân vùng tương đương và giá trị biên.
- Decision table hoặc state transition được dùng khi có nhiều điều kiện/trạng thái.
- Security, error và side effect behaviors được bao phủ.
- Assertion kiểm tra kết quả và dữ liệu sau thao tác.
- Test không chỉ xác nhận code đã chạy.

### Các tầng MVC

- Controller mapping, binding, validation và response được kiểm tra.
- Application use case và domain invariant được kiểm tra.
- Persistence, transaction và concurrency được kiểm tra khi liên quan.
- View render và form contract được kiểm tra.
- Authentication, authorization và CSRF được kiểm tra.
- Integration và E2E bao phủ các luồng đại diện.

### Chất lượng bộ test

- Test độc lập, ổn định và có thể lặp lại.
- Coverage report được dùng để tìm vùng code chưa chạy.
- Mutation testing được cân nhắc cho logic rủi ro cao.
- Không chạy theo 100% coverage bằng assertion yếu.
- Pull request nêu rõ behavior coverage và khoảng trống còn lại.

## Kết luận

Kiểm tra mức bao phủ hành vi bắt đầu từ câu hỏi hệ thống phải phản ứng thế nào trong từng tình huống. Danh mục hành vi và ma trận truy vết liên kết yêu cầu với test; phân vùng tương đương, giá trị biên, decision table và state transition giúp chọn tình huống có ý nghĩa. Trong MVC, cần kiểm tra từ HTTP boundary đến application/domain, persistence và View, đặt mỗi hành vi ở tầng test phù hợp.

Line và branch coverage cho biết code đã được thực thi đến đâu; mutation testing cho biết test có phát hiện một số thay đổi sai hay không. Các tín hiệu này bổ sung cho việc review assertion và traceability. Một bộ test có độ bao phủ hành vi tốt chứng minh được cả đường thành công, đường từ chối, trạng thái sau thao tác và side effect quan trọng, từ đó tạo cơ sở đáng tin cậy hơn cho design review và thay đổi hệ thống.
