# Triển khai ràng buộc theo giai đoạn với `NOT VALID` và `VALIDATE`

Khi một bảng PostgreSQL đã có nhiều dữ liệu, thêm ràng buộc có thể cần kiểm tra toàn bộ các hàng hiện có. Với ràng buộc `CHECK` và khóa ngoại (`FOREIGN KEY`), PostgreSQL cho phép tách công việc này thành hai giai đoạn: tạo ràng buộc bằng `NOT VALID`, sau đó kiểm tra dữ liệu cũ bằng `VALIDATE CONSTRAINT`. Cách làm này giúp đưa quy tắc mới vào hiệu lực sớm, đồng thời chủ động thời điểm quét và xử lý dữ liệu lịch sử.

## 1. Vì sao cần triển khai ràng buộc theo giai đoạn?

Giả sử bảng `orders` đã lưu hàng chục triệu đơn hàng. Hệ thống cần bổ sung hai quy tắc:

- Mỗi `customer_id` khác `NULL` phải tham chiếu đến một khách hàng đang tồn tại trong `customers`.
- `amount` phải lớn hơn `0`.

Nếu thêm ràng buộc theo cách thông thường, PostgreSQL phải xác minh dữ liệu hiện có thỏa mãn quy tắc. Với bảng lớn, lần kiểm tra này có thể kéo dài, tạo tải đọc đáng kể và làm tăng thời gian giữ khóa của thao tác DDL.

Với `NOT VALID`, PostgreSQL đăng ký ràng buộc mà không quét toàn bộ dữ liệu cũ ngay lúc thêm. Kể từ thời điểm đó, các thao tác ghi mới vẫn phải tuân thủ ràng buộc. Sau khi xử lý các hàng lịch sử vi phạm, có thể chạy `VALIDATE CONSTRAINT` để PostgreSQL kiểm tra phần dữ liệu đã tồn tại và đánh dấu ràng buộc là hợp lệ.

## 2. Ý nghĩa của `NOT VALID` và `VALIDATE CONSTRAINT`

`NOT VALID` là tùy chọn khi thêm một số loại ràng buộc bằng `ALTER TABLE ... ADD CONSTRAINT`. Nó có nghĩa là PostgreSQL chưa xác minh toàn bộ các hàng đang có trong bảng. Nó không có nghĩa là ràng buộc bị tắt.

`VALIDATE CONSTRAINT ten_rang_buoc` yêu cầu PostgreSQL kiểm tra dữ liệu hiện có theo ràng buộc đã đăng ký. Nếu tất cả dữ liệu đều phù hợp, PostgreSQL đánh dấu ràng buộc đã được xác thực. Nếu còn dữ liệu vi phạm, lệnh thất bại và ràng buộc vẫn ở trạng thái chưa được xác thực; quy tắc vẫn tiếp tục áp dụng cho các thao tác ghi mới.

| Trạng thái | Dữ liệu đã tồn tại trước khi thêm ràng buộc | Hàng được thêm hoặc cập nhật sau khi thêm ràng buộc |
|---|---|---|
| Chưa có ràng buộc | Không được kiểm tra theo quy tắc mới | Không bị ràng buộc mới kiểm soát |
| Đã thêm bằng `NOT VALID` | Chưa được quét và xác minh toàn bộ | Phải thỏa mãn ràng buộc |
| Đã `VALIDATE` thành công | Đã được xác minh | Phải thỏa mãn ràng buộc |

Như vậy, khoảng thời gian giữa hai lệnh là giai đoạn xử lý dữ liệu lịch sử. Trong khoảng thời gian này, dữ liệu mới vẫn được kiểm soát, giúp số lượng vi phạm không tiếp tục tăng do các thao tác ghi thông thường.

## 3. Những loại ràng buộc hỗ trợ `NOT VALID`

PostgreSQL hỗ trợ `NOT VALID` khi thêm hai loại ràng buộc:

- `CHECK`: kiểm tra một biểu thức trên từng hàng, chẳng hạn `amount > 0`.
- `FOREIGN KEY`: kiểm tra giá trị khóa ngoại có tham chiếu đến khóa hợp lệ ở bảng được tham chiếu hay không.

Các ràng buộc `PRIMARY KEY`, `UNIQUE` và `EXCLUDE` không hỗ trợ cách thêm bằng `NOT VALID`. Với yêu cầu duy nhất trên bảng lớn, một phương án triển khai thường dùng là tạo unique index bằng `CREATE UNIQUE INDEX CONCURRENTLY`, sau đó gắn index đó vào ràng buộc bằng `ALTER TABLE ... ADD CONSTRAINT ... USING INDEX`. Phương án này có quy trình và giới hạn riêng, không phải `NOT VALID`.

Ràng buộc khóa ngoại vẫn cần cột hoặc nhóm cột được tham chiếu có khóa duy nhất phù hợp, thường là `PRIMARY KEY` hoặc `UNIQUE`. Việc thêm khóa ngoại bằng `NOT VALID` chỉ trì hoãn xác minh các hàng đang có ở bảng chứa khóa ngoại; nó không bỏ qua các điều kiện cấu trúc của khóa ngoại.

## 4. Quy trình triển khai chuẩn

Một lần triển khai nên được chia thành các bước có thể theo dõi độc lập:

1. **Chuẩn bị ứng dụng và dữ liệu.** Xác định quy tắc nghiệp vụ, kiểm tra các luồng ghi hiện tại và bảo đảm phiên bản ứng dụng sắp chạy có thể tạo dữ liệu hợp lệ.
2. **Thêm ràng buộc với `NOT VALID`.** Đăng ký quy tắc để các thao tác ghi tiếp theo chịu sự kiểm soát ngay lập tức, trong khi dữ liệu lịch sử chưa bị quét.
3. **Tìm và xử lý dữ liệu cũ vi phạm.** Dùng truy vấn phù hợp để xác định hàng lỗi; sửa, gán lại khóa tham chiếu hoặc xử lý hàng theo chính sách nghiệp vụ.
4. **Xác thực ràng buộc.** Chạy `VALIDATE CONSTRAINT` sau khi đã xử lý dữ liệu lịch sử.
5. **Kiểm tra trạng thái.** Đọc metadata của PostgreSQL để xác nhận ràng buộc đã được đánh dấu là hợp lệ.

Nên tách thao tác thêm ràng buộc và thao tác xác thực thành các lần triển khai riêng. Sau khi thêm thành công, ràng buộc đã kiểm soát dữ liệu mới; nhóm vận hành có thể theo dõi và xử lý dữ liệu cũ trước khi bắt đầu lần quét xác thực.

## 5. Ví dụ: thêm khóa ngoại và `CHECK` cho bảng đơn hàng

Giả sử đã có hai bảng với cấu trúc khái quát sau:

```sql
CREATE TABLE public.customers (
    id bigint PRIMARY KEY,
    full_name text NOT NULL
);

CREATE TABLE public.orders (
    id bigint PRIMARY KEY,
    customer_id bigint,
    amount numeric(12, 2)
);
```

Trong hệ thống thực tế, các bảng có thể đã tồn tại và chứa nhiều dữ liệu. Ta muốn bảo đảm mỗi đơn hàng có `customer_id` hợp lệ khi cột này có giá trị, đồng thời số tiền phải dương.

### Bước 1: thêm các ràng buộc bằng `NOT VALID`

```sql
ALTER TABLE public.orders
    ADD CONSTRAINT orders_customer_id_fkey
    FOREIGN KEY (customer_id)
    REFERENCES public.customers (id)
    NOT VALID;

ALTER TABLE public.orders
    ADD CONSTRAINT orders_amount_positive_check
    CHECK (amount > 0)
    NOT VALID;
```

Hai lệnh trên đăng ký ràng buộc mà không quét tất cả các hàng cũ để xác minh ngay. Sau khi lệnh thêm ràng buộc hoàn tất, các hàng mới được chèn hoặc phiên bản hàng mới được tạo bởi thao tác cập nhật phải tuân thủ quy tắc tương ứng.

Đối với khóa ngoại, các thao tác ghi ở bảng `orders` được kiểm tra theo khóa tham chiếu. Cơ chế khóa ngoại cũng tiếp tục bảo vệ quan hệ khi có thay đổi liên quan ở bảng `customers`, theo hành động tham chiếu đã khai báo như `NO ACTION`, `RESTRICT`, `CASCADE` hoặc `SET NULL`.

### Bước 2: tìm các hàng đang vi phạm khóa ngoại

Có thể dùng `LEFT JOIN` để tìm đơn hàng có `customer_id` khác `NULL` nhưng không tìm thấy khách hàng tương ứng:

```sql
SELECT
    o.id AS order_id,
    o.customer_id
FROM public.orders AS o
LEFT JOIN public.customers AS c
    ON c.id = o.customer_id
WHERE o.customer_id IS NOT NULL
  AND c.id IS NULL
ORDER BY o.id;
```

Kết quả là các hàng cần được xử lý trước khi xác thực khóa ngoại. Tùy nghiệp vụ, có thể gán lại `customer_id` về khách hàng đúng, khôi phục bản ghi khách hàng bị thiếu, hoặc lưu trữ/xóa đơn hàng theo quy trình được phê duyệt. Không nên tự tạo một khóa khách hàng giả chỉ để làm cho truy vấn xác thực thành công.

Nếu khóa ngoại gồm nhiều cột, truy vấn tìm vi phạm phải đối chiếu đầy đủ các cột theo đúng quy tắc `MATCH` của khóa ngoại. Với mặc định `MATCH SIMPLE`, một hàng có ít nhất một thành phần khóa ngoại là `NULL` không bắt buộc phải tìm thấy hàng tham chiếu. Nếu dùng `MATCH FULL`, các thành phần phải cùng `NULL` hoặc cùng có giá trị.

### Bước 3: tìm các hàng đang vi phạm `CHECK`

Với `CHECK (amount > 0)`, truy vấn tìm các số tiền không dương như sau:

```sql
SELECT
    id,
    amount
FROM public.orders
WHERE amount <= 0
ORDER BY id;
```

Các hàng tìm được cần được điều chỉnh theo dữ liệu nguồn hoặc quy tắc nghiệp vụ. Nếu `amount` có thể `NULL`, biểu thức `CHECK (amount > 0)` vẫn cho phép giá trị `NULL`: trong PostgreSQL, ràng buộc `CHECK` được xem là đạt khi biểu thức trả về `TRUE` hoặc `NULL`. Nếu nghiệp vụ yêu cầu số tiền bắt buộc có giá trị, cần thêm quy tắc `NOT NULL` riêng hoặc kiểm tra đồng thời `amount IS NOT NULL`.

Với biểu thức `CHECK` phức tạp hơn, có thể tìm hàng vi phạm bằng điều kiện phủ định của biểu thức, ví dụ `WHERE NOT (bieuthuc_check)`. Cần lưu ý ngữ nghĩa ba giá trị `TRUE`, `FALSE`, `NULL` của SQL để truy vấn tìm lỗi phản ánh chính xác quy tắc đã khai báo.

### Bước 4: sửa dữ liệu lịch sử

Thực hiện sửa dữ liệu theo từng nhóm nếu bảng lớn. Chẳng hạn, có thể cập nhật theo khóa chính hoặc theo khoảng khóa để giới hạn thời gian và lượng dữ liệu bị tác động trong mỗi giao dịch. Với khóa ngoại, hãy xác định đúng khách hàng cần tham chiếu. Với `CHECK`, hãy lấy giá trị hợp lệ từ nguồn dữ liệu đáng tin cậy hoặc áp dụng quy tắc nghiệp vụ đã thống nhất.

Sau mỗi đợt sửa, chạy lại các truy vấn tìm vi phạm để xác nhận số hàng lỗi đã giảm. Việc cập nhật một hàng cũ đang vi phạm cũng phải tạo ra phiên bản hàng mới thỏa mãn các ràng buộc đang có hiệu lực. Ví dụ, cập nhật một cột không liên quan trên hàng vẫn có `amount <= 0` có thể thất bại vì hàng mới vẫn vi phạm `CHECK`.

### Bước 5: xác thực từng ràng buộc

Khi dữ liệu lịch sử đã phù hợp, chạy:

```sql
ALTER TABLE public.orders
    VALIDATE CONSTRAINT orders_customer_id_fkey;

ALTER TABLE public.orders
    VALIDATE CONSTRAINT orders_amount_positive_check;
```

PostgreSQL quét dữ liệu cần xác minh. Nếu không còn vi phạm, ràng buộc được chuyển sang trạng thái đã xác thực. Có thể xác thực từng ràng buộc để dễ xác định nguyên nhân nếu một lệnh thất bại.

Nếu một lệnh `VALIDATE CONSTRAINT` phát hiện vi phạm, lệnh đó thất bại và ràng buộc vẫn tồn tại ở trạng thái chưa xác thực. Nó vẫn kiểm soát các thao tác ghi mới. Hãy đọc lỗi, tìm các hàng còn vi phạm, xử lý dữ liệu rồi chạy lại lệnh xác thực.

### Bước 6: xác nhận metadata

Có thể kiểm tra trạng thái bằng catalog `pg_constraint`:

```sql
SELECT
    conname,
    contype,
    convalidated,
    pg_get_constraintdef(oid) AS definition
FROM pg_constraint
WHERE conrelid = 'public.orders'::regclass
  AND conname IN (
      'orders_customer_id_fkey',
      'orders_amount_positive_check'
  )
ORDER BY conname;
```

Trong kết quả:

- `conname` là tên ràng buộc.
- `contype` cho biết loại ràng buộc, chẳng hạn `f` cho khóa ngoại và `c` cho `CHECK`.
- `convalidated = false` cho biết dữ liệu hiện có chưa được xác thực đầy đủ.
- `convalidated = true` cho biết PostgreSQL đã xác thực thành công ràng buộc.
- `pg_get_constraintdef` hiển thị định nghĩa ràng buộc để đối chiếu với yêu cầu.

Chỉ xem bước triển khai hoàn tất khi đúng các ràng buộc mong muốn tồn tại và có `convalidated = true`.

## 6. Tác động đến ghi dữ liệu và vận hành

### Ràng buộc có hiệu lực ngay sau khi thêm

Sau khi thêm thành công bằng `NOT VALID`, PostgreSQL kiểm tra dữ liệu được ghi tiếp theo. Với `CHECK`, hàng mới phải thỏa mãn biểu thức. Với khóa ngoại, giá trị khóa tham chiếu mới phải hợp lệ theo định nghĩa khóa ngoại. Vì vậy, trước khi thêm ràng buộc, cần kiểm tra các phiên bản ứng dụng, tác vụ nền, luồng nhập dữ liệu và tích hợp bên ngoài có thể ghi vào bảng.

Nếu ứng dụng vẫn tạo dữ liệu vi phạm, các câu lệnh ghi đó sẽ nhận lỗi từ PostgreSQL. Do đó, thứ tự triển khai thường là đưa mã ứng dụng tạo dữ liệu hợp lệ lên trước, sau đó thêm ràng buộc `NOT VALID`.

### Xác thực vẫn tiêu thụ tài nguyên

`NOT VALID` giúp tránh lần quét dữ liệu cũ ngay ở bước thêm ràng buộc, nhưng `VALIDATE CONSTRAINT` vẫn phải đọc dữ liệu cần kiểm tra. Với bảng lớn, quá trình này có thể tạo tải I/O và kéo dài tùy kích thước bảng, tốc độ lưu trữ, bộ nhớ đệm và tải hệ thống.

PostgreSQL thiết kế thao tác xác thực để cho phép các hoạt động đọc và ghi thông thường tiếp tục trong nhiều trường hợp. Tuy nhiên, xác thực vẫn cần khóa bảng phù hợp; nó có thể xung đột với một số thao tác DDL hoặc bảo trì khác. Bản thân lệnh thêm ràng buộc cũng cần khóa DDL, và mức khóa cụ thể phụ thuộc loại ràng buộc cùng thao tác. Vì vậy, không nên hiểu `NOT VALID` là thao tác hoàn toàn không khóa hoặc `VALIDATE` là thao tác không có chi phí.

Với bảng lớn, nên chọn thời điểm ít tải hơn, theo dõi thời gian chạy và mức sử dụng I/O, đồng thời tránh xếp chồng nhiều thao tác DDL có khả năng tranh chấp khóa. Việc sửa dữ liệu lịch sử theo các lô nhỏ cũng giúp kiểm soát kích thước giao dịch và lượng WAL phát sinh.

### Tính nhất quán trong lúc xác thực

Kể từ lúc ràng buộc `NOT VALID` được thêm, các thao tác ghi mới đã bị kiểm soát. Vì thế, trong khi PostgreSQL quét dữ liệu cũ để xác thực, các thao tác ghi thông thường không thể tiếp tục đưa thêm hàng vi phạm vào bảng theo ràng buộc đó. Đây là cơ sở để chia quá trình thành hai giai đoạn mà vẫn duy trì tính toàn vẹn cho dữ liệu phát sinh sau thời điểm thêm ràng buộc.

## 7. Một số giới hạn và trường hợp cần xử lý riêng

### `NOT VALID` không áp dụng cho mọi ràng buộc

Không thể thêm `PRIMARY KEY`, `UNIQUE` hoặc `EXCLUDE` bằng `NOT VALID`. Nếu cần triển khai tính duy nhất trên bảng lớn, hãy xem xét quy trình tạo index phù hợp, thường là `CREATE UNIQUE INDEX CONCURRENTLY`, rồi gắn index vào constraint bằng `USING INDEX` khi đáp ứng các điều kiện của PostgreSQL.

### `NOT NULL` có quy trình riêng

Không thể khai báo trực tiếp một ràng buộc `NOT NULL` bằng cú pháp `NOT VALID`. Một cách triển khai theo giai đoạn là thêm `CHECK (cot IS NOT NULL) NOT VALID`, sửa các giá trị `NULL`, xác thực `CHECK`, sau đó đặt thuộc tính cột thành `NOT NULL`:

```sql
ALTER TABLE public.users
    ADD CONSTRAINT users_email_not_null_check
    CHECK (email IS NOT NULL)
    NOT VALID;

-- Xử lý các hàng có email IS NULL theo quy tắc nghiệp vụ.

ALTER TABLE public.users
    VALIDATE CONSTRAINT users_email_not_null_check;

ALTER TABLE public.users
    ALTER COLUMN email SET NOT NULL;

ALTER TABLE public.users
    DROP CONSTRAINT users_email_not_null_check;
```

Ở các phiên bản PostgreSQL có tối ưu sử dụng `CHECK` hợp lệ để chứng minh không có giá trị `NULL`, bước `SET NOT NULL` có thể tránh quét lại toàn bộ bảng. Thao tác này vẫn cần khóa DDL; hãy kiểm tra hành vi trên phiên bản PostgreSQL đang vận hành trước khi đưa vào quy trình triển khai.

### `VALIDATE` không tự sửa dữ liệu

Lệnh xác thực chỉ kiểm tra và cập nhật trạng thái xác thực của ràng buộc. Nó không tự chọn khách hàng thay thế, sửa số tiền, xóa hàng lỗi hoặc thay đổi dữ liệu nghiệp vụ. Trách nhiệm xác định cách sửa thuộc về ứng dụng và quy trình dữ liệu.

### Tên ràng buộc cần được quản lý rõ ràng

Nên đặt tên ổn định, dễ nhận biết và duy nhất trong phạm vi bảng. Tên này được dùng trong lệnh `VALIDATE CONSTRAINT`, truy vấn catalog, log triển khai và quy trình khôi phục. Tránh dựa vào tên tự sinh nếu cần tự động hóa nhiều môi trường.

## 8. Xử lý sự cố và khôi phục

Khi `ADD CONSTRAINT ... NOT VALID` thất bại, trước hết kiểm tra lỗi cú pháp, tên trùng, kiểu dữ liệu, khóa được tham chiếu và quyền thực thi. Lệnh thêm chưa thành công thì không có ràng buộc mới để xác thực.

Khi `VALIDATE CONSTRAINT` thất bại:

1. Giữ nguyên trạng thái ràng buộc và ghi nhận lỗi PostgreSQL trả về.
2. Chạy truy vấn tìm vi phạm tương ứng với `CHECK` hoặc `FOREIGN KEY`.
3. Kiểm tra các hàng mới có thể đã được ghi trong thời gian xử lý dữ liệu cũ; các hàng mới vi phạm sẽ bị ràng buộc chặn, nhưng hàng lịch sử vẫn cần được tìm và sửa.
4. Sửa dữ liệu theo quy tắc nghiệp vụ và chạy lại truy vấn kiểm tra.
5. Thực hiện lại `VALIDATE CONSTRAINT`.

Nếu phải hủy thay đổi, có thể xóa ràng buộc bằng `ALTER TABLE ... DROP CONSTRAINT ten_rang_buoc`. Đây là thay đổi làm mất cơ chế bảo vệ tương ứng, vì vậy chỉ thực hiện theo quyết định triển khai và cần đánh giá ảnh hưởng đến dữ liệu được ghi sau đó. Không xóa ràng buộc chỉ để làm cho bước xác thực có vẻ thành công.

## 9. Danh sách kiểm tra trước khi hoàn tất triển khai

- [ ] Đã xác định đúng bảng, cột, biểu thức `CHECK` hoặc quan hệ khóa ngoại cần bảo vệ.
- [ ] Ứng dụng và các luồng ghi đã sẵn sàng tuân thủ quy tắc mới.
- [ ] Ràng buộc đã được thêm thành công với `NOT VALID`.
- [ ] Đã truy vấn và xử lý các hàng lịch sử vi phạm.
- [ ] Đã cân nhắc tải I/O, thời gian chạy và khả năng tranh chấp khóa khi xác thực.
- [ ] `VALIDATE CONSTRAINT` đã chạy thành công cho từng ràng buộc.
- [ ] `pg_constraint.convalidated` trả về `true` cho các ràng buộc cần triển khai.

Triển khai theo giai đoạn giúp áp dụng quy tắc toàn vẹn dữ liệu sớm, kiểm soát dữ liệu mới ngay sau khi thêm ràng buộc và chủ động xử lý dữ liệu lịch sử trước khi xác thực toàn bảng. Đây là kỹ thuật hữu ích cho các thay đổi `CHECK` và `FOREIGN KEY` trên bảng PostgreSQL lớn, miễn là kế hoạch sửa dữ liệu và thời điểm xác thực được chuẩn bị phù hợp.
