# Batch item isolation — Cô lập từng phần tử trong xử lý hàng loạt

## 1. Cô lập item bảo vệ điều gì?

Trong chương **Batch Operations** của Business Logic Security, batch item isolation là việc giữ cho danh tính, dữ liệu đầu vào, quyết định quyền, thay đổi trạng thái, lỗi và kết quả của từng phần tử không bị lẫn sang phần tử khác.

Một vòng `for` chưa tạo ra sự cô lập. Mỗi item chạy trên một thread riêng cũng chưa đủ. Lỗi có thể xuất hiện ở nhiều lớp: dùng nhầm tenant từ item trước, dùng lại entity đã bị sửa, rollback chung ngoài ý muốn, ghi trạng thái thành công trước commit hoặc retry cả batch làm lặp tác động của item đã hoàn tất.

Xét API hủy nhiều đơn hàng. Hợp đồng của ví dụ là xử lý độc lập từng đơn đủ điều kiện:

| Item | Dữ liệu ban đầu | Kết quả mong đợi |
| --- | --- | --- |
| A | Actor được hủy, đơn còn chờ và phiên bản đúng | Hủy đơn, giải phóng reservation đúng một lần |
| B | Đơn thuộc tenant khác | Không tác động, không tiết lộ dữ liệu của đơn |
| C | Actor được hủy nhưng phiên bản đã cũ | Không ghi theo dữ liệu cũ |
| D | Actor được hủy, dữ liệu hợp lệ | Vẫn có thể thành công dù B và C bị từ chối |

Mục tiêu của bài là thiết kế ranh giới xử lý để giữ các invariant như quyền theo đối tượng, state machine, số lượng giữ kho, transaction và idempotency khi một request chứa nhiều lệnh.

## 2. Trước hết phải xác định đơn vị nghiệp vụ độc lập

### 2.1. Item của JSON chưa chắc là đơn vị transaction

Một item có thể chứa nhiều thay đổi cần đi cùng nhau. Hủy một đơn có thể cần:

```text
chuyển trạng thái đơn
+ ghi biên bản hủy
+ đánh dấu reservation đã giải phóng
+ cập nhật số lượng liên quan
+ ghi outbox
+ ghi receipt chống xử lý trùng
```

Nếu chỉ trạng thái đơn được commit còn reservation không được xử lý, item chưa hoàn tất dù vòng lặp đã đi tới phần tử tiếp theo.

Ngược lại, hai item có thể cùng thuộc một aggregate hoặc cùng đáp ứng một điều kiện toàn nhóm. Ví dụ, chuyển hai phần tài sản tạo thành một giao dịch cân bằng không thể được coi là hai lệnh độc lập chỉ vì client gửi hai dòng.

### 2.2. Phân biệt ba mô hình xử lý

| Mô hình | Ranh giới thành công | Ý nghĩa khi một phần tử thất bại |
| --- | --- | --- |
| Toàn batch nguyên tử | Tất cả item cùng chấp nhận hoặc cùng rollback | Không item nào được giữ lại thay đổi nghiệp vụ |
| Mỗi item độc lập | Một transaction cho một đơn vị nghiệp vụ hoàn chỉnh | Item khác có thể thành công theo hợp đồng |
| Theo nhóm phụ thuộc | Một transaction cho một nhóm đã xác định | Cả nhóm rollback, các nhóm độc lập khác có thể tiếp tục |

Bài này tập trung mô hình mỗi item độc lập và nhóm độc lập. Không áp dụng transaction riêng cho từng item vào một API đã cam kết nguyên tử toàn batch rồi coi đó là tối ưu nội bộ.

### 2.3. Cô lập không làm biến mất tài nguyên dùng chung

Hai item độc lập về kết quả vẫn có thể cùng tiêu thụ một hạn mức hoặc thay đổi một dòng tồn kho. Ràng buộc tổng cần được bảo vệ bằng lock, cập nhật có điều kiện, constraint hoặc cơ chế đồng thời phù hợp ở tài nguyên dùng chung.

Nếu cả A và D được hủy và giải phóng hai reservation khác nhau, mỗi reservation cần đúng một lần giải phóng. Nếu cùng trỏ tới một reservation do dữ liệu đầu vào bất thường, cơ chế domain không được cộng số lượng hai lần. Ranh giới aggregate phải phản ánh quan hệ thực, không chỉ quan hệ do client tuyên bố.

## 3. Những lớp thông tin cần được cô lập

| Lớp | Lỗi điển hình | Cơ chế thiết kế |
| --- | --- | --- |
| Danh tính và tenant | Item sau dùng tenant hoặc đặc quyền item trước | Context tin cậy, rõ phạm vi, được truyền có chủ đích |
| Payload | Dùng lại DTO/builder làm ID hoặc số tiền bị ghi đè | Input bất biến, kiểm tra cấu trúc từng item |
| Quyền đối tượng | Kiểm tra item đầu rồi áp cho tất cả | Quyết định actor–action–resource cho từng đơn vị |
| Transaction | Lỗi B rollback cả A hoặc B commit dở | Ranh giới transaction đúng hợp đồng |
| Bộ nhớ ORM | Entity lỗi còn trong context rồi bị flush ở item sau | Persistence context phù hợp transaction, không chia sẻ entity giữa worker |
| Kết quả | Gắn kết quả B vào ID của A | Tham chiếu item ổn định và đối chiếu ánh xạ |
| Retry | Thử lại batch làm lặp item đã thành công | Receipt và idempotency ở đơn vị lệnh |
| Tác động ngoài | Item bị từ chối vẫn đã gửi email/thu tiền | Outbox, consumer khử trùng và cơ chế đối soát |
| Tài nguyên chạy | Một item lớn chiếm toàn bộ worker | Giới hạn công việc, thời hạn và mức đồng thời |

Kiểm tra quyền theo đối tượng vẫn là bắt buộc. [OWASP API1:2023 — Broken Object Level Authorization](https://api-security.owasp.org/editions/2023/en/0xa1-broken-object-level-authorization/) mô tả nguy cơ khi ứng dụng nhận ID mà không xác minh quyền thực hiện action trên đối tượng. Với batch, lỗi có thể bị che vì phần lớn item trong cùng request là hợp lệ.

## 4. Hợp đồng input, tham chiếu và kết quả từng item

### 4.1. Dùng tham chiếu ổn định

Ví dụ request:

```json
{
  "items": [
    {
      "clientRef": "line-A",
      "operationId": "cancel-op-701",
      "orderId": "O-101",
      "expectedVersion": 7
    },
    {
      "clientRef": "line-B",
      "operationId": "cancel-op-702",
      "orderId": "O-102",
      "expectedVersion": 3
    }
  ]
}
```

`clientRef` dùng ánh xạ kết quả, không phải bằng chứng quyền. `operationId` nhận diện ý định lệnh để hỗ trợ gửi lại trong phạm vi được server quy định. `orderId` và `expectedVersion` vẫn là input không tin cậy cần kiểm tra.

Trong hợp đồng minh họa:

- `clientRef` phải duy nhất trong một request và có giới hạn độ dài.
- Hai lệnh cùng đối tượng trong cùng batch bị từ chối ở bước xác thực envelope để tránh thứ tự ngầm.
- Cùng `operationId` nhưng payload khác bị coi là xung đột, không chọn tùy tiện một payload.
- Actor và tenant lấy từ ngữ cảnh xác thực, không được item tự ghi đè.
- Thứ tự hoàn thành có thể khác thứ tự gửi; kết quả luôn có tham chiếu rõ ràng.

Nếu nghiệp vụ cho phép nhiều lệnh tuần tự trên cùng đối tượng, cần mô tả thứ tự và điều kiện phụ thuộc thành một workflow riêng. Không dựa vào việc stream hiện tại tình cờ chạy tuần tự.

### 4.2. Tách lỗi envelope khỏi lỗi nghiệp vụ item

Một body không parse được, danh sách vượt giới hạn hoặc không có quyền dùng chức năng batch có thể làm cả request bị từ chối trước khi xử lý. Không nên bắt đầu ghi item A trong khi vẫn chưa biết phần còn lại của cấu trúc request có hợp lệ hay không, trừ khi API streaming đã định nghĩa rõ cơ chế đó.

Khi envelope hợp lệ, các lỗi như item không được phép, phiên bản cũ hoặc trạng thái không hủy được mới được ánh xạ theo hợp đồng từng item.

### 4.3. Đừng gắn thành công của item với HTTP chung

Response của batch có thể mô tả nhiều kết quả:

```json
{
  "results": [
    { "clientRef": "line-A", "outcome": "SUCCEEDED", "receiptId": "R-701" },
    { "clientRef": "line-B", "outcome": "REJECTED", "code": "NOT_PROCESSABLE" }
  ]
}
```

Đây là định dạng ví dụ, không phải schema chuẩn áp dụng cho mọi API. Mã lỗi phải phản ánh mức thông tin người gọi được biết. Với một ID ngoài tenant, không trả kèm owner, trạng thái hoặc giá trị đơn chỉ để giải thích vì sao không xử lý.

Nếu job chạy bất đồng bộ, việc job đã được tiếp nhận chưa có nghĩa item đã thành công. Client cần theo dõi kết quả sau commit và có cách đối soát khi mất kết nối.

## 5. Tách transaction để lỗi không lan sai phạm vi

### 5.1. Vòng lặp trong một transaction chung

```java
@Transactional
public List<ItemResult> processBatch(List<CancelItem> items) {
    for (CancelItem item : items) {
        try {
            cancel(item);
        } catch (RuntimeException ex) {
            // Continue to the next item.
        }
    }
    return results;
}
```

Đoạn mã này không chứng minh mỗi item có transaction riêng. Một thao tác bên trong có thể đánh dấu transaction chung rollback-only; những kết quả “thành công” thu thập trước đó sẽ không được commit. Hoặc nếu exception bị nuốt trước khi cơ chế rollback nhận biết, các thay đổi dở có thể vẫn được giữ lại.

Không giải quyết bằng cách bắt mọi exception rồi tiếp tục. Cần kiểm soát ranh giới transaction và chỉ chuyển thành kết quả item sau khi đã biết transaction tương ứng kết thúc ra sao.

### 5.2. Ý nghĩa propagation trong Spring

`REQUIRED` có thể tham gia transaction đang có. `REQUIRES_NEW` dùng transaction vật lý độc lập. `NESTED` thường dựa trên savepoint trong một transaction chung, nên phần đã qua savepoint vẫn có thể mất khi transaction ngoài rollback. Khả năng hỗ trợ phụ thuộc transaction manager. Xem [Spring Framework — Transaction Propagation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html).

Với batch best-effort đồng bộ, một cấu trúc dễ kiểm soát là coordinator không giữ transaction nghiệp vụ toàn batch, còn mỗi item mở transaction riêng qua service proxy hoặc `TransactionTemplate`.

Nếu dùng annotation ở một phương thức item, không gọi `this.processItem(...)` rồi giả định đã đi qua proxy. Hành vi self-invocation trong proxy mode được mô tả tại [Spring Framework — Using @Transactional](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html).

### 5.3. Không trả thành công trước commit

Trong callback của transaction, một lệnh `save()` chưa chắc đã flush hoặc commit. Receipt gửi ra ngoài phải dựa trên kết quả transaction đã hoàn tất. Lỗi constraint, deadlock hoặc kết nối tại commit có thể xuất hiện sau khi callback đã tạo đối tượng kết quả trong bộ nhớ.

Nếu việc commit có kết quả không xác định từ phía ứng dụng, không đánh dấu item chắc chắn thất bại rồi tạo một lệnh mới. Cần tra receipt, trạng thái domain hoặc cơ chế reconciliation để xác định kết quả trước khi tiếp tục.

## 6. Minh họa Java với TransactionTemplate

Ví dụ sau xử lý từng lệnh hủy độc lập trên một database. Không gọi dịch vụ bên ngoài trong transaction; thay vào đó ghi outbox. Các kiểu repository và domain là thành phần ứng dụng cần tự hiện thực.

Cấu hình template chuyên cho item:

```java
@Bean
TransactionTemplate batchItemTransaction(PlatformTransactionManager manager) {
    TransactionTemplate template = new TransactionTemplate(manager);
    template.setPropagationBehavior(
        TransactionDefinition.PROPAGATION_REQUIRES_NEW);
    return template;
}
```

Luồng xử lý minh họa:

```java
public ItemResult processItem(TrustedBatchContext context, CancelItem input) {
    try {
        return Objects.requireNonNull(itemTransaction.execute(tx -> {
            Actor actor = identities.requireActiveActor(
                context.actorId(), context.tenantId());

            Order order = orders.lockInTenant(
                    context.tenantId(), input.orderId())
                .orElseThrow(ItemNotProcessableException::new);
            authorization.requireCancelPermission(actor, order);

            CommandKey key = new CommandKey(
                context.tenantId(), actor.id(), "CANCEL_ORDER", input.operationId());
            String fingerprint = fingerprints.forCancel(input);
            Optional<CommandReceipt> previous = receipts.find(key);
            if (previous.isPresent()) {
                previous.get().requireFingerprint(fingerprint);
                return ItemResult.succeeded(
                    input.clientRef(), previous.get().id());
            }

            order.requireVersion(input.expectedVersion());
            order.requireCancellable();
            order.cancelBy(actor.id());
            reservations.releaseOnce(order.reservationId());

            CommandReceipt receipt = receipts.insertUnique(
                key, fingerprint, order.id());
            outbox.appendUnique(OrderCancelled.from(order, receipt.id()));
            orders.flush();
            return ItemResult.succeeded(input.clientRef(), receipt.id());
        }));
    } catch (ItemNotProcessableException ex) {
        return ItemResult.rejected(input.clientRef(), "NOT_PROCESSABLE");
    } catch (StaleVersionException ex) {
        return ItemResult.rejected(input.clientRef(), "VERSION_CONFLICT");
    }
}
```

Trong ví dụ, `ItemNotProcessableException` và `StaleVersionException` là runtime exception và thoát khỏi callback để transaction rollback trước khi được chuyển thành kết quả. Các lỗi persistence, mất kết nối hoặc kết quả commit không rõ không bị gộp vào hai nhánh từ chối nghiệp vụ này.

`TransactionTemplate` cung cấp callback cho luồng imperative và xử lý ranh giới transaction quanh callback, theo [Spring Framework — Programmatic Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/programmatic.html).

Những điều kiện quan trọng của ví dụ:

1. `TrustedBatchContext` được tạo từ request đã xác thực hoặc bản ghi job tin cậy. Client không được tự tạo context với actor/tenant tùy ý.
2. `requireCancelPermission` kiểm tra quyền trên đối tượng và cơ chế thu hồi phù hợp. Điều kiện domain “đơn đang hủy được” được kiểm tra riêng sau khi tìm receipt, để replay thành công không bị hiểu thành một lần hủy mới.
3. Quyền truy xuất receipt vẫn phải phù hợp chính sách hiện hành. Không trả receipt của actor/tenant khác chỉ vì trùng chuỗi operation ID.
4. `releaseOnce` bảo vệ trạng thái reservation và số lượng ở database; đây không phải lời gọi kho ngoài không thể rollback.
5. Receipt, đơn, reservation và outbox dùng cùng transaction phù hợp. Constraint duy nhất bảo vệ khóa lệnh và định danh sự kiện.
6. Fingerprint do server tính từ ý định được chuẩn hóa, gồm đối tượng và phiên bản liên quan; không tin một giá trị hash client tự khai. `clientRef` chỉ để ánh xạ kết quả, không làm thay đổi ý nghĩa lệnh.
7. Entity và `EntityManager` không được chia sẻ giữa các task xử lý item. Giá trị trả về là DTO bất biến, không giữ entity để serialize sau transaction.

Nếu hai request cạnh tranh cùng key nhưng khác đối tượng, constraint có thể phát hiện xung đột tại insert/commit. Luồng xử lý xung đột cần đọc lại receipt trong transaction mới, đối chiếu fingerprint và quyền trước khi quyết định trả kết quả cũ hay lỗi; không thử lại mù quáng với key mới.

Coordinator chỉ tiếp tục khi đã có kết quả được phân loại đáng tin cậy. Với lỗi hạ tầng ảnh hưởng toàn hệ thống, có thể dừng nhận item mới và chuyển các item chưa có kết quả sang trạng thái chờ xử lý hoặc đối soát, thay vì ghi hàng loạt kết quả từ chối sai.

## 7. Cô lập context, payload và bộ nhớ giữa các item

### 7.1. Truyền context có chủ đích

Một batch thông thường hoạt động trong một tenant đã xác thực. Nếu batch quản trị được phép chứa nhiều tenant, mỗi item phải có phạm vi thực thi được server kiểm chứng riêng. Không lấy tenant của item đầu rồi sử dụng cho những item còn lại.

Context nên bất biến và tối thiểu: actor tham chiếu, tenant, action đã giới hạn, batch ID, item ID hoặc delegation được xác minh. Nó không nên chứa một field `isAdmin` do client gửi hoặc một entity mutable được item khác sửa.

Nếu worker dùng tài khoản dịch vụ, phân biệt danh tính kỹ thuật của worker với chủ thể được ủy quyền thực hiện nghiệp vụ. Quyền truy cập database rộng của worker không cho phép nó bỏ qua quyền đối tượng của người yêu cầu.

### 7.2. Cẩn thận với ThreadLocal và thread pool

`ThreadLocal` gắn giá trị với thread; `remove()` xóa giá trị của thread hiện hành. Tài liệu Java mô tả hành vi này tại [Java SE — ThreadLocal](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ThreadLocal.html).

Suy ra trong thiết kế worker dùng lại thread, context đặt cho item A có thể còn tồn tại khi thread nhận item B nếu không được quản lý đúng vòng đời. Truyền context tường minh thường dễ kiểm chứng hơn. Nếu buộc phải bind context vào thread, dùng cơ chế đặt/khôi phục hoặc xóa trong `finally`, kể cả đường exception và hủy task.

Việc chạy task trên thread khác cũng không có nghĩa thread đó tự nhận đầy đủ session, tenant hoặc transaction của request gốc. Dùng cơ chế truyền context được framework hỗ trợ và kiểm thử kết quả thực tế. Không dùng `parallelStream()` như một cách tự động làm batch an toàn.

### 7.3. Không tái sử dụng dữ liệu mutable một cách mơ hồ

Ví dụ lỗi:

```java
MutableCommand command = new MutableCommand();
for (CancelItem item : items) {
    command.setOrderId(item.orderId());
    executor.submit(() -> cancel(command));
}
```

Các task cùng tham chiếu một object; nhiều task có thể nhìn thấy ID của item cuối. Đổi sang một command bất biến riêng cho mỗi task và chỉ truyền những giá trị cần thiết.

Tương tự, cache quyết định quyền không được chỉ dùng key `APPROVE=true` hoặc `tenantId`. Nếu cache, key và chính sách hết hiệu lực phải phản ánh actor, action, đối tượng, phiên bản policy và các thuộc tính thực sự chi phối quyền. Với yêu cầu thu hồi tức thời, cần cơ chế nhất quán đáp ứng yêu cầu đó.

## 8. Lỗi, retry và kết quả không xác định

### 8.1. Phân loại theo điều có thể chứng minh

| Loại | Ví dụ | Hướng xử lý |
| --- | --- | --- |
| Từ chối nghiệp vụ xác định | Sai quyền, trạng thái không phù hợp, phiên bản cũ | Rollback item; trả lỗi an toàn theo hợp đồng |
| Lỗi tạm thời và biết chưa commit | Deadlock đã rollback rõ ràng | Retry có giới hạn, dùng cùng định danh lệnh |
| Kết quả commit chưa xác định | Mất kết nối tại thời điểm xác nhận commit | Đối soát receipt/domain trước khi thực thi lại |
| Lỗi cấu hình hoặc lỗi hệ thống rộng | Không kết nối được database, schema không tương thích | Dừng hoặc giảm xử lý; không coi mọi item là sai nghiệp vụ |

Không phân loại mọi timeout thành “chưa xảy ra gì”. Request có thể đã commit rồi mất response. Chính receipt và trạng thái domain mới giúp chứng minh kết quả.

### 8.2. Idempotency nằm ở đơn vị lệnh ổn định

Chỉ dùng `(batchId, index)` làm khóa chống trùng có thể thất bại khi client tạo batch mới hoặc thay thứ tự item. `operationId` nên nhận diện cùng ý định lệnh trong phạm vi tenant, actor/action đã định nghĩa, kể cả khi item được gửi lại qua một batch khác.

Tuy nhiên, định danh lệnh không thay thế invariant domain. Một người gọi có thể tạo operation ID mới liên tục; state machine và ràng buộc giải phóng reservation vẫn phải ngăn hủy/hoàn tác lặp trái phép.

Quy tắc với key cần rõ:

- Cùng key, cùng nội dung, cùng phạm vi được phép: trả kết quả đã ghi nhận hoặc tiếp tục đối soát.
- Cùng key nhưng nội dung khác: từ chối xung đột, không sửa lệnh đã hoàn tất.
- Khác tenant hoặc actor: không truy cập nhầm receipt của nhau.
- Quyền đã đổi: việc thực thi mới và việc xem receipt áp dụng đúng chính sách hiện hành đã công bố.

### 8.3. Không reset cả batch khi một item cần retry

Giả sử A đã commit, B bị deadlock, C chưa chạy. Retry cả batch bằng key mới có thể làm A giải phóng kho lần hai. Cần giữ kết quả A, thử lại B bằng định danh cũ và tiếp tục C theo trạng thái riêng.

Nếu client không biết A đã thành công do response bị mất, server tra receipt để trả kết quả đã có. Đừng yêu cầu client đoán từ mã HTTP chung hoặc tự suy ra từ thứ tự trong mảng response.

## 9. Job bền vững: kết quả phải sống qua việc worker chết

Đối với xử lý bất đồng bộ, có thể lưu trạng thái từng item như:

```text
PENDING → RUNNING → SUCCEEDED
                  → REJECTED
                  → WAITING_RETRY
                  → NEEDS_RECONCILIATION
```

Đây là state machine minh họa. Các transition quay lại xử lý cần được định nghĩa rõ; không cho sửa một item SUCCEEDED thành PENDING chỉ vì toàn job được gửi lại.

### 9.1. Ghi nhận kết quả cùng bằng chứng nghiệp vụ

Nếu worker commit hủy đơn rồi chết trước khi ghi trạng thái item, lần chạy sau phải tìm được receipt thay vì hủy lại. Có hai cách thiết kế phổ biến trong phạm vi bài:

- Khi cùng database, cập nhật trạng thái thành công của item, receipt, domain và outbox trong một transaction phù hợp.
- Nếu trạng thái job ở kho khác, receipt nghiệp vụ là bằng chứng bền vững; trạng thái job được đối soát hoặc tái dựng từ bằng chứng đó.

Không tuyên bố nguyên tử giữa hai hệ lưu trữ chỉ vì hai lời gọi được đặt cạnh nhau trong Java.

### 9.2. Claim và lease không đủ nếu thiếu chống worker cũ

Hai worker có thể cùng thấy item đang chờ, hoặc một worker cũ tiếp tục chạy sau khi lease đã hết và worker mới đã nhận lại item. Cần claim nguyên tử và cơ chế chống thực thi trùng tại điểm commit, chẳng hạn khóa bản ghi lệnh, ràng buộc duy nhất, kiểm tra fencing token phù hợp hoặc kết hợp các cơ chế này.

Nếu dùng fencing token, tài nguyên thực sự bị ghi phải kiểm chứng token; chỉ ghi token vào log không ngăn worker cũ sửa dữ liệu. Trạng thái thành công đã ghi không được bị một attempt thất bại đến muộn ghi đè.

### 9.3. Tác động ngoài cần định danh và đối soát riêng

Email, kho ngoài hoặc cổng thanh toán không cùng transaction database. Ghi ý định qua outbox, gửi kèm định danh lệnh ổn định khi dịch vụ đích hỗ trợ và xử lý delivery trùng ở consumer.

Khi bên ngoài có thể đã thực hiện nhưng response không rõ, chuyển sang đối soát thay vì phát một lệnh mới không liên quan. Nếu nghiệp vụ cần bù, thao tác bù là một lệnh có quyền, điều kiện và idempotency riêng; không phải rollback database từ xa.

## 10. Cô lập tài nguyên và bảo vệ tính công bằng

Một item có thể hợp lệ nhưng rất tốn tài nguyên: danh sách dòng hàng lớn, nhiều đối tượng liên quan hoặc dịch vụ phụ thuộc chậm. Nếu không giới hạn, nó có thể chặn các item khác hoặc chiếm toàn bộ worker của tenant khác.

Thiết kế các giới hạn phù hợp:

- Số item mỗi batch và kích thước từng item.
- Số task đồng thời toàn hệ thống và theo tenant/actor.
- Thời gian thực thi, thời gian giữ lock và ngân sách retry.
- Số đối tượng liên quan, kích thước kết quả và dữ liệu audit.
- Backoff có giới hạn và cơ chế dừng nhận việc mới khi phụ thuộc đang lỗi.

Đừng tạo một thread hoặc một connection mới không giới hạn cho mỗi item. Với transaction riêng, số connection và thời gian giữ tài nguyên vẫn cần được tính toán. Đặc biệt tránh một coordinator giữ transaction ngoài rồi chờ nhiều transaction con lấy thêm connection.

Timeout hoặc hủy task không chứng minh database đã rollback hay dịch vụ ngoài chưa chạy. Đường hủy cũng cần đi qua cơ chế xác định kết quả và đối soát như các lỗi vận chuyển khác.

## 11. Kiểm thử sự cô lập bằng dữ liệu đã commit

### 11.1. Oracle cho từng item và tài nguyên chung

Chuẩn bị fixture riêng có actor, tenant, đơn, reservation và phiên bản xác định. Bản chụp trước/sau nên bao gồm:

```text
Theo đơn: trạng thái, phiên bản, người thực hiện, biên bản hủy
Theo reservation: lượng giữ, trạng thái release, số lần áp dụng
Theo lệnh: receipt, fingerprint, operation ID trong đúng phạm vi
Theo tác động: outbox và kết quả consumer
Theo job: trạng thái hiện hành và lịch sử attempt
Theo tài nguyên chung: tồn kho/hạn mức sau tổng các item thực sự thành công
```

Đọc lại qua transaction mới sau khi xử lý, không dùng cùng entity đang được ORM quản lý. Không kết luận từ transaction test tự rollback. Những log truy cập hoặc audit từ chối được phép phát sinh cần được phân biệt với thay đổi nghiệp vụ bị cấm.

### 11.2. Ma trận tình huống

| Tình huống | Cách kích hoạt | Bằng chứng mong đợi |
| --- | --- | --- |
| B sai quyền giữa A và D hợp lệ | Đổi thứ tự B ở đầu/giữa/cuối | A, D đúng hợp đồng; B không đổi và không phát lệnh |
| Lỗi khi ghi B | Fault injection sau khi sửa entity nhưng trước commit | Toàn bộ tác động B rollback; kết quả A không bị mất |
| Transaction rollback-only | Gây lỗi persistence trong một item | Không báo success cho dữ liệu chưa commit; item sau xử lý đúng phạm vi |
| Context còn sót | Cùng thread xử lý tuần tự hai tenant | Item sau không nhận quyền hoặc dữ liệu item trước |
| DTO dùng chung | Cho task chạy trễ sau khi vòng lặp đổi ID | Mỗi tác động vẫn gắn đúng order và clientRef |
| Response đảo thứ tự | Cho item sau hoàn thành trước | ClientRef/receipt không bị gán chéo |
| Gửi lại một item | Retry cùng operation ID qua batch mới | Một receipt và một tác động nghiệp vụ |
| Cùng key khác payload | Đổi order hoặc phiên bản | Xung đột theo hợp đồng, không thực thi ý định mới |
| Worker chết sau commit | Dừng sau ghi domain/receipt, trước cập nhật projection job | Chạy lại tìm được kết quả, không hủy lần hai |
| Lease hết hạn | Worker cũ và mới cùng tới điểm ghi | Chỉ tác động hợp lệ được commit, kết quả cuối không bị ghi đè sai |
| Dịch vụ ngoài trả lời không rõ | Fake đã thực hiện nhưng làm mất response | Đối soát theo định danh, không tạo lệnh mới mù quáng |
| Tài nguyên dùng chung | Nhiều item cạnh tranh tồn kho/hạn mức | Invariant tổng vẫn đúng sau tất cả commit |

Mỗi test quyền cần positive control: cùng cách đăng nhập, body hợp lệ và cấu hình thật nhưng dùng một đối tượng được phép thì lệnh thành công. Nếu request bị chặn bởi JSON hỏng hoặc thiếu CSRF trước khi tới service, nó chưa chứng minh được cô lập quyền theo item.

Để kiểm tra race, dùng barrier/latch ở điểm cạnh tranh đã kiểm soát. Để kiểm tra tác động muộn, xử lý hết outbox liên quan bằng consumer kiểm soát được rồi đọc lại dữ liệu. Đừng chỉ chờ một khoảng thời gian tùy ý rồi khẳng định không còn việc nào có thể chạy.

### 11.3. Tổng hợp job phải khớp trạng thái item

Mỗi item có đúng một trạng thái hiện hành. Tổng số item của job phải khớp tổng các nhóm trạng thái không giao nhau; lịch sử nhiều attempt không được làm tăng số item.

Một job có A thành công và B bị từ chối không được hiển thị như mọi item đều đã thành công. Nếu còn item cần đối soát, job phải thể hiện điều đó theo mô hình trạng thái đã chọn. Quyền đọc, tải lỗi, retry và hủy job vẫn phải kiểm tra theo actor và tenant của job cụ thể.

## 12. Bài tập thực hành

Một hệ thống hủy đơn hàng loạt có các đặc điểm sau:

```text
- Coordinator có @Transactional.
- processItem có @Transactional(REQUIRES_NEW) nhưng được gọi bằng this.processItem.
- Mọi task dùng chung một MutableCommand.
- Khi timeout, client gửi lại toàn bộ batch với operation ID mới.
- Worker lưu trạng thái SUCCEEDED trước khi transaction nghiệp vụ commit.
```

Hãy thiết kế lại luồng với các yêu cầu:

1. A hợp lệ được hủy, B sai quyền không thay đổi, C hợp lệ vẫn được xử lý theo hợp đồng best-effort.
2. Lỗi persistence của B không để lại reservation đã release dở và không làm mất commit của A.
3. Task của tenant B không sử dụng ngữ cảnh tenant A trên cùng thread pool.
4. Chết worker sau commit không làm lặp tác động khi item được nhận lại.
5. Mất response của dịch vụ ngoài tạo ra trạng thái cần đối soát phù hợp, không bị gắn nhãn thất bại chắc chắn.
6. Kết quả của từng item luôn ánh xạ đúng tham chiếu đầu vào, kể cả khi hoàn thành khác thứ tự.

Với từng yêu cầu, chỉ rõ đơn vị transaction, nguồn context tin cậy, định danh chống trùng, dữ liệu quan sát sau commit và cách kích hoạt lỗi trong test. Cô lập item được chứng minh bằng quyền và tác động đúng phạm vi của từng đơn vị nghiệp vụ, đồng thời giữ nguyên các invariant của những tài nguyên mà chúng cùng sử dụng.
