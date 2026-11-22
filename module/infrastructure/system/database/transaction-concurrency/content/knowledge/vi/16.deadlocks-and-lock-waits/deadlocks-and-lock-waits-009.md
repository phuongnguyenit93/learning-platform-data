# Đói tài nguyên (starvation), livelock và tính công bằng

Trong hệ thống cơ sở dữ liệu có nhiều giao dịch chạy đồng thời, một giao dịch có thể phải chờ khóa, bị hủy rồi chạy lại, hoặc liên tục mất cơ hội sử dụng tài nguyên đang tranh chấp. Không phải mọi tình huống như vậy đều là deadlock. Có trường hợp hệ thống vẫn xử lý được nhiều giao dịch khác nhưng một giao dịch cụ thể gần như không bao giờ hoàn tất; có trường hợp các giao dịch liên tục phản ứng với nhau nhưng không tạo ra tiến triển hữu ích.

Ba khái niệm cần phân biệt là:

- **Starvation (đói tài nguyên):** một giao dịch hoặc yêu cầu liên tục không được cấp tài nguyên cần thiết, trong khi những giao dịch khác vẫn tiến triển.
- **Livelock (bế tắc sống):** các giao dịch hoặc tiến trình vẫn hoạt động, liên tục nhường, hủy, thử lại hoặc thay đổi trạng thái để tránh xung đột, nhưng không hoàn thành được công việc hữu ích.
- **Fairness (tính công bằng):** chính sách phân phối cơ hội sử dụng tài nguyên giữa các yêu cầu, nhằm hạn chế việc một giao dịch bị bỏ đói hoặc bị đối xử bất lợi kéo dài.

Các hiện tượng này có liên quan đến hàng đợi khóa, chính sách ưu tiên, deadlock recovery, optimistic concurrency control và cách ứng dụng retry transaction. Một hệ thống có throughput cao vẫn có thể không công bằng nếu một số transaction phải chờ vô hạn. Ngược lại, một chính sách rất công bằng có thể làm giảm thông lượng vì phải giữ thứ tự hàng đợi chặt chẽ.

## 1. Starvation là gì?

Starvation xảy ra khi một yêu cầu liên tục bị trì hoãn hoặc bị các yêu cầu khác vượt qua, khiến giao dịch không có cơ hội hoàn thành trong thời gian hữu hạn. Trong lúc đó, hệ thống vẫn hoạt động và các giao dịch khác vẫn được xử lý.

Ví dụ, T1 cần khóa độc quyền X trên tài nguyên A. Nhiều giao dịch đọc liên tục đến và được cấp khóa chia sẻ S. Nếu lock manager cho phép yêu cầu S mới vượt qua yêu cầu X đang chờ, T1 có thể phải chờ mãi vì luôn có reader mới giữ S trên A.

```text
Tài nguyên A

Đang giữ:
  T2: S(A)

Hàng đợi:
  T1: X(A)  [đang chờ từ trước]
  T3: S(A)  [được phép vượt qua T1]
  T4: S(A)  [được phép vượt qua T1]
  T5: S(A)  [được phép vượt qua T1]
  ...
```

Mỗi reader mới có thể chỉ giữ S trong thời gian ngắn, nhưng nếu luồng reader liên tục thì T1 không bao giờ thấy thời điểm không còn S để nhận X. Hệ thống vẫn có nhiều truy vấn đọc hoàn tất; chỉ riêng T1 bị đói.

Starvation khác với một transaction chờ lâu do transaction giữ khóa đang chạy quá lâu. Chờ lâu có thể chỉ là blocking tạm thời. Starvation nói đến việc chính sách lập lịch hoặc mẫu tranh chấp khiến một yêu cầu liên tục không có cơ hội tiến triển.

## 2. Phân biệt blocking, deadlock và starvation

Ba hiện tượng đều có thể khiến transaction không hoàn tất ngay, nhưng cấu trúc và cách xử lý khác nhau.

| Hiện tượng | Cơ chế | Hệ thống có tiến triển không? | Cách xử lý thường gặp |
|---|---|---|---|
| Blocking | Một transaction chờ khóa do transaction khác đang giữ khóa xung đột | Có thể có; transaction giữ khóa có thể commit rồi giải phóng | Tìm blocker, rút ngắn transaction, giảm lock contention |
| Deadlock | Một nhóm transaction tạo chu trình chờ lẫn nhau | Các transaction trong chu trình không thể tự tháo gỡ | Phát hiện chu trình, chọn victim, rollback và retry |
| Starvation | Một yêu cầu liên tục bị trì hoãn hoặc vượt qua | Các transaction khác vẫn tiến triển | Chính sách công bằng, aging, giới hạn vượt hàng đợi, điều chỉnh ưu tiên |

Ví dụ blocking đơn giản:

```text
T1 giữ X(A)
T2 cần S(A), nên chờ T1
T1 COMMIT và nhả X(A)
T2 nhận S(A) và tiếp tục
```

Ví dụ deadlock:

```text
T1 giữ X(A), chờ X(B)
T2 giữ X(B), chờ X(A)

T1 -> T2 -> T1
```

Ví dụ starvation:

```text
T1 chờ X(A)
T2, T3, T4, ... liên tục được cấp S(A)
Các reader hoàn tất, nhưng luôn có reader mới trước khi T1 lấy được X(A)
```

Một transaction có thể bị blocking mà không bị starvation; nếu nó cuối cùng được cấp khóa thì yêu cầu đã tiến triển. Một transaction có thể bị starvation dù không có deadlock, vì không tồn tại chu trình chờ. Deadlock detection không tự giải quyết mọi dạng starvation.

## 3. Nguyên nhân phổ biến gây starvation

### 3.1. Chính sách ưu tiên reader hoặc writer

Nếu hệ thống ưu tiên reader, writer có thể bị đói khi các truy vấn đọc liên tục đến. Nếu hệ thống ưu tiên writer, reader có thể bị đói khi hàng đợi writer luôn có yêu cầu mới.

Không có một chính sách ưu tiên duy nhất phù hợp cho mọi workload. Hệ thống phải cân bằng độ trễ đọc, độ trễ ghi, throughput và mức công bằng mong muốn.

### 3.2. Yêu cầu mới liên tục vượt qua yêu cầu cũ

Một số lock manager cho phép yêu cầu tương thích mới được cấp ngay cả khi có yêu cầu xung đột đang chờ phía trước. Điều này có thể tăng throughput vì tài nguyên không phải chờ rỗi. Nhưng nếu yêu cầu mới cứ tiếp tục đến, yêu cầu cũ có thể bị bỏ đói.

Ví dụ, S mới tương thích với S đang giữ, nhưng X cũ ở đầu hàng đợi đang chờ. Nếu lock manager luôn cho S mới vượt qua X, writer có thể phải chờ vô hạn.

### 3.3. Transaction liên tục trở thành deadlock victim

DBMS thường chọn một transaction làm victim để phá chu trình deadlock. Nếu thuật toán chọn victim không cân bằng, một transaction có thể liên tục bị rollback trong khi các transaction khác hoàn tất.

Ví dụ, nếu T1 luôn là transaction ít tốn chi phí rollback nhất, nó có thể bị chọn làm victim qua nhiều lần deadlock. T1 liên tục mất công việc đã thực hiện và không bao giờ hoàn tất.

### 3.4. Hot row hoặc tài nguyên có mức tranh chấp cao

Một hàng được nhiều transaction cập nhật thường xuyên có thể trở thành điểm nóng. Các transaction phải xếp hàng lấy khóa trên cùng hàng. Nếu có ưu tiên, batching hoặc retry không cân bằng, một số yêu cầu có thể liên tục đứng sau.

Các ví dụ thường gặp:

- Một hàng counter dùng để đếm tổng số request.
- Một bản ghi số dư được nhiều giao dịch cập nhật.
- Một hàng trạng thái đại diện cho cả nhóm công việc.
- Một khóa chỉ mục hoặc khoảng khóa mà nhiều transaction cùng truy cập.

### 3.5. Dùng SKIP LOCKED không có cơ chế bảo đảm tiến triển

`SKIP LOCKED` giúp worker không chờ một hàng đang bị khóa, nhưng nó cố ý bỏ qua hàng đó. Một công việc cũ có thể liên tục bị bỏ qua nếu nó thường xuyên bị worker khác khóa hoặc có vấn đề khiến lease hết hạn và bị nhận lại nhiều lần.

Nếu hàng ưu tiên cao luôn bị khóa, worker khác có thể liên tục nhận hàng ưu tiên thấp hơn. Throughput vẫn cao nhưng hàng cũ có thể chờ rất lâu. Queue dùng `SKIP LOCKED` cần theo dõi tuổi công việc, lease, số lần claim và starvation.

## 4. Livelock là gì?

Livelock xảy ra khi các thành phần vẫn hoạt động và liên tục phản ứng với nhau, nhưng hành động đó không đưa hệ thống đến kết quả hữu ích. Không giống deadlock, các transaction không nhất thiết đứng yên chờ nhau; chúng có thể liên tục rollback, retry, nhường quyền hoặc đổi trạng thái.

Một ví dụ rõ hơn là hai transaction cần khóa cả A và B, nhưng để tránh deadlock chúng dùng khóa không chờ (non-blocking) và nhả toàn bộ khóa nếu không lấy được khóa thứ hai. T1 lấy A trong khi T2 lấy B. Khi mỗi bên thử lấy tài nguyên còn lại, cả hai đều thất bại. Cả hai cùng nhả khóa đã lấy rồi retry gần như đồng thời. Nếu lịch chạy lặp lại đúng nhịp cũ, T1 lại lấy A và T2 lại lấy B; sau đó cả hai lại nhả khóa. Các transaction luôn hoạt động và nhường nhau, nhưng không bên nào hoàn thành.

```text
Vòng 1:
  T1 lấy A                 T2 lấy B
  T1 thử lấy B -> thất bại T2 thử lấy A -> thất bại
  T1 nhả A                 T2 nhả B

Vòng 2 (cùng nhịp cũ):
  T1 lại lấy A             T2 lại lấy B
  T1 thử lấy B -> thất bại T2 thử lấy A -> thất bại
  T1 nhả A                 T2 nhả B

Vòng 3: lặp lại, không transaction nào hoàn tất.
```

Đây là livelock: các transaction không đứng yên chờ nhau mà liên tục lấy, nhả và thử lại, nhưng không tạo ra tiến triển. Với optimistic concurrency control, một mẫu retry đồng bộ cũng có thể tạo ra livelock hoặc khiến một transaction bị starvation. Vì vậy, starvation mô tả việc một yêu cầu không được phục vụ; livelock mô tả một vòng hoạt động lặp lại mà không hoàn thành công việc hữu ích. Hai hiện tượng có thể cùng xuất hiện.

### 4.1. Livelock trong chiến lược tránh deadlock

Một thuật toán tránh deadlock có thể buộc transaction nhường tài nguyên hoặc rollback khi phát hiện xung đột. Nếu nhiều transaction liên tục phản ứng theo cùng một quy tắc và không có cơ chế phân xử ổn định, chúng có thể liên tục nhường nhau hoặc retry mà không hoàn tất.

Các chiến lược timestamp như wait-die và wound-wait định hướng việc chờ hoặc rollback theo tuổi transaction để tránh chu trình. Chúng làm giảm nguy cơ livelock bằng cách tạo quy tắc ưu tiên ổn định, nhưng transaction trẻ có thể bị rollback nhiều lần. Việc giữ timestamp khi retry và chính sách ưu tiên ảnh hưởng đến khả năng tiến triển.

### 4.2. Retry đồng bộ có thể làm xung đột lặp lại

Nếu tất cả client bị lỗi cùng lúc rồi retry sau một khoảng cố định, chúng có thể quay lại đúng cùng thời điểm và tiếp tục tranh chấp. Hiện tượng này thường thấy ở optimistic update, unique-key race, queue consumer hoặc dịch vụ ghi vào cùng một tài nguyên nóng.

```text
T0: 20 client cùng đọc version 12
T1: một client cập nhật thành công; 19 client thất bại
T2: 19 client cùng retry ngay
T3: một client thắng; 18 client lại thất bại
T4: cả nhóm tiếp tục retry cùng nhịp
```

Hệ thống có hoạt động liên tục nhưng tốn CPU, round trip và log cho các lần thử thất bại. Backoff có jitter, giới hạn retry và phân phối công việc theo khóa có thể giảm hiện tượng này.

## 5. Tính công bằng trong quản lý khóa

Fairness mô tả mức độ một chính sách cho các yêu cầu có cơ hội sử dụng tài nguyên. Một chính sách công bằng thường cố tránh để yêu cầu cũ bị yêu cầu mới vượt qua vô hạn.

Một số thuộc tính thường được nhắc đến:

- **FIFO fairness:** xử lý yêu cầu theo thứ tự đến trong hàng đợi.
- **Bounded waiting:** một yêu cầu chỉ bị vượt qua một số lần hữu hạn trước khi được xử lý.
- **Starvation freedom:** nếu tài nguyên tiếp tục được giải phóng và các điều kiện khác được đáp ứng, một yêu cầu hợp lệ cuối cùng sẽ có cơ hội tiến triển.
- **Priority fairness:** tôn trọng mức ưu tiên nhưng có cơ chế ngăn yêu cầu ưu tiên thấp bị bỏ đói vô hạn.

Fairness không đồng nghĩa với tất cả transaction có thời gian hoàn tất giống nhau. Transaction lớn có thể cần nhiều tài nguyên hơn; transaction ưu tiên cao có thể được xử lý trước trong giới hạn chính sách. Mục tiêu là bảo đảm quy tắc phân phối có thể dự đoán và không để một nhóm yêu cầu bị bỏ quên vô hạn.

## 6. FIFO và head-of-line blocking

Chính sách FIFO cấp khóa theo thứ tự yêu cầu đến. Khi một yêu cầu xung đột đứng đầu hàng đợi, các yêu cầu phía sau có thể phải chờ dù chúng tương thích với những khóa đang được giữ.

Ví dụ:

```text
Đang giữ: T1 giữ S(A)

Hàng đợi FIFO:
  T2 yêu cầu X(A)  [đầu hàng, xung đột với T1]
  T3 yêu cầu S(A)  [tương thích với T1]

T3 vẫn chờ phía sau T2.
```

Hiện tượng này gọi là **head-of-line blocking**. FIFO giúp T2 không bị các reader mới vượt qua mãi, nhưng làm giảm khả năng tận dụng tài nguyên vì T3 có thể được cấp ngay nếu bỏ qua T2.

Một số lock manager dùng chính sách trung gian: cấp một nhóm yêu cầu tương thích liên tiếp ở đầu hàng đợi, nhưng không cho yêu cầu mới vượt qua một yêu cầu xung đột cũ hơn. Cách này cân bằng fairness và throughput tốt hơn FIFO tuyệt đối trong một số workload.

## 7. Reader preference và writer preference

Chính sách ưu tiên reader và writer thể hiện rõ sự đánh đổi giữa fairness và throughput.

### 7.1. Reader preference

Reader preference cho phép reader mới vào khi khóa đang giữ vẫn tương thích. Điều này giúp các thao tác đọc đồng thời và giảm độ trễ đọc. Nhưng nếu reader liên tục đến, writer cần X có thể bị starvation.

```text
Reader R1 giữ S
Writer W1 yêu cầu X và chờ
Reader R2 đến, được cấp S
Reader R3 đến, được cấp S
Reader R4 đến, được cấp S
... writer W1 tiếp tục chờ
```

### 7.2. Writer preference

Writer preference ngăn reader mới vượt qua writer đang chờ. Khi các reader hiện tại nhả S, writer được cấp X trước. Điều này hạn chế writer starvation nhưng có thể làm reader mới chờ lâu nếu writer liên tục đến.

```text
Reader R1 giữ S
Writer W1 yêu cầu X và chờ
Reader R2 đến, phải chờ phía sau W1
Reader R3 đến, phải chờ phía sau W1
R1 nhả S -> W1 nhận X
```

Writer preference không tự bảo đảm mọi writer đều công bằng với nhau. Nếu có ưu tiên theo mức độ quan trọng hoặc transaction cũ/mới, một writer vẫn có thể bị trì hoãn.

### 7.3. Công bằng theo nhóm tương thích

Một chính sách khác là xử lý theo nhóm: khi các khóa hiện tại được giải phóng, cấp một nhóm yêu cầu tương thích ở đầu hàng đợi, nhưng dừng trước yêu cầu xung đột tiếp theo. Ví dụ, một nhóm reader có thể cùng nhận S, sau đó writer đang chờ được cấp trước các reader đến muộn hơn.

Chính sách này hạn chế starvation mà vẫn cho phép nhiều thao tác tương thích chạy song song. Chi tiết phụ thuộc implementation của lock manager; không nên mặc định mọi DBMS dùng cùng một quy tắc FIFO hoặc reader/writer preference.

## 8. Aging: tăng ưu tiên theo thời gian chờ

**Aging** là kỹ thuật tăng dần mức ưu tiên của một yêu cầu khi nó chờ lâu. Mục tiêu là ngăn yêu cầu ưu tiên thấp bị các yêu cầu ưu tiên cao mới liên tục vượt qua.

Ví dụ, mỗi giây chờ tăng một điểm ưu tiên:

```text
effective_priority = base_priority + wait_seconds * aging_rate
```

Một yêu cầu ban đầu có ưu tiên thấp có thể dần đạt mức ưu tiên của các yêu cầu mới. Khi đạt ngưỡng, nó sẽ được chọn trước theo chính sách lập lịch.

Aging hữu ích khi hệ thống có nhiều lớp ưu tiên, chẳng hạn job khẩn cấp và job thông thường. Tuy nhiên, DBMS không nhất thiết cung cấp aging cho mọi loại lock request. Ứng dụng có thể áp dụng aging trong queue riêng bằng cách tăng độ ưu tiên theo thời gian chờ.

Không nên để aging làm thay đổi thứ tự một cách khó dự đoán. Cần xác định:

- Mức ưu tiên ban đầu và mức tối đa.
- Tốc độ tăng ưu tiên.
- Thời điểm tính lại ưu tiên.
- Cách xử lý khi nhiều yêu cầu có cùng mức ưu tiên.
- Liệu một yêu cầu mới khẩn cấp có được phép vượt qua yêu cầu cũ đã chờ quá lâu hay không.

## 9. Fairness và deadlock victim selection

Khi phát hiện deadlock, DBMS cần chọn một transaction làm victim để phá chu trình. Việc chọn victim thường dựa trên chi phí rollback, lượng công việc đã thực hiện, mức ưu tiên hoặc thông tin nội bộ khác.

Nếu luôn chọn transaction có chi phí rollback thấp nhất, một transaction nhỏ có thể liên tục bị hủy. Nếu luôn chọn transaction trẻ nhất, một transaction mới có thể bị hủy nhiều lần khi cạnh tranh với transaction cũ. Vì vậy, thuật toán chọn victim cần cân bằng chi phí phục hồi và nguy cơ starvation.

Một số hướng giảm starvation:

- Theo dõi số lần một transaction hoặc loại công việc bị chọn làm victim.
- Tăng ưu tiên cho transaction đã bị rollback nhiều lần.
- Giữ tuổi hoặc timestamp ổn định khi retry nếu thuật toán cho phép.
- Tránh retry ngay đồng loạt khiến transaction liên tục va vào cùng đối thủ.
- Thiết kế thứ tự khóa thống nhất để giảm số deadlock phải xử lý.

DBMS có thể không cam kết tuyệt đối rằng một transaction sẽ không bao giờ bị chọn làm victim nhiều lần. Ứng dụng cần ghi nhận lỗi deadlock, retry toàn bộ transaction và theo dõi các trường hợp lặp lại.

## 10. Backoff và jitter để giảm livelock

Khi một transaction thất bại do xung đột, retry ngay có thể làm nó va vào cùng transaction khác. Backoff làm transaction đợi trước khi thử lại; jitter thêm một khoảng ngẫu nhiên để các transaction không cùng retry theo một nhịp.

Một chiến lược exponential backoff có giới hạn:

```text
base_delay = 50 milliseconds
max_delay  = 2 seconds

for attempt in 1..MAX_RETRIES:
    try transaction
    if success:
        return success

    if retryable_conflict:
        cap = min(max_delay, base_delay * 2^(attempt - 1))
        delay = random(0, cap)  # full jitter
        sleep(delay)

return retryable_failure
```

Backoff giúp giảm số lần các client cùng tranh chấp, nhưng không tự giải quyết nguyên nhân gốc. Nếu một hàng luôn nóng hoặc thứ tự khóa luôn tạo deadlock, hệ thống vẫn có thể tiếp tục lỗi sau thời gian chờ.

Khi thiết kế retry, cần lưu ý:

- Chỉ retry lỗi được xác định là có thể thử lại, ví dụ deadlock victim hoặc serialization failure.
- Rollback transaction cũ trước khi bắt đầu transaction mới.
- Retry toàn bộ transaction nếu quyết định phụ thuộc vào dữ liệu đã đọc trước đó.
- Giới hạn số lần thử hoặc tổng thời gian retry.
- Dùng idempotency cho tác động bên ngoài database.
- Ghi nhận attempt count, delay và nguyên nhân thất bại để phát hiện livelock.

## 11. Transaction ngắn và thứ tự khóa nhất quán

Giảm thời gian giữ khóa là một trong những cách thực tế nhất để giảm blocking và nguy cơ starvation. Transaction nên chỉ bao gồm những thao tác cần tính nguyên tử; tránh giữ khóa trong lúc chờ người dùng, gọi HTTP, gửi email hoặc xử lý tệp lớn.

Nếu nhiều transaction cùng khóa A và B, hãy lấy khóa theo một thứ tự thống nhất, ví dụ theo ID tăng dần. Điều này giảm deadlock do thứ tự lấy khóa ngược nhau và giảm số lần một transaction phải rollback rồi retry.

Với một tài nguyên nóng, có thể cân nhắc:

- Chia nhỏ counter theo shard hoặc partition nếu bất biến cho phép.
- Gộp nhiều cập nhật thành batch có giới hạn để giảm round trip.
- Dùng atomic update thay cho read-modify-write ở tầng ứng dụng.
- Dùng optimistic concurrency khi xung đột hiếm và có retry phù hợp.
- Dùng pessimistic lock khi xung đột thường xuyên và cần giữ quyền cập nhật.
- Tách queue theo tenant hoặc loại công việc để tránh một nhóm chiếm toàn bộ worker.

Không nên chia một hàng nóng thành nhiều counter nếu việc đó làm mất khả năng bảo đảm bất biến tổng hợp. Tối ưu thông lượng phải giữ đúng quy tắc nghiệp vụ.

## 12. Starvation trong queue dùng SKIP LOCKED

`SKIP LOCKED` cho phép worker bỏ qua hàng đang bị khóa và nhận hàng khác. Cơ chế này tăng khả năng tiến triển của worker nhưng không bảo đảm mọi job được xử lý theo FIFO hoặc strict priority.

Ví dụ, job 101 có ưu tiên cao nhưng thường xuyên bị worker A khóa. Worker B liên tục bỏ qua 101 và nhận job 102, 103, 104. Nếu 101 luôn bị khóa lại hoặc lease của nó liên tục được gia hạn mà không hoàn tất, nó có thể bị starvation.

Để giảm nguy cơ:

- Giữ transaction claim ngắn và commit ngay sau khi cập nhật trạng thái sở hữu.
- Dùng lease có thời hạn để phục hồi job bị worker chết bỏ lại.
- Dùng lease token hoặc fencing token để worker cũ không ghi đè lần claim mới.
- Theo dõi tuổi của job READY và RUNNING, số lần claim và số lần hết lease.
- Áp dụng priority aging hoặc hàng đợi riêng cho công việc đã chờ quá lâu.
- Có cơ chế xử lý thủ công cho job bị kẹt hoặc vượt ngưỡng retry.

Nếu nghiệp vụ yêu cầu strict FIFO, `SKIP LOCKED` có thể không phù hợp vì bỏ qua hàng đầu đang khóa là hành vi có chủ đích. Cần dispatcher hoặc cơ chế tuần tự hóa khác, chấp nhận rằng throughput có thể thấp hơn.

## 13. MVCC có loại bỏ starvation không?

MVCC giúp nhiều thao tác đọc nhìn thấy phiên bản dữ liệu phù hợp mà không phải chờ mọi writer. Điều đó giảm một số dạng reader-writer blocking, nhưng không loại bỏ mọi tranh chấp.

Các trường hợp vẫn có thể chờ hoặc thất bại:

- Hai transaction cùng cập nhật một hàng.
- Transaction cần khóa tường minh như `SELECT FOR UPDATE`.
- DDL hoặc thao tác quản trị cần table lock.
- Transaction Serializable gặp phụ thuộc nguy hiểm và bị abort.
- Writer cạnh tranh trên index, unique constraint hoặc tài nguyên dùng chung.
- Một transaction giữ snapshot cũ quá lâu, làm chậm thu gom phiên bản và tăng áp lực lưu trữ.

MVCC thay đổi cách đọc và quản lý phiên bản; nó không phải chính sách fairness cho mọi lock hoặc transaction. Một reader không bị block vẫn có thể gặp serialization failure, còn writer trên hot row vẫn phải được điều phối.

## 14. Priority inversion

Priority inversion xảy ra khi một transaction ưu tiên cao phải chờ tài nguyên do transaction ưu tiên thấp đang giữ. Một transaction ưu tiên trung bình có thể tiếp tục chạy và làm transaction ưu tiên thấp khó hoàn tất, khiến transaction ưu tiên cao bị chậm gián tiếp.

Ví dụ:

```text
T_low giữ khóa X(A)
T_high cần X(A), phải chờ T_low
T_medium không cần A nhưng liên tục chiếm CPU hoặc tài nguyên xử lý
T_low hoàn tất chậm
T_high tiếp tục chờ
```

Trong hệ điều hành, priority inheritance có thể tạm nâng ưu tiên của tiến trình đang giữ khóa để nó hoàn tất nhanh hơn. DBMS không nhất thiết áp dụng priority inheritance ở cấp transaction giống hệ điều hành. Vì vậy, ứng dụng không nên giả định transaction ưu tiên cao sẽ tự động làm transaction giữ khóa được ưu tiên chạy.

Có thể giảm priority inversion bằng cách rút ngắn transaction giữ khóa, tránh công việc ngoài database trong transaction, kiểm soát ưu tiên ở queue, và hạn chế để transaction ưu tiên thấp giữ tài nguyên nóng quá lâu.

## 15. Đo lường starvation và livelock

Chỉ nhìn throughput tổng thể có thể bỏ qua một nhóm yêu cầu bị đói. Cần theo dõi phân phối thời gian chờ và số lần retry ở mức transaction hoặc loại công việc.

Các chỉ số hữu ích:

| Chỉ số | Ý nghĩa | Dấu hiệu cần điều tra |
|---|---|---|
| Lock wait time p50/p95/p99 | Phân phối thời gian chờ khóa | p99 hoặc max tăng mạnh dù p50 thấp |
| Longest wait age | Yêu cầu đang chờ lâu nhất | Một yêu cầu già hơn nhiều so với phần còn lại |
| Retry attempts per transaction | Số lần transaction phải thử lại | Một nhóm transaction có số lần retry cao bất thường |
| Deadlock victim count | Số lần transaction bị chọn làm victim | Một loại transaction liên tục bị rollback |
| Serialization failure rate | Tỷ lệ abort do Serializable | Tăng mạnh sau thay đổi query hoặc tải |
| Queue oldest-ready age | Tuổi công việc READY lâu nhất | Job cũ vẫn chờ trong khi job mới liên tục hoàn tất |
| Lease expiration/reclaim count | Số lần quyền xử lý hết hạn và job được nhận lại | Worker chết, lease quá ngắn hoặc xử lý bị treo |
| Useful completion per retry | Công việc hoàn tất so với số lần thử | Nhiều retry nhưng ít transaction commit |

Nên xem thêm lock graph, transaction age, câu lệnh đang giữ khóa, execution plan và trạng thái worker. Một p99 cao có thể do transaction dài, hot row, queue policy hoặc deadlock recovery; cần tìm nguyên nhân trước khi đổi chính sách.

## 16. Quy trình điều tra một transaction bị đói

Khi một transaction hoặc job chờ lâu bất thường, hãy lần lượt xác định:

1. **Yêu cầu đang chờ điều gì?** Xác định lock, row, key range, connection, worker slot hay một tài nguyên logic khác.
2. **Có blocker trực tiếp không?** Tìm transaction giữ tài nguyên và xem thời gian giữ.
3. **Có chu trình chờ không?** Nếu có, đây là deadlock; nếu không, tiếp tục phân tích blocking/starvation.
4. **Yêu cầu cũ có bị vượt qua không?** Xem thứ tự hàng đợi và các yêu cầu mới được cấp sau nó.
5. **Transaction có bị rollback lặp lại không?** Phân loại deadlock victim, serialization failure, optimistic conflict hoặc timeout.
6. **Retry có đồng bộ không?** Kiểm tra khoảng delay, jitter và số lần thử.
7. **Có hot resource không?** Xem tần suất truy cập, index, counter và hàng đại diện.
8. **Có công việc bị SKIP LOCKED bỏ qua lâu không?** Kiểm tra tuổi job, lease và số lần claim.
9. **Chính sách fairness hiện tại là gì?** Xác định reader/writer preference, FIFO, priority hoặc quy tắc riêng của ứng dụng.
10. **Có thể rút ngắn transaction hoặc thay đổi mô hình truy cập không?** Kiểm tra atomic update, thứ tự khóa, partition và queue.

Khi kết luận starvation, cần có bằng chứng rằng yêu cầu liên tục không tiến triển trong khi các yêu cầu khác vẫn được phục vụ. Một transaction chờ lâu duy nhất chưa đủ để kết luận; nó có thể đang bị một transaction giữ khóa lâu hoặc đang chờ I/O.

## 17. Ví dụ thiết kế retry có fairness cho optimistic update

Giả sử bảng `account` có cột `version`. Ứng dụng đọc số dư và version, tính toán rồi cập nhật có điều kiện:

```sql
UPDATE account
SET balance = :new_balance,
    version = version + 1
WHERE account_id = :account_id
  AND version = :observed_version;
```

Nếu số hàng được cập nhật là 0, một transaction khác đã thay đổi hàng sau lần đọc. Ứng dụng phải đọc lại dữ liệu và tính lại nghiệp vụ. Để tránh các client retry cùng nhịp, có thể dùng bounded exponential backoff với jitter:

```text
attempt = 0

while attempt < MAX_ATTEMPTS:
    begin transaction
    read balance, version
    calculate new balance
    update where version = observed_version

    if one row updated:
        commit
        return success

    rollback
    attempt += 1
    wait random(0, min(MAX_DELAY, BASE_DELAY * 2^attempt))

return retryable_conflict
```

Nếu cùng một tài khoản liên tục có xung đột, backoff giảm nhịp retry nhưng có thể không đủ. Có thể chuyển sang khóa bi quan trên hàng tài khoản, gom thao tác qua một queue theo `account_id`, hoặc tuần tự hóa các cập nhật cho tài nguyên nóng.

## 18. Những điểm cần ghi nhớ

- Starvation là một yêu cầu không được phục vụ trong thời gian dài hoặc vô hạn trong khi hệ thống vẫn xử lý yêu cầu khác.
- Livelock là hoạt động lặp lại, nhường hoặc retry mà không tạo ra tiến triển hữu ích; một yêu cầu bị livelock cũng có thể bị starvation.
- Deadlock có chu trình chờ; starvation không cần chu trình và không được giải quyết chỉ bằng deadlock detection.
- FIFO và writer preference có thể giảm starvation cho một nhóm nhưng tạo head-of-line blocking hoặc starvation cho nhóm khác.
- Aging, bounded waiting và ưu tiên theo thời gian chờ giúp cân bằng fairness khi có nhiều lớp ưu tiên.
- Deadlock victim selection và retry không cân bằng có thể khiến một transaction liên tục bị rollback.
- Exponential backoff với jitter giảm retry đồng bộ, nhưng cần giới hạn số lần thử và xử lý nguyên nhân tranh chấp.
- `SKIP LOCKED` tăng throughput bằng cách bỏ qua hàng đang khóa; cần theo dõi job cũ và cơ chế lease để tránh starvation.
- MVCC giảm một số reader-writer blocking nhưng không loại bỏ tranh chấp trên hàng ghi, lock tường minh hoặc serialization failure.
- Đo p95/p99/max wait, retry count, victim count và tuổi job để phát hiện vấn đề mà throughput tổng thể che khuất.

Một hệ thống đồng thời tốt cần vừa giữ được tính đúng đắn vừa tạo cơ hội tiến triển cho các transaction. Khi thấy một giao dịch chờ hoặc retry nhiều lần, hãy xác định đó là blocking, deadlock, starvation hay livelock; sau đó điều chỉnh hàng đợi, ưu tiên, retry và mô hình truy cập phù hợp với yêu cầu fairness của workload.
