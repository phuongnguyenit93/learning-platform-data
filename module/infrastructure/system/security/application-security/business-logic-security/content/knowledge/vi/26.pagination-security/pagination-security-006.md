# Hành vi phân trang khi item bị xóa (Deleted item behavior)

Một danh sách có thể thay đổi giữa hai lần tải trang. Item đã đọc bị xóa, item tiếp theo biến mất hoặc quyền truy cập bị thu hồi. Nếu API coi tập dữ liệu luôn cố định, nó có thể bỏ sót bản ghi, trả trùng, làm hỏng cursor hoặc dùng một nhánh dự phòng bỏ điều kiện phân quyền.

Đây không chỉ là vấn đề trải nghiệm. Các tham số xem dữ liệu đã xóa, tombstone, tổng số, cache và snapshot lịch sử đều có thể làm lộ thông tin hoặc giữ quyền đọc lâu hơn chính sách cho phép.

Bài học thuộc chương **Pagination Security** trong bảo mật logic nghiệp vụ. Trọng tâm là định nghĩa việc xóa có ý nghĩa gì đối với từng trang, thiết kế cursor tiếp tục được khi phù hợp và giữ nguyên ranh giới tenant, scope cùng hiệu lực truy cập.

Ví dụ xuyên suốt là danh sách đề nghị mua hàng mà người dùng được phép xem.

## 1. Phân biệt xóa, ẩn và không còn quyền

Một item không xuất hiện trong trang có thể do nhiều nguyên nhân:

| Trường hợp | Ý nghĩa |
|---|---|
| Hard delete | Bản ghi nguồn không còn theo cơ chế lưu trữ tương ứng |
| Soft delete | Bản ghi còn nhưng có dấu hiệu bị loại khỏi view hoạt động |
| Lưu trữ hoặc archive | Có thể vẫn xem qua một view hoặc quyền riêng |
| Chuyển owner hoặc thu hồi chia sẻ | Caller không còn thuộc scope được đọc |
| Đổi trạng thái hoặc bộ lọc | Item không còn khớp tập truy vấn |
| Projection hoặc cache chưa cập nhật | Các nguồn đọc chưa phản ánh cùng mốc |

Không nên trả chi tiết những nguyên nhân này cho người không có quyền biết item tồn tại.

Trong view hoạt động của ví dụ, dữ liệu trả về phải thỏa:

```text
đúng tenant
AND được phép đọc theo scope
AND chưa bị xóa khỏi view này
AND khớp bộ lọc
AND nằm sau ranh giới cursor nếu có
```

Thiếu một điều kiện không được bù bằng việc item từng xuất hiện ở trang trước.

### 1.1. Quyền đọc tại mốc nào?

Cần xác định một trang phản ánh dữ liệu tại mốc đọc nào và quyền được kiểm tra theo chính sách nào.

Một query đã đọc item trước khi thao tác xóa có hiệu lực có thể giữ một ảnh dữ liệu khác với query chạy sau đó. Nếu yêu cầu phải chặn tại một mốc mạnh hơn, cần cơ chế phối hợp tương ứng.

Không hứa rằng mọi byte đang gửi sẽ tự biến mất ngay khi một transaction xóa commit. Hệ thống phải nêu bảo đảm thực tế về nguồn đọc, cache, replica và điểm cấp dữ liệu.

### 1.2. View hoạt động khác view lịch sử

Một bản ghi bị soft delete có thể cần giữ cho audit. Điều đó không có nghĩa endpoint danh sách thông thường được phép trả nó.

View lịch sử cần action và phạm vi riêng. Tham số includeDeleted chỉ thể hiện một đề nghị, không tự tạo quyền đọc dữ liệu đã xóa.

Nếu không hỗ trợ chế độ đó cho caller, không được bỏ điều kiện deleted rồi tiếp tục.

## 2. Vì sao offset có thể đổi ý nghĩa sau khi xóa?

Giả sử thứ tự đang là:

```text
A, B, C, D, E, F
pageSize = 2

Trang đầu:
    A, B
```

Sau đó A bị xóa. Danh sách hiện tại:

```text
B, C, D, E, F
```

Nếu trang sau lấy offset 2, kết quả có thể là D, E. C bị bỏ qua vì vị trí đã dịch.

### 2.1. Đây không tự là bằng chứng vượt quyền

Skip hoặc duplicate có thể là hệ quả nhất quán dữ liệu của cách phân trang live. Nó không tự chứng minh một hàng ngoài tenant đã bị đọc.

Tuy nhiên, nếu API dùng danh sách để kiểm kê, lập batch hoặc giải thích “đã xem hết”, sự bỏ sót có thể làm sai quy trình nghiệp vụ.

Cần công bố hợp đồng live hoặc snapshot, không diễn giải tổng số ở trang đầu như một cam kết rằng các offset sau sẽ duyệt đúng tập ban đầu.

### 2.2. Chèn và khôi phục cũng có thể làm dịch vị trí

Nếu một item mới được thêm trước vị trí đã đọc, offset tiếp theo có thể trả lại một item cũ.

Một item được khôi phục với khóa sắp xếp cũ cũng có thể nằm phía trước phần đã duyệt. API live cần nêu cách người dùng thấy dữ liệu đó, chẳng hạn bắt đầu một lượt đọc mới.

Không suy ra rằng chuyển sang cursor sẽ tự tạo một ảnh chụp cố định của mọi item từ đầu đến cuối.

### 2.3. Không dùng bỏ lọc làm cách lấp chỗ trống

Khi một trang ít phần tử vì xóa hoặc thay đổi quyền, không được mở rộng scope, bỏ tenant, thêm dữ liệu đã xóa hoặc lấy item của owner khác để đủ pageSize.

PageSize là giới hạn của trang theo hợp đồng, không phải quyền nhận đúng từng ấy item từ bất kỳ nguồn nào.

Nếu còn ít item hợp lệ, trang ngắn hoặc rỗng có thể là kết quả đúng.

## 3. Cursor theo ranh giới sắp xếp

Một cách tiếp tục là giữ khóa sắp xếp cuối đã trả thay vì vị trí số thứ tự.

Giả sử view sắp:

```text
createdAt giảm dần, rồi id giảm dần
```

Trong ví dụ, createdAt không null và không đổi, id duy nhất trong phạm vi tenant. Hai trường tạo ranh giới xác định khi nhiều item có cùng thời điểm.

### 3.1. Anchor bị xóa không nhất thiết làm mất ranh giới

Trang đầu trả A, B. Cursor giữ khóa của B.

Ngay cả khi B bị xóa, server vẫn có thể truy vấn các item nằm sau khóa đó nếu cursor đã được phát hành và xác minh theo hợp đồng.

Không nhất thiết tải lại bản ghi B để tiếp tục. Khóa của B là ranh giới đã được cấp, không phải bằng chứng B còn tồn tại hoặc caller vẫn được đọc B.

### 3.2. Truy vấn minh họa

Với view cá nhân chỉ gồm các đề nghị người gọi sở hữu:

```sql
SELECT id,
       created_at,
       state,
       purpose
FROM purchase_request
WHERE tenant_id = :authorized_tenant_id
  AND owner_subject_id = :authorized_subject_id
  AND deleted_at IS NULL
  AND (
        created_at < :last_created_at
        OR (
             created_at = :last_created_at
             AND id < :last_id
           )
      )
ORDER BY created_at DESC, id DESC;
```

Đây là phần điều kiện của trang tiếp theo. Repository áp dụng giới hạn số hàng có kiểm soát theo cơ sở dữ liệu thực tế.

Các placeholder là tham số bind. Trang đầu dùng cùng scope và thứ tự nhưng không có ranh giới tiếp tục.

Nếu view cho phép quan hệ khác, thay predicate owner bằng policy phù hợp; không bỏ scope chỉ vì không tìm thấy anchor.

### 3.3. Tiebreaker, độ chính xác và kiểu so sánh

Chỉ dùng createdAt có thể bỏ hoặc lặp các item cùng timestamp. Cần khóa phụ làm thứ tự đủ xác định.

Cursor phải giữ đúng độ chính xác và kiểu mà query sử dụng. Không làm tròn timestamp hoặc đổi ID sang một kiểu so sánh khác rồi dùng ranh giới không còn tương đương.

Nếu hỗ trợ null hoặc trường sort có thể sửa, cần quy tắc riêng. Không mặc định mẫu truy vấn trên vẫn đúng cho mọi kiểu sort.

### 3.4. Cursor chỉ giữ anchorId cần kế hoạch khác

Nếu cursor chỉ chứa ID và phải tải anchor để biết khóa sort, hard delete có thể làm thiếu dữ kiện.

Có thể dùng state cursor phía server, dữ kiện tối thiểu còn được phép giữ hoặc chọn token có ranh giới đầy đủ theo thiết kế.

Nếu không thể tiếp tục hợp lệ, trả lỗi cursor không dùng được hoặc yêu cầu bắt đầu lại theo contract. Không reset ngầm về trang đầu, dùng offset 0 hay truy vấn anchor toàn cục ngoài tenant.

Tombstone không luôn bắt buộc cho mọi kiểu cursor. Nó cũng không tự tạo quyền đọc dữ liệu đã xóa.

## 4. Cursor là dữ liệu điều hướng có ràng buộc

Một cursor cần được gắn với ngữ cảnh đủ để không bị tái dùng sai:

```text
phiên bản cursor
dataset hoặc view
tenant đã xác minh
subject hoặc phạm vi chia sẻ theo hợp đồng
bộ lọc chuẩn hóa
thứ tự sort
chế độ dữ liệu hoạt động hoặc lịch sử
ranh giới khóa hoặc tham chiếu state phía server
thời hạn và phiên bản quyền cần thiết nếu áp dụng
```

Không cho caller thay tenant hoặc includeDeleted mà vẫn dùng cursor cũ như một grant rộng hơn.

### 4.1. Bảo vệ tính toàn vẹn không thay thế quyền hiện tại

Một token có thể được bảo vệ để phát hiện chỉnh sửa. Tuy nhiên, cursor được phát trước khi quyền bị thu hồi không tự giữ quyền đó mãi.

Cần kiểm tra quyền và scope hiện tại hoặc một mô hình quyền snapshot đã được cấp rõ ràng. Khóa sort không phải danh sách quyền.

Một biểu diễn chỉ encode không tự che giấu nội dung. Nếu cursor có dữ kiện nhạy cảm, thiết kế phải bảo vệ hoặc tối thiểu hóa chúng phù hợp.

### 4.2. Không gắn mọi lượt đọc live với sự tồn tại của anchor

Một cursor live có thể hợp lệ dù anchor đã xóa hoặc caller không còn được đọc riêng anchor đó. Điều kiện tiếp tục vẫn dựa trên scope mới được phép và ranh giới đã xác minh.

Nếu policy yêu cầu vô hiệu toàn lượt đọc khi phạm vi đổi, hãy làm theo contract đó. Không nhầm việc kiểm tra epoch quyền với yêu cầu mỗi anchor phải còn visibility như trước.

Một epoch của policy hoặc scope khác với epoch của từng item. Tăng hoặc kiểm tra sai loại epoch có thể làm mọi lần xóa bình thường khiến phân trang không thể tiếp tục.

## 5. Ví dụ Java: tiếp tục mà không tải lại anchor

Mã giả sau minh họa view live. Nó trả dữ liệu theo mốc đọc và chính sách nhất quán của nguồn, không khẳng định một thao tác xóa xảy ra sau query sẽ tự thay đổi response đang gửi.

```java
Page<PurchaseRequestSummary> list(
        PageQuery query,
        VerifiedRequest verifiedRequest) {

    ActorContext actor =
            actorContexts.fromVerifiedRequest(verifiedRequest);

    PageInput input = pageInputs.decodeAndValidate(query);

    VisibilityReadPlan plan = visibilityPolicy.resolve(
            actor,
            input.filters(),
            input.requestedView());

    CursorBoundary boundary = cursorVerifier.verifyAndBind(
            input.cursor(),
            plan.cursorContext(),
            input.sort());

    int pageSize = input.pageSize();

    List<SummaryRow> rows = repository.readVisibleAfter(
            plan, boundary, pageSize + 1);

    boolean hasNext = rows.size() > pageSize;

    List<SummaryRow> returnedRows = rows.stream()
            .limit(pageSize)
            .toList();

    String nextCursor = null;

    if (hasNext) {
        SummaryRow lastReturned = returnedRows.get(
                returnedRows.size() - 1);

        nextCursor = cursorIssuer.issue(
                plan.cursorContext(),
                lastReturned.sortKey());
    }

    return Page.of(
            summaryMapper.allowedFields(returnedRows, plan),
            hasNext,
            nextCursor);
}
```

Các lớp là cổng trừu tượng, không phải API của một framework cụ thể. Hợp đồng cần giữ:

- VerifiedRequest chỉ được dựng từ nguồn xác thực đã kiểm chứng.
- PageSize phải dương và có giới hạn đủ an toàn trước phép cộng 1.
- VisibilityPolicy kiểm tra tenant, action, scope và quyền dùng view dữ liệu đã xóa nếu có.
- CursorVerifier xử lý trang đầu hoặc cursor hợp lệ theo contract; không mặc định một token lỗi là trang đầu.
- ReadVisibleAfter áp dụng đầy đủ scope, visibility, bộ lọc và ranh giới trước giới hạn hàng.
- Các dữ kiện sort đến từ nguồn và được mã hóa đúng kiểu, độ chính xác.
- SummaryMapper không thêm dữ liệu ngoài quyền qua label, field phụ hoặc join không được kiểm soát.
- Không có bước tìm anchor toàn cục chỉ vì cursor chứa một ID.
- Kết quả quyền hoặc dữ liệu cũ không được dùng vượt bảo đảm nhất quán mà hệ thống đã chọn.

### 5.1. Cursor mới phải ở item cuối đã trả

Giả sử lấy dư được A, B, C với pageSize bằng 2. Response trả A, B.

Cursor tiếp theo phải dùng khóa B trong mô hình này. Nếu dùng C, trang sau có thể bỏ C dù nó chưa được trả.

Nếu C bị xóa trước trang sau, query sau B chỉ bỏ C theo visibility rồi tiếp tục. Không cần đổi scope để bù item đã mất.

### 5.2. hasNext chỉ phản ánh mốc đọc

Có một item dư hợp lệ tại query không bảo đảm nó còn tồn tại hoặc được đọc ở request kế tiếp.

Nếu tất cả item sau cursor bị xóa hoặc mất quyền trước trang sau, một trang rỗng có thể là kết quả đúng của view live.

Không biến tình huống đó thành lỗi dữ liệu rồi reset cursor, trả lại trang cũ hoặc hiển thị tombstone ngoài chính sách.

### 5.3. Nếu phải lọc bổ sung ngoài nguồn

Đôi khi một nguồn tìm kiếm chỉ trả candidate và hệ thống phải kiểm tra visibility ở nguồn có thẩm quyền.

Khi đó một lần đọc pageSize + 1 candidate chưa đủ để kết luận hasNext của tập được phép. Cần cơ chế tiến độ, đọc thêm có giới hạn và contract kết quả phù hợp.

Không dùng số candidate ẩn để tiết lộ có bao nhiêu item đã xóa hoặc ngoài quyền. Nếu cần checkpoint nội bộ vượt qua các candidate, nó phải được bảo vệ, không lộ key nhạy cảm hoặc trở thành quyền đọc chúng.

Giải pháp này phức tạp hơn mẫu query đầy đủ predicate. Không tự cho phép truy vấn rộng hơn khi chưa lấp đủ trang.

## 6. View live, snapshot và hiệu lực xóa

### 6.1. Chọn contract trước

| Mô hình | Điều được giữ |
|---|---|
| Live pagination | Mỗi trang xét tập dữ liệu và quyền theo mốc đọc đã công bố |
| Snapshot dữ liệu | Nội dung được đọc theo một ảnh hoặc phiên bản xác định |
| Snapshot tập ID | Chốt những đối tượng cần xét, nhưng giá trị có thể được đọc hoặc kiểm tra lại theo hợp đồng |

Ba mô hình không có cùng hành vi khi item bị xóa.

Một timestamp trong cursor không tự tạo snapshot. Cần nguồn dữ liệu, phiên bản hoặc cơ chế có thể tái dựng đúng tập và giá trị cần thiết.

### 6.2. Snapshot có thể giữ dữ liệu đã bị xóa về sau

Một ảnh dữ liệu trước thao tác xóa có thể vẫn chứa item. Điều đó có thể phù hợp với một view lịch sử được cấp quyền, nhưng không tự phù hợp với view yêu cầu chặn đọc sau xóa.

Nếu quyền phải hiện tại, cần lớp kiểm tra hoặc cơ chế vô hiệu phù hợp. Khi overlay loại item khỏi snapshot, kết quả không còn là toàn bộ ảnh ban đầu theo nghĩa nguyên vẹn.

Cần nói rõ sự lựa chọn này. Không đồng thời hứa một snapshot hoàn chỉnh và luôn loại mọi dữ liệu bị xóa về sau mà không mô hình hóa sự khác biệt.

### 6.3. Không đổi mô hình giữa chừng

Nếu snapshot hết hiệu lực hoặc nguồn phiên bản không còn khả dụng, trả kết quả cursor không tiếp tục được theo contract.

Không lấy trang đầu từ snapshot rồi âm thầm lấy trang sau từ dữ liệu live. Item có thể lặp, mất hoặc thay giá trị trong khi client vẫn tưởng đang duyệt một ảnh cố định.

Tương tự, không tự chuyển sang view lịch sử để tìm lại anchor đã xóa khi caller chỉ được dùng view hoạt động.

### 6.4. Snapshot tập ID cần kết quả cho item không còn dùng được

Một batch hoặc lượt xuất có thể đã chốt ID. Khi xử lý từng ID, item có thể đã bị xóa hoặc mất quyền.

Cần áp dụng contract của hành động tiếp theo: từ chối, bỏ qua có ghi nhận an toàn hoặc yêu cầu lập lại phạm vi. Không dùng việc ID nằm trong manifest như quyền bỏ qua lifecycle hiện tại.

Thông báo cụ thể rằng một ID đã xóa chỉ được trả nếu caller được biết thông tin đó. Không tạo một dịch vụ dò lịch sử tồn tại qua kết quả pagination.

## 7. Soft delete, tombstone, quan hệ con và khôi phục

### 7.1. Soft delete phải được áp dụng ở mọi view tương ứng

Một cột deletedAt không có tác dụng nếu một số query quên predicate, raw query bỏ scope hoặc cache vẫn trả dữ liệu theo hợp đồng lỗi thời.

Các đường danh sách, tìm kiếm, tổng hợp và tải tài liệu cần dùng đúng policy. Không chỉ bảo vệ một repository method rồi coi mọi đường đọc an toàn.

DeletedAt cũng không thay thế state machine nghiệp vụ. Xóa khỏi danh sách không tự hủy thanh toán, thu hồi quyền hoặc xóa căn cứ phê duyệt. Nếu nghiệp vụ yêu cầu các tác dụng đó, lệnh xóa cần workflow riêng phù hợp.

### 7.2. Tombstone là dữ liệu được bảo vệ

Tombstone có thể giữ tenant, ID, thế hệ, mốc xóa hoặc khóa cần thiết theo nhu cầu. Nó không nhất thiết cần toàn bộ payload cũ.

Việc có tombstone không cho phép API công khai trả “item từng tồn tại” cho người ngoài scope. Quyền xem lịch sử và cách che giấu sự tồn tại vẫn phải được giữ.

Vòng đời tombstone và cursor cần tương thích. Nếu dữ kiện cần để tiếp tục đã bị dọn theo chính sách, không bịa ranh giới hoặc dùng mặc định.

Không giữ mọi dữ liệu nhạy cảm vô hạn chỉ để một kiểu cursor tiện hoạt động. Có thể chọn thiết kế điều hướng cần ít dữ kiện hơn hoặc một contract hết hạn rõ.

### 7.3. Parent đã xóa không mở quyền đọc child

Nếu attachment kế thừa quyền và visibility từ đề nghị, endpoint child phải xét parent tương ứng.

Biết attachmentId hoặc có một cursor cũ không tạo quyền đọc child khi chính sách đã loại parent khỏi view.

Nếu child có lifecycle riêng, cần policy riêng rõ ràng. Không dùng owner hoặc tenant của một parent khác do caller chọn để cấp quyền cho child thực tế.

### 7.4. Join và đếm child phải cùng ngữ nghĩa

Một danh sách có thể hiển thị số attachment đang hoạt động. Khi đó count cần cùng scope và điều kiện visibility, không đếm cả child đã xóa nếu view không được phép biết.

Với quan hệ tùy chọn, đặt điều kiện child sai vị trí có thể làm mất parent không có child. Cần giữ đúng ý nghĩa query khi thiết kế join và aggregation.

Một join một-nhiều còn có thể nhân số dòng. Nếu limit theo dòng join rồi mới loại trùng parent, pageSize và hasNext có thể không còn nói về item mà API công bố.

Có thể phân trang parent hợp lệ trước rồi tải dữ liệu con theo scope, hoặc dùng biểu diễn mỗi parent một dòng phù hợp. Bất kỳ bước đọc phụ nào vẫn cần contract nhất quán tương ứng.

### 7.5. Khôi phục không tự phục hồi mọi quyền cũ

Restore có thể làm cùng ID xuất hiện lại với khóa sort ban đầu. Nó không tự biến cursor cũ thành một grant đọc hoặc lệnh ghi mới.

Nếu dữ liệu được khôi phục nằm trước ranh giới đã duyệt, một lượt live có thể không nhìn thấy nó cho tới khi bắt đầu lại. Điều này cần được mô tả đúng, không hứa cursor live là một luồng thay đổi đầy đủ.

Restore cần thẩm quyền và các quyết định về owner, chia sẻ, state và bằng chứng. Không tự kích hoạt lại mọi quyền từng bị thu hồi hoặc mọi quyết định của vòng nghiệp vụ cũ.

Thế hệ visibility hoặc đối tượng có thể hữu ích cho các quyền và lệnh gắn với một vòng cụ thể. Tuy nhiên, không bắt mọi cursor live phải khớp visibility của anchor hiện tại nếu mục tiêu là tiếp tục sau khi anchor bị xóa.

## 8. Tổng số, cache và nguồn đọc chậm

### 8.1. Count phải cùng scope và visibility

Nếu response trả total, phép đếm cần dùng cùng tenant, quyền, chế độ và bộ lọc có ý nghĩa với danh sách.

Không đếm toàn bộ bảng rồi chỉ lọc items. Người dùng có thể không thấy hàng của tenant khác nhưng vẫn biết số lượng, số item đã xóa hoặc hoạt động của một nhóm không được xem.

Tương tự, totalIncludingDeleted hoặc deletedCount là dữ liệu có quyền riêng. Chúng không tự được phép chỉ vì endpoint có phân trang.

### 8.2. Count và page có thể phản ánh hai mốc

Nếu count chạy trước một lần xóa còn query page chạy sau, total và số dòng hiện tại có thể khác nhau.

API cần chọn mức nhất quán và cách trình bày. Có thể không trả total, trả một giá trị với ngữ nghĩa phù hợp hoặc dùng một ảnh đọc nhất quán nếu có yêu cầu.

Không hứa một tổng cố định chính xác xuyên suốt lượt live rồi tự lấp các hàng đã mất bằng dữ liệu ngoài scope.

Một ID bị thiếu trong chuỗi cũng không tự chứng minh có item đã xóa. Không dùng suy đoán từ ID làm thống kê lịch sử công khai.

### 8.3. Cache cũ có thể giữ payload đã bị ẩn

Một query có deletedAt đúng không giúp nếu response được trả thẳng từ cache có dữ liệu trước khi xóa.

Cache cần scope đúng, gồm tenant, subject hoặc chính sách chia sẻ, dataset, bộ lọc, view, sort và các dữ kiện hiệu lực liên quan. Một trang active không được dùng lại entry của view lịch sử.

Nếu việc xóa hoặc thu hồi phải có hiệu lực tại mốc chặt, cần cơ chế làm mới, vô hiệu hoặc kiểm chứng đáp ứng được mốc đó. Chỉ đặt một TTL không tự chứng minh dữ liệu biến mất ngay sau commit.

Cache version của dữ liệu có thể đổi khi item bị xóa mà cursor live vẫn tiếp tục được. Cache giữ kết quả đọc; cursor giữ ranh giới điều hướng. Không bắt buộc chúng dùng cùng một version hoặc cùng cách hết hiệu lực.

### 8.4. Replica, search index và projection

Nguồn đọc có thể chưa nhận thao tác xóa hoặc thay đổi quyền. Cần biết độ mới mà contract yêu cầu.

Nếu dùng candidate từ một nguồn chậm, có thể cần kiểm tra visibility ở nguồn đủ thẩm quyền trước khi trả. Việc đọc thêm để lấp trang phải có giới hạn và giữ nguyên scope.

Nếu không xác minh được, không chuyển sang trả dữ liệu rộng hơn. Cũng không nên giả vờ tập đã được kiểm tra là rỗng khi thực tế nguồn quyền hoặc nguồn visibility đang lỗi.

Một hàng biến mất bình thường khác với việc hệ thống không đủ dữ kiện để quyết định được trả hàng nào.

## 9. Danh sách phân trang và hành động tiếp theo

### 9.1. Được thấy ở trang trước không phải quyền ghi hiện tại

Client có thể lưu ID và version rồi gửi lệnh duyệt sau đó. Item có thể đã bị xóa, chuyển owner hoặc đổi state.

Handler của hành động ghi phải tải và kiểm tra lại theo tenant, quyền, lifecycle cùng precondition. Cursor hoặc kết quả trang cũ không tự là một grant để bỏ qua các điều kiện.

Trong mô hình không cho thao tác thông thường trên item đã xóa, chỉ loại khỏi danh sách là chưa đủ. Endpoint theo ID cũng phải giữ guard tương ứng.

Nếu nghiệp vụ cho phép một hành động lịch sử riêng, cần định nghĩa action và phạm vi riêng thay vì vô tình dùng lại handler đang hoạt động.

### 9.2. Duyệt hết một lượt live không chứng minh đã xử lý đủ tập ban đầu

Một quy trình có thể làm:

```text
đọc trang
    → lấy ID
    → thực hiện batch
    → đọc trang sau
```

Trong thời gian đó, item có thể bị xóa, thêm, khôi phục hoặc đổi scope.

Nếu yêu cầu là xử lý tất cả đối tượng của một tập tại mốc T, cần snapshot hoặc manifest có thẩm quyền phù hợp, cùng kiểm tra khi thực hiện. Không suy ra từ việc hasNext cuối cùng là false rằng mọi item của một tập quá khứ đều đã được xét.

Nếu mục tiêu chỉ là lượt live có thể thay đổi, kết quả phải mô tả đúng mức bảo đảm đó.

### 9.3. Không tự restore để tiếp tục thao tác

Một item không còn khả dụng không nên được tự tạo lại, xóa cờ deleted hoặc chuyển state về DRAFT để một lệnh cũ chạy được.

Restore và mở lại workflow là các hành động cần quyền, version và audit theo chính sách.

Nếu batch hoặc job đã chốt item, kết quả có thể cần trạng thái không còn khả dụng theo contract. Chi tiết rằng item bị xóa, thuộc ai hoặc chuyển đi đâu chỉ được trả khi caller có quyền biết.

### 9.4. Cùng ID sau restore cần đúng ngữ nghĩa

Một hệ thống có thể giữ ID khi restore, nhưng lệnh hoặc link gắn với một vòng đối tượng trước chưa chắc còn hiệu lực.

Nếu policy dùng generation hoặc epoch cho các quyền đó, endpoint cần kiểm tra đúng. Không lấy việc ID trùng làm bằng chứng nội dung và quyền không đổi.

Ngược lại, ranh giới sort của một cursor live không nhất thiết là một quyền gắn với vòng owner. Cần phân biệt hai mục đích để không vô hiệu điều hướng ngoài ý muốn.

## 10. Phản hồi lỗi không tạo dịch vụ dò item đã xóa

Có thể phân loại nội bộ:

| Tình huống | Hành vi theo contract |
|---|---|
| Cursor hợp lệ, chứa đủ ranh giới, anchor đã xóa | Có thể tiếp tục query đúng scope |
| Cursor cần state hoặc snapshot đã hết vòng đời | Báo không tiếp tục được, yêu cầu bắt đầu lại |
| Cursor bị sửa hoặc không khớp tenant, view, sort | Từ chối theo cơ chế xác minh |
| Cursor hợp lệ nhưng không còn hàng được phép | Trang rỗng và trạng thái tiếp tục phù hợp |
| Nguồn quyền hoặc visibility lỗi | Lỗi hệ thống theo contract, không giả làm một tập rỗng đã xác minh |
| Caller xin view deleted không có quyền | Không mở predicate hoặc dùng dữ liệu lịch sử làm dự phòng |

Mã lỗi công khai cần đủ để client xử lý nhưng không phân biệt các đối tượng ngoài quyền theo cách làm lộ sự tồn tại.

### 10.1. Không tra cứu toàn cục để giải thích

Khi không tìm được anchor, không nên tự tìm ở mọi tenant rồi trả “item này đã xóa ở tenant B”.

Một token đã được phát hành hợp lệ có thể cho phép biết một số dữ kiện điều hướng theo contract. Token giả hoặc không đúng ngữ cảnh không có quyền đó.

Thông báo chung như cursor không hợp lệ hoặc không còn dùng được có thể phù hợp hơn việc tiết lộ trạng thái của ID mà caller gửi.

### 10.2. Client cần phân biệt trang rỗng và cần bắt đầu lại

Trang rỗng hợp lệ không có nghĩa cursor bị hỏng. Cursor hết hiệu lực cũng không nên bị giấu bằng một response rỗng khiến client tưởng không còn dữ liệu.

Nếu phải bắt đầu lại, client có thể làm theo flow rõ ràng. Không tự tải trang đầu rồi ghép vào trang cũ như thể đó là phần tiếp theo.

Với thay đổi bộ lọc, sort hoặc view, cần cursor mới theo contract, tránh trộn kết quả của hai tập khác nhau.

### 10.3. Không phản chiếu dữ liệu anchor tùy ý

Thông báo lỗi không cần trả payload cũ, owner hoặc tên item đã bị xóa để giải thích vì sao không tiếp tục.

Các đường dẫn lỗi, token và tên field do caller điều khiển cần giới hạn, định dạng an toàn. Không serialize nguyên cấu trúc cursor hoặc exception ra ngoài.

## 11. Vòng đời cursor, giới hạn và quan sát

Cursor có thể phụ thuộc tài nguyên phía server như snapshot, checkpoint hoặc state điều hướng. Cần giới hạn thời gian và khối lượng giữ theo chính sách.

Một cursor cũ không được ép hệ thống giữ dữ liệu nhạy cảm hoặc tài nguyên không giới hạn. Nếu nguồn cần thiết đã hết vòng đời, dùng kết quả kết thúc rõ ràng thay vì fallback sang một mô hình khác.

### 11.1. Giới hạn pageSize và việc đọc thêm

PageSize, số lần overfetch, độ sâu điều hướng hoặc lượng candidate cần có giới hạn phù hợp.

Khi gặp nhiều candidate đã xóa hoặc mất quyền, không lặp vô hạn, không nhảy scope và không bỏ kiểm tra chỉ để đủ trang.

Nếu một nguồn chưa cho phép kết luận hasNext chính xác trong ngân sách đọc, cần contract diễn đạt được giới hạn thay vì bịa một kết quả chắc chắn.

### 11.2. Không làm bước đọc có tác dụng nghiệp vụ bất ngờ

Lấy trang không nên tự restore item, xác nhận phê duyệt hoặc tạo thao tác mới chỉ vì gặp một bản ghi lịch sử.

Các chỉ số truy cập nếu có cần được phân biệt với state nghiệp vụ. Một lần retry đọc trang không tự trở thành một lần xử lý thêm item.

Nếu có cơ chế cursor một lần dùng hoặc checkpoint tiêu thụ được, phải định nghĩa riêng. Không mặc định mọi lượt đọc thông thường có ý nghĩa thực hiện command.

### 11.3. Dấu vết cần giữ ở mức an toàn

Có thể quan sát tenant có thẩm quyền, actor, dataset, view, loại lỗi cursor, phiên bản policy, nguồn đọc và correlationId.

Không ghi nguyên token hoặc toàn bộ payload item đã xóa chỉ để debug. Cursor có thể chứa thông tin nhạy cảm hoặc tham chiếu cần được bảo vệ.

Tỷ lệ trang rỗng tăng sau một đợt xóa chưa chắc là tấn công. Nhiều lần đổi tenant, view hoặc token không hợp lệ cần được xem cùng ngữ cảnh.

Audit đọc lịch sử hoặc includeDeleted, nếu chính sách yêu cầu, phải lấy actor và quyền thực tế từ nguồn có thẩm quyền, không từ các claim tự khai trong query.

## 12. Kiểm thử hành vi khi item biến mất

### 12.1. Fixture phân trang dễ kiểm chứng

Chuẩn bị các item đã có thứ tự:

```text
A, B, C, D, E, F
pageSize = 2
trang đầu trả A, B
```

Với cursor theo khóa cuối B và sort bất biến như ví dụ:

| Thay đổi trước query trang sau | Kỳ vọng theo view live minh họa |
|---|---|
| Xóa A | Tiếp tục sau B, không bỏ C chỉ vì vị trí số học đổi |
| Xóa B | Tiếp tục được nếu cursor chứa đủ ranh giới |
| Xóa C | Không trả C; lấy những item hợp lệ sau đó |
| Xóa toàn bộ phần sau B | Trang rỗng, không lấy ngoài scope để lấp |
| Khôi phục item ở trước B | Không tự hứa lượt hiện tại sẽ quay lại lấy item đó |
| Item sau B mất quyền đọc | Không trả dù cursor vẫn đúng về thứ tự |

Nếu dùng offset, kiểm thử phải phản ánh khả năng dịch vị trí và contract tương ứng. Không đánh đồng hành vi khác nhau của hai thiết kế với một bảo đảm hoàn chỉnh mà API chưa có.

### 12.2. Ma trận an toàn

| Tình huống | Kết quả cần kiểm chứng |
|---|---|
| Anchor soft delete | Không cần trả dữ liệu anchor để tiếp tục hợp lệ |
| Anchor hard delete và cursor có đủ khóa | Không reset hoặc bỏ predicate |
| Cursor chỉ có ID nhưng nguồn ranh giới đã mất | Kết thúc bằng hành vi không tiếp tục được theo contract |
| Cursor tenant A dùng ở tenant B | Không nhận dữ liệu ngoài binding |
| Cursor cá nhân của U dùng cho V | Không mở scope ngoài chính sách chia sẻ đã định nghĩa |
| Đổi includeDeleted hoặc view giữa lượt | Kiểm tra quyền và context cursor, không nâng quyền |
| Token bị sửa key hoặc sort | Không tin ranh giới chưa được xác minh |
| Cùng createdAt cho nhiều item | Tiebreaker giữ thứ tự đúng theo contract |
| Timestamp cursor bị giảm độ chính xác | Không bỏ sót hoặc lặp ngoài bảo đảm đã chọn |
| Nguồn có nhiều candidate đã xóa | Không dùng count candidate làm hasNext của tập được phép |
| Page không đủ size | Không lấy item owner khác hoặc tenant khác |
| Parent đã xóa nhưng child còn | Policy kế thừa visibility vẫn được giữ |
| Count hoặc tổng hợp có item deleted | Không tiết lộ dữ liệu ngoài view |
| Cache có payload cũ | Đáp ứng mốc hiệu lực xóa đã công bố |
| Search hoặc replica chưa cập nhật | Không coi predicate ở nguồn chậm là đủ cho bảo đảm mạnh hơn |
| Snapshot trước xóa vẫn chứa item | Chỉ trả theo view và quyền lịch sử phù hợp |
| Snapshot hết vòng đời | Không âm thầm chuyển sang live |
| Restore cùng ID | Không tự phục hồi grant hoặc command cũ |
| Người dùng gọi action bằng ID đã thấy trước | Kiểm tra lại quyền, state và visibility phù hợp |
| Nguồn quyền lỗi | Không giả làm trang rỗng đã xác minh hoặc mở rộng quyền |

### 12.3. Xóa ở những mốc khác nhau

Cần phân biệt ít nhất:

1. Item đã xóa trước khi bắt đầu query.
2. Anchor bị xóa sau trang đầu nhưng trước trang sau.
3. Item được query đọc rồi mới có thao tác xóa.
4. Cache được tạo trước xóa và dùng sau xóa.
5. Candidate trong nguồn tìm kiếm chưa nhận cập nhật.
6. Quyền bị thu hồi giữa các trang.
7. Restore xảy ra trong khi lượt live vẫn đang duyệt.

Mỗi ca cần kỳ vọng theo mốc nhất quán đã chọn. Một query trước xóa và response sau xóa không thể tự được đánh giá như thể nguồn đã đọc sau xóa.

Nếu policy yêu cầu chặn ở một mốc mạnh hơn, test phải chứng minh cơ chế phối hợp đó, thay vì chỉ kiểm tra có deletedAt trong query.

### 12.4. Kiểm tra toàn bộ response, không chỉ items

Cần xem cả:

```text
items và các trường được trả
hasNext cùng nextCursor
total và các thống kê nếu có
nhãn, số child và dữ liệu join
thông báo lỗi
tệp hoặc bản xuất nếu dùng cùng lượt đọc
cache key và dữ liệu được dùng lại
dấu vết truy cập theo phạm vi phù hợp
```

Một response không có item trái quyền vẫn có thể lộ số lượng hoặc tên thông qua metadata.

Với cursor, kiểm tra nội dung được mã hóa hoặc tham chiếu không mang quá nhiều dữ kiện và không thể đổi context ngoài contract. Encode không thay cho bảo vệ dữ liệu.

### 12.5. Các điều không được xảy ra

Sau khi item bị loại khỏi view theo mốc có hiệu lực:

```text
không trả nó qua một query hoặc cache trái contract
không bỏ tenant hoặc scope để tìm anchor
không dùng view lịch sử làm phương án dự phòng chưa được cấp
không tạo tombstone công khai ngoài quyền
không reset cursor ngầm rồi ghép trang cũ với trang mới
không dùng item đã thấy trước làm quyền thực hiện lệnh mới
không tự restore hoặc đặt lại state để job tiếp tục
không ghi hoặc trả payload deleted qua lỗi chẩn đoán
```

Những dữ liệu đã được nhận ở mốc hợp lệ trước đó là một vấn đề vòng đời riêng. Không mô tả việc xóa như cơ chế thu hồi ngược mọi dữ liệu phía client.

### 12.6. Kiểm thử lượt duyệt phục vụ nghiệp vụ

Nếu danh sách dùng để lập batch, hãy thử:

```text
đọc trang đầu
    → xóa hoặc chuyển scope một item
    → đọc trang sau
    → gửi batch dựa trên dữ liệu đã thu thập
```

Kiểm tra rằng kết luận “đã đọc hết” không bị biến thành bằng chứng đã có đủ tập tại một thời điểm quá khứ. Batch vẫn phải dùng manifest và precondition phù hợp với yêu cầu của nó.

Cũng cần kiểm tra cursor cũ sau khi đổi filter, sort hoặc view, và trường hợp một item được khôi phục về trước ranh giới đã đọc.

## 13. Bài tập áp dụng

Thiết kế API danh sách đề nghị mua hàng có soft delete, sort theo createdAt và id, quyền đọc theo owner cùng một view lịch sử riêng.

1. Chọn hợp đồng live, snapshot dữ liệu hoặc snapshot tập ID cho từng nhu cầu.
2. Mô tả điều gì xảy ra khi item trước trang, anchor hoặc item tiếp theo bị xóa.
3. Viết predicate tenant, scope, visibility và ranh giới khóa.
4. Thiết kế binding của cursor với actor, view, bộ lọc và sort.
5. Xác định hasNext, total và cách xử lý trang ngắn hoặc rỗng.
6. Mô tả cache, replica hoặc nguồn tìm kiếm đáp ứng mốc hiệu lực xóa ra sao.
7. Chọn dữ kiện tombstone cần giữ và hành vi khi cursor hết vòng đời.
8. Xử lý child, restore và command dựa trên ID đã đọc từ trang cũ.
9. Viết test xóa anchor, nhiều item cùng timestamp và includeDeleted trái quyền.
10. Chỉ ra cách tránh dùng lượt live làm bằng chứng hoàn chỉnh cho một batch tại mốc T.

Một thiết kế đúng phải tiếp tục hoặc kết thúc lượt đọc theo hợp đồng mà không mở rộng quyền để bù cho item biến mất. Ranh giới điều hướng, visibility và quyền truy cập cần được giữ riêng nhưng phối hợp nhất quán để xóa, restore hoặc thay đổi scope không tạo ra dữ liệu ngoài quyền hay kết luận nghiệp vụ sai.
