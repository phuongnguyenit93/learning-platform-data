# Ghi lệch qua ví dụ lịch trực của hai nhân viên

Snapshot Isolation (cô lập ảnh chụp) cho phép mỗi giao dịch làm việc trên một ảnh chụp nhất quán của dữ liệu tại một thời điểm. Nhờ vậy, giao dịch có thể đọc dữ liệu ổn định trong khi các giao dịch khác tiếp tục cập nhật. Tuy nhiên, hai giao dịch vẫn có thể cùng đưa ra quyết định dựa trên những dữ liệu mà chúng đã đọc, rồi ghi vào các hàng khác nhau. Khi các quyết định riêng lẻ đó kết hợp lại làm hỏng một quy tắc nghiệp vụ, ta gặp **write skew (ghi lệch)**.

Bài học này dùng lịch trực của hai nhân viên để minh họa hiện tượng đó. Quy tắc nghiệp vụ là: **mỗi ca trực phải có ít nhất một trong hai nhân viên đang trực**. Hai giao dịch cùng kiểm tra quy tắc trên một ảnh chụp cũ, mỗi giao dịch tắt lịch trực của một người khác nhau, và cả hai có thể commit. Kết quả là không còn ai trực dù mỗi giao dịch riêng lẻ đều thấy quyết định của mình là an toàn.

## 1. Bối cảnh: lịch trực của An và Bình

Giả sử một ca trực có hai nhân viên: An và Bình. Bảng `duty_roster` lưu trạng thái trực của từng người trong ca đó.

| Ca trực | Nhân viên | Đang trực? |
|---|---|---:|
| Ca sáng | An | Có |
| Ca sáng | Bình | Có |

Ứng dụng có quy tắc nghiệp vụ:

> Không được để một ca trực không có nhân viên nào đang trực. Trước khi cho một người nghỉ ca, phải bảo đảm còn ít nhất một người khác trực.

Ban đầu cả An và Bình đều đang trực. Mỗi người gửi yêu cầu nghỉ ca gần như cùng lúc:

- Giao dịch `T1` xử lý yêu cầu nghỉ của An.
- Giao dịch `T2` xử lý yêu cầu nghỉ của Bình.

Mỗi giao dịch đọc lịch trực, kiểm tra rằng người còn lại vẫn trực, rồi cập nhật trạng thái của nhân viên mình phụ trách.

## 2. Snapshot Isolation hoạt động như thế nào?

Với Snapshot Isolation (SI), một giao dịch đọc từ một ảnh chụp nhất quán của cơ sở dữ liệu. Ảnh chụp được xác định theo quy tắc của DBMS, thường gắn với thời điểm giao dịch bắt đầu hoặc thời điểm giao dịch thực hiện truy vấn đầu tiên. Giao dịch cũng nhìn thấy những thay đổi do chính nó tạo ra.

Điều quan trọng là ảnh chụp của `T1` và `T2` có thể giống nhau, dù hai giao dịch chạy đồng thời. Nếu cả hai bắt đầu trước khi giao dịch nào commit, cả hai có thể nhìn thấy trạng thái ban đầu:

| Giao dịch | Ảnh chụp mà giao dịch nhìn thấy |
|---|---|
| `T1` | An đang trực, Bình đang trực |
| `T2` | An đang trực, Bình đang trực |

Snapshot Isolation thường ngăn dirty read và giúp một giao dịch đọc lại dữ liệu từ cùng một ảnh chụp. Nhưng SI không đồng nghĩa với Serializable Isolation. Nó thường phát hiện xung đột khi hai giao dịch đồng thời ghi vào cùng một hàng, trong khi hai giao dịch ghi vào các hàng khác nhau vẫn có thể cùng commit.

Đó chính là điều làm cho write skew có thể xảy ra.

## 3. Lịch thực thi gây ra write skew

### Bước 1: Hai giao dịch cùng đọc trạng thái ban đầu

`T1` và `T2` bắt đầu trước khi có giao dịch nào commit. Cả hai đọc hai hàng của ca sáng và đều nhận được:

```text
An   = đang trực
Bình = đang trực
Số người đang trực = 2
```

`T1` xử lý yêu cầu cho An. Nó thấy Bình vẫn trực nên cho rằng An có thể nghỉ.

`T2` xử lý yêu cầu cho Bình. Nó thấy An vẫn trực nên cho rằng Bình có thể nghỉ.

Mỗi giao dịch đều kiểm tra trên cùng ảnh chụp hợp lệ tại thời điểm đọc. Chưa giao dịch nào nhìn thấy thay đổi chưa commit của giao dịch còn lại.

### Bước 2: Mỗi giao dịch ghi vào một hàng khác nhau

- `T1` cập nhật hàng của An: `on_duty = FALSE`.
- `T2` cập nhật hàng của Bình: `on_duty = FALSE`.

Hai giao dịch có tập hàng được ghi khác nhau:

| Giao dịch | Hàng đọc | Hàng ghi |
|---|---|---|
| `T1` | An, Bình | An |
| `T2` | An, Bình | Bình |

Do `T1` và `T2` ghi vào hai hàng khác nhau, cơ chế phát hiện xung đột ghi trên cùng hàng của Snapshot Isolation có thể không phát hiện xung đột nào. Cả hai giao dịch có thể tiếp tục đến `COMMIT`.

### Bước 3: Cả hai commit và quy tắc nghiệp vụ bị phá vỡ

Sau khi cả hai giao dịch commit, trạng thái mới là:

| Ca trực | Nhân viên | Đang trực? |
|---|---|---:|
| Ca sáng | An | Không |
| Ca sáng | Bình | Không |

Không còn ai trực. Mỗi giao dịch đã kiểm tra rằng người còn lại đang trực, nhưng kiểm tra đó dựa trên ảnh chụp trước khi giao dịch kia cập nhật.

Đây là **write skew**: các giao dịch đọc những dữ liệu có liên quan đến cùng một điều kiện nghiệp vụ, nhưng ghi vào các phần dữ liệu riêng biệt. Mỗi lần ghi riêng lẻ không xung đột, song kết hợp lại làm cho điều kiện chung không còn đúng.

## 4. Sơ đồ lịch thực thi

```text
Thời gian ↓

T1: Xử lý yêu cầu nghỉ của An       T2: Xử lý yêu cầu nghỉ của Bình
--------------------------------    -----------------------------------
BEGIN                               BEGIN
Đọc An = trực                       Đọc An = trực
Đọc Bình = trực                     Đọc Bình = trực
Kiểm tra: Bình còn trực             Kiểm tra: An còn trực
UPDATE An = nghỉ                    UPDATE Bình = nghỉ
COMMIT                              COMMIT

Trạng thái cuối: An = nghỉ, Bình = nghỉ
Quy tắc “mỗi ca có ít nhất một người trực” bị vi phạm.
```

Thứ tự chính xác giữa các câu lệnh có thể xen kẽ theo nhiều cách. Điều kiện cốt lõi là cả hai giao dịch đã đọc ảnh chụp cho thấy hai người đều trực trước khi các cập nhật riêng của chúng được commit.

## 5. Vì sao đây không phải lost update?

Write skew thường bị nhầm với lost update (mất cập nhật), nhưng hai hiện tượng có cấu trúc khác nhau.

| Đặc điểm | Lost update | Write skew |
|---|---|---|
| Dữ liệu được ghi | Thường cùng một hàng hoặc cùng một giá trị logic | Các giao dịch ghi vào những hàng khác nhau |
| Nguyên nhân | Một lần ghi dựa trên giá trị cũ ghi đè kết quả của lần ghi khác | Các quyết định riêng dựa trên dữ liệu đọc chung làm hỏng một bất biến |
| Phát hiện xung đột ghi cùng hàng | Có thể phát hiện hoặc ngăn chặn bằng khóa/kiểm tra phiên bản | Có thể không phát hiện vì tập hàng ghi không giao nhau |
| Ví dụ | Hai giao dịch cùng đọc số dư 100, mỗi giao dịch cộng 10 rồi ghi 110 | Hai nhân viên cùng được đánh dấu nghỉ vì mỗi giao dịch thấy người kia vẫn trực |

Trong ví dụ lịch trực, không có cập nhật nào ghi đè lên cập nhật của giao dịch còn lại. An được cập nhật thành nghỉ ở hàng của An; Bình được cập nhật thành nghỉ ở hàng của Bình. Cả hai giá trị đều được lưu. Lỗi nằm ở mối quan hệ giữa hai hàng và quy tắc nghiệp vụ áp dụng cho cả ca trực.

## 6. Nhìn write skew qua quan hệ phụ thuộc

Có thể giải thích vì sao lịch thực thi trên không tương đương với một thứ tự tuần tự hợp lệ bằng các phụ thuộc đọc-sau-ghi.

- `T1` đọc trạng thái của Bình trước khi `T2` ghi Bình thành nghỉ. Đây là một phụ thuộc đọc/ghi từ `T1` đến `T2`.
- `T2` đọc trạng thái của An trước khi `T1` ghi An thành nghỉ. Đây là một phụ thuộc đọc/ghi từ `T2` đến `T1`.

Ta có chu trình phụ thuộc:

```text
T1 ── đọc Bình trước lần ghi của T2 ──▶ T2
 ▲                                      │
 └──── đọc An trước lần ghi của T1 ─────┘
```

Chu trình này cho thấy không thể sắp xếp `T1` và `T2` thành một thứ tự tuần tự duy nhất mà vẫn giữ được kết quả quan sát của cả hai. Nếu chạy `T1` trước `T2`, khi `T2` kiểm tra thì An đã nghỉ và Bình không thể nghỉ tiếp. Nếu chạy `T2` trước `T1`, tình huống đối xứng xảy ra. Vì vậy lịch thực thi đã commit cả hai không conflict-serializable.

## 7. Vì sao Snapshot Isolation vẫn cho phép hiện tượng này?

Snapshot Isolation thường sử dụng quy tắc gần với **first-committer-wins** cho các cập nhật đồng thời trên cùng một hàng hoặc cùng một phiên bản dữ liệu. Nếu `T1` và `T2` cùng sửa một hàng, DBMS có thể buộc một giao dịch chờ hoặc hủy giao dịch để tránh ghi đè xung đột.

Trong ví dụ lịch trực:

- `T1` chỉ ghi hàng của An.
- `T2` chỉ ghi hàng của Bình.
- Không có hàng nào bị cả hai giao dịch cùng ghi.

Do đó, kiểm tra xung đột ghi cùng hàng không đủ để nhận ra rằng hai cập nhật riêng lẻ làm hỏng điều kiện “ít nhất một người trực”. SI bảo vệ ảnh chụp đọc và xử lý xung đột ghi theo quy tắc của nó, nhưng không tự động kiểm tra mọi bất biến nghiệp vụ liên quan đến nhiều hàng.

Đây là giới hạn quan trọng của Snapshot Isolation: **một lịch có thể không có xung đột ghi cùng hàng nhưng vẫn không tuần tự hóa được**.

## 8. Cách phòng tránh write skew

Không có một biện pháp duy nhất phù hợp với mọi DBMS và mọi mô hình dữ liệu. Cần chọn cách bảo vệ đúng bất biến nghiệp vụ, nghĩa là tất cả giao dịch có thể làm thay đổi điều kiện đó phải tham gia cùng một cơ chế điều phối.

### Cách 1: Dùng Serializable Isolation

Nếu nghiệp vụ yêu cầu kết quả tương đương với một thứ tự chạy tuần tự, có thể dùng isolation level `SERIALIZABLE`.

```sql
BEGIN TRANSACTION ISOLATION LEVEL SERIALIZABLE;

-- Đọc trạng thái trực của cả ca.
SELECT employee_id, on_duty
FROM duty_roster
WHERE shift_name = 'MORNING';

-- Ứng dụng kiểm tra còn người trực trước khi cập nhật.
UPDATE duty_roster
SET on_duty = FALSE
WHERE shift_name = 'MORNING'
  AND employee_id = 'AN';

COMMIT;
```

Với Serializable Isolation, DBMS phải bảo đảm kết quả tương đương với một thứ tự tuần tự hợp lệ. Khi hai giao dịch tạo ra phụ thuộc không thể tuần tự hóa, DBMS có thể hủy một giao dịch với lỗi serialization. Ứng dụng phải rollback và có thể retry toàn bộ giao dịch từ đầu, bao gồm cả bước đọc và kiểm tra.

Tên isolation level giống nhau không có nghĩa mọi hệ thống có cách triển khai giống nhau. Cần xem tài liệu DBMS để biết cách phát hiện xung đột, loại lỗi trả về và quy tắc retry.

### Cách 2: Khóa một tài nguyên điều phối chung

Một cách khác là làm cho các giao dịch cùng thay đổi lịch của một ca phải lấy cùng một khóa điều phối trước khi đọc và kiểm tra điều kiện. Ví dụ, có thể khóa hàng đại diện cho ca sáng:

```sql
BEGIN;

-- Khóa hàng đại diện cho ca trực trước khi kiểm tra lịch.
SELECT shift_name
FROM shift_guard
WHERE shift_name = 'MORNING'
FOR UPDATE;

-- Sau khi đã lấy khóa điều phối, đọc trạng thái hiện tại.
SELECT employee_id, on_duty
FROM duty_roster
WHERE shift_name = 'MORNING';

-- Chỉ cập nhật nếu vẫn còn ít nhất một người khác trực.
UPDATE duty_roster
SET on_duty = FALSE
WHERE shift_name = 'MORNING'
  AND employee_id = 'AN';

COMMIT;
```

Giao dịch xử lý ca sáng tiếp theo phải chờ khóa trên cùng hàng `shift_guard`. Khi giao dịch đầu tiên commit, giao dịch đang chờ tiếp tục và phải kiểm tra trạng thái mới nhất trước khi quyết định. Cách này chỉ hiệu quả khi **mọi đường ghi có thể ảnh hưởng đến quy tắc của ca đều khóa cùng tài nguyên điều phối**, và thứ tự lấy khóa được thực hiện đúng.

Chi tiết về snapshot và câu lệnh `SELECT ... FOR UPDATE` phụ thuộc DBMS. Ở một số hệ thống hoặc isolation level, giao dịch có ảnh chụp cũ có thể nhận lỗi serialization khi cố khóa hàng đã thay đổi. Ứng dụng cần xử lý lỗi đó bằng cách retry toàn bộ giao dịch theo hướng dẫn của DBMS.

### Cách 3: Khóa các hàng liên quan trước khi kiểm tra

Nếu hai giao dịch đều khóa cả hai hàng An và Bình trước khi kiểm tra rồi mới cập nhật, chúng phải tranh chấp trên ít nhất một khóa chung. Nhờ vậy, hai quyết định không thể cùng dựa trên trạng thái ban đầu mà cùng commit theo lịch write skew trên.

```sql
BEGIN;

SELECT employee_id, on_duty
FROM duty_roster
WHERE shift_name = 'MORNING'
ORDER BY employee_id
FOR UPDATE;

-- Kiểm tra trạng thái sau khi đã khóa các hàng liên quan.
-- Chỉ cho phép một người nghỉ nếu người còn lại vẫn trực.

UPDATE duty_roster
SET on_duty = FALSE
WHERE shift_name = 'MORNING'
  AND employee_id = 'AN';

COMMIT;
```

Khóa theo thứ tự ổn định, chẳng hạn `ORDER BY employee_id`, giúp giảm nguy cơ deadlock khi nhiều giao dịch khóa cùng tập hàng. Cần xác nhận DBMS khóa đúng các hàng cần thiết và áp dụng isolation level phù hợp; một giao dịch gặp lỗi do snapshot cũ vẫn phải được retry.

### Cách 4: Thiết kế dữ liệu để bất biến được bảo vệ trực tiếp

Nếu nghiệp vụ có thể mô hình hóa quy tắc thành một ràng buộc mà DBMS kiểm tra được, hãy cân nhắc dùng constraint hoặc thiết kế lại dữ liệu. Ví dụ, thay vì lưu hai cờ trực độc lập, có thể lưu một bản ghi phân công đại diện cho người chịu trách nhiệm chính của ca và chỉ cho phép thay đổi sau khi đã phân công người thay thế.

Một `CHECK` constraint thông thường trên từng hàng không thể tự kiểm tra tổng số nhân viên đang trực trên nhiều hàng. Với quy tắc tổng hợp như “ít nhất một hàng trong nhóm còn `on_duty = TRUE`”, cần cơ chế phù hợp như bảng đại diện, trigger được đồng bộ đúng cách, khóa điều phối hoặc Serializable Isolation. Không nên giả định rằng constraint đơn giản trên một hàng sẽ bảo vệ được bất biến nhiều hàng.

### Cách 5: Dùng một phiên bản/điểm ghi chung

Có thể bổ sung một hàng phiên bản cho ca trực. Mọi giao dịch thay đổi trạng thái nhân viên trong ca đều phải cập nhật hàng phiên bản đó. Khi hai giao dịch cùng cố cập nhật hàng chung, cơ chế xung đột ghi có thể buộc một giao dịch thất bại.

Sau lỗi xung đột, ứng dụng phải chạy lại toàn bộ thao tác đọc, kiểm tra và cập nhật với ảnh chụp mới. Chỉ cập nhật hàng phiên bản ở cuối mà không kiểm tra kết quả, không xử lý lỗi hoặc không retry đúng cách sẽ không bảo vệ được quy tắc nghiệp vụ.

## 9. Chọn biện pháp nào?

| Biện pháp | Khi phù hợp | Điều cần chú ý |
|---|---|---|
| Serializable Isolation | Bất biến liên quan đến nhiều hàng hoặc truy vấn phức tạp; cần bảo đảm tuần tự hóa | Phải xử lý serialization failure và retry toàn bộ giao dịch |
| Khóa hàng điều phối | Có một phạm vi nghiệp vụ rõ ràng như một ca trực, một phòng hoặc một tài khoản | Mọi giao dịch liên quan phải lấy cùng khóa trước khi kiểm tra |
| Khóa tất cả hàng liên quan | Tập hàng cần kiểm tra xác định và có thể khóa tường minh | Chú ý thứ tự khóa, deadlock và hành vi snapshot của DBMS |
| Constraint/thiết kế lại dữ liệu | Có thể biểu diễn quy tắc bằng cấu trúc hoặc ràng buộc do DBMS bảo vệ | Constraint trên từng hàng không tự bảo vệ điều kiện tổng hợp nhiều hàng |
| Hàng phiên bản chung | Muốn tạo một điểm xung đột ghi có chủ đích cho một nhóm dữ liệu | Phải kiểm tra lỗi xung đột và retry từ đầu |

Với lịch trực của An và Bình, lựa chọn đơn giản thường là Serializable Isolation hoặc khóa một hàng đại diện cho ca trực trước khi đọc và kiểm tra. Lựa chọn cụ thể phụ thuộc DBMS, lưu lượng giao dịch và cách ứng dụng xử lý retry.

## 10. Write skew trong các nghiệp vụ khác

Mẫu lỗi này không chỉ xuất hiện trong lịch trực. Bất cứ khi nào một quy tắc phụ thuộc vào nhiều hàng, các giao dịch có thể đọc chung dữ liệu nhưng cập nhật các hàng khác nhau.

- **Phân công bác sĩ:** một khoa phải luôn có ít nhất một bác sĩ trực; hai giao dịch lần lượt cho hai bác sĩ khác nhau nghỉ.
- **Giới hạn phòng:** một phòng họp phải luôn có ít nhất một người phụ trách; hai giao dịch cùng xóa hai người phụ trách khác nhau.
- **Hạn mức nhóm:** tổng số thành viên đang hoạt động phải lớn hơn một; hai giao dịch đồng thời vô hiệu hóa hai thành viên cuối cùng.
- **Phân bổ tài nguyên:** phải luôn có một máy chủ dự phòng; hai giao dịch cùng loại bỏ hai máy chủ khác nhau vì mỗi giao dịch thấy máy chủ kia vẫn hoạt động.

Khi gặp những quy tắc dạng “ít nhất một”, “không vượt quá N”, “tổng phải nằm trong giới hạn” hoặc “luôn phải có một người chịu trách nhiệm”, hãy xem điều kiện đó có trải trên nhiều hàng hay không. Nếu có, chỉ kiểm tra trên ảnh chụp đọc chưa chắc đã đủ để bảo vệ điều kiện khi nhiều giao dịch commit đồng thời.

## 11. Những hiểu nhầm thường gặp

| Hiểu nhầm | Cách hiểu đúng |
|---|---|
| Snapshot Isolation đồng nghĩa Serializable. | SI cho ảnh chụp đọc nhất quán nhưng vẫn có thể cho phép write skew; Serializable phải loại bỏ lịch không thể tuần tự hóa. |
| Hai giao dịch ghi hai hàng khác nhau thì luôn an toàn. | Chúng vẫn có thể phá một quy tắc nghiệp vụ liên quan đến cả hai hàng. |
| Không có dirty read thì không có anomaly. | Dirty read chỉ là một loại vấn đề; write skew có thể xảy ra mà không cần đọc dữ liệu chưa commit. |
| First-committer-wins ngăn mọi xung đột. | Cơ chế này thường phát hiện xung đột ghi cùng hàng; write skew có thể ghi vào các hàng khác nhau. |
| Khóa hàng mà giao dịch định sửa là đủ. | Nếu quyết định phụ thuộc nhiều hàng, cần khóa hoặc điều phối toàn bộ phạm vi liên quan. |
| Retry chỉ câu lệnh UPDATE là đủ. | Phải chạy lại toàn bộ giao dịch để đọc ảnh chụp mới và kiểm tra lại quy tắc. |

## 12. Tự kiểm tra

**Tình huống 1:** Ban đầu An và Bình đều trực. `T1` đọc hai hàng và quyết định cho An nghỉ. `T2` cũng đọc hai hàng và quyết định cho Bình nghỉ. Hai giao dịch cập nhật hai hàng khác nhau. Vì sao cả hai có thể commit dưới Snapshot Isolation?

**Đáp án:** Vì cả hai đọc cùng ảnh chụp ban đầu nhưng ghi vào các hàng khác nhau. Cơ chế phát hiện xung đột ghi cùng hàng không thấy hai giao dịch cùng sửa một hàng, nên có thể cho phép cả hai commit dù điều kiện “ít nhất một người trực” bị vi phạm.

**Tình huống 2:** Đây có phải lost update không?

**Đáp án:** Không. Không có lần ghi nào ghi đè kết quả của lần ghi còn lại. Hai lần ghi đều được giữ trên hai hàng riêng. Vấn đề là hai quyết định dựa trên dữ liệu đọc chung làm hỏng một bất biến liên quan đến nhiều hàng.

**Tình huống 3:** Dùng Serializable Isolation thì điều gì có thể xảy ra?

**Đáp án:** DBMS phải ngăn cả hai giao dịch commit nếu lịch của chúng không thể tương đương với một thứ tự tuần tự hợp lệ. Một giao dịch có thể bị hủy với serialization failure; ứng dụng cần retry toàn bộ giao dịch.

**Tình huống 4:** Nếu mỗi giao dịch chỉ khóa hàng của nhân viên mà nó định cho nghỉ, điều đó có ngăn write skew không?

**Đáp án:** Chưa chắc. `T1` khóa hàng An còn `T2` khóa hàng Bình, nên hai giao dịch vẫn không tranh chấp khóa. Cần một khóa chung đại diện cho ca trực hoặc khóa toàn bộ tập hàng liên quan trước khi kiểm tra.

Khi phân tích một tình huống Snapshot Isolation, hãy xác định ba điều: các giao dịch đã đọc ảnh chụp nào, mỗi giao dịch ghi vào những hàng nào, và quy tắc nghiệp vụ phụ thuộc vào những hàng nào. Nếu các giao dịch đọc dữ liệu liên quan nhưng ghi vào các hàng riêng biệt, hãy kiểm tra nguy cơ write skew và chọn cơ chế bảo vệ bất biến phù hợp.
