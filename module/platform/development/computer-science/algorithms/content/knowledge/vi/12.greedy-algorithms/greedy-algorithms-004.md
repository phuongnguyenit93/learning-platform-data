# Chứng minh bằng duy trì lợi thế qua từng bước (Staying Ahead) trong thuật toán tham lam

Một thuật toán **tham lam (greedy)** chọn phương án có vẻ tốt nhất ngay ở bước hiện tại mà không quay lại sửa những quyết định trước đó. Cách chọn đơn giản này có thể đem lại thuật toán nhanh, nhưng **“tốt nhất ở hiện tại” không tự chứng minh được “tối ưu ở cuối”**.

Một kỹ thuật chứng minh quan trọng là **duy trì lợi thế qua từng bước**, thường gọi là **greedy stays ahead** hoặc **staying-ahead proof**. Thay vì cố chứng minh lựa chọn đầu tiên là một phần của lời giải tối ưu, ta so sánh **trạng thái sau k lựa chọn** của thuật toán tham lam với **trạng thái sau k lựa chọn** của một lời giải khả thi bất kỳ (đặc biệt là lời giải tối ưu). Ta tìm một thước đo có ý nghĩa, rồi chứng minh bằng quy nạp rằng greedy **không bao giờ tụt lại phía sau** theo thước đo ấy.

Hai ví dụ nền tảng:

1. **Chọn nhiều khoảng thời gian không giao nhau nhất:** sau k lựa chọn, greedy kết thúc **không muộn hơn** một lịch khả thi bất kỳ có k hoạt động.
2. **Dùng ít đoạn nhất để phủ một trục liên tục:** sau k đoạn được chọn, greedy đã phủ tới vị trí **không ngắn hơn** một phương án hợp lệ có k đoạn.

Hai bài có hướng bất đẳng thức khác nhau. Bản chất chung không phải là chọn “nhỏ nhất” hay “lớn nhất”, mà là chọn **lợi thế trung gian có thể được giữ và truyền sang bước tiếp theo**.

## 1. Mẫu lập luận: từ lựa chọn cục bộ đến tối ưu toàn cục

Giả sử thuật toán tham lam tạo dãy trạng thái G₀,G₁,... và một lời giải khả thi khác tạo O₀,O₁,...; chỉ số k là **số quyết định đã thực hiện**, không nhất thiết là chỉ số của phần tử dữ liệu.

Ta định nghĩa một thước đo tiến độ **p(state)** sao cho “tốt hơn” có ý nghĩa với cơ hội thực hiện các bước tiếp theo. Ví dụ:

- Khi cần chọn **nhiều hoạt động không chồng lấn**, kết thúc sớm hơn để lại nhiều thời gian hơn: **finish(Gₖ) ≤ finish(Oₖ)** là lợi thế.
- Khi cần phủ xa nhất bằng **cùng số đoạn**, đạt xa hơn có lợi: **reach(Gₖ) ≥ reach(Oₖ)** là lợi thế.
- Trong một số bài lập lịch, cần so lượng tài nguyên đã tiêu, số phần tử đã hoàn thành hoặc mức tiến triển; nhưng phải chứng minh thước đo đó thực sự giúp cho phần tiếp theo.

Một chứng minh staying ahead hoàn chỉnh cần ba phần:

**Bước cơ sở:** chứng minh G₁ không kém O₁ (hoặc bắt đầu từ k=0 nếu thuận tiện).

**Bước quy nạp:** giả sử Gₖ₋₁ không kém Oₖ₋₁. Phải chỉ ra từ bất đẳng thức này rằng bước thứ k của phương án O **cũng là một ứng viên hợp lệ hoặc không mạnh hơn ứng viên greedy**, vì vậy lựa chọn greedy giữ được bất đẳng thức ở k.

**Kết thúc:** dùng bất đẳng thức tại các tiền tố để suy ra **giá trị mục tiêu toàn cục**. Ví dụ, nếu có phương án chọn k+1 hoạt động còn greedy chỉ chọn k, bất đẳng thức cho thấy greedy vẫn có thể chọn hoạt động thứ k+1 — mâu thuẫn.

Không đủ nếu chỉ viết “greedy luôn chọn tốt nhất, nên tối ưu”. Ta phải chứng minh được cầu nối từ **thước đo trung gian** sang **đáp án cuối cùng**.

## 2. Phân biệt ba tính chất thường bị trộn lẫn

### Khả thi (feasibility)

Mọi lựa chọn greedy phải giữ được ràng buộc đề bài: không chồng lấn thời gian, không tạo lỗ hổng chưa phủ, không vượt ngân sách hoặc không phá điều kiện hợp lệ.

### Tối ưu cục bộ (local choice)

Tại một trạng thái, greedy lấy ứng viên tốt nhất theo quy tắc đang xét: kết thúc sớm nhất, vươn xa nhất, chi phí thấp nhất, v.v.

### Duy trì lợi thế (prefix dominance)

Cần một **mệnh đề định lượng** đúng với **mọi** phương án so sánh sau **cùng số bước**. Đây mới là phần tạo ra chứng minh tối ưu. Một lựa chọn có kết quả cục bộ tốt không tự suy ra điều kiện này nếu nó làm mất cơ hội trong tương lai.

Khi phát biểu thước đo, cần chú ý hướng bất đẳng thức:

| Mục tiêu | Thước đo tiền tố hữu ích | Greedy được coi là đang dẫn trước khi |
| --- | --- | --- |
| Chọn nhiều khoảng không giao nhau | Thời gian kết thúc hoạt động thứ k | finish(Gₖ) ≤ finish(Oₖ) |
| Phủ đoạn mục tiêu bằng ít khoảng | Tọa độ phải xa nhất đã phủ sau k khoảng | reach(Gₖ) ≥ reach(Oₖ) |
| Hoàn thành các phần việc theo một số ràng buộc | Một đại lượng tiến độ phù hợp | Phải xác định theo đúng bài |
| Tối thiểu tổng số lựa chọn | Số lựa chọn đã dùng để đạt một mức tiến độ | Chỉ suy ra được khi quan hệ tiến độ–khả thi đã chứng minh |

Tập trung vào **tiền tố** là điểm khác biệt so với việc chỉ so hai đáp án ở cuối.

## 3. Ví dụ A — Chọn số hoạt động không giao nhau lớn nhất

Cho n hoạt động. Hoạt động i chiếm khoảng nửa mở **[sᵢ,fᵢ)** với **sᵢ < fᵢ**; hai hoạt động a rồi b tương thích nếu **s_b ≥ f_a**. Chúng có thể tiếp giáp ở cùng thời điểm, vì đầu kết thúc không nằm trong khoảng chiếm dụng.

**Mục tiêu:** chọn **số lượng hoạt động lớn nhất** sao cho các khoảng đã chọn không giao nhau.

Ví dụ:

| ID | Bắt đầu | Kết thúc |
| --- | ---: | ---: |
| A | 1 | 4 |
| B | 3 | 5 |
| C | 0 | 6 |
| D | 5 | 7 |
| E | 3 | 9 |
| F | 5 | 9 |
| G | 6 | 10 |
| H | 8 | 11 |
| I | 8 | 12 |
| J | 2 | 14 |
| K | 12 | 16 |

Quy tắc greedy đúng:

1. **Sắp tăng theo thời gian kết thúc f**.
2. Chọn hoạt động kết thúc sớm nhất trong các hoạt động còn tương thích với lịch đã chọn.
3. Sau mỗi lựa chọn, đặt **lastFinish** bằng thời điểm kết thúc của hoạt động mới.
4. Tiếp tục đến khi không còn hoạt động tương thích.

Kết quả trên ví dụ là **[A,D,H,K]**, gồm **4 hoạt động**:

~~~text
A: [ 1, 4)
D:       [ 5, 7)
H:                [ 8,11)
K:                         [12,16)

Các mốc kết thúc greedy: 4, 7, 11, 16
~~~

Không phải lúc nào lịch tối ưu cũng duy nhất. Đổi H thành I có thể vẫn chọn được bốn hoạt động; mục tiêu chỉ yêu cầu **số lượng tối đa**.

### Vì sao chọn hoạt động kết thúc sớm nhất?

Sau khi chọn một hoạt động, phần thời gian từ lúc nó kết thúc trở đi là miền mà các hoạt động tiếp theo có thể bắt đầu. Một hoạt động kết thúc **không muộn hơn** để lại **ít nhất cùng nhiều cơ hội** cho phần còn lại.

Điều cần chứng minh chính xác là:

**Sau k lựa chọn, thời gian kết thúc của hoạt động thứ k do greedy chọn không lớn hơn thời gian kết thúc của hoạt động thứ k trong bất kỳ lịch hợp lệ nào có ít nhất k hoạt động.**

Đây là phát biểu “greedy đi trước”, không chỉ là nhận xét cảm tính về thời gian.

## 4. Chứng minh staying ahead đầy đủ cho chọn hoạt động

Đặt lịch greedy theo thứ tự thời gian là:

**G = (g₁,g₂,...,gᵣ)**.

Xét một lịch hợp lệ bất kỳ có m hoạt động, được xếp theo thời gian bắt đầu/diễn ra:

**O = (o₁,o₂,...,oₘ)**.

Viết **f(x)** và **s(x)** lần lượt là thời gian kết thúc và bắt đầu. Do mỗi lịch hợp lệ không giao nhau, với j ≥ 2:

**s(oⱼ) ≥ f(oⱼ₋₁)**.

### Mệnh đề bất biến

Với mọi k từ 1 đến m mà greedy đã có (hoặc sẽ chứng minh có) hoạt động thứ k:

**f(gₖ) ≤ f(oₖ).**

Cần chứng minh đồng thời rằng nếu O có k hoạt động thì greedy **cũng có thể chọn được ít nhất k hoạt động**.

### Cơ sở k = 1

Greedy chọn hoạt động có thời gian kết thúc nhỏ nhất trong toàn bộ tập hoạt động. Vì o₁ cũng là một hoạt động của tập:

**f(g₁) ≤ f(o₁)**.

Nếu O có ít nhất một hoạt động thì greedy không thể dừng ngay trước hoạt động đầu tiên.

### Bước quy nạp

Giả sử với k−1 đã có:

**f(gₖ₋₁) ≤ f(oₖ₋₁)**.

Vì lịch O hợp lệ:

**s(oₖ) ≥ f(oₖ₋₁)**.

Kết hợp hai bất đẳng thức:

**s(oₖ) ≥ f(oₖ₋₁) ≥ f(gₖ₋₁)**.

Vậy hoạt động **oₖ tương thích với lịch greedy đã chọn đến gₖ₋₁**. Nghĩa là khi greedy chuẩn bị chọn hoạt động thứ k, tập ứng viên **không rỗng**: ít nhất oₖ là một ứng viên tương thích.

Greedy luôn chọn hoạt động **kết thúc sớm nhất trong các ứng viên tương thích**, nên:

**f(gₖ) ≤ f(oₖ)**.

Bất biến tiếp tục đúng. Lưu ý: trong chứng minh này, ta không yêu cầu hoạt động của greedy giống hệt hoạt động của O; ta chỉ so **thời gian kết thúc** sau cùng số lựa chọn.

### Kết luận tối ưu bằng phản chứng

Giả sử greedy chọn r hoạt động và dừng, nhưng tồn tại một lịch hợp lệ O chọn **m > r** hoạt động.

Từ bất biến tại k=r:

**f(gᵣ) ≤ f(oᵣ)**.

Vì O vẫn có hoạt động oᵣ₊₁:

**s(oᵣ₊₁) ≥ f(oᵣ) ≥ f(gᵣ)**.

Vậy oᵣ₊₁ **vẫn tương thích với hoạt động cuối cùng của greedy**. Greedy phải còn một hoạt động để chọn, mâu thuẫn với việc nó đã dừng ở r. Do đó không có lịch hợp lệ nào có nhiều hơn r hoạt động: **greedy tối ưu**.

Nếu tập hoạt động rỗng, greedy trả 0; kết luận đúng trực tiếp, không cần đặt g₁.

### Điểm cần nhớ trong chứng minh

Không so số lượng sau cùng ngay từ đầu; ta chứng minh trước một thước đo giúp **mở rộng lời giải**. Đó là thời gian kết thúc của **hoạt động thứ k**. Bất biến làm cho một hoạt động trong lời giải O cũng hợp lệ cho greedy ở bước tương ứng, nhờ vậy greedy **không thể hết lựa chọn sớm hơn** một lịch khác có nhiều hoạt động hơn.

## 5. Những quy tắc tham lam sai cho bài chọn hoạt động

Chỉ vì một quy tắc có vẻ hợp lý không có nghĩa nó tạo được bất biến staying ahead.

Xét bốn khoảng:

~~~text
X = [0,10)
Y = [1, 2)
Z = [2, 3)
W = [3, 4)
~~~

Nếu chọn **hoạt động bắt đầu sớm nhất**, ta lấy X và không chọn được Y,Z,W: chỉ **1 hoạt động**. Nhưng chọn Y,Z,W được **3 hoạt động**.

Vì sao thử chứng minh staying ahead cho “bắt đầu sớm nhất” thất bại? Bắt đầu sớm **không bảo đảm kết thúc sớm** và không bảo đảm còn nhiều cơ hội về sau. Không có bước suy luận hợp lệ từ **s(gₖ) ≤ s(oₖ)** sang “oₖ₊₁ sẽ tương thích với greedy”.

Các quy tắc khác cũng cần xem xét bằng phản ví dụ:

- Chọn **khoảng dài nhất** trước có thể khóa nhiều khoảng ngắn.
- Chọn **khoảng ngắn nhất** không phải luôn tối ưu về số lượng nếu vị trí của khoảng ngắn làm cản các lựa chọn tiếp theo.
- Chọn hoạt động **có trọng số lớn nhất** không giải được bài chọn số lượng tối đa theo cùng chứng minh.
- Nếu mục tiêu đổi thành **tổng trọng số lớn nhất**, earliest-finish greedy cũng không còn bảo đảm tối ưu.

Ví dụ trọng số:

~~~text
A = [0,2), weight = 1
B = [2,4), weight = 1
C = [0,4), weight = 100
~~~

Greedy kết thúc sớm chọn A rồi B: tổng trọng số **2**. Lời giải tối ưu cho **tổng trọng số** lại chọn C: **100**. Bất biến “kết thúc sớm hơn” chỉ chứng minh được mục tiêu **số lượng**, không phải tự động chứng minh mọi mục tiêu khác.

## 6. Ví dụ B — Chọn ít đoạn nhất để phủ [0,T]

Cho một tập các đoạn liên tục **[lᵢ,rᵢ]** với **lᵢ < rᵢ**. Có thể chọn nhiều đoạn; các đoạn được phép **chồng lấn hoặc tiếp giáp**. Cần chọn **ít đoạn nhất** sao cho hợp của những đoạn đã chọn phủ toàn bộ đoạn đích **[0,T]**, với **T ≥ 0**.

Khác với bài chọn hoạt động, ở đây hai đoạn chồng nhau **không bị cấm**; trái lại, giao nhau có thể giúp mở rộng miền phủ liên tục.

Ví dụ T = 10:

| Đoạn | Trái | Phải |
| --- | ---: | ---: |
| P | 0 | 4 |
| Q | 0 | 2 |
| R | 2 | 7 |
| S | 4 | 8 |
| T | 7 | 10 |
| U | 8 | 11 |
| V | 1 | 3 |

Một cách chọn là **P → S → U**:

~~~text
Bắt đầu: đã phủ tới 0
Chọn P [0,4]:  đã phủ tới 4
Chọn S [4,8]:  đã phủ tới 8
Chọn U [8,11]: đã phủ tới 11 >= T=10

Kết quả: dùng 3 đoạn.
~~~

Quy tắc greedy:

1. Gọi **reach** là ranh giới phải của phần đích **[0,reach]** đã phủ liên tục.
2. Trong mọi đoạn có **l ≤ reach** và **r > reach**, chọn đoạn có **r lớn nhất**.
3. Cập nhật **reach = r** của đoạn vừa chọn.
4. Lặp đến khi **reach ≥ T**; nếu không có đoạn nào mở rộng reach thì **không thể phủ [0,T]**.

Có thể sắp các đoạn theo l tăng dần, dùng con trỏ để quét mỗi đoạn tối đa một lần. Các đoạn đã xem nhưng không chọn **không thể trở thành lựa chọn tốt hơn về sau** nếu r của chúng không vượt reach đã đạt.

### Tại sao chọn r lớn nhất, không chọn chiều dài đoạn lớn nhất?

Lợi thế của bài phủ là **vươn xa nhất về bên phải trong khi không để lại lỗ hổng**, chứ không phải chiều dài tuyệt đối r−l.

Ví dụ T=10, có các đoạn:

~~~text
A = [-100,1]  (dài 101)
B = [0,4]     (dài 4)
C = [3,10]    (dài 7)
~~~

Tại reach=0, nếu chọn đoạn **dài nhất** trong các đoạn bắt đầu trước reach, ta chọn A và chỉ vươn tới 1; sau đó còn cần B rồi C: **3 đoạn**. Nếu chọn **r lớn nhất**, lấy B (reach=4) rồi C (reach=10): chỉ **2 đoạn**.

Đây là một phản ví dụ cho lựa chọn “dài nhất”, đồng thời làm rõ tại sao thước đo đúng phải là **tọa độ phủ xa nhất sau k đoạn**.

## 7. Chứng minh staying ahead cho phủ đoạn tối thiểu

Xét thuật toán greedy tạo các ranh giới:

**G₀ = 0, G₁, G₂, ...**,

trong đó Gₖ là vị trí xa nhất đã được greedy phủ liên tục sau k lựa chọn. Mỗi lựa chọn phải mở rộng reach, nên Gₖ > Gₖ₋₁ trong khi chưa phủ đủ T.

Xét một phương án hợp lệ bất kỳ chọn các đoạn theo một **chuỗi phủ liên tục từ 0**; gọi O₀=0 và Oₖ là ranh giới phải đã phủ sau k đoạn. Mọi lời giải phủ [0,T] bằng m đoạn đều có thể sắp xếp/chọn ra một chuỗi không có lỗ hổng, dùng **không quá m đoạn**; các đoạn dư không cần cho phép chứng minh.

### Bất biến

Với mọi k mà phương án so sánh đã có k bước hữu ích:

**Gₖ ≥ Oₖ.**

Nói cách khác, **với cùng số đoạn**, greedy phủ đến ít nhất vị trí mà đối thủ đạt được.

### Cơ sở

Tại k=0, cả hai bắt đầu tại **0**, nên G₀=O₀.

Ở bước đầu, mọi đoạn mở rộng từ 0 phải có l≤0 và r>0. Greedy chọn r lớn nhất trong tập ấy, nên G₁ ≥ O₁ nếu đối thủ chọn được một đoạn hữu ích.

### Bước quy nạp

Giả sử **Gₖ₋₁ ≥ Oₖ₋₁**.

Đoạn thứ k của phương án đối thủ phải có **lₖ ≤ Oₖ₋₁**, để không tạo lỗ hổng, và nó đạt ít nhất Oₖ về phía phải. Vì:

**lₖ ≤ Oₖ₋₁ ≤ Gₖ₋₁**,

đoạn này **có điểm bắt đầu nằm trước hoặc tại ranh giới mà greedy đã phủ**.

Nếu đoạn của đối thủ có rₖ > Gₖ₋₁, nó là một ứng viên hợp lệ có thể mở rộng reach của greedy, và greedy chọn đoạn có đầu phải **xa nhất**, nên:

**Gₖ ≥ rₖ ≥ Oₖ**.

Nếu rₖ ≤ Gₖ₋₁, greedy đã đi xa hơn hoặc bằng đoạn ấy **trước cả bước k**. Không cần chọn đúng đoạn đó; bất biến vẫn được duy trì với những bước greedy tiếp theo. Nếu greedy đã đạt T thì đã hoàn thành và không cần xét thêm.

Cài đặt quét theo đầu trái có thể đã bỏ qua một đoạn đối thủ ở bước trước. Đoạn bị bỏ qua chỉ bị loại vì đầu phải của nó không vượt được reach greedy khi đó; vì reach không giảm, nó cũng không thể giúp mở rộng reach trong bước hiện tại. Do đó việc dùng con trỏ quét một chiều không phá tính đúng đắn.

### Kết luận

Nếu có lời giải phủ được [0,T] bằng m đoạn, từ bất biến greedy đạt **Gₘ ≥ Oₘ ≥ T** sau **không quá m** bước. Vậy greedy cũng phủ được [0,T] với không quá m đoạn. Chọn phương án đối thủ là tối ưu, ta suy ra greedy dùng **số đoạn tối thiểu**.

Ngược lại, nếu greedy đứng ở reach<T mà không còn đoạn nào có l≤reach và r>reach, mọi phương án phủ liên tục đến xa hơn reach đều phải có một đoạn vượt qua điểm reach. Không tồn tại đoạn như vậy, nên bài toán **vô nghiệm**.

Đối với **T=0**, đoạn đích là một điểm và theo quy ước bài học cần **0 đoạn**; nếu đề quy định phải có một khoảng chứa điểm 0 thì đây sẽ là **một bài toán khác** và phải xử lý riêng.

## 8. Đặt cạnh nhau: vì sao hai bài cần hai bất biến khác nhau?

| Tiêu chí | Chọn hoạt động không giao nhau | Phủ [0,T] bằng ít đoạn |
| --- | --- | --- |
| Ràng buộc | Các khoảng được chọn không giao nhau | Các đoạn phải phủ liên tục, được chồng lấn |
| Mục tiêu | Tối đa số hoạt động | Tối thiểu số đoạn |
| Quy tắc greedy | Chọn hoạt động **kết thúc sớm nhất** còn tương thích | Chọn đoạn **vươn phải xa nhất** từ ranh giới đã phủ |
| Trạng thái tiến độ | finish sau k hoạt động | reach sau k đoạn |
| Bất biến | Gₖ.finish **≤** Oₖ.finish | Gₖ.reach **≥** Oₖ.reach |
| Cầu nối quy nạp | Hoạt động thứ k của O cũng tương thích với greedy | Đoạn tiếp theo của O cũng bắt đầu không quá reach greedy |
| Kết luận | Greedy không thể dừng trước một lịch có nhiều hoạt động hơn | Greedy đạt đích không muộn hơn một lời giải dùng nhiều đoạn |
| Thời gian điển hình | O(n log n) vì sắp theo finish | O(n log n) vì sắp theo left |

Một thước đo chỉ hữu ích nếu nó đảm bảo được **tập lựa chọn cho tương lai**. Với chọn hoạt động, finish nhỏ tốt; với phủ, reach lớn tốt. Đừng mặc định “lợi thế” luôn tương ứng với số lớn hơn.

## 9. Java 17+: hai thuật toán tham lam chạy độc lập

Chương trình minh họa cả hai bài và cố ý dùng tên lớp/record riêng để phân biệt:

- **Activity** có khoảng nửa mở **[start,end)**, tương thích khi hoạt động sau bắt đầu **≥** end của hoạt động trước.
- **Segment** mô tả đoạn đóng liên tục **[left,right]**, dùng để phủ [0,target] bằng số đoạn ít nhất.
- Danh sách đầu vào **không bị sắp xếp trực tiếp**; chương trình tạo bản sao rồi sort.
- Trường hợp **không thể phủ** trả **Optional.empty()**, khác với **Optional.of(List.of())** khi target=0.
- Kiểm tra mỗi khoảng có độ dài dương; thuật toán không tự diễn giải khoảng có đầu cuối ngược chiều.

~~~java
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Objects;
import java.util.Optional;

public class GreedyStaysAheadDemo {

    record Activity(String id, int start, int end) {}
    record Segment(String id, int left, int right) {}

    static List<Activity> maxNonOverlapping(List<Activity> input) {
        Objects.requireNonNull(input, "input");
        List<Activity> sorted = new ArrayList<>(input);

        for (Activity a : sorted) {
            Objects.requireNonNull(a, "activity");
            Objects.requireNonNull(a.id(), "activity id");
            if (a.start() >= a.end()) {
                throw new IllegalArgumentException("Invalid activity");
            }
        }

        sorted.sort(Comparator
                .comparingInt(Activity::end)
                .thenComparingInt(Activity::start)
                .thenComparing(Activity::id));

        List<Activity> chosen = new ArrayList<>();
        int lastEnd = Integer.MIN_VALUE;

        for (Activity a : sorted) {
            if (a.start() >= lastEnd) {
                chosen.add(a);
                lastEnd = a.end();
            }
        }

        return List.copyOf(chosen);
    }

    static Optional<List<Segment>> minimumCover(
            int target, List<Segment> input) {
        if (target < 0) {
            throw new IllegalArgumentException("target must be >= 0");
        }
        Objects.requireNonNull(input, "input");

        List<Segment> sorted = new ArrayList<>(input);
        for (Segment s : sorted) {
            Objects.requireNonNull(s, "segment");
            Objects.requireNonNull(s.id(), "segment id");
            if (s.left() >= s.right()) {
                throw new IllegalArgumentException("Invalid segment");
            }
        }

        if (target == 0) {
            return Optional.of(List.of());
        }

        sorted.sort(Comparator
                .comparingInt(Segment::left)
                .thenComparingInt(Segment::right)
                .thenComparing(Segment::id));

        List<Segment> chosen = new ArrayList<>();
        int reach = 0;
        int index = 0;

        while (reach < target) {
            Segment best = null;
            int newReach = reach;

            // Mỗi đoạn chỉ được quét một lần.
            while (index < sorted.size()
                    && sorted.get(index).left() <= reach) {
                Segment candidate = sorted.get(index++);
                if (candidate.right() > newReach) {
                    best = candidate;
                    newReach = candidate.right();
                }
            }

            // Không có đoạn bắt đầu kịp và mở rộng được reach.
            if (best == null) {
                return Optional.empty();
            }

            chosen.add(best);
            reach = newReach;
        }

        return Optional.of(List.copyOf(chosen));
    }

    static List<String> activityIds(List<Activity> activities) {
        return activities.stream().map(Activity::id).toList();
    }

    static String coverIds(Optional<List<Segment>> answer) {
        return answer
                .map(parts -> parts.stream()
                        .map(Segment::id).toList().toString())
                .orElse("impossible");
    }

    public static void main(String[] args) {
        List<Activity> activities = List.of(
                new Activity("A", 1, 4),
                new Activity("B", 3, 5),
                new Activity("C", 0, 6),
                new Activity("D", 5, 7),
                new Activity("E", 3, 9),
                new Activity("F", 5, 9),
                new Activity("G", 6, 10),
                new Activity("H", 8, 11),
                new Activity("I", 8, 12),
                new Activity("J", 2, 14),
                new Activity("K", 12, 16)
        );

        List<Activity> chosen = maxNonOverlapping(activities);
        System.out.println("Scheduling: " + activityIds(chosen));
        System.out.println("Selected count: " + chosen.size());

        List<Segment> segments = List.of(
                new Segment("P", 0, 4),
                new Segment("Q", 0, 2),
                new Segment("R", 2, 7),
                new Segment("S", 4, 8),
                new Segment("T", 7, 10),
                new Segment("U", 8, 11),
                new Segment("V", 1, 3)
        );

        System.out.println("Cover [0,10]: "
                + coverIds(minimumCover(10, segments)));

        List<Segment> gap = List.of(
                new Segment("X", 0, 2),
                new Segment("Y", 3, 6)
        );
        System.out.println("Gap [0,6]: "
                + coverIds(minimumCover(6, gap)));
        System.out.println("Empty target: "
                + coverIds(minimumCover(0, segments)));
    }
}
~~~

Lưu đúng tên **GreedyStaysAheadDemo.java**. Biên dịch và chạy bằng JDK 17 trở lên:

~~~bash
javac GreedyStaysAheadDemo.java
java GreedyStaysAheadDemo
~~~

Đầu ra:

~~~text
Scheduling: [A, D, H, K]
Selected count: 4
Cover [0,10]: [P, S, U]
Gap [0,6]: impossible
Empty target: []
~~~

### Phân tích cài đặt và độ phức tạp

**Chọn hoạt động:**

- Sort tăng theo end, sau đó theo start và id để kết quả có thể tái lập khi có hòa: **O(n log n)** thời gian thông thường.
- Duyệt n hoạt động một lần, mỗi hoạt động chỉ kiểm tra start ≥ lastEnd: **O(n)**.
- Tổng thời gian: **O(n log n)**; nếu dữ liệu đã sắp theo end và được tin cậy theo đúng quy tắc, phần chọn riêng chỉ O(n).
- Bộ nhớ phụ có thể **O(n)** cho bản sao, kết quả và không gian sort; chương trình không tự sửa danh sách đầu vào.
- Nếu không có hoạt động nào, trả danh sách rỗng, tức số hoạt động tối ưu bằng 0.

**Phủ [0,target]:**

- Sort tăng theo left: **O(n log n)**.
- Chỉ số index đi tới trước và không lùi; mỗi đoạn được xét nhiều nhất một lần trong vòng while bên trong: **O(n)** tổng cho bước quét.
- Số lần chọn không vượt n nếu mỗi lựa chọn phải mở rộng reach.
- Tổng thời gian: **O(n log n)**; bộ nhớ phụ **O(n)** cho bản sao và kết quả.
- Một đoạn chỉ có thể được chọn nếu nó bắt đầu **không sau reach hiện tại** và có điểm phải **lớn hơn reach**. Nếu không có, kết quả là **vô nghiệm**.
- Khi target=0, theo quy ước trong chương trình không cần đoạn nào; trả danh sách rỗng **thành công**, khác với trường hợp vô nghiệm.

**Các lựa chọn hòa:** Nếu hai hoạt động cùng end, chọn hoạt động nào theo quy tắc so sánh phụ không làm thay đổi **số lượng tối ưu**. Nếu hai đoạn phủ có cùng right, chọn một trong hai không thay đổi **reach** đạt được tại bước đó; các trường phụ chỉ để đầu ra ổn định.

## 10. Phân tích một lượt chạy của hai thuật toán

### Chọn hoạt động

Với bảng hoạt động ở mục 3, sau khi sort theo end:

~~~text
A(1,4), B(3,5), C(0,6), D(5,7), E(3,9),
F(5,9), G(6,10), H(8,11), I(8,12), J(2,14), K(12,16)
~~~

Các thay đổi lastEnd:

| Hoạt động | Quyết định | Giải thích | lastEnd |
| --- | --- | --- | ---: |
| A [1,4) | Chọn | Lịch còn trống | 4 |
| B [3,5) | Bỏ | 3 < 4 | 4 |
| C [0,6) | Bỏ | 0 < 4 | 4 |
| D [5,7) | Chọn | 5 ≥ 4 | 7 |
| E [3,9) | Bỏ | 3 < 7 | 7 |
| F [5,9) | Bỏ | 5 < 7 | 7 |
| G [6,10) | Bỏ | 6 < 7 | 7 |
| H [8,11) | Chọn | 8 ≥ 7 | 11 |
| I [8,12) | Bỏ | 8 < 11 | 11 |
| J [2,14) | Bỏ | 2 < 11 | 11 |
| K [12,16) | Chọn | 12 ≥ 11 | 16 |

Những quyết định bỏ không có nghĩa hoạt động bị loại vì “kém chất lượng tuyệt đối”. Chúng bị loại vì **không tương thích với lịch đã chọn**; tính tối ưu của việc chọn lịch trước đó đã được chứng minh bằng bất biến kết thúc sớm.

### Phủ đoạn

Với các đoạn P...V ở mục 6:

| Lượt | Reach trước | Các đoạn có thể mở rộng | Chọn | Reach sau |
| ---: | ---: | --- | --- | ---: |
| 1 | 0 | P [0,4], Q [0,2] | P | 4 |
| 2 | 4 | R [2,7], S [4,8] (V [1,3] không mở rộng) | S | 8 |
| 3 | 8 | T [7,10], U [8,11] | U | 11 |

Đã phủ tới 11 ≥ 10 nên dừng. **Không bắt buộc điểm phải cuối cùng bằng đúng T**; vượt T vẫn được, vì mục tiêu là phủ hết [0,T].

Với X=[0,2] và Y=[3,6], sau X chỉ đạt reach=2, nhưng Y bắt đầu tại 3>2. Có **khoảng trống (2,3)** nên không thể phủ liên tục [0,6]. Thuật toán phải báo vô nghiệm, không được chọn Y rồi xem [0,6] đã phủ xong.

## 11. Staying ahead khác gì với chứng minh trao đổi?

Hai kỹ thuật thường chứng minh tính đúng của cùng một greedy nhưng đi theo cách khác nhau.

### Staying ahead

So sánh **đại lượng của tiền tố** greedy với một phương án khả thi bất kỳ:

~~~text
G_1 không kém O_1
G_2 không kém O_2
...
G_k không kém O_k
=> không có phương án nào vượt được greedy ở mục tiêu cuối.
~~~

Điểm mạnh là có thể chứng minh bằng **bất biến định lượng**, không phải dựng một lời giải tối ưu mới.

### Exchange argument (lập luận trao đổi)

Bắt đầu từ một lời giải tối ưu O. Nếu lựa chọn đầu tiên của O khác greedy, thay một phần của O bằng lựa chọn của greedy sao cho:

1. Lời giải vẫn **khả thi**.
2. Giá trị mục tiêu **không tệ hơn**.
3. Có thể tiếp tục chỉnh O để nó chia sẻ những lựa chọn đầu với greedy.

Kết luận tồn tại một lời giải tối ưu bắt đầu bằng lựa chọn greedy, sau đó áp dụng lại cho bài toán còn lại.

Ví dụ chọn hoạt động: nếu O bắt đầu bằng o₁, đổi thành hoạt động g₁ kết thúc sớm nhất. Vì f(g₁)≤f(o₁), mọi hoạt động sau o₁ trong O vẫn có thể theo sau g₁. Số hoạt động không giảm. Đây là một chứng minh bằng trao đổi; còn staying ahead không yêu cầu thay đổi O, chỉ so f(gₖ) với f(oₖ).

### Khi nào chọn kỹ thuật nào?

- Có thước đo tiền tố rõ ràng và dễ chứng minh bằng quy nạp → **staying ahead**.
- Dễ thay lựa chọn của một lời giải tối ưu mà không giảm chất lượng → **exchange**.
- Có thể tách bài toán còn lại thành một bài cùng dạng sau mỗi lựa chọn → cần kết hợp **greedy-choice property** và **optimal substructure**.
- Không tìm được bất biến hoặc phép trao đổi hợp lệ → phải kiểm tra lại chiến lược greedy; không nên “ép” một chứng minh.

Hai kỹ thuật là công cụ **chứng minh**, không phải thuật toán thay thế cho thao tác lựa chọn.

## 12. Những sai lầm logic thường gặp khi viết chứng minh

1. **Chỉ nói “chọn cục bộ tốt nhất nên toàn cục tốt nhất”.** Đây là mô tả greedy, chưa phải chứng minh.
2. **Chọn sai thước đo lợi thế.** Bắt đầu sớm không đồng nghĩa kết thúc sớm; đoạn dài không đồng nghĩa vươn phải xa.
3. **Không so cùng số bước.** Muốn chứng minh duy trì lợi thế phải xác định “bước k” tương đương trong hai phương án.
4. **Bỏ qua tính hợp lệ của ứng viên đối thủ.** Bước quy nạp phải chỉ ra lựa chọn thứ k của đối thủ không bị ràng buộc greedy loại mất, hoặc greedy đã có tiến độ tốt hơn.
5. **Không phát biểu điều kiện cơ sở.** Tập rỗng, không có hoạt động thứ nhất hoặc target=0 phải xử lý riêng.
6. **Chỉ chứng minh một phép bất đẳng thức nhưng không suy ra mục tiêu cuối.** Bất biến chưa đủ nếu thiếu phần kết luận tối ưu hoặc phản chứng.
7. **Áp dụng chứng minh số lượng cho mục tiêu tổng trọng số.** Thay objective có thể làm greedy cũ sai ngay.
8. **Nhầm thời gian đóng và nửa mở.** Với [s,f), hoạt động bắt đầu tại f của hoạt động trước là tương thích. Với khoảng thời gian đóng hay quy tắc khác, phải điều chỉnh điều kiện.
9. **Tưởng mọi đoạn phủ có thể chọn độc lập.** Không được để lại lỗ hổng rồi “nhảy” đến đoạn ở xa hơn.
10. **Bỏ qua cách các đoạn đã xét được loại.** Khi quét theo left, cần hiểu vì sao đoạn cũ không mở rộng reach sẽ không hữu ích về sau.
11. **Dùng trạng thái tiến độ không đủ thông tin.** Nếu hai trạng thái có cùng chỉ số nhưng năng lực tương lai khác nhau, phải bổ sung đại lượng so sánh.
12. **Cho rằng lập luận đúng cho dữ liệu có trọng số, có thời gian chờ hay tài nguyên phụ.** Các ràng buộc mới có thể phá bước quy nạp; cần chứng minh lại.
13. **Không xử lý hòa và tính xác định của đầu ra.** Nhiều phương án có cùng kết thúc hoặc reach có thể đều tối ưu; nếu cần một lịch cụ thể, đặt quy tắc phá hòa nhất quán.
14. **Bỏ qua hành vi của thuật toán khi vô nghiệm.** Với bài phủ, không có đoạn mở rộng reach phải trả thất bại thay vì đưa ra danh sách chưa phủ đủ.

## 13. Khi staying ahead không chứng minh được: bài đổi tiền

Xét các mệnh giá **{1,3,4}** và số tiền cần đổi **6**, mục tiêu dùng **ít đồng nhất** (số tờ/đồng ít nhất).

Greedy chọn mệnh giá lớn nhất không vượt tiền còn lại:

~~~text
6 -> chọn 4, còn 2
2 -> chọn 1, còn 1
1 -> chọn 1, còn 0

Greedy: [4,1,1] = 3 đồng.
~~~

Nhưng phương án **[3,3]** dùng **2 đồng**, tốt hơn.

Nếu chọn thước đo “tiền còn lại sau k đồng”, greedy sau đồng đầu còn 2, trong khi phương án tối ưu sau đồng đầu còn 3; greedy có vẻ **đang đi trước** về số tiền đã trả. Tuy nhiên, từ “tiền còn ít hơn” không suy ra “số đồng còn cần ít hơn”, vì khả năng tạo số dư tùy thuộc tập mệnh giá. Bước quy nạp không hợp lệ.

**Bài học:** bất biến cần có cả **khả năng tiếp tục giải bài** và **liên hệ với objective**, không phải chỉ một thước đo tiến bộ có vẻ đẹp. Khi greedy sai, hãy xây phản ví dụ nhỏ thay vì cố chứng minh một quan hệ không đúng.

## 14. Mẫu chứng minh có thể tái sử dụng

Khi gặp bài toán tham lam mới, có thể dùng quy trình sau để thiết kế lời giải và chứng minh:

**Bước 1 — Viết chính xác mục tiêu.** Tối đa số lượng, tối thiểu số bước, tối đa giá trị hay tối thiểu thời gian? Đừng trộn chúng.

**Bước 2 — Viết rõ ràng quy tắc chọn.** Tại một trạng thái, tập ứng viên hợp lệ là gì? Greedy chọn theo thuộc tính nào? Có cần sắp xếp trước?

**Bước 3 — Chọn đối thủ so sánh.** Lấy một lời giải khả thi bất kỳ O, hoặc một lời giải tối ưu O có các bước được sắp theo thứ tự thích hợp.

**Bước 4 — Định nghĩa một thước đo tiền tố.** Ví dụ thời gian kết thúc sau k công việc, đoạn đã phủ sau k lựa chọn, tài nguyên còn lại sau k hành động. Nêu rõ hướng bất đẳng thức.

**Bước 5 — Viết mệnh đề mạnh đủ dùng.** Không chỉ “greedy tốt”, mà là “với mọi k mà O thực hiện, greedy cũng thực hiện được k bước và trạng thái greedy không kém theo thước đo”.

**Bước 6 — Chứng minh cơ sở.** Trường hợp k=0 hoặc k=1 phải đúng theo quy tắc greedy và điều kiện đầu vào.

**Bước 7 — Chứng minh quy nạp.** Từ bất biến tại k−1, chứng minh hành động thứ k của đối thủ **không tốt hơn lựa chọn có thể thực hiện của greedy**. Đây thường là bước khó nhất và quyết định thuật toán đúng hay sai.

**Bước 8 — Kết luận tối ưu.** Nếu O tốt hơn greedy, điều gì mâu thuẫn với bất biến hoặc với điều kiện dừng? Phải chỉ ra cụ thể.

**Bước 9 — Kiểm tra phản ví dụ nhỏ.** Thử dữ liệu rỗng, trùng mốc, khoảng tiếp giáp, lỗ hổng, nhiều phương án cùng chất lượng và một mục tiêu gần giống nhưng khác.

**Bước 10 — Phân tích độ phức tạp.** Tách chi phí chuẩn bị (sort), duyệt/chọn, bộ nhớ và chi phí tạo kết quả. Tối ưu của greedy không nói lên thời gian chạy nếu thao tác “chọn tốt nhất” được cài đặt kém hiệu quả.

### Khung trình bày lời giải gọn nhưng đủ chặt chẽ

~~~text
1. Thuật toán:
   - Chuẩn bị ...
   - Ở mỗi bước, chọn ... trong tập ứng viên hợp lệ ...
   - Cập nhật trạng thái ...
   - Dừng khi ...

2. Bất biến staying ahead:
   - Với mọi phương án O và mọi k liên quan:
     measure(G_k) <= / >= measure(O_k).

3. Cơ sở:
   - Vì greedy chọn ... nên bất đẳng thức đúng ở k=1.

4. Quy nạp:
   - Giả sử đúng ở k-1.
   - Lựa chọn k của O phải thỏa ...
   - Do giả thiết quy nạp, lựa chọn ấy cũng ...
   - Vì greedy chọn tốt nhất trong tập này nên ...

5. Kết luận:
   - Nếu O có đáp án tốt hơn thì ...
   - Mâu thuẫn với ...; greedy tối ưu.

6. Độ phức tạp:
   - Thời gian chuẩn bị + số bước chọn + bộ nhớ.
~~~

Khi lời giải không thể lấp đầy phần **“do giả thiết quy nạp, lựa chọn ấy cũng...”**, cần xem xét lại **thước đo**, **tập ứng viên** hoặc **chính quy tắc greedy**.

## 15. Bài tập tự kiểm tra

**Câu 1.** Trong bài chọn nhiều hoạt động không giao nhau, tại sao bất biến cần dùng **thời gian kết thúc**, không phải thời gian bắt đầu?  
**Đáp án:** Kết thúc sớm hơn bảo đảm hoạt động tiếp theo của lịch đối thủ vẫn tương thích với lịch greedy; bắt đầu sớm không tạo bảo đảm ấy.

**Câu 2.** Nếu một lịch O có k hoạt động và greedy đã chọn k−1 hoạt động với **f(gₖ₋₁)≤f(oₖ₋₁)**, hãy giải thích vì sao oₖ hợp lệ ở bước k của greedy.  
**Đáp án:** O hợp lệ nên s(oₖ)≥f(oₖ₋₁)≥f(gₖ₋₁); do đó oₖ không chồng lấn với hoạt động cuối greedy.

**Câu 3.** Với các hoạt động [0,10), [1,2), [2,3), [3,4), quy tắc bắt đầu sớm nhất và kết thúc sớm nhất lần lượt chọn bao nhiêu?  
**Đáp án:** Bắt đầu sớm nhất chọn 1; kết thúc sớm nhất chọn 3.

**Câu 4.** Trong bài phủ [0,T], “đoạn dài nhất” và “đầu phải xa nhất” có phải một quy tắc không?  
**Đáp án:** Không. Độ dài là r−l; một đoạn bắt đầu rất xa bên trái có thể dài nhưng vươn ít về phía phải, nên không tạo reach tốt nhất.

**Câu 5.** Khi đang phủ tới reach=5, có các đoạn [2,6], [4,9], [6,12]. Chọn đoạn nào và reach mới bằng bao nhiêu?  
**Đáp án:** [4,9] vì bắt đầu ≤5 và có đầu phải lớn nhất trong các ứng viên mở rộng được; reach mới = **9**. Đoạn [6,12] chưa hợp lệ vì để lại lỗ hổng (5,6).

**Câu 6.** Nếu một phương án phủ bằng m đoạn đạt tới T nhưng greedy ở bước m đạt reach ≥ T, kết luận gì?  
**Đáp án:** Greedy dùng không quá m đoạn. Khi so với một phương án tối ưu m đoạn, greedy cũng tối ưu về số đoạn.

**Câu 7.** Vì sao đổi tiền 6 bằng mệnh giá {1,3,4} là phản ví dụ cho greedy chọn mệnh giá lớn nhất trước?  
**Đáp án:** Greedy dùng 4+1+1 = 3 đồng; tối ưu dùng 3+3 = 2 đồng. Ít tiền còn lại ở bước đầu không bảo đảm ít đồng hơn cuối cùng.

**Câu 8.** Tại sao cần một phần **kết luận cuối** sau khi đã chứng minh bất biến staying ahead?  
**Đáp án:** Bất biến chỉ so các trạng thái tiền tố. Phải chứng minh thêm rằng nó ngăn đối thủ đạt mục tiêu tốt hơn, ví dụ không thể chọn thêm hoạt động khi greedy đã dừng, hoặc không thể phủ đích bằng ít đoạn hơn greedy.

**Câu 9.** Nếu thời gian kết thúc của hai hoạt động bằng nhau, chọn hoạt động nào có làm thay đổi chứng minh tối đa số lượng không?  
**Đáp án:** Không, miễn lựa chọn hợp lệ và cùng thời gian kết thúc; bất biến về finish vẫn đúng. Chỉ cần quy tắc hòa nếu muốn đầu ra cụ thể, có thể tái lập.

**Câu 10.** Nếu một đoạn phủ bắt đầu đúng tại reach hiện tại, có dùng được không?  
**Đáp án:** Có khi các đoạn biểu diễn miền liên tục và cho phép tiếp giáp: l=reach không tạo lỗ hổng, miễn r>reach.

## 16. Tổng kết

**Chứng minh bằng duy trì lợi thế qua từng bước** là cách biến một trực giác tham lam thành một lập luận có thể kiểm chứng:

- **Chọn đúng thước đo** phản ánh khả năng tiếp tục, không chỉ vẻ tốt của một bước hiện tại.
- **So sánh cùng số quyết định** giữa greedy và phương án đối thủ.
- **Chứng minh bất biến bằng quy nạp**, đặc biệt chỉ ra vì sao bước tiếp theo của đối thủ cũng không vượt được greedy.
- **Suy ra mục tiêu cuối bằng phản chứng hoặc so tiến độ đạt đích**.
- **Thử phản ví dụ** khi thước đo không đủ liên hệ với chất lượng lời giải.

Trong chọn hoạt động, greedy **kết thúc không muộn hơn** sau k lựa chọn nên chọn được số hoạt động tối đa. Trong phủ đoạn, greedy **vươn không ngắn hơn** sau k lựa chọn nên đạt đích với số đoạn tối thiểu. Đó là hai hình mẫu quan trọng của tư duy **greedy stays ahead**; hãy dùng cấu trúc chứng minh này để kiểm tra những quy tắc tham lam khác thay vì mặc định mọi lựa chọn cục bộ đều tối ưu.