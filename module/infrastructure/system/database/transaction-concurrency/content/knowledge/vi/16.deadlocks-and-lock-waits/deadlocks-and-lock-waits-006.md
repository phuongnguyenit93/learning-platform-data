# Thứ tự lấy khóa nhất quán để giảm nguy cơ bế tắc

Khi nhiều transaction cùng cập nhật dữ liệu, chúng có thể phải chờ khóa mà transaction khác đang giữ. Chờ khóa là bình thường: một transaction có thể tiếp tục sau khi transaction kia commit hoặc rollback. Bế tắc (deadlock) xuất hiện khi các transaction chờ lẫn nhau theo một vòng khép kín, khiến không transaction nào trong vòng đó tự tiếp tục được.

Một cách quan trọng để giảm nguy cơ deadlock là quy định **thứ tự lấy khóa thống nhất**. Nếu mọi transaction cần nhiều tài nguyên đều xin khóa theo cùng một thứ tự toàn cục, chúng không thể tạo vòng chờ chỉ từ những khóa tuân thủ thứ tự đó. Quy tắc này đặc biệt hữu ích với các nghiệp vụ chuyển tiền, cập nhật nhiều sản phẩm, đặt chỗ hoặc thay đổi nhiều hàng liên quan.

Thứ tự khóa không loại bỏ mọi deadlock có thể phát sinh trong hệ thống. Khóa ngầm do foreign key, trigger, index, lock upgrade hoặc các tài nguyên ngoài database vẫn có thể tạo thêm quan hệ chờ. Vì vậy, cần thiết kế thứ tự rõ ràng, giữ transaction ngắn và xử lý được trường hợp database chọn transaction làm nạn nhân.

## 1. Deadlock hình thành như thế nào?

Giả sử có hai tài khoản A và B. T1 chuyển tiền từ A sang B, còn T2 chuyển tiền từ B sang A. Mỗi transaction cần khóa cả hai hàng để bảo đảm số dư được đọc và cập nhật nhất quán.

Nếu T1 lấy khóa A trước còn T2 lấy khóa B trước, lịch thực thi có thể diễn ra như sau:

| Bước | Transaction T1 | Transaction T2 |
| --- | --- | --- |
| 1 | Lấy khóa A thành công | |
| 2 | | Lấy khóa B thành công |
| 3 | Yêu cầu khóa B, phải chờ T2 | |
| 4 | | Yêu cầu khóa A, phải chờ T1 |

T1 đang giữ A và chờ B. T2 đang giữ B và chờ A. Cả hai đều không thể giải phóng khóa đang giữ vì transaction chưa thể hoàn tất.

Có thể biểu diễn quan hệ chờ bằng đồ thị:

```text
T1 --chờ khóa B--> T2
T2 --chờ khóa A--> T1

T1 -> T2 -> T1
```

Vòng khép kín trong wait-for graph là dấu hiệu deadlock. Một chuỗi chờ không có vòng vẫn có thể làm transaction chậm, nhưng khi transaction ở cuối chuỗi hoàn tất và nhả khóa, những transaction phía trước có thể tiếp tục.

Hệ quản trị cơ sở dữ liệu thường theo dõi quan hệ chờ và phát hiện chu trình. Khi tìm thấy deadlock, hệ thống chọn một transaction làm nạn nhân (victim), hủy hoặc rollback transaction đó để giải phóng khóa. Transaction còn lại sau đó có thể tiếp tục. Việc chọn nạn nhân dựa trên chính sách của engine, không nên giả định transaction mới nhất hay ít thay đổi nhất luôn bị chọn.

## 2. Nguyên tắc thứ tự lấy khóa thống nhất

Để tránh vòng chờ do các transaction lấy cùng một nhóm tài nguyên theo thứ tự ngược nhau, hãy xác định một thứ tự toàn cục và yêu cầu mọi luồng xử lý tuân thủ thứ tự đó.

Ví dụ, với tài khoản có ID số, quy định:

1. Khóa tài khoản có ID nhỏ hơn trước.
2. Khóa tài khoản có ID lớn hơn sau.
3. Chỉ thực hiện các thao tác cập nhật sau khi đã lấy đủ các khóa cần thiết.
4. Commit hoặc rollback để giải phóng tất cả khóa.

Với hai tài khoản 100 và 200, cả giao dịch chuyển tiền từ 100 sang 200 lẫn giao dịch chuyển tiền từ 200 sang 100 đều khóa theo thứ tự 100 rồi 200. Hướng chuyển tiền không quyết định thứ tự khóa.

```text
T1: khóa account 100 -> khóa account 200 -> cập nhật -> COMMIT
T2: khóa account 100 -> khóa account 200 -> cập nhật -> COMMIT
```

Nếu T1 lấy khóa account 100 trước, T2 phải chờ ngay tại account 100. T2 chưa giữ account 200 nên không thể tạo vòng chờ với T1 trên hai tài khoản này. Khi T1 kết thúc, T2 lấy được khóa 100 rồi tiếp tục lấy khóa 200.

### Vì sao thứ tự toàn cục ngăn vòng chờ?

Giả sử mỗi tài nguyên có một khóa thứ tự duy nhất và mọi transaction luôn lấy khóa theo thứ tự tăng dần. Nếu T1 đang giữ tài nguyên X và chờ tài nguyên Y, T1 phải đã lấy X trước khi yêu cầu Y, nên X đứng trước Y trong thứ tự toàn cục. Transaction giữ Y chỉ có thể chờ một tài nguyên đứng sau Y. Nếu mọi cạnh chờ đều tuân thủ quy tắc này, một vòng chờ sẽ đòi hỏi thứ tự tài nguyên tăng dần rồi quay lại tài nguyên ban đầu. Điều đó không thể xảy ra trong một thứ tự toàn phần.

Lập luận này chỉ áp dụng cho các khóa thực sự tuân theo cùng thứ tự. Nếu có một đường code lấy khóa ngoài quy tắc, hoặc database tự lấy thêm khóa theo thứ tự khác, deadlock vẫn có thể xuất hiện.

## 3. Xây dựng thứ tự khóa cho một bảng

Với các hàng trong cùng một bảng, khóa theo primary key tăng dần là một quy ước dễ áp dụng. Ví dụ, một nghiệp vụ cập nhật nhiều sản phẩm cần khóa các hàng có `product_id` là 18, 4 và 27. Thứ tự chuẩn là 4, 18, 27.

Ví dụ theo cách lấy từng hàng tuần tự:

```sql
BEGIN;

SELECT product_id, quantity
FROM inventory
WHERE product_id = 4
FOR UPDATE;

SELECT product_id, quantity
FROM inventory
WHERE product_id = 18
FOR UPDATE;

SELECT product_id, quantity
FROM inventory
WHERE product_id = 27
FOR UPDATE;

-- Sau khi đã khóa đủ các hàng, kiểm tra và cập nhật.
UPDATE inventory
SET quantity = quantity - 1
WHERE product_id = 4;

COMMIT;
```

Đây là ví dụ dùng cú pháp PostgreSQL/MySQL/InnoDB/Oracle cho locking read; cú pháp trên hệ khác cần điều chỉnh. Ứng dụng có thể tạo danh sách ID, loại bỏ ID trùng, sắp xếp theo cùng comparator rồi lần lượt khóa từng hàng trong transaction.

Nếu dùng một truy vấn dạng:

```sql
SELECT product_id, quantity
FROM inventory
WHERE product_id IN (4, 18, 27)
ORDER BY product_id
FOR UPDATE;
```

hãy xác nhận tài liệu của hệ quản trị và kế hoạch thực thi bảo đảm thứ tự lấy khóa phù hợp. `ORDER BY` mô tả thứ tự kết quả; không nên mặc định rằng mọi engine hoặc mọi execution plan đều lấy khóa theo đúng thứ tự dòng trả về. Khi cần bảo đảm rõ ràng và có thể chuyển giữa các engine, việc khóa từng ID theo thứ tự đã sắp xếp là cách dễ kiểm soát hơn, dù có thể tạo thêm round trip.

Nếu số hàng rất lớn, hãy cân nhắc stored procedure, batch locking hoặc cơ chế khóa phạm vi phù hợp để giảm số lần gọi. Dù chọn cách nào, quy tắc thứ tự lấy khóa phải được chứng minh theo semantics của database đang dùng.

## 4. Xây dựng thứ tự khóa giữa nhiều bảng

Khi transaction cần khóa nhiều loại tài nguyên, chỉ sắp xếp ID trong từng bảng có thể chưa đủ. Cần định nghĩa thứ tự giữa các loại tài nguyên.

Ví dụ hệ thống bán hàng có quy ước:

1. Hàng `customer` theo `customer_id` tăng dần.
2. Hàng `orders` theo `order_id` tăng dần.
3. Hàng `inventory` theo `product_id` tăng dần.
4. Hàng `warehouse` theo `warehouse_id` tăng dần.

Mọi transaction liên quan đến các loại tài nguyên này phải dùng cùng thứ tự, kể cả khi một luồng xử lý chỉ cần một phần danh sách. Nếu một luồng khóa inventory trước rồi mới khóa order, trong khi luồng khác khóa order trước rồi mới khóa inventory, vòng chờ vẫn có thể hình thành.

Có thể mô hình hóa thứ tự bằng một khóa tổng hợp:

```text
lock_key = (resource_rank, resource_id)

customer  -> rank 10
orders    -> rank 20
inventory -> rank 30
warehouse -> rank 40
```

Khi transaction cần nhiều tài nguyên, sắp xếp theo `resource_rank` trước, sau đó theo ID trong từng loại. Với tài nguyên có tenant hoặc partition, có thể bổ sung tenant ID vào khóa thứ tự, miễn là mọi luồng dùng cùng một quy tắc so sánh ổn định.

Không dùng cách sắp xếp phụ thuộc locale, ngôn ngữ hoặc định dạng chuỗi khác nhau giữa các service. Nếu ID là chuỗi, hãy xác định comparator nhất quán, chẳng hạn so sánh byte hoặc một dạng chuẩn hóa cố định. Mục tiêu là hai service nhận cùng tập tài nguyên phải tạo ra cùng một thứ tự.

## 5. Ví dụ: chuyển tiền giữa hai tài khoản

Một transaction chuyển tiền cần kiểm tra số dư tài khoản nguồn, trừ tiền ở nguồn và cộng tiền vào đích. Để tránh hai transaction khóa ngược nhau, cả hai đều lấy khóa theo account ID tăng dần, không theo vai trò nguồn/đích.

Giả sử chuyển 50 từ tài khoản 100 sang 200:

```sql
BEGIN;

-- Khóa theo ID tăng dần, dù hướng chuyển là 100 -> 200.
SELECT account_id, balance
FROM account
WHERE account_id = 100
FOR UPDATE;

SELECT account_id, balance
FROM account
WHERE account_id = 200
FOR UPDATE;

-- Ứng dụng kiểm tra số dư nguồn và quy tắc nghiệp vụ.
UPDATE account
SET balance = balance - 50
WHERE account_id = 100
  AND balance >= 50;

-- Kiểm tra cập nhật đúng một hàng.
UPDATE account
SET balance = balance + 50
WHERE account_id = 200;

-- Chỉ commit nếu cả hai cập nhật thành công.
COMMIT;
```

Với giao dịch ngược chiều, từ 200 sang 100, thứ tự khóa vẫn là 100 rồi 200. Sau khi đã lấy đủ khóa, ứng dụng mới xác định hàng nào là nguồn và hàng nào là đích để áp dụng phép trừ/cộng.

Trong mã thực tế, nếu cập nhật nguồn không tác động đúng một hàng vì không đủ tiền, transaction phải rollback. Nếu cập nhật đích thất bại, transaction cũng phải rollback để tránh tiền bị trừ mà không được cộng. Lịch sử giao dịch nên được ghi trong cùng transaction nếu tính đúng đắn yêu cầu số dư và ledger luôn đồng bộ.

## 6. Xử lý danh sách ID động

Nhiều nghiệp vụ chỉ biết danh sách hàng cần khóa sau khi đọc dữ liệu đầu vào hoặc tính toán. Để giữ thứ tự nhất quán:

1. Xác định toàn bộ tài nguyên có thể cần thay đổi trước khi khóa.
2. Chuẩn hóa ID, loại bỏ trùng lặp và kiểm tra quyền truy cập.
3. Sắp xếp theo thứ tự toàn cục.
4. Mở transaction và lấy khóa theo đúng thứ tự.
5. Kiểm tra lại các điều kiện nghiệp vụ trong transaction.
6. Cập nhật và kết thúc transaction.

Ví dụ giả mã:

```text
ids = determineAffectedProductIds(request)
ids = distinct(ids)
ids = sortAscending(ids)

beginTransaction()
try:
    lockedRows = []
    for id in ids:
        row = selectInventoryForUpdate(id)
        if row does not exist:
            raise ProductNotFound(id)
        lockedRows.add(row)

    validateBusinessRules(lockedRows)
    applyChanges(lockedRows)
    commit()
catch error:
    rollback()
    raise error
```

Không nên khóa một số hàng, sau đó mới phát hiện cần thêm một hàng đứng trước chúng trong thứ tự toàn cục. Ví dụ transaction đã khóa inventory 27 rồi mới phát hiện cần inventory 4. Nếu một transaction khác đã khóa 4 và đang chờ 27, thứ tự toàn cục đã bị phá vỡ và deadlock có thể xảy ra.

Nếu không thể biết đầy đủ tài nguyên từ đầu, có một số cách xử lý:

- Tách bước xác định tài nguyên khỏi transaction ghi, sau đó bắt đầu transaction mới và khóa danh sách đã sắp xếp; phải kiểm tra lại dữ liệu vì danh sách có thể thay đổi.
- Nếu trong lúc thực thi phát hiện cần thêm khóa đứng trước khóa đã giữ, rollback và khởi động lại với danh sách tài nguyên mới.
- Dùng một hàng guard hoặc khóa điều phối cấp cao hơn nếu tập tài nguyên thay đổi liên tục và khó khóa theo danh sách ổn định.
- Chuyển nghiệp vụ sang Serializable nếu cần bảo vệ điều kiện trên tập dữ liệu và không thể duy trì thứ tự khóa thủ công.

Việc đọc danh sách tài nguyên trước transaction chỉ giúp lập kế hoạch. Nó không bảo đảm dữ liệu vẫn như cũ khi transaction ghi bắt đầu, nên các điều kiện nghiệp vụ vẫn phải được xác nhận lại trong transaction.

## 7. Khóa chia sẻ, khóa độc quyền và nâng cấp khóa

Thứ tự lấy khóa không chỉ liên quan đến hàng nào được khóa, mà còn liên quan đến chế độ khóa. Hai transaction có thể cùng lấy shared lock (S-lock) để đọc một hàng. Nếu cả hai sau đó đều muốn cập nhật và nâng cấp S-lock thành exclusive lock (X-lock), chúng có thể chờ nhau:

```text
T1: S-lock(A) -> được cấp
T2: S-lock(A) -> được cấp

T1: yêu cầu nâng cấp lên X-lock(A) -> chờ T2 nhả S-lock
T2: yêu cầu nâng cấp lên X-lock(A) -> chờ T1 nhả S-lock
```

Đây là deadlock do lock upgrade. Hai transaction không khóa nhiều hàng theo thứ tự ngược nhau; chúng cùng giữ một khóa chia sẻ rồi cùng cần độc quyền.

Nếu ngay từ đầu transaction biết sẽ cập nhật hàng, hãy cân nhắc xin khóa cập nhật/độc quyền phù hợp ngay trong lần đọc đầu tiên, thay vì cùng lấy khóa chia sẻ rồi nâng cấp. Ví dụ dùng `SELECT ... FOR UPDATE` trên PostgreSQL, MySQL/InnoDB hoặc Oracle; SQL Server có thể dùng `UPDLOCK` khi phù hợp. Tên và mức khóa cụ thể phụ thuộc engine.

Không phải lúc nào cũng nên dùng X-lock. Khóa mạnh hơn làm giảm khả năng đồng thời. Chỉ xin chế độ khóa đủ mạnh cho thao tác dự kiến, và bảo đảm mọi luồng liên quan tuân theo cùng quy tắc.

## 8. Các khóa ngầm có thể phá vỡ thứ tự dự kiến

Ứng dụng thường nhìn thấy các câu `SELECT ... FOR UPDATE`, `UPDATE` hoặc `DELETE`, nhưng database có thể lấy thêm khóa khi thực hiện những thao tác khác. Những khóa này cũng tham gia vào wait-for graph.

Các nguồn khóa ngầm thường gặp:

- **Foreign key:** chèn hoặc cập nhật khóa ngoại có thể cần kiểm tra hàng được tham chiếu và lấy khóa tương ứng.
- **Unique index:** chèn hoặc cập nhật khóa duy nhất phải kiểm tra xung đột với giá trị đang được transaction khác ghi.
- **Trigger:** trigger có thể cập nhật bảng khác theo thứ tự không giống luồng ứng dụng.
- **Cascade:** `ON DELETE CASCADE` hoặc `ON UPDATE CASCADE` có thể tác động nhiều bảng và hàng liên quan.
- **Index maintenance:** cập nhật cột được lập chỉ mục làm thay đổi cấu trúc chỉ mục và có thể tạo thêm khóa.
- **Lock escalation:** một số engine có thể nâng nhiều khóa nhỏ thành khóa phạm vi lớn hơn, chẳng hạn page hoặc table lock.

Ví dụ, luồng A khóa hàng `orders` rồi cập nhật `customer`, trong khi trigger của luồng B khóa `customer` rồi cập nhật `orders`. Dù hai đoạn code chính không thể hiện thứ tự ngược nhau, các thao tác do trigger thực hiện vẫn có thể tạo deadlock.

Để xử lý, hãy đưa thứ tự truy cập các bảng và các thao tác do trigger/constraint/cascade gây ra vào thiết kế chung. Khi có deadlock trong môi trường thật, đọc deadlock graph hoặc báo cáo tương ứng của hệ quản trị để xác định chính xác resource và statement tham gia, thay vì chỉ nhìn câu SQL cuối cùng của ứng dụng.

## 9. Thứ tự khóa và chỉ mục

Chỉ mục ảnh hưởng đến cách database tìm hàng và có thể ảnh hưởng đến phạm vi cũng như thứ tự lấy khóa. Một truy vấn có thể dùng index seek, index scan hoặc table scan; mỗi kế hoạch có thể đi qua các khóa chỉ mục theo cách khác nhau.

Một số nguyên tắc:

- Dùng điều kiện tìm kiếm có chỉ mục phù hợp để tránh quét và khóa nhiều hàng không cần thiết.
- Nếu khóa theo primary key, hãy dùng chính khóa đó để xác định hàng cần khóa.
- Với predicate hoặc range lock, kiểm tra index được dùng và isolation level vì phạm vi khóa có thể bao gồm khoảng chỉ mục.
- Không suy ra thứ tự khóa nội bộ chỉ từ thứ tự kết quả trả về của câu SELECT.
- Sau thay đổi schema, index hoặc execution plan, kiểm thử lại những luồng có tranh chấp cao.

Thứ tự toàn cục ở tầng ứng dụng là một quy tắc về thứ tự yêu cầu khóa tài nguyên. Nó không phải lời khẳng định rằng mọi engine luôn lấy tất cả khóa nội bộ theo đúng thứ tự ID. Những khóa phụ do index, foreign key hoặc lock manager cần được xem xét riêng.

## 10. Khi nào thứ tự khóa vẫn chưa đủ?

Thứ tự lấy khóa nhất quán làm giảm deadlock do các transaction khóa cùng nhóm tài nguyên theo thứ tự khác nhau. Nó không tự giải quyết mọi loại tranh chấp.

### Predicate và hàng chưa tồn tại

Một transaction có thể khóa những hàng hiện có rồi dựa vào kết luận “không có hàng nào khác thỏa điều kiện”. Một transaction khác có thể chèn hàng mới thỏa predicate. Khóa hàng theo ID không nhất thiết bảo vệ khoảng trống hoặc toàn bộ điều kiện tìm kiếm.

Nếu quy tắc phụ thuộc vào một tập hàng, cân nhắc range/key-range lock, predicate lock, constraint phù hợp, hàng guard hoặc Serializable tùy hệ quản trị.

### Khóa tài nguyên ngoài database

Một transaction có thể giữ khóa database rồi chờ mutex trong ứng dụng; một luồng khác giữ mutex rồi chờ database. Vòng chờ khi đó trải qua hai loại tài nguyên. Thứ tự khóa database không thể tự ngăn vòng này nếu mutex không nằm trong cùng quy ước.

Nếu hệ thống dùng nhiều loại khóa, cần xác định thứ tự toàn cục giữa chúng hoặc tránh giữ khóa của loại này trong khi chờ loại khác. Đặc biệt, không giữ transaction mở trong lúc gọi dịch vụ bên ngoài hoặc chờ người dùng.

### Lock escalation và tranh chấp ở mức bảng

Một transaction khóa nhiều hàng có thể khiến engine nâng cấp khóa lên phạm vi rộng hơn. Một transaction khác chỉ khóa một hàng có thể bị chặn bởi table/page lock. Việc nâng cấp phạm vi khóa có thể làm xuất hiện quan hệ chờ ngoài thứ tự ID hàng ban đầu. Hãy kiểm tra ngưỡng và hành vi lock escalation của engine, đồng thời giới hạn số hàng xử lý trong mỗi transaction khi phù hợp.

## 11. Giảm thời gian giữ khóa

Ngay cả khi thứ tự khóa đúng, transaction giữ khóa lâu vẫn làm tăng thời gian chờ và giảm throughput. Một số cách giảm thời gian giữ khóa:

1. Tính toán dữ liệu đầu vào trước khi bắt đầu transaction nếu có thể.
2. Mở transaction ngay trước các thao tác đọc/ghi cần đồng bộ hóa.
3. Khóa đủ tài nguyên cần thiết theo thứ tự chuẩn rồi thực hiện thay đổi liên tiếp.
4. Không gọi HTTP API, gửi email, ghi file hoặc chờ người dùng trong khi đang giữ khóa.
5. Commit sớm sau khi trạng thái database đã nhất quán.
6. Chia batch lớn thành các transaction nhỏ nếu nghiệp vụ cho phép và vẫn giữ được tính đúng đắn.
7. Theo dõi transaction chạy lâu và lock wait để phát hiện luồng xử lý giữ khóa quá lâu.

Không nên rút ngắn transaction bằng cách commit giữa các bước mà nghiệp vụ yêu cầu nguyên tử. Nếu hai cập nhật phải cùng thành công hoặc cùng thất bại, chúng phải nằm trong cùng transaction dù thời gian giữ khóa cần được tối ưu.

## 12. Phát hiện deadlock và xử lý retry

Thứ tự khóa là biện pháp phòng ngừa, nhưng ứng dụng vẫn phải xử lý deadlock vì hệ thống có thể có nhiều luồng ghi, khóa ngầm và tài nguyên ngoài database.

Khi database báo deadlock victim:

1. Transaction bị chọn làm nạn nhân phải rollback theo yêu cầu của driver/engine.
2. Không tiếp tục sử dụng kết quả đọc hoặc quyết định đã dựa trên transaction thất bại.
3. Nếu nghiệp vụ có thể retry an toàn, bắt đầu transaction mới và chạy lại toàn bộ đơn vị công việc.
4. Giới hạn số lần retry và dùng backoff có jitter để các transaction không va chạm liên tục.
5. Ghi log loại lỗi, mã lỗi, thời gian, tài nguyên và transaction correlation ID để điều tra.

Không nên chỉ retry statement cuối. Transaction có thể đã đọc dữ liệu cũ, giữ các giả định không còn đúng hoặc thực hiện một phần công việc trước khi bị rollback. Chạy lại toàn bộ transaction giúp các quyết định được tính từ trạng thái mới.

Nếu transaction có tác dụng phụ ngoài database, như gửi thông báo hoặc gọi dịch vụ thanh toán, cần dùng idempotency key hoặc transactional outbox để retry không tạo tác dụng phụ trùng lặp.

Deadlock khác lock timeout. Deadlock có vòng chờ; database có thể phát hiện và chủ động hủy một transaction. Lock timeout chỉ cho biết một thao tác đã chờ quá lâu; có thể không tồn tại vòng chờ nào. Cả hai đều cần xử lý lỗi, nhưng cách điều tra và quyết định retry có thể khác nhau.

## 13. Quy trình áp dụng thứ tự khóa trong một hệ thống

Một quy trình triển khai thực tế có thể đi theo các bước sau:

1. **Liệt kê tài nguyên:** xác định mọi hàng, bảng, phạm vi và tài nguyên ngoài database mà từng nghiệp vụ có thể khóa.
2. **Xây dựng thứ tự toàn cục:** chọn rank cho loại tài nguyên, rồi dùng ID ổn định để sắp xếp trong từng loại.
3. **Chuẩn hóa helper:** tạo hàm hoặc repository dùng chung để khóa một hoặc nhiều tài nguyên theo thứ tự chuẩn.
4. **Rà soát mọi luồng ghi:** bao gồm API, batch job, trigger, cascade, tác vụ nền và công cụ quản trị.
5. **Khóa trước khi cập nhật:** xác định đủ tài nguyên, lấy khóa theo thứ tự và chỉ sau đó mới thay đổi dữ liệu.
6. **Xử lý tài nguyên phát hiện muộn:** rollback và khởi động lại nếu cần khóa một tài nguyên đứng trước tài nguyên đã giữ.
7. **Kiểm thử cạnh tranh:** chạy hai hoặc nhiều transaction theo các hướng ngược nhau, cố tình tạo lịch xen kẽ và xác nhận không còn vòng chờ do thứ tự ngược.
8. **Theo dõi production:** phân tích deadlock graph, lock wait và transaction chạy lâu để cập nhật quy tắc khi phát sinh đường truy cập mới.

Một helper khóa chung chỉ hữu ích khi tất cả luồng liên quan thực sự sử dụng nó. Nếu một service tự viết SQL và lấy khóa theo thứ tự khác, quy tắc toàn cục không còn được bảo đảm.

## 14. Ví dụ kiểm thử hai giao dịch ngược chiều

Giả sử có hai hàng tài khoản 100 và 200. Mục tiêu là kiểm tra hai luồng chuyển tiền chạy đồng thời.

### Trường hợp lấy khóa không nhất quán

- T1 khóa 100, rồi yêu cầu 200.
- T2 khóa 200, rồi yêu cầu 100.
- Điều khiển hai phiên để cả hai đã giữ khóa đầu tiên trước khi yêu cầu khóa thứ hai.
- Quan sát deadlock và transaction bị chọn rollback.

### Trường hợp lấy khóa theo thứ tự ID tăng dần

- T1 và T2 đều yêu cầu khóa 100 trước.
- Một transaction lấy được khóa 100; transaction còn lại chờ và chưa giữ khóa 200.
- Transaction thắng lấy khóa 200, cập nhật và commit.
- Transaction chờ lấy được khóa 100 rồi tiếp tục lấy khóa 200.
- Không có vòng chờ do thứ tự hai tài khoản bị đảo ngược.

Kiểm thử nên dùng hai connection thật và có barrier/latch để điều khiển thời điểm mỗi transaction lấy khóa. Chạy hai câu lệnh tuần tự trên một connection không thể chứng minh quy tắc hoạt động dưới cạnh tranh.

## 15. Những điểm cần ghi nhớ

- Deadlock xảy ra khi các transaction chờ nhau theo một vòng khép kín trong wait-for graph.
- Thứ tự lấy khóa nhất quán yêu cầu mọi transaction khóa các tài nguyên theo cùng một thứ tự toàn cục, chẳng hạn ID tăng dần.
- Với nhiều bảng, cần quy định cả thứ tự giữa các loại tài nguyên và thứ tự ID trong từng loại.
- Hãy xác định đủ tài nguyên trước khi khóa; nếu phát hiện cần thêm tài nguyên đứng trước khóa đã giữ, rollback và khởi động lại.
- Nếu biết sẽ ghi, cân nhắc xin khóa cập nhật/độc quyền ngay từ đầu để tránh nhiều transaction cùng nâng cấp shared lock.
- `ORDER BY` của câu SELECT không phải bằng chứng portable rằng engine lấy khóa theo thứ tự kết quả; kiểm tra semantics hoặc khóa tuần tự theo ID đã sắp xếp.
- Foreign key, unique index, trigger, cascade, index maintenance và lock escalation có thể tạo khóa ngầm cần đưa vào phân tích.
- Thứ tự khóa giảm nguy cơ deadlock nhưng không loại bỏ mọi vòng chờ, nhất là khi có predicate, khóa ngoài database hoặc tài nguyên ẩn.
- Transaction nên ngắn và không chờ dịch vụ bên ngoài khi đang giữ khóa.
- Khi gặp deadlock victim, rollback và retry toàn bộ transaction có giới hạn nếu nghiệp vụ cho phép; không chỉ chạy lại statement cuối.
