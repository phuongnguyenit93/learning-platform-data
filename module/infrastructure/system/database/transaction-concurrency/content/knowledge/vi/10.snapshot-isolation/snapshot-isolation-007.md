# Chuyển bất biến nhiều hàng thành điểm tranh chấp được bảo vệ

Trong cơ sở dữ liệu, một quy tắc nghiệp vụ đôi khi phụ thuộc vào nhiều hàng cùng lúc. Ví dụ, một ca trực phải luôn có ít nhất một bác sĩ đang trực; một kho phải giữ đủ số lượng hàng tối thiểu; hoặc một nhóm chỉ được phép có tối đa một người giữ vai trò trưởng nhóm. Những quy tắc như vậy được gọi là **bất biến nhiều hàng** (*multi-row invariant*) vì tính đúng đắn của chúng phụ thuộc vào trạng thái kết hợp của nhiều bản ghi.

Với mức cô lập ảnh chụp (*snapshot isolation*), mỗi giao dịch có thể đọc cùng một ảnh chụp nhất quán rồi cập nhật các hàng khác nhau. Hai giao dịch riêng lẻ đều có thể thấy rằng thao tác của mình hợp lệ, nhưng khi cả hai cùng commit, trạng thái kết hợp lại vi phạm quy tắc nghiệp vụ. Đây là dạng vấn đề thường được gọi là **write skew**.

Một cách xử lý là chuyển quy tắc nhiều hàng thành một **điểm tranh chấp được bảo vệ** (*protected contention point*): mọi giao dịch có khả năng làm thay đổi bất biến đều phải tranh quyền trên cùng một tài nguyên điều phối trước khi kiểm tra và thay đổi dữ liệu. Tài nguyên này có thể là một hàng khóa bảo vệ, một hàng lưu bộ đếm tổng hợp, hoặc một cơ chế tuần tự hóa tương đương. Nhờ đó, các quyết định ảnh hưởng đến cùng một bất biến được thực hiện theo thứ tự.

## 1. Bất biến nhiều hàng và write skew

Giả sử hệ thống quản lý lịch trực của một nhóm bác sĩ. Quy tắc nghiệp vụ là:

> Mỗi nhóm phải luôn có ít nhất một bác sĩ đang trực.

Bảng `doctor` có thể lưu trạng thái trực của từng bác sĩ:

| doctor_id | team_id | on_call |
|---:|---:|---|
| 101 | 7 | true |
| 102 | 7 | true |

Ban đầu nhóm 7 có hai bác sĩ đang trực. T1 muốn cho bác sĩ 101 nghỉ trực; T2 đồng thời muốn cho bác sĩ 102 nghỉ trực.

Ở mức snapshot isolation, cả hai giao dịch có thể bắt đầu từ cùng một snapshot và cùng đếm được hai bác sĩ đang trực. T1 cập nhật hàng 101; T2 cập nhật hàng 102. Vì hai giao dịch sửa hai hàng khác nhau, chúng có thể không tạo xung đột ghi trên cùng một hàng.

```text
Snapshot ban đầu của cả T1 và T2:
  Bác sĩ 101: on_call = true
  Bác sĩ 102: on_call = true
  Số bác sĩ đang trực = 2

T1                                      T2
----------------------------------------------------------------
Đọc snapshot: có 2 người trực          Đọc snapshot: có 2 người trực
Tắt trực bác sĩ 101                    Tắt trực bác sĩ 102
Ghi hàng 101                            Ghi hàng 102
COMMIT                                  COMMIT

Trạng thái sau cùng:
  Bác sĩ 101: on_call = false
  Bác sĩ 102: on_call = false
  Số bác sĩ đang trực = 0  <-- vi phạm bất biến
```

Mỗi giao dịch đều dựa trên một snapshot hợp lệ và cập nhật một hàng riêng. Tuy nhiên, quyết định “có thể cho người này nghỉ trực không?” phụ thuộc vào toàn bộ tập bác sĩ đang trực. Chỉ kiểm tra số lượng trong snapshot riêng của từng giao dịch không đủ để bảo vệ bất biến.

Đây là điểm khác biệt giữa xung đột ghi trên cùng hàng và xung đột logic trên nhiều hàng. Hệ quản trị có thể phát hiện hai giao dịch cùng sửa một hàng, nhưng không phải mọi trường hợp write skew đều tạo ra xung đột ghi trực tiếp.

## 2. Ý tưởng: tạo một tài nguyên chung để các giao dịch phải tranh quyền

Thay vì để mỗi giao dịch chỉ kiểm tra các hàng bác sĩ rồi tự quyết định, ta tạo một hàng điều phối cho mỗi nhóm. Ví dụ:

```sql
CREATE TABLE team_guard (
    team_id BIGINT PRIMARY KEY,
    lock_version BIGINT NOT NULL DEFAULT 0
);
```

Hàng `team_guard` không nhất thiết lưu dữ liệu nghiệp vụ. Nó đại diện cho quyền điều phối các thay đổi có thể ảnh hưởng đến bất biến của nhóm đó.

Quy tắc bắt buộc là:

1. Giao dịch xác định nhóm mà bất biến cần được bảo vệ.
2. Giao dịch lấy khóa trên hàng điều phối của nhóm.
3. Sau khi đã có quyền điều phối, giao dịch đọc trạng thái liên quan và kiểm tra bất biến.
4. Nếu thao tác vẫn hợp lệ, giao dịch cập nhật các hàng nghiệp vụ.
5. Giao dịch commit và giải phóng khóa điều phối.

Vì mọi giao dịch thay đổi trạng thái trực đều phải lấy khóa trên cùng hàng `team_guard` của nhóm 7, chỉ một giao dịch có thể đi qua vùng kiểm tra và cập nhật tại một thời điểm. Giao dịch tiếp theo phải đợi giao dịch trước commit hoặc rollback rồi mới kiểm tra trạng thái mới.

```text
T1: lấy khóa team_guard(7)
    đọc trạng thái bác sĩ
    kiểm tra bất biến
    cập nhật bác sĩ 101
    COMMIT, nhả khóa
                 |
                 v
T2:          lấy được khóa team_guard(7)
             đọc trạng thái mới nhất phù hợp
             kiểm tra bất biến
             phát hiện chỉ còn 1 người trực
             từ chối tắt trực bác sĩ 102
```

Điểm tranh chấp được bảo vệ biến một quy tắc phân tán trên nhiều hàng thành một điểm điều phối chung. Nó không làm cho dữ liệu nghiệp vụ chỉ còn một hàng; nó tạo ra một nơi mà các giao dịch phải đồng thuận về thứ tự xử lý.

## 3. Bảo vệ bất biến bằng hàng khóa điều phối

Ví dụ sau minh họa cách dùng `SELECT ... FOR UPDATE` để khóa hàng điều phối. Mã giả giả định hệ quản trị hỗ trợ cú pháp này và giao dịch chạy ở `READ COMMITTED`, trong đó câu truy vấn đếm sau khi lấy được khóa có snapshot mới của câu lệnh.

```sql
BEGIN;

-- Mọi thay đổi trạng thái trực của team 7 đều khóa cùng hàng này trước.
SELECT team_id
FROM team_guard
WHERE team_id = 7
FOR UPDATE;

-- Truy vấn này được thực hiện sau khi đã lấy được khóa điều phối.
SELECT COUNT(*) AS active_count
FROM doctor
WHERE team_id = 7
  AND on_call = TRUE;

-- Ứng dụng kiểm tra kết quả:
-- Nếu active_count <= 1 thì ROLLBACK và từ chối cho bác sĩ nghỉ trực.
-- Nếu active_count > 1 thì tiếp tục cập nhật.

UPDATE doctor
SET on_call = FALSE
WHERE doctor_id = 101
  AND team_id = 7
  AND on_call = TRUE;

COMMIT;
```

Trong ứng dụng thực tế, cần kiểm tra số hàng bị ảnh hưởng bởi câu `UPDATE`. Nếu bác sĩ không tồn tại, không thuộc nhóm đó hoặc đã được thay đổi bởi một thao tác khác, ứng dụng nên rollback để toàn bộ quyết định và cập nhật được giữ nhất quán.

Điều quan trọng nhất là **thứ tự thao tác**. Giao dịch phải lấy khóa điều phối trước khi đọc dữ liệu để quyết định có được phép thay đổi hay không. Nếu đọc và kiểm tra trước rồi mới lấy khóa, hai giao dịch vẫn có thể cùng đưa ra quyết định dựa trên trạng thái cũ.

### Điều kiện để mẫu khóa điều phối có hiệu lực

- Mọi đường ghi có thể ảnh hưởng đến bất biến đều phải khóa cùng hàng điều phối: API, tác vụ nền, công cụ quản trị, import và batch job.
- Phạm vi khóa phải trùng với phạm vi bất biến. Nếu quy tắc áp dụng cho từng nhóm và từng ca trực, khóa có thể cần khóa theo cặp `(team_id, shift_id)`.
- Hàng điều phối phải tồn tại trước khi giao dịch yêu cầu khóa. Nếu không tìm thấy hàng, không được âm thầm bỏ qua bước khóa.
- Giữ khóa cho đến khi các thay đổi nghiệp vụ commit hoặc rollback. Không nhả khóa giữa bước kiểm tra và bước cập nhật.
- Khi một giao dịch cần khóa nhiều điểm điều phối, mọi giao dịch nên lấy chúng theo cùng một thứ tự để giảm nguy cơ deadlock.

## 4. Snapshot isolation cần được chú ý khi dùng hàng khóa

Một hàng khóa không tự động làm mới snapshot mà giao dịch đã có. Đây là điểm rất quan trọng khi triển khai mẫu điều phối trong hệ thống dùng snapshot isolation.

Ở các hệ quản trị và mức cô lập sử dụng snapshot cố định cho cả giao dịch, giao dịch có thể đã tạo snapshot trước khi chờ khóa điều phối. Sau khi lấy được khóa, một truy vấn đọc thông thường vẫn có thể nhìn thấy snapshot cũ theo quy tắc của hệ quản trị. Khi đó, giao dịch có thể tiếp tục đưa ra quyết định dựa trên dữ liệu cũ dù nó đã đợi giao dịch trước nhả khóa.

Vì vậy, không nên giả định rằng chỉ cần `SELECT ... FOR UPDATE` trên hàng guard là đủ trong mọi mức cô lập. Cần chọn một trong các cách sau dựa trên hệ quản trị cụ thể:

- Dùng `READ COMMITTED` với quy trình khóa điều phối trước, sau đó đọc lại trạng thái bằng câu lệnh mới. Trong mô hình này, câu lệnh đọc sau khi chờ khóa có thể nhìn thấy các commit đã hoàn tất trước khi câu lệnh bắt đầu.
- Dùng `SERIALIZABLE` và xử lý lỗi serialization bằng cách retry toàn bộ giao dịch. Hệ quản trị có thể từ chối một lịch thực thi không tương đương thứ tự tuần tự.
- Nếu dùng snapshot isolation, tạo xung đột ghi có chủ đích trên hàng guard, chẳng hạn tăng `lock_version`, để các giao dịch cạnh tranh cùng cập nhật một hàng. Phải hiểu chính xác hành vi của hệ quản trị và retry khi có lỗi xung đột hoặc serialization.

Ví dụ cập nhật phiên bản guard:

```sql
BEGIN;

-- Mỗi giao dịch thay đổi trạng thái trực đều cập nhật cùng hàng guard.
UPDATE team_guard
SET lock_version = lock_version + 1
WHERE team_id = 7;

-- Sau khi cập nhật guard thành công, kiểm tra và cập nhật dữ liệu nghiệp vụ
-- theo quy tắc snapshot/locking đã chọn cho hệ quản trị.

COMMIT;
```

Việc cập nhật cùng một hàng tạo ra điểm xung đột ghi rõ ràng. Một giao dịch có thể phải đợi hoặc bị từ chối khi phiên bản guard đã thay đổi kể từ snapshot của nó. Ứng dụng phải nhận diện lỗi tương ứng và chạy lại toàn bộ giao dịch từ đầu với snapshot mới. Câu lệnh trên chỉ minh họa cơ chế tạo xung đột; nó không thay thế việc xác minh ngữ nghĩa snapshot, khóa và retry của sản phẩm cơ sở dữ liệu đang dùng.

## 5. Cách khác: vật chất hóa bất biến thành bộ đếm tổng hợp

Nếu bất biến có thể biểu diễn bằng một con số, có thể lưu con số đó trên một hàng điều phối và cập nhật nguyên tử cùng với dữ liệu chi tiết. Đây là cách **vật chất hóa trạng thái tổng hợp** (*materialized aggregate*).

Với ví dụ lịch trực, ta lưu số bác sĩ đang trực trong `team_guard`:

```sql
CREATE TABLE team_guard (
    team_id BIGINT PRIMARY KEY,
    active_count INTEGER NOT NULL CHECK (active_count >= 1)
);
```

`active_count` là số bác sĩ có `on_call = TRUE` trong nhóm. Bất biến “luôn có ít nhất một bác sĩ trực” được chuyển thành bất biến cục bộ trên một hàng: `active_count >= 1`.

Khi cho một bác sĩ nghỉ trực, ứng dụng giảm bộ đếm bằng một câu lệnh có điều kiện:

```sql
BEGIN;

UPDATE team_guard
SET active_count = active_count - 1
WHERE team_id = 7
  AND active_count > 1;

-- Nếu số hàng cập nhật = 0:
--   Không còn quyền giảm số người trực; ROLLBACK và từ chối yêu cầu.

UPDATE doctor
SET on_call = FALSE
WHERE doctor_id = 101
  AND team_id = 7
  AND on_call = TRUE;

-- Nếu số hàng cập nhật doctor khác 1: ROLLBACK.
-- Việc rollback cũng hoàn tác thay đổi active_count ở trên.

COMMIT;
```

Hai cập nhật phải nằm trong cùng một giao dịch. Nếu cập nhật bộ đếm thành công nhưng cập nhật hàng bác sĩ thất bại, rollback sẽ hoàn tác cả hai. Nếu cập nhật hàng bác sĩ thành công, bộ đếm và dữ liệu chi tiết cùng được commit.

Khi bật trực cho một bác sĩ, giao dịch cũng phải tăng bộ đếm và cập nhật hàng chi tiết trong cùng transaction:

```sql
BEGIN;

UPDATE team_guard
SET active_count = active_count + 1
WHERE team_id = 7;

UPDATE doctor
SET on_call = TRUE
WHERE doctor_id = 102
  AND team_id = 7
  AND on_call = FALSE;

-- Nếu hàng doctor không được cập nhật đúng một hàng: ROLLBACK.

COMMIT;
```

Các câu lệnh cập nhật trên cùng hàng `team_guard` được cơ sở dữ liệu điều phối. Điều kiện `active_count > 1` được đánh giá khi cập nhật có thể thực hiện theo quy tắc của hệ quản trị; giao dịch thứ hai không thể dựa vào cùng một giá trị bộ đếm cũ để giảm xuống dưới giới hạn nếu câu lệnh cập nhật được thực thi đúng ngữ nghĩa nguyên tử của hệ quản trị.

### Bộ đếm tổng hợp có những yêu cầu gì?

- Giá trị ban đầu phải khớp với dữ liệu chi tiết. Cần có bước khởi tạo hoặc đối soát khi đưa tính năng vào hệ thống.
- Mọi thao tác thêm, xóa hoặc đổi trạng thái bác sĩ phải cập nhật bộ đếm tương ứng trong cùng giao dịch.
- Phải xử lý trường hợp cập nhật lặp, cập nhật không tìm thấy hàng và retry để tránh tăng/giảm bộ đếm hai lần.
- Ràng buộc `CHECK` bảo vệ giá trị bộ đếm, nhưng không tự chứng minh bộ đếm khớp với số hàng thực tế. Sự nhất quán giữa bộ đếm và dữ liệu chi tiết đến từ giao thức cập nhật chung và transaction.
- Nên có tác vụ đối soát để phát hiện sai lệch nếu dữ liệu có thể được sửa bởi công cụ ngoài luồng ứng dụng.

## 6. Chọn hàng khóa hay bộ đếm tổng hợp?

Hai cách đều tạo ra một điểm tranh chấp được bảo vệ, nhưng phục vụ mục tiêu khác nhau.

| Tiêu chí | Hàng khóa điều phối | Bộ đếm tổng hợp |
|---|---|---|
| Dữ liệu bổ sung | Một hàng đại diện cho phạm vi bất biến | Một hàng lưu trạng thái tổng hợp |
| Kiểm tra nghiệp vụ | Đọc lại các hàng chi tiết sau khi có quyền điều phối | Kiểm tra và cập nhật bộ đếm bằng điều kiện nguyên tử |
| Phù hợp khi | Quy tắc phức tạp, cần đọc nhiều dữ liệu để quyết định | Quy tắc có thể biểu diễn bằng số đếm, tổng hoặc hạn mức |
| Chi phí | Các giao dịch cùng phạm vi phải chờ khóa guard | Các cập nhật cùng bộ đếm phải tuần tự hóa trên hàng đó |
| Rủi ro chính | Đọc snapshot cũ nếu dùng sai mức cô lập hoặc thứ tự thao tác | Bộ đếm lệch dữ liệu chi tiết nếu có đường ghi bỏ qua giao thức |

Nếu điều kiện chỉ là “số lượng không vượt hạn mức”, một câu lệnh cập nhật nguyên tử có điều kiện thường rất phù hợp. Nếu điều kiện cần tính toán phức tạp trên nhiều hàng, một hàng khóa điều phối có thể giúp các giao dịch kiểm tra tuần tự. Có thể kết hợp cả hai: khóa guard để điều phối và bộ đếm để kiểm tra nhanh.

## 7. Phạm vi điểm tranh chấp quyết định khả năng đồng thời

Nếu toàn bộ hệ thống chỉ có một hàng guard toàn cục, mọi giao dịch thay đổi lịch trực của mọi nhóm sẽ phải chờ nhau, kể cả khi chúng không liên quan. Điều này bảo vệ được bất biến nhưng làm giảm khả năng đồng thời không cần thiết.

Hãy tạo điểm tranh chấp ở phạm vi nhỏ nhất có thể bảo vệ đúng bất biến:

- Nếu bất biến áp dụng cho từng nhóm, dùng một guard cho mỗi `team_id`.
- Nếu bất biến áp dụng riêng cho từng ca trực, dùng khóa theo `(team_id, shift_id)`.
- Nếu một giao dịch thay đổi hai nhóm, nó phải khóa cả hai guard theo thứ tự nhất quán, ví dụ tăng dần theo `team_id`.
- Nếu hai bất biến dùng chung dữ liệu, cần xác định phạm vi giao nhau và thứ tự lấy khóa để không bỏ sót xung đột.

Ví dụ, T1 cập nhật nhóm 7 và nhóm 9, trong khi T2 cập nhật nhóm 9 và nhóm 7. Nếu T1 khóa 7 rồi 9 còn T2 khóa 9 rồi 7, hai giao dịch có thể tạo deadlock. Nếu cả hai luôn khóa nhóm theo thứ tự tăng dần, chúng sẽ tranh quyền theo cùng một thứ tự.

## 8. Chi phí của việc tuần tự hóa có chủ đích

Điểm tranh chấp làm giảm khả năng xảy ra write skew bằng cách buộc các giao dịch liên quan phải xếp hàng. Đây là sự đánh đổi có chủ đích: một phần thao tác không còn chạy song song, nhưng quyết định nghiệp vụ được bảo vệ theo thứ tự.

Các rủi ro cần quản lý:

- **Điểm nóng (hot row):** một guard được truy cập quá thường xuyên có thể trở thành nút thắt cổ chai.
- **Giao dịch giữ khóa lâu:** truy vấn chậm hoặc gọi dịch vụ bên ngoài khi đang giữ guard làm tăng thời gian chờ của giao dịch khác.
- **Deadlock:** một giao dịch khóa nhiều guard hoặc nhiều hàng theo thứ tự khác nhau có thể tạo chu trình chờ.
- **Retry:** mức `SERIALIZABLE` hoặc cơ chế phát hiện xung đột có thể hủy giao dịch; ứng dụng cần retry toàn bộ đơn vị công việc khi lỗi có thể thử lại.
- **Đường ghi bị bỏ sót:** chỉ một tác vụ cập nhật không tuân thủ giao thức cũng có thể phá vỡ bất biến.

Để giảm các chi phí này, hãy giới hạn guard theo đúng phạm vi dữ liệu, giữ transaction ngắn, khóa theo thứ tự thống nhất và theo dõi thời gian chờ. Không giữ khóa trong khi chờ người dùng hoặc gọi API bên ngoài.

## 9. Khi nào nên dùng SERIALIZABLE thay vì tự tạo guard?

Với một số bất biến, việc xác định chính xác hàng nào cần khóa khá phức tạp. Ví dụ, quy tắc có thể phụ thuộc vào một điều kiện truy vấn theo khoảng, nhiều bảng hoặc tập hàng thay đổi theo thời gian. Nếu hệ quản trị hỗ trợ `SERIALIZABLE` đúng nghĩa, có thể dùng mức này để yêu cầu lịch thực thi tương đương một thứ tự tuần tự. Hệ quản trị có thể phát hiện xung đột phụ thuộc và từ chối một giao dịch thay vì cho phép kết quả vi phạm.

Ví dụ về luồng xử lý ở mức khái niệm:

```text
BEGIN TRANSACTION ISOLATION LEVEL SERIALIZABLE
    Đọc các hàng liên quan
    Kiểm tra bất biến nhiều hàng
    Cập nhật dữ liệu
COMMIT

Nếu hệ quản trị báo lỗi serialization:
    ROLLBACK (hoặc transaction đã bị hủy)
    Retry toàn bộ giao dịch từ đầu với snapshot mới
```

`SERIALIZABLE` không có nghĩa giao dịch chắc chắn không bị lỗi. Hệ quản trị có thể từ chối một giao dịch để bảo vệ tính tuần tự hóa; ứng dụng cần xử lý và retry phù hợp. Chi phí và cơ chế phát hiện phụ thuộc sản phẩm. Một guard row tường minh có thể dễ hiểu và dự đoán hơn cho một bất biến có phạm vi rõ ràng; `SERIALIZABLE` có thể phù hợp hơn khi phụ thuộc dữ liệu quá rộng hoặc khó mô hình hóa.

## 10. Quy trình thiết kế một điểm tranh chấp được bảo vệ

Khi gặp một quy tắc nghiệp vụ phụ thuộc nhiều hàng, có thể thực hiện theo trình tự sau:

1. **Phát biểu bất biến chính xác.** Ví dụ: “Mỗi nhóm và mỗi ca trực phải có ít nhất một bác sĩ đang trực”. Xác định phạm vi và điều kiện biên.
2. **Tìm các thao tác có thể phá vỡ bất biến.** Bao gồm tạo, xóa, chuyển trạng thái, chuyển nhóm, import và tác vụ nền.
3. **Xác định điểm điều phối chung.** Chọn hàng guard, bộ đếm tổng hợp, tài nguyên khóa hoặc cơ chế tuần tự hóa phù hợp.
4. **Đặt điểm tranh chấp trước bước đọc quyết định.** Mọi giao dịch liên quan phải lấy quyền điều phối trước khi đánh giá trạng thái.
5. **Thực hiện kiểm tra và cập nhật trong cùng transaction.** Không để khoảng trống giữa kiểm tra và ghi.
6. **Chọn mức cô lập và ngữ nghĩa snapshot phù hợp.** Kiểm tra cách hệ quản trị xử lý khóa, snapshot, xung đột ghi và lỗi serialization.
7. **Xử lý retry và deadlock.** Retry toàn bộ giao dịch từ đầu, có giới hạn số lần và chỉ với lỗi có thể thử lại.
8. **Kiểm chứng mọi đường ghi.** Đảm bảo không có tác vụ nào sửa dữ liệu chi tiết mà bỏ qua guard hoặc bộ đếm.
9. **Theo dõi điểm nóng và đối soát.** Đo thời gian chờ, tần suất retry và tính nhất quán của dữ liệu tổng hợp.

## 11. Những điều cần ghi nhớ

- Bất biến nhiều hàng có thể bị vi phạm bởi write skew ngay cả khi các giao dịch cập nhật những hàng khác nhau.
- Snapshot isolation cung cấp ảnh chụp nhất quán cho từng giao dịch, nhưng không tự bảo đảm mọi bất biến liên hàng.
- Hàng guard tạo một điểm tranh chấp chung để các giao dịch liên quan phải kiểm tra và cập nhật theo thứ tự.
- Bộ đếm tổng hợp chuyển một quy tắc nhiều hàng thành điều kiện trên một hàng, có thể bảo vệ bằng cập nhật nguyên tử và constraint.
- Mọi đường ghi phải tuân thủ cùng giao thức; nếu một đường ghi bỏ qua điểm điều phối, bất biến vẫn có thể bị phá vỡ.
- Hàng khóa không tự làm mới snapshot trong mọi hệ quản trị và mức cô lập. Phải kiểm tra ngữ nghĩa cụ thể, cân nhắc `READ COMMITTED`, cập nhật guard có xung đột ghi hoặc `SERIALIZABLE` cùng retry.
- Điểm tranh chấp nên có phạm vi nhỏ nhất phù hợp để bảo vệ đúng bất biến mà không tuần tự hóa các giao dịch không liên quan.

Thiết kế tốt biến quyết định “có được phép thay đổi trạng thái này không?” thành một thao tác có thể được điều phối rõ ràng. Khi mọi giao dịch liên quan phải đi qua cùng một điểm tranh chấp được bảo vệ, hệ thống có thể giữ bất biến nhiều hàng ngay cả khi nhiều người dùng cùng thao tác đồng thời.
