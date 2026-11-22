# Kiểm tra tập đọc và tập ghi khi xác nhận giao dịch

Trong kiểm soát khả tuần tự, một giao dịch có thể đọc dữ liệu ở một thời điểm rồi mới yêu cầu commit sau khi đã tính toán xong. Trong khoảng thời gian đó, giao dịch khác có thể đã thay đổi dữ liệu mà giao dịch hiện tại dựa vào. Nếu hệ quản trị chỉ ghi các thay đổi mà không kiểm tra lại những gì giao dịch đã đọc, kết quả commit có thể không tương đương với bất kỳ thứ tự chạy tuần tự hợp lệ nào.

Một cách tiếp cận là **kiểm soát đồng thời lạc quan** (*Optimistic Concurrency Control – OCC*). Giao dịch được phép đọc và tính toán trước; khi chuẩn bị commit, hệ quản trị kiểm tra tập đọc và tập ghi để xác định liệu giao dịch có thể được chấp nhận mà vẫn giữ được tính khả tuần tự hay không.

## 1. Tập đọc và tập ghi biểu diễn điều gì?

Với một transaction T, ta thường theo dõi hai tập dữ liệu:

- **Tập đọc RS(T) – Read Set:** những mục dữ liệu mà transaction đã đọc từ cơ sở dữ liệu trong giai đoạn thực thi. Mỗi mục đọc cần gắn với phiên bản hoặc dấu thời gian mà transaction thực sự quan sát.
- **Tập ghi WS(T) – Write Set:** những mục dữ liệu transaction dự định chèn, sửa hoặc xóa. Trong OCC, các thay đổi thường được giữ trong vùng làm việc riêng trước khi được công bố vào cơ sở dữ liệu.

Ví dụ, một transaction tính tổng tiền đơn hàng từ giá sản phẩm và số lượng:

~~~sql
BEGIN;

SELECT price
FROM product
WHERE product_id = 7;

SELECT quantity
FROM cart_item
WHERE product_id = 7;

UPDATE purchase_order
SET total_amount = 500
WHERE order_id = 91;

COMMIT;
~~~

Nếu các giá trị đọc đến từ cơ sở dữ liệu, có thể mô hình hóa:

- RS(T) = {product(7).price, cart_item(7).quantity}
- WS(T) = {purchase_order(91).total_amount}

Các tập này giúp hệ quản trị biết transaction đã phụ thuộc vào dữ liệu nào và dự định làm thay đổi dữ liệu nào. Khi một transaction khác thay đổi mục thuộc tập đọc, quyết định hiện tại có thể đã dựa trên dữ liệu cũ. Khi hai transaction cùng ghi một mục, có nguy cơ ghi đè hoặc vi phạm thứ tự thực thi dự kiến.

Trong triển khai thực tế, một tập đọc có thể lưu khóa hàng kèm phiên bản, mã trang, khoảng chỉ mục hoặc predicate đã được đánh giá. Tập ghi có thể lưu khóa, thao tác và giá trị mới. Cách biểu diễn phụ thuộc storage engine và cơ chế kiểm soát đồng thời.

## 2. Ba giai đoạn của Optimistic Concurrency Control

OCC thường được mô tả qua ba giai đoạn:

1. **Read phase:** transaction đọc dữ liệu và tính toán. Các thay đổi được ghi vào workspace riêng; chúng chưa được công bố cho transaction khác.
2. **Validation phase:** khi transaction yêu cầu commit, hệ quản trị kiểm tra xem các lần đọc và ghi có xung đột với những transaction chạy đồng thời hay không.
3. **Write phase:** nếu validation thành công, hệ quản trị áp dụng các thay đổi của transaction một cách nguyên tử. Nếu thất bại, transaction bị hủy và có thể được chạy lại.

~~~mermaid
flowchart TD
    A["Bắt đầu transaction"] --> B["Read phase: đọc dữ liệu, ghi nhận RS"]
    B --> C["Tính toán, chuẩn bị WS riêng"]
    C --> D["Validation phase: kiểm tra RS và WS"]
    D --> E{"Validation đạt?"}
    E -->|Có| F["Write phase: công bố thay đổi nguyên tử"]
    E -->|Không| G["Abort transaction"]
    F --> H["Commit"]
    G --> I["Rollback và có thể retry"]
~~~

Ý tưởng của OCC là không phải khóa mọi dữ liệu ngay từ đầu. Hệ thống chấp nhận cho các transaction đọc và tính toán đồng thời, rồi kiểm tra xung đột ở thời điểm xác nhận. Cách này có thể hiệu quả khi xung đột ghi ít xảy ra. Nếu dữ liệu bị tranh chấp thường xuyên, số transaction phải rollback và retry có thể tăng đáng kể.

## 3. Vì sao phải kiểm tra lại khi commit?

Giả sử số dư tài khoản ban đầu là 1.000. T1 đọc số dư và dự định trừ 200. Trong lúc T1 tính toán, T2 trừ 500 và commit.

**T1:**

~~~sql
BEGIN;

SELECT balance
FROM account
WHERE account_id = 10;

-- T1 đọc được 1000 và tính số dư mới là 800.
-- Chưa công bố thay đổi.

UPDATE account
SET balance = 800
WHERE account_id = 10;

COMMIT;
~~~

**T2 chạy đồng thời:**

~~~sql
BEGIN;

UPDATE account
SET balance = balance - 500
WHERE account_id = 10;

COMMIT;
~~~

Giả sử T2 commit trước khi T1 hoàn tất validation. T1 đã tính giá trị 800 từ số dư cũ 1.000, trong khi số dư hiện hành sau T2 là 500. Nếu T1 ghi đè 800 mà không kiểm tra, khoản trừ 500 của T2 có thể bị mất.

Với mô hình tập dữ liệu:

- RS(T1) chứa account(10).balance.
- WS(T1) chứa account(10).balance.
- WS(T2) cũng chứa account(10).balance.

Khi T1 xác nhận sau khi T2 đã ghi, hệ quản trị nhận ra T2 đã thay đổi dữ liệu mà T1 đọc. T1 phải được xử lý theo quy tắc validation, thường là abort để đọc lại số dư mới và tính toán lại. T1 không nên đơn giản phát lại giá trị 800.

Ví dụ này minh họa xung đột đọc–ghi và ghi–ghi trên cùng một mục. Trong hệ thống thật, câu UPDATE dạng cộng/trừ có thể được thực thi theo cơ chế khóa và tính trên giá trị hiện hành; kết quả cụ thể phụ thuộc câu lệnh, isolation level và engine. Mục tiêu của ví dụ là thể hiện trường hợp ứng dụng đã tính một giá trị mới từ dữ liệu đọc trước đó rồi ghi giá trị tuyệt đối.

## 4. Các dạng giao nhau giữa tập đọc và tập ghi

Khi so sánh hai transaction Ti và Tj, có thể gặp các quan hệ sau:

| Quan hệ tập hợp | Ý nghĩa | Điều cần xem xét |
|---|---|---|
| RS(Ti) ∩ RS(Tj) | Cả hai cùng đọc một mục | Thông thường không xung đột vì không có ghi |
| RS(Ti) ∩ WS(Tj) | Ti đọc mục mà Tj ghi | Có thể khiến Ti dựa trên phiên bản cũ |
| WS(Ti) ∩ RS(Tj) | Ti ghi mục mà Tj đọc | Thứ tự tuần tự phải phản ánh transaction nào đọc trước khi ghi xảy ra |
| WS(Ti) ∩ WS(Tj) | Cả hai cùng ghi một mục | Cần điều phối để tránh ghi đè hoặc kết quả không tuần tự hóa được |

Một giao nhau giữa tập đọc và tập ghi là dấu hiệu cần kiểm tra, nhưng không phải mọi giao nhau đều tự động có nghĩa transaction phải bị hủy. Thời điểm bắt đầu, kết thúc, validation và phiên bản mà transaction đọc quyết định thứ tự tuần tự có thể hợp lệ hay không.

Ví dụ, Tj đã commit trước khi Ti bắt đầu. Ti đọc phiên bản mới do Tj tạo ra. Dù RS(Ti) và WS(Tj) có cùng mục, đây là thứ tự hợp lệ Tj trước Ti. Ngược lại, nếu Ti đã đọc phiên bản cũ rồi Tj mới ghi và commit trong khi Ti còn chạy, việc chấp nhận Ti theo thứ tự Tj trước Ti sẽ không hợp lệ nếu Ti đã dùng giá trị cũ.

Vì vậy, validator phải kết hợp tập hợp với thông tin thời gian hoặc phiên bản; chỉ kiểm tra hai tập hợp có giao nhau hay không là chưa đủ.

## 5. Kiểm tra theo thứ tự validation trong OCC

Một thuật toán OCC phổ biến chọn thứ tự tuần tự theo thời điểm transaction vượt qua validation. Gọi Ti là transaction đang cần xác nhận. Với mỗi transaction Tj đã vượt validation trước Ti, validator xét thời điểm Tj hoàn tất so với thời điểm Ti bắt đầu và thời điểm Ti xác nhận.

Các điều kiện thường được mô tả như sau:

| Trường hợp của Tj | Điều kiện để Ti có thể được chấp nhận theo thứ tự Tj trước Ti |
|---|---|
| Tj đã hoàn tất trước khi Ti bắt đầu | Không có khoảng thực thi chồng lấn; không cần kiểm tra giao nhau cho cặp này |
| Tj hoàn tất sau khi Ti bắt đầu nhưng trước khi Ti validation | RS(Ti) ∩ WS(Tj) phải rỗng |
| Tj vẫn đang thực thi tại lúc Ti validation | RS(Ti) ∩ WS(Tj) phải rỗng và WS(Ti) ∩ WS(Tj) phải rỗng |

Giải thích:

**Trường hợp 1 – Không chồng lấn**

Tj đã commit và kết thúc trước khi Ti bắt đầu. Ti bắt đầu sau đó nên có thể đọc trạng thái đã bao gồm các thay đổi của Tj. Hai transaction có thứ tự rõ ràng: Tj rồi Ti.

**Trường hợp 2 – Tj hoàn tất trong lúc Ti đang chạy**

Ti có thể đã đọc một số dữ liệu trước khi Tj commit. Nếu Tj ghi vào một mục mà Ti đã đọc, Ti có thể đang dựa trên phiên bản cũ. Vì vậy, cần bảo đảm:

RS(Ti) ∩ WS(Tj) = ∅

Nếu hai tập giao nhau, Ti không thể được xem như đã chạy sau Tj một cách hợp lệ với những giá trị mà nó thực sự đọc.

**Trường hợp 3 – Tj vẫn đang chạy khi Ti xác nhận**

Ngoài việc bảo đảm Ti không đọc mục mà Tj ghi, cần tránh hai transaction cùng ghi một mục:

RS(Ti) ∩ WS(Tj) = ∅

WS(Ti) ∩ WS(Tj) = ∅

Nếu Tj còn đang ghi và hai tập ghi giao nhau, hệ thống không thể tùy ý công bố cả hai tập thay đổi rồi giả định thứ tự Tj trước Ti. Một trong các transaction cần bị trì hoãn, hủy hoặc được xử lý theo cơ chế khác của hệ thống.

Các điều kiện trên mô tả một biến thể validation OCC với thứ tự tuần tự theo validation. Những hệ thống khác có thể dùng forward validation, backward validation, timestamp, version check hoặc cơ chế khóa. Không nên áp dụng bảng này như một quy tắc chung cho mọi database engine mà không xác định thuật toán đang dùng.

## 6. Ví dụ validation phát hiện dữ liệu đã bị thay đổi

Giả sử T1 đọc giá sản phẩm rồi tạo đơn hàng. Trong khi đó, T2 cập nhật giá sản phẩm.

Trạng thái ban đầu:

| product_id | price |
|---:|---:|
| 7 | 100 |

T1 bắt đầu trước:

~~~sql
BEGIN;

SELECT price
FROM product
WHERE product_id = 7;

-- T1 đọc price = 100.
-- T1 tính total_amount = 2 * 100 = 200.
-- T1 chuẩn bị ghi purchase_order(91).
~~~

T2 cập nhật và commit:

~~~sql
BEGIN;

UPDATE product
SET price = 120
WHERE product_id = 7;

COMMIT;
~~~

Sau đó T1 yêu cầu xác nhận:

~~~sql
UPDATE purchase_order
SET total_amount = 200
WHERE order_id = 91;

COMMIT;
~~~

Tập dữ liệu của T1:

- RS(T1) = {product(7).price}
- WS(T1) = {purchase_order(91).total_amount}

Tập ghi của T2:

- WS(T2) = {product(7).price}

Vì:

RS(T1) ∩ WS(T2) = {product(7).price}

nên T1 đã đọc dữ liệu mà T2 thay đổi sau khi T1 bắt đầu. Nếu validator chọn thứ tự T2 trước T1, T1 phải nhìn thấy giá 120 để tính đơn hàng. Giá trị 200 được tính từ giá cũ 100 không phù hợp với thứ tự đó. T1 cần bị hủy hoặc xử lý theo quy tắc xung đột để ứng dụng đọc lại giá và tính lại.

Nếu T2 đã commit trước khi T1 bắt đầu, T1 đọc được giá 120 ngay từ đầu. Khi đó thứ tự T2 trước T1 là hợp lệ và không cần hủy T1 chỉ vì hai tập có cùng mục dữ liệu.

## 7. Tập đọc phải theo dõi cả predicate và phạm vi

Một lỗi phổ biến là chỉ ghi nhận các khóa hàng mà câu SELECT trả về. Điều đó có thể bỏ sót **phantom**: một transaction khác chèn hàng mới làm thay đổi kết quả của điều kiện truy vấn.

Ví dụ T1 kiểm tra số lượng phòng đã đặt:

~~~sql
SELECT COUNT(*)
FROM room_booking
WHERE room_id = 5
  AND booking_date = DATE '2026-11-20';
~~~

T1 thấy chưa có lượt đặt nào. Trong lúc đó, T2 chèn một lượt đặt mới thỏa điều kiện trên rồi commit. Nếu T1 chỉ lưu tập đọc gồm những hàng đã trả về, tập đó có thể rỗng; validator không biết rằng một hàng mới đã xuất hiện trong phạm vi truy vấn.

Vì vậy, để bảo vệ khả tuần tự với truy vấn theo điều kiện, hệ thống cần theo dõi được phạm vi hoặc predicate đã đọc, không chỉ các hàng hiện hữu. Các cách triển khai có thể bao gồm:

- Predicate locking hoặc theo dõi predicate logic.
- Key-range lock trên khoảng chỉ mục.
- Theo dõi phiên bản trang, dải khóa hoặc dấu thời gian của phạm vi.
- Ghi nhận phụ thuộc đọc–ghi theo predicate trong cơ chế SSI.

Ví dụ về predicate có thể là: mọi hàng trong room_id = 5 và booking_date = ngày được yêu cầu. Một transaction chèn hàng mới thỏa predicate có thể xung đột với lần đọc trước đó dù khóa chính của hàng mới chưa từng xuất hiện trong RS dạng danh sách khóa hàng.

## 8. Phân biệt OCC validation với Serializable Snapshot Isolation

Cả OCC validation và Serializable Snapshot Isolation (SSI) đều có thể sử dụng thông tin đọc–ghi để bảo đảm khả tuần tự, nhưng cách vận hành khác nhau.

| Tiêu chí | OCC validation truyền thống | SSI |
|---|---|---|
| Thời điểm phát hiện | Thường kiểm tra khi transaction yêu cầu commit | Theo dõi phụ thuộc trong lúc các transaction chạy và quyết định hủy khi phát hiện nguy cơ |
| Thông tin chính | Read set, write set, thời điểm và trạng thái transaction | Các phụ thuộc đọc–ghi, đặc biệt là rw-antidependency |
| Cách xử lý | Transaction không vượt validation bị abort trước khi công bố write set | Một transaction có thể bị hủy để phá cấu trúc phụ thuộc tạo nguy cơ không tuần tự hóa |
| Ghi dữ liệu | Thường giữ write set riêng rồi công bố sau validation | Có thể kết hợp với MVCC và cơ chế commit của engine |
| Ví dụ | OCC trong một số hệ thống giao dịch hoặc thuật toán học thuật | PostgreSQL SERIALIZABLE dùng SSI |

Trong SSI, một transaction đọc phiên bản cũ của dữ liệu mà transaction khác ghi có thể tạo phụ thuộc đọc–ghi. Nếu các phụ thuộc tạo thành cấu trúc nguy hiểm, hệ quản trị có thể hủy một transaction. SSI không đơn giản chỉ so sánh RS và WS tại đúng một thời điểm commit; nó theo dõi quan hệ phụ thuộc và lịch sử transaction theo cách riêng.

Do đó, khi nói “kiểm tra tập đọc và tập ghi”, cần xác định đang nói về validator của OCC hay cơ chế theo dõi phụ thuộc của SSI. Cả hai cùng hướng đến khả tuần tự, nhưng không có cùng một thuật toán kiểm tra.

## 9. Khi validation thất bại, transaction cần làm gì?

Nếu validation thất bại, transaction không được công bố một phần write set rồi tiếp tục như thể commit đã thành công. Thông thường, hệ thống abort transaction và loại bỏ workspace chưa công bố.

Ứng dụng nên xử lý theo trình tự:

1. Nhận diện lỗi serialization hoặc optimistic conflict từ driver/framework.
2. Rollback hoặc đóng transaction hiện tại.
3. Tạo transaction mới và đọc lại dữ liệu hiện hành.
4. Tính toán lại toàn bộ quyết định phụ thuộc vào dữ liệu đã đọc.
5. Thử lại với giới hạn số lần và backoff phù hợp.
6. Bảo đảm các tác động bên ngoài như gửi email, thu tiền hoặc phát message không bị lặp khi transaction retry.

Không nên giữ kết quả tính toán cũ rồi chỉ gửi lại câu UPDATE. Dữ liệu đầu vào có thể đã thay đổi; transaction mới phải thực hiện lại cả bước đọc và kiểm tra điều kiện.

## 10. OCC phù hợp trong trường hợp nào?

OCC thường phù hợp khi:

- Xung đột ghi hiếm hơn nhiều so với thao tác đọc.
- Transaction có thời gian thực thi ngắn hoặc vừa phải.
- Dữ liệu có thể được đọc mà không cần giữ khóa dài.
- Chi phí validation và retry thấp hơn chi phí khóa, chờ và điều phối ngay từ đầu.

OCC có thể kém hiệu quả khi nhiều transaction liên tục cập nhật cùng một nhóm dữ liệu nóng. Nếu tỷ lệ abort cao, hệ thống tiêu tốn tài nguyên để tính toán những transaction cuối cùng không được commit.

Một số hệ thống kết hợp các cách tiếp cận: đọc lạc quan cho phần ít tranh chấp, dùng khóa hoặc hàng điều phối cho tài nguyên nóng, và sử dụng mức SERIALIZABLE cho những nghiệp vụ có bất biến phức tạp.

## 11. Checklist khi kiểm tra tập đọc và tập ghi

- [ ] Tập đọc có lưu phiên bản hoặc dấu thời gian của dữ liệu đã quan sát không?
- [ ] Tập ghi có bao gồm thao tác insert, update và delete không?
- [ ] Validator so sánh với những transaction nào đã commit hoặc đã vượt validation?
- [ ] Có phân biệt transaction kết thúc trước khi transaction hiện tại bắt đầu với transaction kết thúc trong lúc nó đang chạy không?
- [ ] Có kiểm tra giao nhau giữa RS của transaction hiện tại và WS của transaction đồng thời không?
- [ ] Khi transaction khác vẫn đang chạy, có kiểm tra thêm giao nhau giữa hai tập ghi không?
- [ ] Predicate/range read có được theo dõi để phát hiện phantom không?
- [ ] Validation thất bại có hủy toàn bộ thay đổi chưa công bố không?
- [ ] Ứng dụng có retry toàn bộ transaction và tính toán lại từ dữ liệu mới không?
- [ ] Thuật toán đang dùng là OCC validation, SSI hay một cơ chế riêng của database engine?

Việc ghi nhận tập đọc và tập ghi giúp hệ quản trị biết transaction đã phụ thuộc vào dữ liệu nào và định thay đổi những mục nào. Khi xác nhận giao dịch, validator kết hợp các tập này với thời điểm thực thi hoặc phiên bản dữ liệu để quyết định thứ tự tuần tự có hợp lệ hay không. Muốn bảo vệ truy vấn theo điều kiện, tập đọc còn phải phản ánh phạm vi và predicate, vì một hàng mới xuất hiện cũng có thể làm thay đổi kết quả mà transaction dựa vào.
