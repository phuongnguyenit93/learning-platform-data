# Vấn đề ABA khi trạng thái quay lại giá trị cũ

Khóa lạc quan (optimistic locking) thường cho phép nhiều người đọc cùng một bản ghi mà không khóa nó trong suốt thời gian xử lý. Khi ghi, ứng dụng kiểm tra dữ liệu hiện tại có còn đúng với phiên bản mà nó đã đọc hay không. Nếu bản ghi đã thay đổi, thao tác cập nhật bị từ chối để tránh ghi đè một thay đổi mới hơn.

Một lỗi tinh vi xuất hiện khi ứng dụng chỉ so sánh giá trị nghiệp vụ hiện tại. Giá trị có thể thay đổi từ A sang B rồi quay lại A. Một transaction cũ đọc A sẽ thấy A ở thời điểm ghi và tưởng rằng dữ liệu chưa thay đổi, dù ở giữa đã có hai lần chuyển trạng thái. Đây là vấn đề ABA.

Giải pháp phổ biến là kiểm tra một token phiên bản thay đổi sau mỗi lần cập nhật, thay vì chỉ so sánh giá trị hiện tại. Khi trạng thái đi từ A → B → A, token vẫn tiến từ 7 → 8 → 9. Một thao tác cũ mang token 7 không thể ghi lên phiên bản 9, dù giá trị nghiệp vụ lại bằng A.

## 1. Khóa lạc quan và kiểm tra phiên bản

Giả sử một đơn hàng có trạng thái `PENDING`. Hai nhân viên cùng mở trang chi tiết và đọc bản ghi ở phiên bản hiện tại. Cả hai có thể xử lý độc lập trong ứng dụng; đến khi lưu, mỗi thao tác cần xác nhận bản ghi chưa bị người khác thay đổi.

Một cách triển khai khóa lạc quan dùng cột `version`:

```sql
CREATE TABLE orders (
    order_id BIGINT PRIMARY KEY,
    status VARCHAR(30) NOT NULL,
    version BIGINT NOT NULL DEFAULT 0
);
```

Khi đọc, ứng dụng lấy cả giá trị và phiên bản:

```sql
SELECT order_id, status, version
FROM orders
WHERE order_id = :order_id;
```

Khi cập nhật, ứng dụng dùng phiên bản đã đọc làm điều kiện:

```sql
UPDATE orders
SET status = :new_status,
    version = version + 1
WHERE order_id = :order_id
  AND version = :expected_version;
```

Nếu số hàng bị ảnh hưởng là 1, thao tác đã cập nhật đúng phiên bản mà nó dựa vào. Nếu số hàng bị ảnh hưởng là 0, bản ghi có thể đã bị xóa hoặc phiên bản đã thay đổi; ứng dụng phải đọc lại và xử lý xung đột theo nghiệp vụ.

Điều kiện `version = :expected_version` là một phép so sánh và cập nhật nguyên tử tại cơ sở dữ liệu. Nó thường được gọi là compare-and-swap (CAS) ở mức khái niệm: chỉ thay đổi khi giá trị hiện tại vẫn khớp với token mà người gọi kỳ vọng.

## 2. ABA xảy ra như thế nào?

Giả sử một đơn hàng có trạng thái `READY` và phiên bản 7. Nhân viên A đọc bản ghi để chuẩn bị giao hàng. Trong lúc đó, một tiến trình khác thay đổi trạng thái sang `CANCELLED`, sau đó đơn hàng được khôi phục về `READY`.

Lịch thay đổi:

| Thời điểm | Tác nhân | Trạng thái | Phiên bản |
|---|---|---|---:|
| T0 | A đọc đơn hàng | `READY` | 7 |
| T1 | B hủy đơn | `CANCELLED` | 8 |
| T2 | C khôi phục đơn | `READY` | 9 |
| T3 | A gửi cập nhật dựa trên dữ liệu đã đọc ở T0 | `READY` | 9 |

Nếu A chỉ kiểm tra `status = 'READY'`, điều kiện vẫn đúng tại T3. A có thể ghi một quyết định được đưa ra trước khi đơn hàng bị hủy và khôi phục. Ứng dụng đã bỏ lỡ lịch sử chuyển trạng thái ở giữa.

Đó là chuỗi:

```text
A  →  B  →  A
READY  CANCELLED  READY
```

Giá trị cuối bằng giá trị ban đầu, nhưng bản ghi không còn ở cùng một trạng thái lịch sử. Nếu nghiệp vụ quan tâm đến việc “bản ghi có bị thay đổi kể từ lúc đọc hay không”, so sánh giá trị hiện tại không đủ.

### Cách kiểm tra chỉ bằng giá trị bị lỗi

Ví dụ, câu lệnh sau có thể chấp nhận cập nhật cũ:

```sql
UPDATE orders
SET status = 'SHIPPED'
WHERE order_id = :order_id
  AND status = 'READY';
```

Điều kiện chỉ xác nhận trạng thái hiện tại là `READY`. Nó không xác nhận trạng thái đó vẫn là lần `READY` mà nhân viên A đã đọc. Sau chuỗi `READY → CANCELLED → READY`, điều kiện vẫn khớp.

### Cách kiểm tra bằng phiên bản

Nếu A đã đọc phiên bản 7, câu lệnh phải dùng cả trạng thái kỳ vọng và phiên bản:

```sql
UPDATE orders
SET status = 'SHIPPED',
    version = version + 1
WHERE order_id = :order_id
  AND status = 'READY'
  AND version = 7;
```

Sau khi B và C thay đổi bản ghi, phiên bản hiện tại là 9. Câu lệnh của A không cập nhật hàng nào vì `version = 7` không còn đúng. Ứng dụng biết thao tác dựa trên dữ liệu cũ và có thể tải lại đơn hàng để quyết định bước tiếp theo.

## 3. Vì sao phiên bản phát hiện được ABA?

Giá trị nghiệp vụ mô tả trạng thái hiện tại. Version token mô tả thế hệ hoặc lần sửa của bản ghi. Hai trạng thái có thể có cùng giá trị nghiệp vụ nhưng khác phiên bản.

| Thông tin | Trước khi đổi | Sau A → B → A |
|---|---|---|
| `status` | `READY` | `READY` |
| `version` | 7 | 9 |
| So sánh status | Khớp | Vẫn khớp |
| So sánh version | Khớp với 7 | Không khớp với 7 |

Điều kiện quan trọng là version phải thay đổi mỗi khi có thay đổi thuộc phạm vi mà optimistic locking cần phát hiện. Nếu một đường ghi cập nhật `status` nhưng không tăng `version`, token không còn phản ánh đầy đủ lịch sử thay đổi và ABA có thể quay lại.

Version thường là số nguyên tăng đơn điệu trong vòng đời bản ghi. Ứng dụng không được tự đặt lại về giá trị cũ, tái sử dụng token đã dùng hoặc bỏ qua tăng version ở một số đường cập nhật. Nếu cần thay thế một bản ghi bằng một thực thể mới cùng ID, cần xem xét thêm generation/identity token để phân biệt hai vòng đời.

## 4. Một ví dụ với số lượng tồn kho

ABA không chỉ xảy ra với cột trạng thái. Bất kỳ giá trị nào có thể quay lại giá trị cũ đều có thể gây ra vấn đề.

Giả sử một màn hình quản trị đọc số lượng tồn kho là 10. Trong khi người quản trị đang xem, hệ thống xử lý đơn hàng và hoàn kho:

```text
available_quantity = 10
        |
        | Đơn hàng được xác nhận
        v
available_quantity = 8
        |
        | Đơn hàng bị hủy, hàng được hoàn lại
        v
available_quantity = 10
```

Người quản trị cũ vẫn thấy giá trị 10 khi lưu và có thể nghĩ dữ liệu chưa thay đổi. Nhưng giữa hai lần đọc đã có một đơn hàng được xử lý và hoàn lại; các tác động phụ như lịch sử giao dịch, reservation, báo cáo hoặc sự kiện kho có thể đã thay đổi.

Nếu nghiệp vụ yêu cầu phát hiện mọi cập nhật kể từ lần đọc, hãy dùng version:

```sql
UPDATE inventory
SET available_quantity = :new_quantity,
    version = version + 1
WHERE product_id = :product_id
  AND version = :expected_version;
```

Version giúp phát hiện chuỗi thay đổi ngay cả khi `available_quantity` quay lại 10. Với thao tác trừ tồn kho đơn giản, cập nhật nguyên tử có điều kiện vẫn là cách bảo vệ invariant `available_quantity >= 0`; version giải quyết một yêu cầu khác là phát hiện dữ liệu đã thay đổi kể từ khi người dùng hoặc transaction đọc.

## 5. Những dạng token nào có thể dùng?

### 5.1. Số phiên bản tăng dần

Đây là cách phổ biến và dễ kiểm tra:

```sql
UPDATE document
SET body = :new_body,
    version = version + 1
WHERE document_id = :id
  AND version = :expected_version;
```

Ưu điểm là dễ so sánh, không phụ thuộc đồng hồ và thể hiện rõ mỗi lần sửa. Cần chọn kiểu dữ liệu đủ lớn và bảo đảm không reset hoặc tràn số trong vòng đời có thể quan sát.

### 5.2. Row version do hệ quản trị quản lý

Một số hệ quản trị cung cấp kiểu hoặc token đại diện cho phiên bản hàng. Ví dụ, SQL Server có kiểu `rowversion`, tự tạo giá trị nhị phân mới khi hàng được cập nhật. Ứng dụng có thể đọc token rồi dùng nó trong điều kiện `WHERE` khi cập nhật.

Token do hệ quản trị tạo giảm nguy cơ ứng dụng quên tăng version, nhưng phạm vi và ngữ nghĩa phụ thuộc sản phẩm. Cần hiểu token thay đổi khi nào, có dùng được giữa các bảng hay không, và cách ORM ánh xạ token đó.

### 5.3. Timestamp hoặc `updated_at`

Dùng thời điểm cập nhật làm token có vẻ thuận tiện, nhưng timestamp không luôn đủ tin cậy:

- Độ chính xác có thể thấp hơn tốc độ cập nhật, khiến hai thay đổi có cùng timestamp.
- Đồng hồ hệ thống có thể lệch hoặc bị điều chỉnh.
- Một số ứng dụng tự gán lại timestamp hoặc chỉ cập nhật nó ở một số đường ghi.
- Hai giá trị thời gian bằng nhau không chứng minh rằng không có thay đổi ở giữa.

Timestamp có thể hữu ích cho hiển thị hoặc audit, nhưng không nên tự động coi nó là version token an toàn nếu chưa chứng minh được độ duy nhất và quy tắc cập nhật.

### 5.4. Hash của nội dung

Hash giúp nhận diện nội dung hiện tại. Tuy nhiên, nếu nội dung đổi A → B → A, hash cũng quay lại giá trị ban đầu. Hash chỉ kiểm tra sự bằng nhau của nội dung, không ghi nhận rằng một thay đổi đã xảy ra. Vì vậy, hash nội dung đơn thuần không giải quyết ABA khi yêu cầu là phát hiện mọi lần sửa.

### 5.5. UUID hoặc generation token

Một token ngẫu nhiên mới có thể được sinh sau mỗi lần cập nhật. Nếu token không bị tái sử dụng, nó cũng có thể phân biệt các thế hệ. Cách này hữu ích khi cần token khó đoán hoặc khi bản ghi có vòng đời xóa rồi tạo lại. Đổi lại, cần bảo đảm mọi đường ghi thay token đúng cách và xử lý việc sinh token trong transaction.

## 6. Xóa rồi tạo lại cùng một ID cũng có thể tạo ABA

Giả sử ứng dụng dùng `order_id = 500` để nhận diện đơn hàng. Một client đọc đơn hàng 500, sau đó đơn hàng bị xóa. Một đơn hàng mới được tạo với cùng ID và trạng thái ban đầu giống hệt.

Nếu client chỉ kiểm tra `order_id` và `status`, nó có thể cập nhật nhầm thực thể mới bằng dữ liệu được đọc từ vòng đời cũ. Đây là một dạng ABA về danh tính: ID và giá trị có vẻ giống nhau, nhưng thực thể đã bị thay thế.

Có thể xử lý bằng một trong các cách:

- Không tái sử dụng ID đã cấp.
- Dùng một generation token hoặc UUID riêng cho mỗi vòng đời thực thể.
- Dùng cặp `(id, generation)` làm danh tính logic và điều kiện cập nhật.
- Dùng version được khởi tạo từ một nguồn không tái sử dụng khi tạo lại bản ghi.

Ví dụ:

```sql
UPDATE orders
SET status = :new_status,
    version = version + 1
WHERE order_id = :id
  AND generation_id = :expected_generation
  AND version = :expected_version;
```

Điều kiện `generation_id` ngăn một client cũ ghi lên thực thể mới có cùng ID. Version tiếp tục phát hiện các thay đổi trong cùng vòng đời.

## 7. Các đường ghi phải cùng tuân thủ version

Một cột version chỉ có tác dụng nếu mọi thay đổi thuộc phạm vi bảo vệ đều cập nhật token. Các đường ghi dễ bị bỏ sót gồm:

- SQL trực tiếp từ một tác vụ nền.
- Bulk update hoặc bulk delete qua ORM.
- Stored procedure.
- Trigger hoặc tác vụ đồng bộ dữ liệu.
- Script quản trị hoặc migration sửa dữ liệu.
- Một service khác ghi cùng bảng.

Ví dụ, câu lệnh sau thay đổi trạng thái nhưng không tăng version:

```sql
UPDATE orders
SET status = 'CANCELLED'
WHERE order_id = :id;
```

Nếu hệ thống đang dựa vào version 7 để phát hiện thay đổi, câu lệnh này có thể khiến token vẫn là 7. Một client cũ mang version 7 sẽ không nhận ra trạng thái đã bị thay đổi.

Hãy thống nhất cách cập nhật token ở một nơi có thể kiểm soát: câu lệnh cập nhật chuẩn của repository, cơ chế ORM, stored procedure dùng chung hoặc trigger được thiết kế cẩn thận. Nếu dùng trigger, cần bảo đảm ứng dụng nhận được version mới sau cập nhật và không tăng version hai lần ngoài ý muốn.

Với ORM, optimistic locking thường được hỗ trợ qua thuộc tính version hoặc annotation tương ứng. Tuy nhiên, bulk JPQL/SQL và native query có thể bỏ qua cơ chế kiểm tra phiên bản tự động hoặc không đồng bộ persistence context. Cần đọc tài liệu framework, kiểm tra câu SQL thực tế và viết test cho từng đường cập nhật.

## 8. ABA và cập nhật nhiều hàng

Version trên một hàng chỉ phát hiện thay đổi của hàng đó. Nó không tự phát hiện mọi thay đổi trong một quy tắc nghiệp vụ phụ thuộc nhiều hàng.

Ví dụ, một transaction đọc trạng thái hai bác sĩ trực, rồi cập nhật một hàng. Transaction khác đọc cùng dữ liệu và cập nhật hàng còn lại. Nếu mỗi hàng có version riêng, mỗi transaction vẫn có thể cập nhật hàng mà nó chưa thấy thay đổi. Invariant “luôn có ít nhất một bác sĩ trực” vẫn có thể bị write skew.

Trong trường hợp này, cần thêm cơ chế bảo vệ invariant tổng hợp:

- Một version/guard row chung mà mọi transaction liên quan phải cập nhật hoặc khóa.
- Một constraint có thể biểu diễn quy tắc.
- Serializable hoặc cơ chế phát hiện phụ thuộc đọc–ghi tương đương.
- Một thao tác cập nhật nguyên tử trên hàng tổng hợp đại diện cho tài nguyên.

Không nên nhầm optimistic locking trên từng hàng với khả tuần tự của toàn bộ transaction. Token phiên bản giải quyết xung đột trên phạm vi mà token đại diện; invariant nhiều hàng cần một phạm vi phối hợp đủ rộng.

## 9. Xử lý khi compare-and-swap không cập nhật hàng nào

Khi câu lệnh cập nhật có điều kiện version trả về số hàng bị ảnh hưởng bằng 0, ứng dụng phải xác định nguyên nhân phù hợp:

1. Bản ghi không còn tồn tại.
2. Bản ghi đã được cập nhật bởi transaction khác.
3. Generation token không còn khớp vì bản ghi đã được thay thế.
4. Điều kiện nghiệp vụ như trạng thái hiện tại không còn đúng.

Không nên tự động gửi lại cùng câu lệnh với version mới mà vẫn giữ nguyên quyết định cũ. Làm như vậy có thể biến kiểm tra xung đột thành thao tác ghi đè mù. Quy trình đúng thường là tải lại bản ghi, hiển thị khác biệt hoặc đánh giá lại điều kiện nghiệp vụ, rồi yêu cầu người dùng xác nhận hay thực hiện một quyết định mới.

Ví dụ, nếu nhân viên A muốn chuyển đơn sang `SHIPPED` nhưng đơn đã bị hủy rồi khôi phục, việc tải lại phiên bản mới không có nghĩa là thao tác giao hàng cũ tự động hợp lệ. Ứng dụng phải kiểm tra quy tắc chuyển trạng thái hiện tại và quyền của người thực hiện.

Nếu nghiệp vụ cho phép retry tự động, hãy chạy lại toàn bộ transaction với dữ liệu mới, giới hạn số lần thử và bảo đảm tác dụng phụ bên ngoài không bị lặp. Nếu xung đột cần người dùng giải quyết, trả về một kết quả conflict rõ ràng.

## 10. Các nguyên tắc thiết kế version token an toàn

- Version thay đổi trong cùng transaction với thay đổi dữ liệu nghiệp vụ.
- Mọi đường ghi thuộc phạm vi optimistic locking đều phải tăng hoặc thay token.
- Không đặt lại version về giá trị cũ trong cùng vòng đời bản ghi.
- Chọn kiểu dữ liệu đủ lớn để tránh tràn hoặc tái sử dụng token.
- Dùng generation token khi ID có thể được tái sử dụng cho một thực thể mới.
- Không mặc định timestamp hoặc hash nội dung là token chống ABA.
- Kiểm tra số hàng bị ảnh hưởng của câu `UPDATE` có điều kiện.
- Khi conflict, tải lại và đánh giá lại nghiệp vụ; không retry mù với quyết định cũ.
- Bảo vệ invariant nhiều hàng bằng cơ chế phối hợp ở phạm vi nhiều hàng.

## 11. Cách kiểm thử vấn đề ABA

Một bài kiểm thử cần tạo đúng chuỗi thay đổi và giữ lại token cũ:

1. Tạo đơn hàng ở trạng thái `READY`, version 7.
2. Transaction hoặc client A đọc `READY`, version 7 và tạm dừng.
3. Client B đổi trạng thái thành `CANCELLED`, tăng version lên 8 và commit.
4. Client C khôi phục trạng thái `READY`, tăng version lên 9 và commit.
5. Client A thử cập nhật dựa trên trạng thái `READY` và version 7.
6. Xác nhận câu lệnh so sánh chỉ bằng status có thể khớp, còn câu lệnh so sánh version phải cập nhật 0 hàng.
7. Xác nhận ứng dụng trả conflict hoặc tải lại để đánh giá lại trạng thái.

Pseudocode kiểm thử:

```text
initial = createOrder(status = READY, version = 7)

staleView = clientA.read(initial.id)       // READY, 7

clientB.update(READY -> CANCELLED)         // version 8
clientC.update(CANCELLED -> READY)         // version 9

affected = clientA.compareAndSwap(
    id = initial.id,
    expectedVersion = staleView.version,
    newStatus = SHIPPED
)

assert affected == 0
assert database.status == READY
assert database.version == 9
```

Kiểm thử bổ sung nên bao gồm bulk update, đường ghi từ background job, xóa rồi tạo lại cùng ID, version gần giới hạn kiểu dữ liệu và hai client cùng cập nhật từ một version. Chỉ thử trường hợp hai client ghi cùng một hàng một lần không chứng minh hệ thống đã xử lý ABA.

## 12. Checklist trước khi dùng optimistic locking

- [ ] Ứng dụng lưu cả giá trị nghiệp vụ và version/generation token khi đọc.
- [ ] Câu lệnh ghi kiểm tra token đã đọc và cập nhật token trong cùng thao tác nguyên tử.
- [ ] Chuỗi A → B → A vẫn làm token thay đổi.
- [ ] Không có đường ghi nào âm thầm thay đổi dữ liệu mà bỏ qua token.
- [ ] Bulk update, native SQL, stored procedure và background job đã được xem xét.
- [ ] ID tái sử dụng có generation token hoặc chính sách không tái sử dụng ID.
- [ ] Ứng dụng kiểm tra số hàng bị ảnh hưởng và xử lý conflict rõ ràng.
- [ ] Retry tải lại và đánh giá lại nghiệp vụ thay vì gửi lại mù quyết định cũ.
- [ ] Invariant nhiều hàng có cơ chế bảo vệ ở phạm vi phù hợp.
- [ ] Đã có kiểm thử ABA với hai hoặc nhiều client/transaction chạy chồng lấp.

ABA nhắc chúng ta rằng hai trạng thái có giá trị bằng nhau không nhất thiết là cùng một phiên bản dữ liệu. Khóa lạc quan cần kiểm tra lịch sử thay đổi thông qua version hoặc generation token, chứ không chỉ so sánh trạng thái hiện tại. Khi token được cập nhật nhất quán trên mọi đường ghi và ứng dụng xử lý conflict bằng cách đánh giá lại nghiệp vụ, một thay đổi quay về giá trị cũ sẽ không thể đánh lừa thao tác ghi đang dùng dữ liệu lỗi thời.
