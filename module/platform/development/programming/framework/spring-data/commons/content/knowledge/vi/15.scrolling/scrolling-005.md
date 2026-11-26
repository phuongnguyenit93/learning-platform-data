# Thứ tự ổn định, khóa phân biệt và chiều duyệt

Scrolling không chỉ là lấy thêm một nhóm bản ghi. Mỗi lần tiếp tục cần trả lời chính xác: đi từ mốc nào, theo chiều nào và dựa trên thứ tự nào? Nếu nhiều bản ghi có cùng giá trị sắp xếp nhưng cursor chỉ giữ giá trị đó, ứng dụng có thể bỏ qua cả phần còn lại của nhóm hoặc đọc lại bản ghi đã xử lý.

Trong chương **Scrolling** của **SPRING_DATA_COMMONS**, bài này tập trung vào bộ khóa đủ phân định kết quả, phép so sánh keyset và sự khác nhau giữa chiều sort với chiều duyệt. Những abstraction như `Sort`, `ScrollPosition` và `Window` là nền tảng chung; khả năng thực thi từng loại scrolling vẫn thuộc module và store cụ thể.

## 1. Ba khái niệm phải tách riêng

| Khái niệm | Câu hỏi được trả lời | Ví dụ |
| --- | --- | --- |
| Thứ tự hiển thị hoặc thứ tự chuẩn | Toàn bộ kết quả được xếp như thế nào? | `createdAt DESC, id DESC` |
| Khóa phân biệt | Làm sao phân định hai kết quả bằng nhau ở các khóa trước? | `id` duy nhất làm khóa cuối |
| Chiều duyệt | Tìm phần sau hay phần trước một mốc trong thứ tự chuẩn? | Đi tiếp từ cuối cửa sổ, hoặc đi lùi từ đầu cửa sổ |

`DESC` không có nghĩa “duyệt lùi”. Với danh sách mới nhất trước, đi tiếp từ đầu đến cuối thường làm các timestamp và id giảm dần.

Tương tự, duyệt lùi không nhất thiết có nghĩa thay đổi thứ tự mà giao diện công bố. Một ứng dụng có thể luôn hiển thị mới nhất trước, dù request đang tìm cửa sổ trước hay sau cửa sổ hiện tại.

Trong bài, **thứ tự chuẩn** là thứ tự mà hợp đồng ứng dụng muốn trả cho caller. Các bước đảo sort khi lấy dữ liệu ngược là một chi tiết thuật toán cần được adapter/module xử lý đúng.

## 2. Vì sao một khóa thời gian thường chưa đủ?

Giả sử hai thuộc tính của đơn hàng là:

```text
createdAt: thời điểm tạo
id: định danh duy nhất
```

Nhiều đơn có thể cùng `createdAt` vì:

- Được tạo trong cùng một khoảng thời gian rất ngắn.
- Được gán cùng timestamp trong một thao tác nghiệp vụ.
- Store lưu thời gian với độ chính xác thấp hơn object Java ban đầu.
- Dữ liệu được nhập hoặc đồng bộ theo một mốc chung.

Sort chỉ theo `createdAt DESC` xếp được các nhóm thời gian, nhưng chưa phân định thứ tự bên trong từng nhóm.

Nếu cursor chỉ chứa timestamp cuối rồi query tiếp bằng `createdAt < lastCreatedAt`, mọi bản ghi còn lại cùng timestamp có thể bị bỏ qua. Đổi thành `<=` lại có thể lấy lại các bản ghi đã đọc.

Một bộ khóa như:

```text
createdAt DESC, id DESC
```

giải quyết sự mơ hồ đó nếu id không null, duy nhất trong đơn vị kết quả và được store sắp xếp phù hợp.

Khóa id không thay thế ý nghĩa nghiệp vụ của thời gian. Nó chỉ phân định những bản ghi mà thời gian chưa phân định được. Id lớn hơn cũng không tự chứng minh bản ghi đã được commit muộn hơn theo mọi cơ chế cấp id.

## 3. Tập dữ liệu xuyên suốt

Giả sử domain `PurchaseOrder` có `id: Long`, `tenantId: String`, `status: OrderStatus`, `createdAt: Instant`. Các giá trị khóa ở dữ liệu đã lưu đều không null; predicate chọn đúng một tenant và trạng thái `PAID`.

Thứ tự chuẩn là `createdAt DESC, id DESC`:

| Vị trí theo thứ tự chuẩn | id | createdAt |
| --- | --- | --- |
| `0` | `108` | `2026-11-25T10:05:00Z` |
| `1` | `107` | `2026-11-25T10:05:00Z` |
| `2` | `106` | `2026-11-25T10:00:00Z` |
| `3` | `105` | `2026-11-25T10:00:00Z` |
| `4` | `104` | `2026-11-25T10:00:00Z` |
| `5` | `103` | `2026-11-25T09:55:00Z` |
| `6` | `102` | `2026-11-25T09:50:00Z` |
| `7` | `101` | `2026-11-25T09:50:00Z` |

Với kích thước cửa sổ bằng `3`, trên dữ liệu không đổi:

```text
Cửa sổ 1: 108, 107, 106
Cửa sổ 2: 105, 104, 103
Cửa sổ 3: 102, 101
```

Nhóm thời gian `10:00` đi qua ranh giới cửa sổ. Đây là một fixture quan trọng vì nó làm lộ lỗi cursor chỉ giữ timestamp.

## 4. So sánh keyset là so sánh theo thứ tự từ điển

Với bộ khóa `(createdAt, id)`, trước hết so `createdAt`; chỉ khi bằng nhau mới so id. Không dùng một điều kiện yêu cầu cả hai thuộc tính cùng nhỏ hơn như một phép thay thế.

### 4.1. Duyệt tiến với hai khóa giảm dần

Sau cửa sổ đầu, mốc cuối là:

```text
lastCreatedAt = 2026-11-25T10:00:00Z
lastId        = 106
```

Với `createdAt DESC, id DESC`, điều kiện chọn phần sau mốc về mặt logic là:

```text
createdAt < lastCreatedAt
OR (createdAt = lastCreatedAt AND id < lastId)
```

Kết hợp đầy đủ với phạm vi:

```text
tenantId = tenant đang xét
AND status = PAID
AND (
    createdAt < lastCreatedAt
    OR (createdAt = lastCreatedAt AND id < lastId)
)
```

Query tiếp tục dùng thứ tự chuẩn và lấy tối đa ba kết quả, nên nhận `105, 104, 103`.

Đây là mô hình logic, không phải một đoạn cú pháp phải chép nguyên vào mọi ngôn ngữ query. Module có hỗ trợ keyset sẽ chuyển vị trí và sort thành điều kiện phù hợp với store.

### 4.2. Các công thức dễ sai

Chỉ dùng:

```text
createdAt < lastCreatedAt
```

sẽ bỏ `105` và `104` vì chúng có cùng thời gian với mốc `106`.

Dùng:

```text
createdAt <= lastCreatedAt
```

có thể lấy lại `106` và những bản ghi cùng nhóm đã đọc.

Dùng:

```text
createdAt < lastCreatedAt AND id < lastId
```

lại thêm một ràng buộc không đúng cho các nhóm thời gian khác. Một bản ghi cũ hơn vẫn thuộc phần sau dù id của nó không nhỏ hơn mốc, nếu cơ chế id và dữ liệu cho phép trường hợp đó.

## 5. Chiều của từng Order quyết định dấu so sánh

Với một khóa đơn giản:

| Hướng sort chuẩn | Phần sau mốc khi duyệt tiến | Phần trước mốc khi duyệt lùi |
| --- | --- | --- |
| `ASC` | Giá trị lớn hơn mốc | Giá trị nhỏ hơn mốc |
| `DESC` | Giá trị nhỏ hơn mốc | Giá trị lớn hơn mốc |

Với hai khóa `a`, `b`, điều kiện **phần sau mốc** là:

| Sort chuẩn | Điều kiện logic |
| --- | --- |
| `a ASC, b ASC` | `a > A OR (a = A AND b > B)` |
| `a DESC, b DESC` | `a < A OR (a = A AND b < B)` |
| `a DESC, b ASC` | `a < A OR (a = A AND b > B)` |
| `a ASC, b DESC` | `a > A OR (a = A AND b < B)` |

Không thể nhìn khóa đầu là DESC rồi đảo mọi phép so sánh theo cùng một hướng nếu các khóa sau có hướng khác.

Ví dụ `createdAt DESC, id ASC` vẫn có thể là một thứ tự đầy đủ, nhưng điều kiện tiếp tục trong nhóm cùng thời gian phải là `id > lastId`. Nó khác với ví dụ chính của bài.

Khi có thêm nhiều khóa, nguyên tắc được mở rộng theo các nhánh: khóa trước bằng nhau rồi mới xét khóa tiếp theo. Cần dùng cơ chế keyset của module hoặc một implementation được kiểm chứng, thay vì ghép dấu tùy ý theo trực giác.

## 6. Mốc tiếp tục là loại trừ, không phải một phần tử cần đọc lại

Sau khi trả `108, 107, 106`, mốc cuối `106` đại diện phần đã đọc. Lần tiếp theo phải tìm sau nó, không đưa nó vào nội dung lần nữa trên dữ liệu không đổi.

Dùng phép so sánh nghiêm ngặt theo bộ khóa giúp thể hiện điều đó. Khái niệm loại trừ mốc cũng ảnh hưởng cách chọn `ScrollPosition`: vị trí của phần tử đã đọc khác với trạng thái bắt đầu chưa đọc phần tử nào.

Với keyset, vị trí ban đầu có thể được tạo bằng:

```java
ScrollPosition initial = ScrollPosition.keyset();
```

Nó chưa chứa một bộ giá trị của một entity cuối nào. Không tự dùng timestamp hiện tại hoặc id `0` để giả làm vị trí ban đầu nếu hợp đồng không định nghĩa điều kiện đó.

Mốc nên được lấy từ dữ liệu đã trả về sau mapping/độ chính xác của store, không phải dựng lại bằng một thời điểm mới hoặc một phép làm tròn khác.

## 7. Ví dụ duyệt tiến bằng Window

Ví dụ dùng **Spring Data JPA** với bộ phiên bản, derived query và mapping đã xác nhận hỗ trợ keyset scrolling. `OrderStatus` là enum nghiệp vụ; phần cấu hình persistence và entity đầy đủ được lược bỏ.

```java
import org.springframework.data.domain.ScrollPosition;
import org.springframework.data.domain.Window;
import org.springframework.data.repository.Repository;

public interface PurchaseOrderRepository
        extends Repository<PurchaseOrder, Long> {

    Window<PurchaseOrder> findFirst3ByTenantIdAndStatusOrderByCreatedAtDescIdDesc(
            String tenantId,
            OrderStatus status,
            ScrollPosition position);
}
```

Vòng duyệt minh họa:

```java
ScrollPosition position = ScrollPosition.keyset();

while (true) {
    Window<PurchaseOrder> window = repository
            .findFirst3ByTenantIdAndStatusOrderByCreatedAtDescIdDesc(
                    tenantId,
                    OrderStatus.PAID,
                    position);

    if (window.isEmpty()) {
        break;
    }

    for (PurchaseOrder order : window) {
        process(order);
    }

    if (!window.hasNext()) {
        break;
    }

    position = window.positionAt(window.size() - 1);
}
```

`process(...)` là bước nghiệp vụ minh họa. Vị trí tiếp tục được lấy tại phần tử cuối thật sự trả về và xử lý, không phải từ một giá trị tự đoán theo id.

Cần kiểm tra window rỗng trước khi lấy chỉ số `size() - 1`. Không tạo lại `ScrollPosition.keyset()` trong mỗi vòng, vì như vậy có thể đọc lặp phần đầu.

Ví dụ này thể hiện đường duyệt tiến. Không suy từ việc module chấp nhận chữ ký đó rằng mọi loại query khai báo, mọi store hoặc mọi chiều duyệt đều có cùng mức hỗ trợ.

## 8. Duyệt lùi cần mốc đầu của cửa sổ hiện tại

Với thứ tự chuẩn:

```text
108, 107, 106 | 105, 104, 103 | 102, 101
```

Nếu đang ở cửa sổ `105, 104, 103`:

- Đi tiếp dùng mốc cuối `103` để tìm phần sau.
- Đi lùi dùng mốc đầu `105` để tìm phần trước.

Lấy mốc cuối rồi chỉ đổi một cờ chiều có thể chọn sai miền hoặc lấy lại một phần cửa sổ hiện tại. Mốc và chiều phải được quyết định cùng nhau.

Với sort `createdAt DESC, id DESC`, phần trước mốc `(anchorCreatedAt, anchorId)` có điều kiện logic:

```text
createdAt > anchorCreatedAt
OR (createdAt = anchorCreatedAt AND id > anchorId)
```

Đó mới là **miền bản ghi trước mốc**. Để lấy cửa sổ liền kề gần nhất trong miền đó, còn phải chọn hướng lấy dữ liệu đúng.

## 9. Tìm cửa sổ trước gần nhất không phải lấy đầu của toàn miền trước

Giả sử đang ở cửa sổ cuối `102, 101`, muốn đi lùi một cửa sổ. Mốc đầu là `102`, thời điểm `09:50`.

Miền trước mốc theo thứ tự chuẩn gồm:

```text
108, 107, 106, 105, 104, 103
```

Nếu chọn ba phần tử đầu miền này theo sort DESC hiện tại, kết quả là `108, 107, 106`: ứng dụng nhảy về cửa sổ đầu, bỏ qua cửa sổ liền kề.

Một thuật toán lấy ngược thường làm:

1. Chọn các bản ghi nằm trước mốc.
2. Đảo hướng từng khóa để lấy những bản ghi gần mốc trước.
3. Giới hạn số lượng cần lấy.
4. Chuẩn hóa nội dung về thứ tự mà hợp đồng hiển thị đã công bố.

Trong ví dụ, query theo hướng lấy ngược `createdAt ASC, id ASC` nhận gần mốc nhất:

```text
103, 104, 105
```

Đưa nội dung đó về thứ tự chuẩn mới nhất trước cho:

```text
105, 104, 103
```

Đây là cửa sổ liền kề cần tìm.

### Tách thuật toán minh họa khỏi hành vi module

Một module có hỗ trợ backward keyset có thể đã đảo điều kiện, sort và chuẩn hóa nội dung trong implementation. Không áp dụng thêm một lần `reverse` chỉ vì đã đọc thuật toán trên.

Cần xác nhận API và thứ tự đầu ra của module/phiên bản đang dùng. Nếu ứng dụng tự viết adapter, adapter phải công bố rõ nội dung trả về luôn theo thứ tự chuẩn hay theo hướng đang lấy dữ liệu.

Duyệt lùi là một khả năng cần kiểm chứng riêng; có `Window` và `ScrollPosition` không tự chứng minh mọi backend hoặc nguồn query hỗ trợ hai chiều.

## 10. Phần tử dư để xác định tiếp tục không phải mốc đã trả

Một implementation có thể lấy `N + 1` kết quả để biết còn phần tiếp theo, rồi chỉ công bố N phần tử nội dung.

Nếu lấy bốn entity cho cửa sổ size ba, phần tử dư chưa được trả cho caller. Dùng nó làm mốc tiếp tục có thể khiến lần sau bỏ qua chính entity chưa đọc đó.

Mốc tiếp tục cần ứng với biên của **nội dung đã công bố**, theo chiều và thứ tự hợp đồng tương ứng.

Với một adapter tự triển khai lấy ngược, thứ tự các bước cũng quan trọng:

```text
Lấy N + 1 phần tử gần mốc theo hướng query ngược
        |
        v
Xác định còn dữ liệu phía đó hay không
        |
        v
Giữ N phần tử gần mốc để làm nội dung
        |
        v
Đưa N phần tử về thứ tự hiển thị chuẩn
```

Đảo toàn bộ N + 1 rồi cắt sai phía có thể chọn một tập khác với cửa sổ liền kề mong muốn.

Cờ `hasNext` của một cửa sổ cần được hiểu trong ngữ cảnh traversal mà module đang thực hiện. Khi ánh xạ thành nút “Tiếp” và “Trước” theo thứ tự chuẩn, không sao chép cờ hoặc token mà bỏ qua chiều hiện tại.

## 11. Khóa phân biệt phải đúng phạm vi và đơn vị kết quả

### 11.1. Duy nhất cục bộ chưa chắc đủ cho toàn truy vấn

Một `localNumber` chỉ duy nhất trong từng tenant có thể phân định tốt khi query cố định một tenant. Nếu truy vấn nhiều tenant, cần thêm tenant hoặc một khóa toàn cục phù hợp.

Nếu dùng composite id, bộ khóa hữu hiệu phải có đủ những thành phần để phân định kết quả theo mapping. Đừng chỉ chọn một thành phần thuận tiện rồi coi cả id đã được đại diện.

### 11.2. Entity id có thể lặp trên kết quả join

Nếu query trả từng dòng chi tiết của đơn, nhiều dòng có cùng `order.id`. Thêm order id vào cuối chưa phân định được các dòng đó.

Cần xác định đơn vị scrolling:

- Mỗi kết quả là một đơn: query và việc loại trùng phải đúng theo entity gốc.
- Mỗi kết quả là một dòng chi tiết: cần khóa của dòng hoặc bộ khóa tương đương.
- Mỗi kết quả là một nhóm tổng hợp: cần khóa phân định các nhóm.

Distinct, grouping và projection ảnh hưởng đơn vị kết quả. Không dùng một công thức cursor của entity gốc cho một tập dòng khác mà chưa kiểm tra.

### 11.3. Khóa tự bổ sung cũng phải được hiểu

Một số implementation có thể bổ sung khóa định danh để hoàn thiện sort cho keyset. Dù vậy, người thiết kế cần biết bộ khóa **hiệu lực** gồm những gì để hiểu vị trí và projection.

Không dựa vào một giả định chung rằng mọi module đều tự thêm id, hoặc tự serialize một cursor chỉ giữ timestamp trong khi implementation thực tế dùng nhiều thuộc tính.

## 12. Projection, null và quy tắc so sánh

### 12.1. Projection cần đủ khóa trích xuất vị trí

Nếu sort theo `createdAt` và `id`, projection trực tiếp phải cung cấp những thuộc tính cần để module trích xuất keyset. Một kết quả chỉ có tên khách hàng không tự đủ thông tin cho mốc đó.

Ứng dụng không nhất thiết phải hiển thị mọi khóa trên màn hình, nhưng tầng tạo cursor phải có cách hợp lệ để lấy và giữ chúng.

Chuyển nội dung từ một Window đã hợp lệ sang DTO bằng cơ chế map container khác với việc ngay từ đầu query một projection thiếu khóa. Cần giữ metadata vị trí thay vì dựng lại cursor bằng thông tin đã bị lược bỏ.

### 12.2. Null cần được xử lý theo khả năng cơ chế keyset

Các công thức trong bài giả định khóa không null. Với SQL, so sánh thông thường và phép bằng với null không có cùng ngữ nghĩa như giá trị thông thường.

Spring Data JPA keyset có yêu cầu non-null đối với các thuộc tính sort cần dùng. Không coi gợi ý null ordering trong `Sort` là một cách tự động loại bỏ giới hạn đó.

Store khác có thể có semantics riêng cho null hoặc trường bị thiếu. Muốn hỗ trợ các trường hợp này, cần cơ chế được module hỗ trợ và kiểm chứng, không chỉ thêm một dấu OR chưa rõ ý nghĩa.

### 12.3. Giá trị token phải giữ đúng kiểu và độ chính xác

Mốc được đọc là một `Instant` theo độ chính xác lưu trữ thì cần được khôi phục tương ứng. Làm tròn sang giây trong token có thể làm rơi vị trí vào một nhóm khác.

Id số cũng không được so sánh như chuỗi chỉ vì nó được truyền qua JSON. Thứ tự từ điển của chuỗi `"100"` và `"99"` khác với thứ tự số.

Với chuỗi, collation hoặc so sánh không phân biệt hoa thường có thể coi những giá trị source khác nhau là bằng nhau. Khóa cuối cần thực sự phân định theo quy tắc comparator của store, không chỉ theo cách Java in giá trị.

## 13. Một token tiếp tục gắn với toàn bộ ngữ cảnh traversal

Ở mức thiết kế, vị trí tiếp tục cần được hiểu cùng những thông tin sau:

| Thành phần | Vai trò |
| --- | --- |
| Bộ giá trị khóa tại biên | Xác định mốc tiếp tục |
| Thứ tự và hướng từng khóa | Xác định phép so sánh |
| Chiều duyệt | Chọn phần trước hay sau mốc |
| Bộ lọc và phạm vi tenant | Giữ cùng tập dữ liệu logic |
| Phiên bản hợp đồng nếu có | Giải thích token sau khi ứng dụng đổi quy tắc |

Không nhất thiết nhúng tất cả thông tin thành văn bản công khai trong token; ứng dụng có thể quản lý một phần ở ngữ cảnh khác. Điều quan trọng là không chấp nhận một token như thể nó độc lập với query đã tạo ra nó.

Ví dụ request đổi từ sort mới nhất sang tổng tiền cao nhất cần bắt đầu một lượt duyệt mới. Đổi tenant hoặc trạng thái cũng không nên tiếp tục từ một mốc cũ bằng cách giữ nguyên token.

`ScrollPosition` là abstraction nội bộ của Commons, không tự định nghĩa định dạng cursor API ổn định cho mọi ứng dụng. Một cursor của backend khác cũng không tự chuyển được sang keyset của repository chỉ bằng một phép cast.

Về mặt keyset, mốc là bộ giá trị so sánh. Nếu entity gốc bị xóa, bộ giá trị đã lưu vẫn có thể đủ để mô tả ranh giới logic; khả năng tiếp tục thực tế còn phụ thuộc adapter có cần tra lại entity hay không. Token chỉ giữ id rồi phụ thuộc lookup có thể có hành vi khác với token giữ đủ khóa.

## 14. Thứ tự ổn định không bảo đảm lịch sử bất biến

Bộ khóa đầy đủ giúp xác định thứ tự trên cùng dữ liệu. Nó không tự giữ nguyên tập kết quả giữa các request.

Ví dụ khi đang đi tiếp:

- Một entity mới đứng trước mốc có thể không xuất hiện trong phần tiếp theo.
- Một entity chưa đọc đổi khóa để chuyển lên trước mốc có thể bị bỏ qua trong lượt duyệt đó.
- Một entity đã đọc đổi khóa để chuyển xuống sau mốc có thể lại thuộc phần được chọn về sau.
- Thay đổi trạng thái làm entity ra/vào predicate dù các khóa sort giữ nguyên.

Do đó, đi lùi rồi đi tiến không tự đảm bảo trả lại đúng nội dung từng thấy trước đó khi dữ liệu đã thay đổi. Nếu sản phẩm cần lịch sử cửa sổ chính xác, có thể cần giữ nội dung, snapshot hoặc một cơ chế phiên bản phù hợp.

Hạ tầng auditing có thể ghi thời gian tạo/cập nhật, nhưng không tự làm chúng duy nhất, bất biến theo mọi nghiệp vụ hoặc trở thành snapshot của toàn truy vấn.

Đối với tác vụ xử lý, còn cần checkpoint và chính sách chạy lại thích hợp. Chỉ lưu cursor không chứng minh mỗi tác dụng nghiệp vụ đã được commit đúng một lần.

## 15. Store quyết định cách thực hiện và chi phí

Một bộ khóa logic đúng vẫn cần query và hạ tầng có khả năng thực thi:

| Khía cạnh | Điều cần xác nhận |
| --- | --- |
| Loại scrolling | Offset hay keyset thực sự được dùng |
| Nguồn query | Derived query, query chuỗi, native query hoặc API riêng có hỗ trợ hay không |
| Chiều | Forward, backward và cách chuẩn hóa thứ tự đầu ra |
| Mapping | Có đủ khóa, đúng kiểu và non-null theo yêu cầu |
| Chỉ mục | Predicate và sort có thể được hỗ trợ hiệu quả không |
| Tài nguyên | Kích thước cửa sổ, materialization và transaction |

Không suy rằng query có keyset luôn rẻ. Store vẫn có thể phải xử lý filter, sort hoặc join tốn kém nếu query shape và chỉ mục không phù hợp.

Ngược lại, việc dùng `Window` với offset không tự có cùng lợi ích truy cập như keyset. Commons mô tả hợp đồng kết quả và vị trí, còn thuật toán thực tế phải được xác nhận ở module.

Ví dụ JPA trong bài không tự áp dụng nguyên vẹn sang MongoDB, JDBC, R2DBC hoặc một hệ tìm kiếm. Các API reactive/coroutine cũng cần kiểm tra hình dạng kết quả và vòng đời tiêu thụ theo module; không chỉ đổi wrapper Java.

## 16. Kiểm thử thứ tự, khóa và hai chiều

### 16.1. Dữ liệu phải tạo tie qua ranh giới cửa sổ

Dùng tập ở phần 3 với size ba giúp xác nhận:

```text
Tiến: 108,107,106 -> 105,104,103 -> 102,101
Lùi từ cửa sổ cuối: 102,101 -> 105,104,103
```

Không chỉ tạo timestamp khác nhau; nếu không có tie, cursor thiếu id vẫn có thể vượt qua toàn bộ test.

### 16.2. Kiểm tra sequence, không chỉ tập hợp

Cần assert thứ tự nội dung của từng window và chuỗi ghép trên dữ liệu không đổi. Một phép so sánh Set bỏ qua đúng thông tin bài toán cần chứng minh.

Nếu id do store cấp, expected result phải dùng định danh thật của fixture. Không ép id của ví dụ lý thuyết thành một giả định về thuật toán sinh id của backend.

### 16.3. Các trường hợp biên quan trọng

| Trường hợp | Điều cần chứng minh |
| --- | --- |
| Vị trí ban đầu | Không bỏ phần tử đầu, không dùng một mốc giả |
| Tiếp tục từ cuối window | Không lặp mốc và không bỏ phần còn lại của nhóm tie |
| Window rỗng | Không gọi `positionAt(-1)` |
| Cửa sổ cuối ngắn | Dừng đúng sau phần tử cuối |
| Tổng vừa đủ một bội của size | Không suy còn dữ liệu chỉ vì nội dung đủ size |
| Sort hỗn hợp ASC/DESC | Mỗi khóa dùng đúng dấu khi tiếp tục |
| Lùi từ cửa sổ thứ ba | Nhận cửa sổ liền kề, không nhảy về phần đầu của toàn miền trước |
| Projection | Có đủ khóa để tạo vị trí |
| Token khác filter hoặc sort | Được xử lý theo chính sách khởi đầu/kiểm tra hợp đồng |
| Dữ liệu thay đổi | Hành vi phù hợp mức nhất quán đã công bố |

Nếu kiểm tra N + 1, cần xác nhận phần tử dư không bị dùng làm biên đã xử lý. Nếu module đã chuẩn hóa nội dung backward, kiểm tra adapter không đảo lần nữa.

Kiểm tra repository thật chứng minh query/mapping/position được module giải quyết. Mock có thể phục vụ kiểm tra chính sách API nhưng không chứng minh store thực hiện đúng keyset hoặc hỗ trợ backward.

## 17. Lỗi thường gặp và hướng chỉnh

| Biểu hiện | Nguyên nhân có thể có | Hướng điều chỉnh |
| --- | --- | --- |
| Bỏ các đơn cùng timestamp với mốc cuối | Cursor hoặc predicate chỉ có thời gian | Dùng đủ bộ khóa phân định |
| Lặp entity ở đầu cửa sổ tiếp theo | Dùng điều kiện bao gồm mốc đã đọc | Giữ ngữ nghĩa exclusive phù hợp |
| Mixed sort cho kết quả sai | Đảo tất cả dấu theo một hướng duy nhất | Xây so sánh theo hướng từng Order |
| Duyệt lùi bị lặp một phần cửa sổ hiện tại | Dùng mốc cuối thay vì mốc đầu phù hợp | Chọn anchor cùng chiều duyệt |
| Duyệt lùi nhảy về cửa sổ đầu | Chọn đầu của toàn miền trước theo sort chuẩn | Lấy phần gần mốc bằng thuật toán ngược đúng |
| Backward trả nội dung đảo không mong muốn | Adapter đảo thêm sau khi module đã chuẩn hóa | Xác nhận hợp đồng thứ tự đầu ra |
| Bỏ một entity chưa hiển thị | Dùng phần tử dư N + 1 làm cursor | Lấy mốc từ nội dung đã công bố |
| Không tạo được keyset | Thiếu khóa, null hoặc mapping không phù hợp | Đối chiếu projection và điều kiện module |
| Token đúng định dạng nhưng sai kết quả | Đổi filter, tenant, sort hoặc kiểu khóa | Giữ và kiểm tra ngữ cảnh traversal |

## 18. Bài tập phân tích

### Bài 1: Cursor chỉ có timestamp

Window đầu là `108, 107, 106`, mốc thời gian cuối là `10:00`. Query sau dùng `createdAt < 10:00`.

**Phân tích:** `105` và `104` cùng thời điểm bị bỏ. Cần bộ khóa `(createdAt, id)` và nhánh so sánh id khi thời gian bằng nhau.

### Bài 2: Forward trong thứ tự giảm dần

Danh sách mới nhất trước dùng `createdAt DESC, id DESC`. Duyệt tiến cần tăng hay giảm giá trị khóa?

**Phân tích:** phần sau mốc có thời gian nhỏ hơn, hoặc cùng thời gian và id nhỏ hơn. Forward là chiều đi trong thứ tự chuẩn, không phải tăng giá trị số.

### Bài 3: Mixed sort

Sort đổi thành `createdAt DESC, id ASC`.

**Gợi ý:** điều kiện tiến là `createdAt < T OR (createdAt = T AND id > I)`. Không dùng lại nhánh `id < I` của ví dụ hai khóa giảm dần.

### Bài 4: Cửa sổ trước gần nhất

Đang ở `102, 101`, phần trước mốc có sáu entity. Nếu sort DESC rồi lấy ba phần tử đầu, có nhận được cửa sổ liền kề không?

**Phân tích:** không; sẽ nhận `108, 107, 106`. Cần lấy gần mốc theo chiều ngược rồi chuẩn hóa thứ tự để nhận `105, 104, 103`, hoặc dùng cơ chế backward đã được module hỗ trợ và kiểm chứng.

### Bài 5: Đi lùi có trả đúng lịch sử không?

Một entity đổi thời điểm sort sau khi caller đi tới cửa sổ tiếp theo rồi quay lại.

**Phân tích:** cursor và thứ tự đầy đủ không tự giữ lịch sử cũ. Nếu sản phẩm cần quay lại đúng nội dung đã thấy, cần thêm một cơ chế phù hợp thay vì hứa snapshot từ keyset đơn thuần.

## 19. Các điểm cần nhớ

- Scrolling cần một thứ tự đầy đủ, mốc đủ khóa và chiều duyệt rõ ràng; timestamp riêng lẻ thường không đủ.
- ASC/DESC là hướng của từng khóa, còn forward/backward là quan hệ trước/sau mốc trong thứ tự chuẩn.
- Duyệt tiến thường dùng biên cuối, duyệt lùi dùng biên đầu; chọn miền trước còn cần lấy đúng phần gần mốc.
- Cursor phải dựa trên nội dung đã trả, giữ kiểu và độ chính xác, không dùng phần tử dư để bỏ qua dữ liệu chưa đọc.
- Projection, null, collation, đơn vị kết quả và khả năng module quyết định bộ khóa có dùng được hay không.
- Thứ tự ổn định và keyset không tự tạo snapshot; sự thay đổi dữ liệu và chính sách tiếp tục phải được thiết kế riêng.
