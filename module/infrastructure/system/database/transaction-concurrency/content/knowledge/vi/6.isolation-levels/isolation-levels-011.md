# Chọn mức cô lập từ yêu cầu nghiệp vụ thay vì tên mức

Khi nhiều transaction chạy đồng thời, mỗi transaction có thể đọc và ghi dữ liệu trong lúc transaction khác cũng đang thay đổi dữ liệu. Mức cô lập (isolation level) quy định những trạng thái mà một transaction được phép quan sát và cách hệ quản trị cơ sở dữ liệu xử lý các thao tác xung đột. Chọn mức cô lập vì thế là quyết định về hành vi nghiệp vụ khi có cạnh tranh, không phải chọn một cái tên nghe có vẻ an toàn nhất.

Một hệ thống bán hàng có thể chấp nhận báo cáo doanh thu chậm hơn vài giây, nhưng không thể chấp nhận bán vượt số lượng tồn kho. Một màn hình tra cứu có thể chấp nhận hai lần đọc liên tiếp cho kết quả khác nhau, trong khi một thao tác tính hạn mức cần dựa trên một ảnh chụp dữ liệu nhất quán. Hai chức năng đó có thể cần chiến lược giao dịch khác nhau dù cùng truy cập một cơ sở dữ liệu.

Nguyên tắc quan trọng là bắt đầu từ điều nghiệp vụ phải bảo vệ, xác định những kết quả đồng thời nào có thể chấp nhận, rồi mới chọn isolation level và cơ chế phối hợp ghi phù hợp.

## 1. Mức cô lập giải quyết vấn đề gì?

Một transaction thường gồm nhiều câu lệnh đọc và ghi. Trong thời gian transaction chưa kết thúc, transaction khác có thể commit thay đổi lên những hàng dữ liệu liên quan. Nếu không có quy tắc cô lập, transaction thứ nhất có thể đọc một giá trị chưa được xác nhận, đọc cùng một hàng nhưng nhận hai giá trị khác nhau, hoặc đưa ra quyết định dựa trên một tập hàng đã thay đổi.

Mức cô lập kiểm soát khả năng quan sát các thay đổi đồng thời. Tùy hệ quản trị, cơ chế thực thi có thể dùng khóa (locking), phiên bản dữ liệu (MVCC), hoặc kết hợp cả hai. Vì vậy, cùng một tên isolation level không bảo đảm mọi hệ quản trị có hành vi hoàn toàn giống nhau.

Isolation level cũng không tự động bảo vệ mọi quy tắc nghiệp vụ. Chẳng hạn, yêu cầu “số lượng còn lại không bao giờ âm” có thể được bảo vệ trực tiếp bằng một câu `UPDATE` có điều kiện hoặc constraint. Tăng isolation level mà vẫn giữ cách đọc rồi ghi thiếu an toàn có thể làm hệ thống chậm hơn mà chưa chắc xử lý đúng mọi trường hợp.

## 2. Bắt đầu từ yêu cầu nghiệp vụ

Trước khi chọn mức cô lập, hãy mô tả rõ bốn khía cạnh sau.

### 2.1. Quy tắc nào tuyệt đối không được vi phạm?

Đây là invariant — điều kiện phải luôn đúng sau mọi transaction đã commit. Ví dụ:

- Số lượng hàng tồn kho không được âm.
- Một ghế chỉ được đặt bởi tối đa một khách hàng.
- Tổng số lượt đăng ký không vượt sức chứa của lớp học.
- Một tài khoản không được chi vượt số dư cho phép.
- Luôn có ít nhất một nhân viên trực trong một ca.

Hãy xác định invariant dựa trên dữ liệu nào: một hàng, nhiều hàng, một bảng hay nhiều bảng. Quy tắc trên một hàng thường có thể bảo vệ bằng constraint hoặc câu cập nhật nguyên tử. Quy tắc phụ thuộc vào một tập hàng hoặc tổng hợp nhiều bản ghi thường cần thêm cơ chế phối hợp.

### 2.2. Transaction cần nhìn thấy dữ liệu nhất quán ở phạm vi nào?

Hãy phân biệt hai nhu cầu:

- **Nhất quán trong một câu lệnh:** một câu truy vấn không được đọc dữ liệu chưa commit. Nhiều màn hình tra cứu thông thường chỉ cần mức bảo đảm này.
- **Nhất quán trong toàn transaction:** nhiều câu truy vấn trong cùng transaction phải cùng quan sát một ảnh chụp dữ liệu, hoặc ít nhất phải thấy cùng giá trị của những hàng đã đọc. Báo cáo nhiều bước, tính hạn mức hoặc quy trình ra quyết định dựa trên nhiều lần đọc có thể cần yêu cầu này.

Nếu nghiệp vụ chấp nhận kết quả thay đổi giữa hai câu lệnh, không cần trả giá cho một ảnh chụp cố định của toàn transaction. Ngược lại, nếu các bước sau phải dựa trên cùng một trạng thái dữ liệu, cần chọn mức hoặc cơ chế cung cấp bảo đảm đó.

### 2.3. Khi có xung đột, hệ thống nên xử lý thế nào?

Các lựa chọn thường gặp là:

- Chờ transaction khác nhả khóa.
- Phát hiện xung đột và từ chối một transaction để ứng dụng thử lại.
- Dùng cập nhật có điều kiện để một yêu cầu thành công, yêu cầu còn lại nhận kết quả “không đủ điều kiện”.
- Chấp nhận đọc dữ liệu cũ nếu nghiệp vụ cho phép.

Hãy quyết định rõ phản hồi nào có ý nghĩa với người dùng. Ví dụ, hai khách cùng đặt một ghế thì một người nhận xác nhận, người còn lại nhận thông báo ghế đã có người đặt. Đó là hành vi nghiệp vụ cụ thể hơn nhiều so với yêu cầu chung chung “dùng mức cô lập cao”.

### 2.4. Mức cạnh tranh và chi phí nào có thể chấp nhận?

Mức cô lập cao hơn có thể làm tăng thời gian chờ, số lần transaction bị hủy, hoặc chi phí thử lại. Một transaction kéo dài qua thời gian người dùng nhập liệu sẽ giữ tài nguyên lâu và làm xung đột dễ xảy ra hơn. Cần cân nhắc thông lượng, độ trễ, tỷ lệ thử lại và khả năng chịu tải cùng với tính đúng đắn.

## 3. Dịch rủi ro nghiệp vụ thành các hiện tượng đồng thời

Các tên hiện tượng dưới đây giúp mô tả chính xác điều gì có thể xảy ra. Chúng là đầu vào để chọn cơ chế bảo vệ, không phải một danh sách mà mọi ứng dụng đều phải loại bỏ bằng cùng một isolation level.

| Hiện tượng | Điều xảy ra | Câu hỏi nghiệp vụ |
|---|---|---|
| Dirty read | Transaction đọc giá trị do transaction khác ghi nhưng chưa commit; transaction ghi có thể rollback sau đó. | Có được phép sử dụng dữ liệu mà cuối cùng không tồn tại không? |
| Non-repeatable read | Cùng một hàng được đọc hai lần trong một transaction nhưng giá trị khác nhau vì transaction khác đã commit cập nhật. | Các bước trong một quy trình có phải dựa trên cùng giá trị của hàng đã đọc không? |
| Phantom read | Cùng một điều kiện truy vấn được thực hiện lại nhưng tập hàng phù hợp thay đổi do transaction khác thêm hoặc xóa hàng. | Quyết định có phụ thuộc vào toàn bộ tập hàng thỏa điều kiện không? |
| Lost update | Hai transaction cùng đọc một giá trị rồi ghi kết quả tính toán; lần ghi sau có thể ghi đè thay đổi của lần ghi trước. | Mỗi cập nhật có phải được tính trên giá trị mới nhất, hoặc phải phát hiện phiên bản đã thay đổi không? |
| Write skew | Hai transaction cùng đọc một quy tắc tổng hợp, sau đó cập nhật các hàng khác nhau; kết quả kết hợp có thể vi phạm quy tắc ban đầu. | Có invariant nào phụ thuộc đồng thời vào nhiều hàng hoặc nhiều người tham gia không? |

Dirty read, non-repeatable read và phantom read là các hiện tượng thường được dùng để mô tả mức cô lập trong SQL. Lost update và write skew cần được xem xét riêng khi thiết kế thao tác ghi và invariant. Không nên giả định chỉ cần chọn một mức có tên phù hợp là mọi kiểu xung đột đều tự biến mất.

## 4. Hiểu các mức cô lập theo bảo đảm cần thiết

Bảng sau mô tả cách hiểu khái quát theo SQL. Hành vi thực tế còn phụ thuộc hệ quản trị, cấu hình và loại câu lệnh đọc — đặc biệt là câu đọc có khóa.

| Mức cô lập | Bảo đảm khái quát | Rủi ro còn cần xem xét |
|---|---|---|
| `READ UNCOMMITTED` | Cho phép mức quan sát lỏng nhất; về mặt chuẩn có thể đọc dữ liệu chưa commit. | Dirty read và các kết quả không ổn định. Một số hệ quản trị triển khai mức này tương đương `READ COMMITTED`. |
| `READ COMMITTED` | Không đọc dữ liệu chưa commit. Mỗi câu lệnh thường nhìn thấy dữ liệu đã commit tại thời điểm câu lệnh bắt đầu. | Hai câu lệnh trong cùng transaction có thể thấy giá trị hoặc tập hàng khác nhau; cần xem xét lost update và invariant nhiều hàng. |
| `REPEATABLE READ` | Không đọc dữ liệu chưa commit và bảo vệ khả năng đọc lại những hàng đã đọc theo ngữ nghĩa của hệ quản trị. | SQL chuẩn vẫn cho phép phantom ở mức này. Một số hệ quản trị dùng snapshot isolation và có thể vẫn cho phép write skew. |
| `SERIALIZABLE` | Kết quả của các transaction đồng thời phải tương đương với một thứ tự thực thi tuần tự nào đó. | Có thể phải chờ hoặc bị hủy khi hệ quản trị phát hiện xung đột; ứng dụng cần xử lý retry đúng cách. |

`SERIALIZABLE` không nhất thiết có nghĩa cơ sở dữ liệu thực sự chạy từng transaction một. Hệ quản trị có thể cho chạy đồng thời rồi khóa, phát hiện xung đột hoặc hủy transaction để bảo đảm kết quả tương đương một thứ tự tuần tự.

Đặc biệt, không nên suy luận rằng `REPEATABLE READ` có cùng ngữ nghĩa trên mọi sản phẩm. Có hệ quản trị định nghĩa mức này theo snapshot của toàn transaction; có hệ quản trị dùng khóa phạm vi để kiểm soát các hàng và khoảng khóa. Một snapshot có thể ngăn nhiều lần đọc cho kết quả khác nhau nhưng vẫn cho phép hai transaction cập nhật các hàng riêng biệt và cùng làm hỏng một invariant tổng hợp. Hãy tra tài liệu của đúng hệ quản trị và kiểm chứng bằng các transaction đồng thời trên phiên bản đang triển khai.

## 5. Chọn mức từ loại yêu cầu

Những gợi ý dưới đây là điểm khởi đầu. Mỗi lựa chọn phải được xác nhận bằng cách triển khai câu lệnh, constraint và kiểm thử phù hợp.

| Nhu cầu nghiệp vụ | Hướng lựa chọn ban đầu | Điều cần bảo vệ thêm |
|---|---|---|
| Tra cứu thông thường; mỗi câu lệnh chỉ cần dữ liệu đã commit | `READ COMMITTED` thường là điểm khởi đầu hợp lý. | Giao diện phải chấp nhận dữ liệu thay đổi giữa các lần đọc. |
| Cần đọc lặp lại cùng một hàng hoặc cùng ảnh chụp trong một transaction | Xem xét `REPEATABLE READ` hoặc chế độ snapshot tương ứng của hệ quản trị. | Xác nhận ngữ nghĩa phantom và write skew; giữ transaction ngắn. |
| Quyết định phụ thuộc vào tập hàng thỏa một điều kiện, như tổng số đăng ký | Xem xét `SERIALIZABLE` hoặc khóa một hàng điều phối đại diện cho tài nguyên. | Có thể cần constraint, khóa rõ ràng và xử lý retry. |
| Cập nhật một giá trị dựa trên chính giá trị hiện tại, như trừ tồn kho | Ưu tiên một câu lệnh cập nhật nguyên tử có điều kiện ở mức phù hợp, thường có thể bắt đầu với `READ COMMITTED`. | Kiểm tra số hàng bị ảnh hưởng và ràng buộc miền giá trị. |
| Nhiều người cùng sửa một bản ghi và cần báo xung đột | Dùng optimistic locking với cột phiên bản, hoặc khóa hàng nếu cần chờ. | Không để lần ghi sau âm thầm ghi đè nội dung của lần ghi trước. |
| Không có yêu cầu rõ ràng cho phép đọc dữ liệu chưa commit | Tránh chọn `READ UNCOMMITTED`. | Dirty read thường gây ra quyết định nghiệp vụ dựa trên dữ liệu có thể bị rollback. |

Đối với nhiều ứng dụng giao dịch, `READ COMMITTED` là lựa chọn mặc định hợp lý khi kết hợp với constraint, cập nhật nguyên tử và xử lý xung đột đúng cách. Chỉ tăng isolation level khi đã xác định được hiện tượng cần ngăn chặn và hiểu chi phí của cơ chế đó.

## 6. Ví dụ: bảo vệ số lượng tồn kho

Giả sử một sản phẩm còn 5 đơn vị. Hai khách hàng cùng đặt 4 đơn vị gần như đồng thời. Một cách viết dễ gặp là:

```sql
BEGIN;

SELECT available_quantity
FROM inventory
WHERE product_id = :product_id;

-- Ứng dụng kiểm tra available_quantity >= :quantity

UPDATE inventory
SET available_quantity = :new_quantity
WHERE product_id = :product_id;

COMMIT;
```

Nếu hai transaction cùng đọc giá trị 5 trước khi transaction nào cập nhật, cả hai đều có thể quyết định đơn hàng hợp lệ. Nếu chúng cùng ghi giá trị tính từ bản đọc cũ, một thay đổi có thể ghi đè thay đổi còn lại. Chỉ nhìn tên isolation level mà không phân tích chuỗi đọc — tính — ghi sẽ bỏ sót vấn đề này.

Với invariant đơn giản “không được trừ quá số lượng còn lại”, có thể đưa điều kiện vào chính câu lệnh cập nhật:

```sql
BEGIN;

UPDATE inventory
SET available_quantity = available_quantity - :quantity
WHERE product_id = :product_id
  AND available_quantity >= :quantity;

-- Ứng dụng kiểm tra số hàng bị ảnh hưởng:
-- 1 hàng: trừ tồn kho thành công.
-- 0 hàng: không tồn tại sản phẩm hoặc không đủ số lượng.

COMMIT;
```

Câu lệnh này để cơ sở dữ liệu thực hiện phép trừ trên giá trị đang được cập nhật và chỉ cập nhật khi điều kiện còn đúng. Ứng dụng phải kiểm tra số hàng bị ảnh hưởng để quyết định xác nhận hay từ chối đơn hàng. Cách làm này thường cho phép bảo vệ invariant ở `READ COMMITTED`, nhưng vẫn cần kiểm chứng hành vi cập nhật đồng thời trên hệ quản trị cụ thể và có thể bổ sung `CHECK` constraint để ngăn giá trị âm do những đường ghi khác.

Ví dụ cho thấy câu hỏi đúng không phải là “tồn kho cần `SERIALIZABLE` hay không?”, mà là “điều kiện nào phải đúng tại thời điểm trừ, và thao tác ghi có bảo vệ điều kiện đó một cách nguyên tử không?”.

## 7. Ví dụ: giới hạn sức chứa và quy tắc nhiều hàng

Một lớp học có sức chứa 30 người. Cách triển khai bằng cách đếm số bản ghi đăng ký rồi mới thêm một bản ghi có thể gặp race condition:

```sql
BEGIN;

SELECT COUNT(*)
FROM enrollment
WHERE class_id = :class_id;

-- Nếu số lượng nhỏ hơn 30 thì thêm đăng ký.

INSERT INTO enrollment (class_id, student_id)
VALUES (:class_id, :student_id);

COMMIT;
```

Hai transaction có thể cùng đếm được 29 rồi mỗi transaction thêm một người, khiến tổng số thành 31. Đây là vấn đề liên quan đến tập hàng thỏa điều kiện; khóa riêng hàng đăng ký hiện có không nhất thiết ngăn được một hàng mới xuất hiện.

Có thể thiết kế một hàng sức chứa cho mỗi lớp và cập nhật có điều kiện:

```sql
UPDATE class_capacity
SET enrolled_count = enrolled_count + 1
WHERE class_id = :class_id
  AND enrolled_count < capacity;
```

Nếu chỉ cập nhật được một hàng, ứng dụng tiếp tục tạo đăng ký trong cùng transaction; nếu không có hàng nào được cập nhật, lớp đã đủ chỗ hoặc không tồn tại. Bản ghi đăng ký và bộ đếm phải được ghi trong cùng transaction để tránh lệch nhau. Có thể bổ sung khóa duy nhất trên `(class_id, student_id)` để một học viên không đăng ký trùng.

Một lựa chọn khác là dùng `SERIALIZABLE` cho quy trình đếm và thêm, rồi xử lý trường hợp transaction bị hủy do xung đột. Cũng có thể khóa một hàng đại diện cho lớp trước khi đếm và thêm. Lựa chọn nào phù hợp phụ thuộc lưu lượng đăng ký, cách tổ chức dữ liệu và khả năng thử lại. Nếu dùng khóa điều phối, mọi đường ghi liên quan phải tuân thủ cùng quy tắc khóa.

## 8. Ví dụ: write skew dù mỗi transaction đều đọc snapshot

Giả sử một ca trực có hai bác sĩ và quy tắc là luôn phải có ít nhất một bác sĩ đang trực. Hai transaction chạy đồng thời:

1. Transaction A đọc trạng thái và thấy cả bác sĩ A lẫn B đều đang trực.
2. Transaction B cũng đọc trạng thái đó.
3. A tắt trạng thái trực của bác sĩ A.
4. B tắt trạng thái trực của bác sĩ B.
5. Hai transaction cập nhật hai hàng khác nhau rồi cùng commit.

Nếu hệ quản trị cung cấp snapshot isolation cho mức được chọn, cả hai transaction có thể đọc cùng một snapshot và không ghi đè cùng một hàng. Tuy nhiên, sau khi cả hai commit, không còn bác sĩ nào trực. Đây là write skew: mỗi transaction riêng lẻ đã kiểm tra quy tắc trên dữ liệu mà nó nhìn thấy, nhưng kết quả kết hợp lại vi phạm invariant.

Với invariant này, cần phối hợp các thao tác cùng tác động lên quy tắc tổng hợp. Có thể dùng `SERIALIZABLE` và retry transaction bị từ chối, hoặc khóa một hàng điều phối chung trước khi đọc và thay đổi trạng thái. Một constraint có thể bảo vệ trực tiếp invariant nếu mô hình dữ liệu biểu diễn được điều kiện đó. Chỉ dùng snapshot để giữ kết quả đọc ổn định là chưa đủ.

## 9. Xử lý transaction bị hủy và thử lại

Ở mức `SERIALIZABLE`, hệ quản trị có thể từ chối một transaction để loại bỏ lịch thực thi không tuần tự hóa được. Deadlock cũng có thể khiến một transaction bị chọn làm nạn nhân. Ứng dụng cần xem những lỗi này là kết quả có thể xảy ra của xử lý đồng thời.

Khi được phép retry, hãy chạy lại toàn bộ đơn vị transaction từ đầu để mọi lần đọc và quyết định được thực hiện trên trạng thái mới. Không chỉ chạy lại câu lệnh cuối cùng vì dữ liệu mà các câu lệnh trước đã đọc có thể không còn đúng. Giới hạn số lần thử, có backoff phù hợp và trả lỗi rõ ràng khi vẫn không thành công.

Transaction có tác dụng phụ bên ngoài cơ sở dữ liệu — chẳng hạn gửi email, gọi dịch vụ thanh toán hoặc phát thông báo — cần được thiết kế để retry không tạo tác dụng phụ trùng lặp. Có thể ghi sự kiện cần gửi cùng transaction rồi chuyển việc gửi sang cơ chế xử lý sau commit, chẳng hạn transactional outbox. Không thực hiện một tác dụng phụ không thể lặp an toàn ở giữa transaction có thể bị chạy lại.

## 10. Quy trình ra quyết định trong một hệ thống thực tế

Khi thiết kế một chức năng mới hoặc điều tra lỗi đồng thời, có thể đi theo trình tự sau:

1. Viết invariant bằng câu có thể kiểm tra được, ví dụ `available_quantity >= 0` hoặc số người đăng ký không vượt sức chứa.
2. Xác định dữ liệu mà quyết định phụ thuộc vào: một hàng, một tập hàng, hay kết quả tổng hợp từ nhiều bảng.
3. Liệt kê hiện tượng đồng thời có thể làm sai nghiệp vụ: dirty read, non-repeatable read, phantom, lost update hoặc write skew.
4. Kiểm tra có thể bảo vệ invariant bằng constraint, cập nhật nguyên tử, optimistic locking hoặc khóa một hàng điều phối hay không.
5. Chọn isolation level thấp nhất vẫn đáp ứng yêu cầu còn lại; nếu cần `SERIALIZABLE`, thiết kế rõ cách xử lý retry và xung đột.
6. Kiểm tra tài liệu của đúng hệ quản trị và cấu hình thực tế. Xác nhận isolation level ở connection/transaction thực sự được áp dụng, không chỉ dựa vào giá trị mặc định tưởng định.
7. Đo thời gian chờ khóa, tỷ lệ deadlock, serialization failure, retry và độ trễ dưới tải đại diện.

Kiểm thử đồng thời phải dùng nhiều connection hoặc transaction thực sự chạy chồng lấp. Có thể dùng barrier/latch trong bài kiểm thử để buộc hai transaction cùng đọc trước khi tiếp tục ghi. Sau mỗi lượt chạy, kiểm tra invariant trên dữ liệu đã commit. Một bài kiểm thử chỉ chạy tuần tự từng transaction không chứng minh được hành vi khi có cạnh tranh.

Ngoài ra, giữ transaction ngắn: không chờ người dùng nhập liệu, không gọi dịch vụ mạng lâu và không giữ khóa trong lúc thực hiện công việc không thuộc cơ sở dữ liệu. Transaction ngắn giúp giảm thời gian tranh chấp ở mọi isolation level.

## 11. Checklist trước khi chốt isolation level

- [ ] Đã xác định invariant cụ thể mà nghiệp vụ cần bảo vệ.
- [ ] Đã biết invariant phụ thuộc vào một hàng hay nhiều hàng.
- [ ] Đã xác định việc đọc dữ liệu cũ hoặc thay đổi giữa các câu lệnh có được chấp nhận không.
- [ ] Đã xem xét lost update và write skew, không chỉ ba hiện tượng đọc kinh điển.
- [ ] Đã kiểm tra khả năng dùng constraint, câu lệnh nguyên tử, optimistic locking hoặc khóa điều phối.
- [ ] Đã xác nhận ngữ nghĩa isolation level trên đúng hệ quản trị và phiên bản đang dùng.
- [ ] Đã định nghĩa cách ứng dụng phản hồi khi chờ, xung đột hoặc retry thất bại.
- [ ] Đã kiểm thử bằng các transaction đồng thời và xác nhận invariant sau commit.
- [ ] Đã đo tác động đến thông lượng, độ trễ và tỷ lệ transaction bị hủy.

Chọn isolation level tốt là chọn đúng bảo đảm cho một quy tắc nghiệp vụ cụ thể với chi phí mà hệ thống có thể chấp nhận. Tên mức cô lập chỉ là điểm bắt đầu để đọc ngữ nghĩa; quyết định cuối cùng phải dựa trên invariant, cách truy cập dữ liệu, cơ chế của hệ quản trị và kết quả kiểm thử đồng thời.
