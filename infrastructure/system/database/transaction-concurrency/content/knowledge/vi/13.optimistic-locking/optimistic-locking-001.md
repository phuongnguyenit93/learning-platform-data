# Cơ chế so sánh phiên bản khi cập nhật dữ liệu

Trong mô hình khóa lạc quan (*optimistic locking*), ứng dụng giả định rằng xung đột ghi không xảy ra thường xuyên. Giao dịch có thể đọc dữ liệu mà không giữ khóa ghi trong suốt thời gian người dùng hoặc chương trình xử lý. Khi cập nhật, nó kiểm tra xem dữ liệu có còn ở phiên bản mà mình đã đọc hay không.

Cách phổ biến là thêm một cột phiên bản (*version column*) vào mỗi hàng. Khi đọc, ứng dụng lưu lại giá trị phiên bản. Khi ghi, câu lệnh `UPDATE` chỉ thành công nếu phiên bản trong cơ sở dữ liệu vẫn bằng giá trị đã đọc. Nếu một giao dịch khác đã cập nhật hàng và tăng phiên bản, điều kiện so sánh không còn đúng; câu lệnh cập nhật không tác động hàng nào và ứng dụng nhận biết được xung đột.

Đây là một phép **so sánh rồi cập nhật nguyên tử** (*compare-and-update*), thường được triển khai bằng câu lệnh SQL có điều kiện `WHERE version = ?`. Nó giúp ngăn một bản cập nhật dựa trên dữ liệu cũ ghi đè âm thầm một bản cập nhật mới hơn.

## 1. Vì sao cần so sánh phiên bản?

Giả sử một sản phẩm có giá 100 và phiên bản 7. Hai nhân viên cùng mở màn hình chỉnh sửa sản phẩm. Cả hai đều đọc giá 100, phiên bản 7.

- Nhân viên A đổi giá thành 110 và lưu trước.
- Nhân viên B đổi giá thành 95 dựa trên dữ liệu đã đọc trước đó và lưu sau.

Nếu câu lệnh cập nhật của B chỉ ghi theo `id`, nó có thể ghi đè giá 110 bằng giá 95. Hệ thống không nhận ra rằng B đang lưu từ một bản dữ liệu cũ. Đây là tình huống **ghi đè mất cập nhật** (*lost update*).

Với kiểm tra phiên bản, lần cập nhật của A tăng phiên bản từ 7 lên 8. Khi B gửi yêu cầu cập nhật với phiên bản 7, điều kiện phiên bản không còn khớp. B nhận được thông báo xung đột và có thể tải lại dữ liệu mới trước khi quyết định tiếp tục.

## 2. Thiết kế cột phiên bản

Một bảng có thể lưu số phiên bản bằng kiểu số nguyên tăng dần:

```sql
CREATE TABLE products (
    product_id BIGINT PRIMARY KEY,
    name       VARCHAR(200) NOT NULL,
    price      DECIMAL(12, 2) NOT NULL,
    version    BIGINT NOT NULL DEFAULT 0
);
```

Mỗi hàng bắt đầu với một phiên bản. Khi một cập nhật có ý nghĩa đối với dữ liệu được bảo vệ thành công, phiên bản phải tăng lên.

Ví dụ dữ liệu ban đầu:

| product_id | name | price | version |
|---:|---|---:|---:|
| 42 | Bàn phím | 100.00 | 7 |

Ứng dụng đọc hàng và lưu cả dữ liệu lẫn phiên bản:

```sql
SELECT product_id, name, price, version
FROM products
WHERE product_id = 42;
```

Ứng dụng nhận `price = 100.00` và `version = 7`. Khi người dùng sửa giá, ứng dụng gửi lại phiên bản 7 như một điều kiện xác nhận rằng thay đổi được tạo ra từ bản dữ liệu đó.

`version` nên là một giá trị đáng tin cậy do cơ sở dữ liệu hoặc tầng ghi quản lý. Không để ứng dụng tùy ý đặt lại phiên bản về một giá trị cũ, vì điều đó có thể làm một bản cập nhật lỗi thời vượt qua phép so sánh.

## 3. Câu lệnh cập nhật có điều kiện phiên bản

Câu lệnh cập nhật dùng cả khóa chính và phiên bản đã đọc:

```sql
UPDATE products
SET price = 110.00,
    version = version + 1
WHERE product_id = 42
  AND version = 7;
```

Hai phần của câu lệnh có vai trò khác nhau:

- `product_id = 42` xác định hàng cần cập nhật.
- `version = 7` xác nhận hàng vẫn ở phiên bản mà ứng dụng đã đọc.
- `version = version + 1` chuyển hàng sang phiên bản mới ngay trong cùng câu lệnh cập nhật.

Việc so sánh và tăng phiên bản diễn ra trong cùng một thao tác SQL. Hai giao dịch không thể cùng thành công dựa trên một phiên bản cũ của cùng một hàng theo cách thông thường: giao dịch đầu tiên cập nhật thành công sẽ làm điều kiện phiên bản của giao dịch sau không còn đúng.

Ứng dụng phải kiểm tra số hàng bị ảnh hưởng (*affected row count*):

| Số hàng bị ảnh hưởng | Ý nghĩa |
|---:|---|
| `1` | Hàng tồn tại và phiên bản khớp; cập nhật đã thành công |
| `0` | Không có hàng nào thỏa cả khóa chính và phiên bản; hàng có thể đã bị xóa hoặc phiên bản đã thay đổi |

Một kết quả `0` thường được xử lý như xung đột lạc quan hoặc dữ liệu không còn tồn tại. Nếu nghiệp vụ cần phân biệt hai trường hợp, ứng dụng có thể đọc lại để kiểm tra, nhưng cần lưu ý trạng thái vẫn có thể thay đổi lần nữa sau lần đọc đó. Không được coi `0` là cập nhật thành công.

## 4. Hai giao dịch cùng cập nhật một phiên bản

Giả sử `T1` và `T2` cùng đọc sản phẩm `42` ở phiên bản 7:

| Thời điểm | Giao dịch T1 | Giao dịch T2 | Trạng thái hàng |
|---|---|---|---|
| 1 | Đọc giá 100, phiên bản 7 | | Giá 100, version 7 |
| 2 | | Đọc giá 100, phiên bản 7 | Giá 100, version 7 |
| 3 | Cập nhật với `WHERE version = 7`, thành công | | Giá mới của T1, version 8 |
| 4 | | Cập nhật với `WHERE version = 7`, không có hàng khớp | Giá mới của T1, version 8 |
| 5 | Commit | Nhận biết xung đột và xử lý | Giá mới của T1 vẫn được giữ |

Diễn biến có thể biểu diễn như sau:

```text
T1: đọc version 7 ── UPDATE ... WHERE version = 7 ──► thành công, version 8

T2: đọc version 7 ───────────────── UPDATE ... WHERE version = 7
                                      │
                                      └─ 0 hàng bị ảnh hưởng: xung đột
```

T2 không ghi đè giá trị mà T1 đã lưu. Hệ thống đã chuyển một cập nhật có nguy cơ làm mất dữ liệu thành một xung đột có thể nhận biết và xử lý.

## 5. Quy trình xử lý xung đột ở tầng ứng dụng

Khi câu lệnh cập nhật không tác động hàng nào, ứng dụng cần quyết định bước tiếp theo dựa trên nghiệp vụ. Một quy trình thông dụng gồm:

1. Đọc dữ liệu cùng phiên bản hiện tại.
2. Cho người dùng hoặc logic nghiệp vụ thực hiện thay đổi trên dữ liệu đó.
3. Gửi `UPDATE` với khóa chính và phiên bản đã đọc; đồng thời tăng phiên bản.
4. Kiểm tra số hàng bị ảnh hưởng.
5. Nếu cập nhật thành công, tiếp tục commit giao dịch.
6. Nếu không có hàng khớp, tải lại dữ liệu và thông báo xung đột; sau đó yêu cầu quyết định mới hoặc áp dụng quy tắc hợp nhất đã được nghiệp vụ chấp thuận.

Ví dụ mã giả:

```text
current = loadProduct(productId)
edited = applyUserChanges(current)

affected = updateProduct(
    productId = current.id,
    expectedVersion = current.version,
    newPrice = edited.price,
    incrementVersion = true
)

if affected == 1:
    reportSuccess()
else:
    latest = loadProduct(productId)
    reportConflict(latest)
```

Không nên tự động gửi lại nguyên trạng giá trị cũ với phiên bản mới mà không đọc và đánh giá lại dữ liệu. Làm như vậy chỉ thay điều kiện phiên bản để ghi đè được dữ liệu mới; nguy cơ mất cập nhật vẫn còn, chỉ bị trì hoãn.

Nếu thay đổi là phép biến đổi có thể áp dụng an toàn lên giá trị mới, ứng dụng có thể tính lại trên phiên bản mới. Ví dụ, yêu cầu “tăng số lượng thêm 2” có thể được diễn đạt thành phép cập nhật nguyên tử `quantity = quantity + 2` nếu quy tắc nghiệp vụ cho phép. Nhưng yêu cầu “đặt số lượng thành 10 dựa trên số lượng 8 đã đọc” cần được xem xét lại khi số lượng hiện tại đã đổi.

## 6. So sánh phiên bản với kiểm tra giá trị cũ

Một cách khác là đưa giá trị cũ vào điều kiện `WHERE`:

```sql
UPDATE products
SET price = 110.00
WHERE product_id = 42
  AND price = 100.00;
```

Đây cũng là một dạng so sánh trước khi cập nhật. Tuy nhiên, dùng cột phiên bản thường rõ ràng và đáng tin cậy hơn:

- Giá trị nghiệp vụ có thể thay đổi rồi trở lại giá trị cũ. Khi đó, phép so sánh giá trị có thể không phát hiện được mọi lần cập nhật trung gian (*ABA problem*).
- So sánh tất cả cột cần bảo vệ làm câu lệnh dài và dễ bỏ sót cột.
- Giá trị số thực, chuẩn hóa chuỗi, `NULL` hoặc độ chính xác thời gian có thể khiến so sánh giá trị cũ phức tạp.
- Một cột phiên bản tăng đơn điệu thể hiện rõ rằng hàng đã trải qua một lần cập nhật được quản lý.

Nếu dùng so sánh giá trị cũ, cần xây dựng điều kiện xử lý `NULL` và kiểu dữ liệu chính xác, đồng thời xác định rõ những cột nào tạo nên trạng thái cần bảo vệ.

## 7. Dùng thời gian cập nhật hay số phiên bản?

Một số hệ thống dùng `updated_at` làm token để phát hiện cập nhật:

```sql
UPDATE products
SET price = 110.00,
    updated_at = CURRENT_TIMESTAMP
WHERE product_id = 42
  AND updated_at = :expected_updated_at;
```

Cách này có thể phù hợp nếu độ chính xác và cách sinh timestamp đủ để phân biệt các lần ghi. Tuy nhiên, timestamp có một số hạn chế:

- Độ phân giải thời gian có thể thấp hơn tốc độ cập nhật, khiến hai lần ghi có cùng giá trị thời gian.
- Đồng hồ của các máy ứng dụng có thể lệch nhau nếu timestamp được tạo ở ứng dụng.
- Một số hệ quản trị hoặc câu lệnh có thể giữ nguyên timestamp khi giá trị không thay đổi.
- Việc làm tròn, múi giờ và cách chuyển đổi kiểu có thể khiến token gửi lại khác giá trị lưu trữ.

Một bộ đếm số nguyên tăng trong cùng câu lệnh cập nhật thường dễ kiểm soát hơn. Nếu dùng timestamp, cần bảo đảm giá trị mới luôn phân biệt được với giá trị cũ theo độ chính xác thực tế của cột và hệ quản trị.

## 8. Kiểm soát phiên bản trong ứng dụng Java/JPA

Các ORM có thể tự động triển khai optimistic locking dựa trên một trường phiên bản. Với Jakarta Persistence/JPA, có thể khai báo `@Version` trên một thuộc tính của entity:

```java
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Version;

@Entity
public class Product {
    @Id
    private Long id;

    private String name;
    private java.math.BigDecimal price;

    @Version
    private Long version;
}
```

Khi ứng dụng tải entity được quản lý và thay đổi thuộc tính, persistence provider sẽ dùng giá trị phiên bản đã đọc để kiểm tra khi ghi và tăng phiên bản khi cập nhật thành công. Câu SQL được sinh ra về mặt khái niệm tương tự:

```sql
UPDATE products
SET price = ?, version = version + 1
WHERE product_id = ?
  AND version = ?;
```

Nếu không hàng nào được cập nhật vì phiên bản đã thay đổi, provider báo lỗi optimistic locking, thường qua `OptimisticLockException` hoặc một ngoại lệ được framework bao bọc. Tùy thời điểm phát hiện, lỗi có thể xuất hiện khi gọi `flush()` hoặc khi transaction commit.

Ứng dụng thường phải rollback giao dịch đã gặp lỗi optimistic locking. Sau đó, nó có thể tải lại entity trong một giao dịch mới và yêu cầu người dùng giải quyết xung đột. Không tiếp tục dùng một persistence context có trạng thái lỗi như thể thao tác trước đã thành công.

### 8.1. Lưu ý với cập nhật hàng loạt

Các câu lệnh bulk update bằng JPQL, Criteria hoặc SQL trực tiếp thường đi vòng qua cơ chế dirty checking của entity được quản lý. Vì vậy, không nên mặc định rằng `@Version` sẽ tự động được áp dụng cho mọi bulk update.

Nếu bulk update cần bảo vệ phiên bản, câu lệnh phải tự đưa điều kiện phiên bản và phép tăng phiên bản vào thao tác ghi, đồng thời ứng dụng cần xử lý số hàng bị ảnh hưởng. Sau bulk update, persistence context có thể đang giữ entity cũ; cần làm mới hoặc xóa trạng thái được quản lý theo cách phù hợp để tránh đọc lại dữ liệu lỗi thời từ bộ nhớ.

## 9. Phạm vi bảo vệ và những gì optimistic locking không giải quyết

Kiểm tra phiên bản trên một hàng bảo vệ việc cập nhật hàng đó dựa trên phiên bản đã đọc. Nó không tự động bảo vệ mọi quy tắc nghiệp vụ liên quan đến nhiều hàng hoặc một tập hàng.

Ví dụ, quy tắc “luôn có ít nhất một bác sĩ đang trực” phụ thuộc vào nhiều hàng. Hai giao dịch có thể đọc cùng một tập bác sĩ, rồi cập nhật hai hàng khác nhau. Nếu mỗi hàng có cột phiên bản riêng, mỗi giao dịch vẫn có thể cập nhật hàng của mình thành công vì không có cùng hàng nào bị cập nhật đồng thời. Kết quả tổng thể vẫn có thể vi phạm quy tắc.

Với bất biến nhiều hàng hoặc điều kiện trên tập kết quả, cần cân nhắc thêm:

- Ràng buộc cơ sở dữ liệu như `UNIQUE`, `CHECK` hoặc khóa ngoại nếu quy tắc có thể biểu diễn bằng ràng buộc.
- Khóa điều phối hoặc khóa phạm vi để tuần tự hóa các thao tác liên quan.
- Mức cô lập `SERIALIZABLE` hoặc cơ chế kiểm soát tuần tự hóa của hệ quản trị.
- Một thiết kế dữ liệu biến quy tắc nhiều hàng thành một hàng hoặc một tài nguyên có thể kiểm tra nguyên tử.

Optimistic locking cũng không ngăn mọi giao dịch khác đọc dữ liệu đã commit. Nó tập trung phát hiện cập nhật dựa trên phiên bản cũ. Mức cô lập giao dịch vẫn quyết định các lần đọc có thể nhìn thấy những thay đổi nào và những bất thường đọc nào có thể xảy ra.

## 10. Các lỗi triển khai thường gặp

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Quên điều kiện `version = :expectedVersion` | Bản cập nhật cũ vẫn có thể ghi đè dữ liệu mới | Dùng điều kiện phiên bản trong mọi đường ghi cần được bảo vệ |
| Cập nhật dữ liệu nhưng không tăng phiên bản | Lần ghi sau vẫn có thể dùng token cũ và vượt qua kiểm tra | Tăng phiên bản nguyên tử trong cùng câu lệnh cập nhật |
| Chỉ một số dịch vụ tuân theo quy ước phiên bản | Đường ghi bỏ qua kiểm tra làm mất tác dụng bảo vệ | Đưa quy tắc cập nhật vào một tầng ghi thống nhất hoặc ràng buộc thích hợp |
| Không kiểm tra số hàng bị ảnh hưởng | Xung đột bị hiểu nhầm là thành công | Kiểm tra kết quả cập nhật và xử lý `0` hàng |
| Tự động retry với dữ liệu cũ và phiên bản mới | Có thể ghi đè thay đổi mới sau khi tải token mới | Tải lại, tính lại hoặc yêu cầu người dùng giải quyết |
| Dùng timestamp có độ phân giải không đủ | Hai lần cập nhật có thể không tạo token khác nhau | Dùng bộ đếm phiên bản hoặc bảo đảm độ phân giải và tính duy nhất |
| Bulk update bỏ qua cơ chế phiên bản ORM | Entity khác có thể bị cập nhật lỗi thời | Viết điều kiện phiên bản rõ ràng và đồng bộ persistence context |
| Chỉ bảo vệ từng hàng trong khi quy tắc liên quan nhiều hàng | Vẫn có thể xảy ra write skew | Dùng ràng buộc, khóa phạm vi hoặc mức cô lập mạnh hơn |

Ngoài ra, không nên xóa rồi tạo lại một hàng với cùng khóa chính và đặt lại phiên bản về giá trị cũ nếu các client vẫn có thể giữ token trước đó. Hãy bảo đảm token phiên bản không bị tái sử dụng theo cách khiến một yêu cầu lỗi thời trông như hợp lệ.

## 11. Khi nào nên dùng khóa lạc quan?

Khóa lạc quan thường phù hợp khi:

- Nhiều giao dịch đọc nhưng ít giao dịch cập nhật cùng một hàng.
- Thời gian giữa lúc đọc và lúc ghi có thể dài, chẳng hạn người dùng mở biểu mẫu rồi mới bấm lưu.
- Việc chờ khóa trong suốt quá trình người dùng chỉnh sửa sẽ làm giảm trải nghiệm hoặc khả năng mở rộng.
- Ứng dụng có thể phát hiện xung đột và yêu cầu tải lại, hợp nhất hoặc xác nhận lại thay đổi.

Khóa lạc quan kém phù hợp hơn khi cùng một hàng bị cập nhật liên tục, xung đột thường xuyên hoặc nghiệp vụ không thể chấp nhận việc hủy và thử lại. Trong các trường hợp đó, khóa bi quan (*pessimistic locking*) hoặc một thiết kế điều phối khác có thể hiệu quả hơn.

Khóa lạc quan không có nghĩa là cơ sở dữ liệu không dùng khóa vật lý. Khi thực thi `UPDATE`, hệ quản trị vẫn phải điều phối việc ghi và có thể giữ khóa ghi trong thời gian ngắn. Điểm khác biệt là ứng dụng không giữ khóa độc quyền từ lúc đọc cho đến lúc người dùng quyết định lưu; nó kiểm tra phiên bản tại thời điểm ghi.

## 12. Ghi nhớ

- Ứng dụng đọc dữ liệu và lưu token phiên bản cùng dữ liệu.
- Khi cập nhật, câu lệnh dùng `WHERE id = ? AND version = ?` để chỉ ghi nếu phiên bản vẫn đúng như lúc đọc.
- Cập nhật thành công phải tăng phiên bản trong cùng thao tác nguyên tử.
- Một hàng bị ảnh hưởng nghĩa là cập nhật thành công; không hàng nào bị ảnh hưởng thường biểu thị dữ liệu đã thay đổi hoặc không còn tồn tại.
- Khi xung đột, cần tải lại và quyết định cách hợp nhất hoặc thử lại dựa trên dữ liệu mới; không gửi lại mù quáng giá trị cũ.
- Mọi đường ghi liên quan phải tuân theo quy tắc phiên bản; bulk update và cập nhật ngoài ORM cần được xử lý riêng.
- Phiên bản trên từng hàng không tự bảo vệ bất biến trải rộng nhiều hàng hoặc tập kết quả truy vấn.

Khi xem một câu lệnh cập nhật, hãy hỏi: **Nó có xác nhận rằng hàng vẫn ở đúng phiên bản mà ứng dụng đã đọc, và có tăng phiên bản nguyên tử nếu cập nhật thành công hay không?**
