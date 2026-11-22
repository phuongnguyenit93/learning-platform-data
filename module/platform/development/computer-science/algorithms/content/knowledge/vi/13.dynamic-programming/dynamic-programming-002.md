# Xác định trạng thái chứa đủ thông tin cho tương lai

Trong **quy hoạch động** (*dynamic programming – DP*), khó khăn thường không phải là viết mảng `dp` hay vòng lặp, mà là **chọn trạng thái**. Một trạng thái tốt phải lưu **đủ thông tin về quá khứ để quyết định mọi lựa chọn hợp lệ và giá trị tối ưu từ thời điểm hiện tại trở đi**, nhưng không giữ những chi tiết quá khứ không còn ảnh hưởng tới tương lai.

Hai lịch sử khác nhau có thể được gộp vào một trạng thái **chỉ khi chúng tương đương đối với phần việc còn lại**. Nếu gộp những lịch sử mà tương lai của chúng khác nhau, công thức chuyển trạng thái có thể bỏ qua ràng buộc và cho kết quả sai. Nếu lưu toàn bộ lịch sử dù không cần thiết, số trạng thái lại quá lớn, khiến DP chậm hoặc không thể chạy.

Bài học này trình bày cách kiểm tra **tính đủ thông tin** (*state sufficiency*), cách tìm biến trạng thái, phép chuyển, trường hợp cơ sở, quy tắc gộp lịch sử, cách giảm chiều, chứng minh tính đúng và phân tích số trạng thái. Ví dụ Java 17+ hoàn chỉnh giải bài **chọn công việc có ngân sách nhưng không được chọn hai công việc liền kề**: trường hợp này cho thấy rõ vì sao trạng thái `(i, ngân_sách_còn_lại)` là thiếu và cần thêm cờ `đã_chọn_phần_tử_trước`.

## 1. Trạng thái DP là bản tóm tắt có mục đích của quá khứ

Giả sử thuật toán đang xử lý một chuỗi quyết định. Tại một thời điểm, ta đã đưa ra một số quyết định trong quá khứ và còn một **bài toán tiếp diễn**.

Một trạng thái DP cần trả lời:

- **Đang đứng ở đâu?** Chỉ số phần tử, vị trí trên lưới, lượng dữ liệu đã xử lý, hoặc thời điểm hiện tại.
- **Nguồn lực nào còn lại hoặc đã dùng?** Ngân sách, khối lượng, số lượt, năng lượng, giới hạn thay đổi.
- **Thông tin lịch sử nào làm thay đổi lựa chọn tiếp theo?** Phần tử trước có được chọn không, đỉnh vừa đi qua, ký tự cuối của chuỗi đang tạo, tập khóa đã có.
- **Từ đây cần tối ưu/đếm/kiểm tra điều gì?** Tổng lợi ích lớn nhất, tổng chi phí nhỏ nhất, số cách, hoặc có tồn tại phương án hay không.

Ví dụ: nếu hai lịch sử đều đã xét đến phần tử thứ i nhưng một lịch sử còn 5 đơn vị ngân sách và một lịch sử chỉ còn 2, hai lịch sử **không thể luôn được coi như cùng trạng thái** trong bài toán có chi phí. Những lựa chọn về sau có thể yêu cầu 4 đơn vị.

Ngược lại, nếu hai lịch sử cùng đến i, cùng ngân sách còn lại và các ràng buộc về sau chỉ phụ thuộc các đại lượng đó, **không cần lưu lại danh sách mọi phần tử đã chọn** chỉ để tính giá trị tối ưu của phần còn lại.

### Cách diễn đạt bằng tính Markov

Một trạng thái `s` đủ thông tin khi **tập hành động còn hợp lệ, trạng thái tiếp theo và đóng góp tương lai** đều có thể xác định từ `s` và hành động kế tiếp, không phải truy vấn lại toàn bộ lịch sử.

```text
history H1 ----\
                > state s ----action----> next state s'
history H2 ----/                       \-> reward/cost of action

H1 và H2 chỉ được gộp nếu mọi phần tiếp diễn
có cùng quy tắc khả thi và tác động tương lai.
```

Đây là trực giác về tính **không nhớ ngoài trạng thái** (*Markov property*). Không có nghĩa mọi bài toán chỉ cần biến `i`; thông tin có liên quan từ quá khứ phải được **mã hóa vào trạng thái**.

## 2. Phép thử quan trọng: hai lịch sử, một trạng thái dự kiến

Để kiểm tra một thiết kế trạng thái, hãy hỏi:

> Nếu có hai lịch sử khác nhau dẫn tới cùng trạng thái mà tôi dự định lưu, các quyết định tương lai hợp lệ và giá trị tốt nhất còn lại có luôn giống nhau không?

Nếu câu trả lời **không**, trạng thái đang **thiếu biến**.

Một cách thực tế là cố ý xây dựng **phản ví dụ nhỏ** gồm hai lịch sử có cùng các chỉ số/budget mà trạng thái hiện tại lưu nhưng khác nhau ở thông tin đã bỏ qua.

### Ví dụ thiếu biến trạng thái

Có ba công việc theo thứ tự 0, 1, 2; chọn công việc i phải trả `cost[i]`, nhận `value[i]`; **không được chọn hai công việc liên tiếp**. Tổng chi phí không vượt ngân sách B=4.

```text
index:        0   1    2
cost:        2   2    2
value:       1   1  100
budget đầu:  4
```

Xét thời điểm **i=2**, ngân sách còn lại đều là **2**:

- **Lịch sử A:** chọn công việc 0, **bỏ** công việc 1. Khi đến i=2, công việc liền trước **không được chọn**; vì vậy có thể chọn công việc 2 và nhận thêm 100.
- **Lịch sử B:** bỏ công việc 0, **chọn** công việc 1. Khi đến i=2, công việc liền trước **đã được chọn**; vì vậy **không thể** chọn công việc 2 dù còn đủ ngân sách.

Nếu trạng thái chỉ là `dp[i][remaining]`, cả hai lịch sử được gộp thành `dp[2][2]`, trong khi khả năng lựa chọn tiếp theo khác nhau. Đây là một **chứng cứ trực tiếp rằng trạng thái thiếu thông tin**, không chỉ là nghi ngờ.

Cần thêm một bit:

```text
dp(i, remaining, previousTaken)

i             : chỉ số công việc kế tiếp cần xét
remaining     : ngân sách còn lại
previousTaken : 1 nếu công việc i-1 được chọn, ngược lại 0
```

Khi đó hai lịch sử trên rơi vào **hai trạng thái khác nhau**: `dp(2,2,0)` và `dp(2,2,1)`.

**Lưu ý tinh tế:** Dù hai lịch sử có thể đã thu được **lợi ích trong quá khứ khác nhau**, ta không nhất thiết phải lưu số lợi ích đã thu vào trạng thái *value-to-go*. Ta tối ưu **lợi ích còn lại**, rồi cộng lợi ích quá khứ bên ngoài. Nếu DP là dạng *giá trị tốt nhất đạt đến trạng thái* thì cần giữ **giá trị tốt nhất** cho mỗi trạng thái, nhưng đó là giá trị của DP chứ không nhất thiết là một **tọa độ trạng thái**.

## 3. Tính đủ thông tin phải được chứng minh trên tương lai

Nói “trạng thái này có vẻ đủ” chưa phải chứng minh. Ta nên xác định bốn điều:

1. **Hành động còn khả thi** từ một trạng thái có thể xác định hoàn toàn từ trạng thái không?
2. **Trạng thái mới** sau hành động có thể tính mà không cần xem lại lịch sử không?
3. **Đóng góp mục tiêu** của hành động có phụ thuộc dữ liệu lịch sử chưa được lưu không?
4. **Trường hợp kết thúc** có xác định được chỉ bằng trạng thái không?

Với bài ngân sách + không liền kề, ở trạng thái `(i,b,p)`:

- Hành động **bỏ i** luôn khả thi: chuyển sang `(i+1,b,0)`, lợi ích tăng 0.
- Hành động **chọn i** chỉ khả thi nếu `p=0` và `cost[i] <= b`: chuyển sang `(i+1,b-cost[i],1)`, lợi ích tăng `value[i]`.
- Khi `i=n`, không còn công việc: lợi ích tương lai tối ưu là 0.

Mọi điều kiện trên chỉ phụ thuộc `i`, `b`, `p` và dữ liệu đầu vào cố định. Không cần biết đã chọn những chỉ số cũ nào ngoài việc **phần tử ngay trước có được chọn không**.

### Hai lịch sử tương đương nghĩa là gì?

Đối với DP tối ưu dạng **giá trị còn lại**, hai lịch sử được gọi là tương đương nếu:

- Chúng còn **cùng tập chuỗi hành động tương lai khả thi** (hoặc ít nhất cùng cấu trúc hành động và kết quả liên quan).
- Với mỗi chuỗi hành động tương lai tương ứng, **đóng góp mục tiêu từ thời điểm này** là như nhau.
- Khi kết thúc, điều kiện hợp lệ và cách đánh giá phần còn lại như nhau.

Khi các điều kiện đó đúng, một hàm `F(s)` có thể đại diện cho tương lai tối ưu của **mọi lịch sử** được ánh xạ vào s. Đây là nền tảng để **memoization** tái sử dụng kết quả mà không cần tính lại cho từng đường đi.

Tính đủ thông tin khác với **tính tối thiểu** của trạng thái. Thêm một biến dư vẫn có thể cho thuật toán đúng nhưng chậm hơn. Bỏ biến quan trọng có thể làm thuật toán sai.

## 4. Xây dựng bài toán ví dụ một cách đầy đủ

Bài toán:

- Có n công việc được đánh chỉ số 0..n-1 theo một thứ tự cố định.
- Công việc i có **chi phí `cost[i] >= 0`** và **lợi ích `value[i]`** (có thể âm, bằng 0 hoặc dương).
- Tổng chi phí của các công việc được chọn phải **≤ B**, với `B >= 0`.
- **Không được chọn hai công việc có chỉ số liên tiếp**.
- Có thể **không chọn công việc nào**, được lợi ích 0.
- Mục tiêu là **tối đa tổng lợi ích**. Nếu có nhiều lời giải cùng lợi ích tối đa, mã Java sẽ **ưu tiên bỏ công việc hiện tại** khi tái dựng để kết quả xác định.

Ví dụ:

```text
index:       0   1   2   3   4
cost:        2   3   2   3   2
value:       6  10   8   9   7
B = 6

Một nghiệm tốt nhất: chọn indices [0,2,4]
Tổng cost = 2+2+2 = 6
Tổng value = 6+8+7 = 21
Không có hai chỉ số được chọn liền kề.
```

Nếu chỉ có ngân sách và **không có ràng buộc liền kề**, trạng thái kiểu `(i,b)` thường đã đủ cho bài 0/1 knapsack theo thứ tự chỉ số. Chính ràng buộc tương tác với **lựa chọn ngay trước** buộc phải thêm cờ `previousTaken`.

## 5. Định nghĩa trạng thái và ý nghĩa của giá trị DP

Chọn quy ước **DP đi từ hiện tại về tương lai** (memoization trên bài toán hậu tố):

```text
F(i, b, p) =
    tổng lợi ích lớn nhất có thể kiếm thêm
    bằng cách quyết định các công việc i, i+1, ..., n-1,

    với:
      b là ngân sách CÒN LẠI, 0 <= b <= B
      p=1 nếu công việc i-1 đã được chọn; p=0 nếu không.

Không tính lợi ích của các công việc ở chỉ số < i vào F.
```

Điểm cuối:

```text
F(n, b, p) = 0
```

Không còn công việc nào, nên lợi ích **tương lai** là 0 bất kể còn bao nhiêu ngân sách và giá trị của p.

Cách đặt trạng thái này bảo đảm:

- Mỗi lần xét i, ta quyết định **chọn hoặc bỏ đúng một công việc**.
- `i` luôn tăng 1, nên đồ thị phụ thuộc giữa các trạng thái không có chu trình.
- `b` không bao giờ âm vì chỉ chọn khi đủ ngân sách.
- `p` có đúng hai giá trị 0/1.
- Hai lịch sử tương đương được gộp vào cùng `F(i,b,p)`.

**Không nhầm hai cách định nghĩa:** Một thiết kế khác có thể dùng `dp[i][b][p]` = lợi ích **lớn nhất đã đạt** sau khi xử lý i công việc và dùng hết b ngân sách. Đó là DP tiến, với ý nghĩa b là **ngân sách đã dùng**, không phải còn lại. Cả hai có thể đúng, nhưng **điều kiện đầu, chiều chuyển và cách trả kết quả phải được xây dựng theo đúng ý nghĩa đã chọn**. Trộn lẫn chúng là nguồn lỗi phổ biến.

## 6. Công thức chuyển trạng thái

Ở trạng thái `F(i,b,p)`, khi i < n, ta có hai nhánh:

**Nhánh 1 — Bỏ công việc i:**

```text
skip = F(i+1, b, 0)
```

Lợi ích hiện tại cộng thêm 0; vì công việc i bị bỏ, ở công việc i+1 thì “công việc trước vừa được chọn” bằng 0.

**Nhánh 2 — Chọn công việc i:**

Chỉ hợp lệ nếu `p == 0` và `cost[i] <= b`:

```text
take = value[i] + F(i+1, b-cost[i], 1)
```

Nếu không thỏa điều kiện, nhánh take không tồn tại.

**Tối ưu:**

```text
F(i,b,p) = max(skip, take)     nếu take hợp lệ
F(i,b,p) = skip                nếu take không hợp lệ
F(n,b,p) = 0                   với mọi b,p
```

Vì luôn cho phép bỏ tất cả phần tử còn lại, giá trị tối ưu của phần còn lại **không nhỏ hơn 0** ngay cả khi có giá trị âm. Điều này giúp tránh đặt một giá trị âm vô cực cho trạng thái vốn vẫn có nghiệm rỗng hợp lệ.

**Nếu bài yêu cầu dùng đúng B ngân sách thay vì không vượt B**, trường hợp cơ sở sẽ khác: không thể cho `F(n,b,p)=0` với mọi b vì còn b>0 là chưa dùng hết. Khi ấy thường cần một giá trị biểu thị *không khả thi* và tránh cộng vào giá trị sentinel để không gây tràn số. Đó là **bài toán khác**, không được dùng nguyên công thức ở trên.

### Diễn giải quyết định tại một trạng thái

Giả sử đang ở `i=2`, b=2, p=0, `cost[2]=2`, `value[2]=8`:

- Bỏ i=2 cho `F(3,2,0)`.
- Chọn i=2 cho `8 + F(3,0,1)`.
- Chọn nhánh có tổng lợi ích lớn hơn.

Nếu chỉ đổi p từ 0 sang 1 trong cùng i=2, b=2 thì **nhánh chọn biến mất**, vì công việc i−1 đã được chọn. Đây chính là lý do phải lưu p.

### Vì sao chỉ giữ b mà không giữ tổng chi phí đã dùng?

Vì ngân sách ban đầu B cố định và chi phí không âm, **b đã tóm tắt toàn bộ ảnh hưởng của chi phí quá khứ lên tương lai**. Hai lịch sử với cùng b có cùng hạn mức còn lại, dù chúng đạt b bằng những nhóm công việc khác nhau.

Nếu đề còn yêu cầu biết cụ thể những công việc đã dùng để kiểm tra xung đột tùy ý (không chỉ liền kề), b và p có thể **không còn đủ**; phải thêm biểu diễn thích hợp của những phần lịch sử ảnh hưởng đến các xung đột đó.

## 7. Chứng minh công thức đúng và đủ thông tin

### Bước 1 — Mọi lời giải tương lai bắt đầu bằng một trong hai quyết định

Vì mỗi công việc chỉ được **chọn hoặc bỏ**, mọi phương án khả thi trên các công việc i..n−1 đều thuộc đúng một nhánh:

- Không chọn i.
- Chọn i.

Không có trường hợp thứ ba. Nhánh chọn chỉ tồn tại nếu chưa chọn i−1 và còn đủ ngân sách. Như vậy công thức đã xét **đầy đủ các phương án**.

### Bước 2 — Mỗi chuyển trạng thái bảo toàn ràng buộc

- Nhánh bỏ không tốn ngân sách, đặt p=0 đúng với việc công việc i vừa bị bỏ.
- Nhánh chọn chỉ được xét khi p=0 (không có cặp được chọn liên tiếp) và `cost[i] <= b` (ngân sách không âm sau chọn); đặt p=1 đúng với lựa chọn mới.
- Khi i=n, chuỗi lựa chọn hoàn thành và không có công việc nào để chọn thêm.

Vì vậy mọi đường đi được DP cho phép là một lựa chọn khả thi theo định nghĩa bài toán.

### Bước 3 — Giá trị của bài toán con chỉ phụ thuộc (i,b,p)

Chọn hay bỏ công việc i+1 và các công việc phía sau chỉ phụ thuộc:

- Ta đang ở công việc tiếp theo nào (i).
- Còn bao nhiêu ngân sách (b).
- Việc chọn công việc i hiện tại có bị chặn bởi công việc ngay trước không (p).

Dữ liệu các công việc còn lại là cố định, nên không có ảnh hưởng nào từ các phần lịch sử khác. Đây là chứng minh **state sufficiency**. Mọi lịch sử cùng (i,b,p) có cùng tập phần tiếp diễn hợp lệ và cùng giá trị tốt nhất **tính từ đó**.

### Bước 4 — Quy nạp theo số công việc còn lại

- **Cơ sở:** Khi i=n, F=0 là tối ưu vì không còn công việc.
- **Giả thiết:** F(i+1,·,·) đã trả lời đúng tối ưu cho mọi trạng thái của hậu tố bắt đầu ở i+1.
- **Bước quy nạp:** Mọi lịch khả thi từ i phải bắt đầu bằng bỏ hoặc chọn i. Tối ưu của phần còn lại ở mỗi nhánh được tính đúng nhờ giả thiết quy nạp. Lấy max giữa các nhánh hợp lệ tạo tối ưu đúng của F(i,b,p).

Kết quả của bài toàn cục là:

```text
F(0, B, 0)
```

Không có công việc trước chỉ số 0 được chọn, nên p ban đầu là 0.

### Bước 5 — Kết thúc

Mỗi lời gọi F từ i sang i+1, nên **n−i giảm nghiêm ngặt**. Số công việc hữu hạn và trường hợp i=n chặn đệ quy. Memoization lưu kết quả của mỗi trạng thái để không tính lại khi cùng trạng thái được đi đến qua nhiều đường.

Cần phân biệt tính đúng toán học với giới hạn bộ nhớ/stack của JVM: n quá lớn có thể gây `StackOverflowError` do độ sâu đệ quy O(n) hoặc hết bộ nhớ do bảng O(nB). Những giới hạn triển khai này không làm công thức quy hoạch động sai, nhưng ảnh hưởng đến việc áp dụng thực tế.

## 8. Tính số trạng thái và chi phí

Số giá trị khả dĩ:

- `i` từ 0..n, có n+1 giá trị.
- `b` từ 0..B, có B+1 giá trị.
- `p` thuộc {0,1}, có 2 giá trị.

Tổng số trạng thái hình thức tối đa:

```text
2 * (n+1) * (B+1)
```

Không phải tất cả các trạng thái đều luôn có thể đến được, nhưng một bảng đậm đặc (*dense*) vẫn có thể cấp phát đủ chúng.

Mỗi trạng thái tính một lần, có tối đa hai chuyển với thời gian O(1). Vậy:

- **Thời gian:** O(n(B+1)) trong mô hình phép toán số nguyên đơn vị.
- **Bộ nhớ memo/visited:** O(n(B+1)).
- **Ngăn xếp đệ quy:** O(n).
- **Danh sách chỉ số được chọn khi truy vết:** O(n) trong trường hợp xấu.

Vì B là **giá trị số của ngân sách**, không phải số bit dùng để mã hóa B, đây là thuật toán **giả đa thức** (*pseudo-polynomial*), không phải thời gian đa thức theo độ dài bit của mọi đầu vào. Nếu B rất lớn như hàng trăm triệu hoặc hàng tỷ, tạo bảng O(nB) thường không khả thi.

**Có hai kiểu chi phí khác nhau:** Memoization giúp không tính lại cùng trạng thái, nhưng không đảm bảo số trạng thái nhỏ. Nén trạng thái có thể giảm bộ nhớ nếu chỉ cần kết quả tối ưu; muốn truy vết chính xác các công việc đã chọn có thể cần lưu đủ quyết định hoặc tái tính toán.

### Bảng so sánh các thiết kế trạng thái

| Thiết kế | Đủ thông tin? | Lý do |
| --- | --- | --- |
| `F(i)` | Không | Không biết ngân sách còn lại, cũng không biết công việc liền trước |
| `F(i,b)` | Không | Không biết công việc i−1 vừa chọn hay bỏ |
| `F(i,p)` | Không | Không biết b, có thể chọn vượt ngân sách |
| **`F(i,b,p)`** | **Có** | Đủ xác định mọi hành động hợp lệ và phần lợi ích tương lai |
| `F(i,b,p,fullHistory)` | Có nhưng thừa | Lưu nhiều lịch sử không còn ảnh hưởng đến quyết định tương lai |

Bảng này áp dụng **cho đúng bài toán đã định nghĩa**. Trong bài khác, có thể cần thêm hoặc bớt biến, vì ràng buộc và hàm mục tiêu đã thay đổi.

## 9. Chương trình Java 17+ hoàn chỉnh

Chương trình dưới đây dùng **memoization trên ba tọa độ** `(index, remainingBudget, previousTaken)`. Mỗi ô có:

- `memo[i][b][p]`: lợi ích tối đa còn có thể nhận.
- `seen[i][b][p]`: trạng thái đã được tính hay chưa, tránh nhầm giá trị 0 hợp lệ với “chưa tính”.

Sau khi tính tối ưu, chương trình **truy vết từ trạng thái ban đầu** và chọn nhánh có giá trị lớn hơn; nếu hòa, **bỏ công việc hiện tại** để đầu ra ổn định. Nó trả `Selection(maximumValue, totalCost, selectedIndices)`; các chỉ số được chọn luôn theo thứ tự tăng và không liền kề.

Để giữ bài tập rõ ràng, mã sử dụng `int[]` cho chi phí/lợi ích, `long` cho tổng lợi ích, từ chối chi phí âm và giới hạn trường hợp B=`Integer.MAX_VALUE` vì biểu thức tạo mảng `B+1` sẽ tràn. Với B nhỏ hơn nhưng quá lớn đối với heap JVM, vẫn có thể phát sinh `OutOfMemoryError`; khi đó phải đổi chiến lược lưu trạng thái.

Lưu thành **`SufficientDpState.java`**:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

public class SufficientDpState {
    record Selection(long maximumValue,
                     int totalCost,
                     List<Integer> selectedIndices) {}

    private static final class Solver {
        private final int[] costs;
        private final int[] values;
        private final int budget;
        private final long[][][] memo;
        private final boolean[][][] seen;

        Solver(int[] costs, int[] values, int budget) {
            this.costs = costs;
            this.values = values;
            this.budget = budget;
            int n = costs.length;
            memo = new long[n][budget + 1][2];
            seen = new boolean[n][budget + 1][2];
        }

        // F(i, remaining, previousTaken):
        // Gia tri lon nhat co the kiem them tu i den cuoi.
        long best(int i, int remaining, int previousTaken) {
            if (i == costs.length) {
                return 0;
            }
            if (seen[i][remaining][previousTaken]) {
                return memo[i][remaining][previousTaken];
            }

            long skip = best(i + 1, remaining, 0);
            long answer = skip;

            if (previousTaken == 0 && costs[i] <= remaining) {
                long take = (long) values[i]
                        + best(i + 1, remaining - costs[i], 1);
                if (take > answer) {
                    answer = take;
                }
            }

            seen[i][remaining][previousTaken] = true;
            memo[i][remaining][previousTaken] = answer;
            return answer;
        }

        Selection solve() {
            long optimum = best(0, budget, 0);
            int remaining = budget;
            int previousTaken = 0;
            List<Integer> chosen = new ArrayList<>();

            for (int i = 0; i < costs.length; i++) {
                long skip = best(i + 1, remaining, 0);
                long take = Long.MIN_VALUE;

                if (previousTaken == 0 && costs[i] <= remaining) {
                    take = (long) values[i]
                            + best(i + 1, remaining - costs[i], 1);
                }

                // Hoa diem: bo cong viec hien tai.
                if (take > skip) {
                    chosen.add(i);
                    remaining -= costs[i];
                    previousTaken = 1;
                } else {
                    previousTaken = 0;
                }
            }
            return new Selection(
                    optimum,
                    budget - remaining,
                    List.copyOf(chosen));
        }
    }

    static Selection maximize(
            int[] costs, int[] values, int budget) {
        Objects.requireNonNull(costs, "costs must not be null");
        Objects.requireNonNull(values, "values must not be null");

        if (costs.length != values.length) {
            throw new IllegalArgumentException(
                    "costs and values must have equal lengths");
        }
        if (budget < 0) {
            throw new IllegalArgumentException(
                    "budget must be nonnegative");
        }
        if (budget == Integer.MAX_VALUE) {
            throw new IllegalArgumentException(
                    "budget too large for dense table");
        }
        for (int cost : costs) {
            if (cost < 0) {
                throw new IllegalArgumentException(
                        "costs must be nonnegative");
            }
        }
        return new Solver(costs, values, budget).solve();
    }

    private static void show(
            String label, int[] costs, int[] values, int budget) {
        Selection answer = maximize(costs, values, budget);
        System.out.println(label
                + ": value=" + answer.maximumValue()
                + ", cost=" + answer.totalCost()
                + ", indices=" + answer.selectedIndices());
    }

    public static void main(String[] args) {
        int[] costs = {2, 3, 2, 3, 2};
        int[] values = {6, 10, 8, 9, 7};

        show("Budget 6", costs, values, 6);
        show("Budget 5", costs, values, 5);
        show("Budget 3", costs, values, 3);
        show("Budget 0", costs, values, 0);

        show("Zero-cost B1",
                new int[]{0, 0, 1},
                new int[]{5, 7, 8}, 1);
        show("Zero-cost B0",
                new int[]{0, 0, 1},
                new int[]{5, 7, 8}, 0);

        show("Negative rewards",
                new int[]{1, 1, 1},
                new int[]{-4, 0, -2}, 2);

        show("Empty", new int[0], new int[0], 0);

        try {
            maximize(new int[]{-1}, new int[]{1}, 1);
        } catch (IllegalArgumentException ex) {
            System.out.println("Invalid: " + ex.getMessage());
        }
    }
}
```

Biên dịch và chạy (JDK 17 trở lên):

```bash
javac SufficientDpState.java
java SufficientDpState
```

**Stdout chính xác:**

```text
Budget 6: value=21, cost=6, indices=[0, 2, 4]
Budget 5: value=17, cost=5, indices=[1, 4]
Budget 3: value=10, cost=3, indices=[1]
Budget 0: value=0, cost=0, indices=[]
Zero-cost B1: value=13, cost=1, indices=[0, 2]
Zero-cost B0: value=7, cost=0, indices=[1]
Negative rewards: value=0, cost=0, indices=[]
Empty: value=0, cost=0, indices=[]
Invalid: costs must be nonnegative
```

### Vì sao từng trường hợp đúng?

- **Budget 6:** Các chỉ số 0, 2, 4 không liền nhau, tổng chi phí 6 và lợi ích 21. Không có lựa chọn khả thi với lợi ích lớn hơn.
- **Budget 5:** Công việc 1 và 4 có tổng chi phí 3+2=5, lợi ích 10+7=17, tốt hơn các lựa chọn còn lại.
- **Budget 3:** Chỉ chọn công việc 1 được lợi ích 10; không đủ ngân sách để ghép các lựa chọn sinh lợi hơn.
- **Budget 0 (mẫu chính):** Mọi công việc có chi phí dương, nên không chọn được gì.
- **Zero-cost B1:** Công việc 0 (chi phí 0, lợi ích 5) và công việc 2 (chi phí 1, lợi ích 8) không liền nhau, tổng 13.
- **Zero-cost B0:** Dù ngân sách bằng 0, vẫn có thể chọn công việc chi phí 0. Vì hai công việc đầu liền nhau, chọn công việc 1 nhận 7 tốt hơn chỉ chọn công việc 0 nhận 5.
- **Negative rewards:** Có thể bỏ tất cả; các công việc có giá trị âm hoặc 0 không cải thiện mục tiêu. Trường hợp hòa 0, quy tắc tái dựng ưu tiên bỏ, nên trả mảng rỗng.
- **Empty:** Không còn công việc, F(0,0,0)=0.
- **Invalid:** Chi phí âm vi phạm mô hình ngân sách không âm, nên được từ chối thay vì cho âm làm tăng ngân sách.

**Tại sao chương trình cần `seen`?** Giá trị DP tối ưu có thể bằng 0 (mảng rỗng hoặc toàn lợi ích âm). Nếu dùng `memo==0` để đại diện chưa tính, chương trình sẽ tính lại những trạng thái có kết quả bằng 0, thậm chí làm tăng thời gian rất nhiều. `seen` là cách tách biệt “đã tính” với “giá trị bằng 0”.

**Tại sao dùng `long` cho tổng lợi ích?** Tổng nhiều giá trị `int` có thể vượt phạm vi `int`. Ép `(long) values[i]` trước khi cộng làm phép cộng theo long. Đây là bài toán tối đa tổng, không phải đếm số lượng công việc.

**Tại sao mã không sửa mảng đầu vào?** Solver chỉ đọc `costs` và `values`, không hoán đổi hoặc gán lại phần tử. Nếu caller sửa các mảng **đồng thời** khi Solver đang tính thì đầu vào không còn cố định; trường hợp đó cần bảo vệ đồng bộ hoặc sao chép dữ liệu trước, nằm ngoài mô hình cơ bản.

## 10. Tái dựng lời giải từ trạng thái đầy đủ

Không phải bài DP nào cũng chỉ cần **giá trị tối ưu**; nhiều bài yêu cầu cả **phương án**. Nếu trạng thái và phép chuyển được mô tả chính xác, có thể tái dựng bằng cách so giá trị tối ưu của các nhánh.

Từ `(i,b,p)`:

1. Tính `skip = F(i+1,b,0)`.
2. Nếu nhánh chọn hợp lệ, tính `take = value[i]+F(i+1,b-cost[i],1)`.
3. Nếu `take > skip`, thêm chỉ số i vào đáp án, giảm b và đặt p=1.
4. Ngược lại, bỏ i và đặt p=0.
5. Tăng i, lặp đến n.

Mã dùng **quy tắc hòa “skip”**, nên kết quả có thể **không phải** phương án tối ưu duy nhất, nhưng vẫn có cùng giá trị tối ưu. Nếu mục tiêu phụ là chọn **ít công việc nhất** hoặc chọn **dãy chỉ số nhỏ nhất theo thứ tự từ điển**, phải định nghĩa lại tiêu chí hòa; chỉ dùng `take > skip` không nhất thiết thỏa mục tiêu phụ ấy.

Một trạng thái DP đủ cho **giá trị tối ưu** không luôn chứa sẵn mọi thông tin để trả về những đối tượng đã chọn; phương án có thể được **truy vết từ các nhánh** như ở đây, hoặc lưu con trỏ quyết định (*parent pointer*) nếu quá trình chuyển trạng thái không thể tái tạo dễ dàng.

## 11. Chọn trạng thái cho những lớp bài toán quen thuộc

### 11.1. Bài toán cái túi 0/1 không có ràng buộc liền kề

Nếu chỉ có từng món được chọn tối đa một lần và giới hạn ngân sách/trọng lượng, trạng thái `F(i,b)` (đang xét món i, còn b) là đủ:

```text
F(i,b) = max(
    F(i+1,b),
    value[i] + F(i+1,b-cost[i]) nếu cost[i] <= b
)
```

Không cần p vì việc chọn món trước **không làm cấm** chọn món hiện tại. Thêm p trong bài này là dư và có thể nhân đôi số trạng thái.

### 11.2. Dãy nhị phân không cho hai số 1 liên tiếp

Nếu cần đếm số chuỗi nhị phân dài n mà không có "11", trạng thái `F(i,lastBit)` đủ: i là vị trí đang điền, lastBit cho biết vị trí trước là 0 hay 1. Không có ngân sách nên không cần b.

- Điền 0 luôn hợp lệ, chuyển `(i+1,0)`.
- Điền 1 chỉ hợp lệ nếu lastBit=0, chuyển `(i+1,1)`.
- Ở i=n, trả **1 cách hoàn thành** chứ không phải 0, bởi ta đang **đếm số cách**.

Đây là ví dụ cho thấy **trường hợp cơ sở tùy thuộc đại lượng DP**. Một công thức tối ưu tổng lợi ích dùng 0 ở lá, còn một công thức đếm cách thường dùng 1 ở lá hợp lệ.

### 11.3. LCS – dãy con chung dài nhất

Cho hai chuỗi A và B, trạng thái `L(i,j)` là độ dài LCS của hậu tố `A[i..]` và `B[j..]`. Hai chỉ số i,j đủ vì phần còn lại phụ thuộc đúng hai hậu tố chưa xét.

```text
Nếu i == |A| hoặc j == |B|: L(i,j) = 0
Nếu A[i] == B[j]:            L(i,j) = 1 + L(i+1,j+1)
Ngược lại:                   L(i,j) = max(L(i+1,j), L(i,j+1))
```

Ở đây không cần lưu chuỗi kết quả đã chọn trong trạng thái để tính **độ dài tối ưu**; có thể truy vết sau. Nếu nhiệm vụ đòi **đếm số LCS phân biệt**, công thức và cách gộp có thể phức tạp hơn do những cách tạo chuỗi trùng nhau.

### 11.4. Đường đi trên lưới có chìa khóa và cửa

Nếu đang tìm đường trên lưới nhưng một số cánh cửa chỉ mở khi đã nhặt chìa khóa, hai lịch sử tới **cùng tọa độ (r,c)** có thể khác nhau ở tập chìa khóa đang mang. Trạng thái chỉ `(r,c)` không đủ.

Một biểu diễn là `(r,c,keysMask)`, trong đó mỗi bit của keysMask cho biết có một loại chìa khóa hay không. Những lịch sử tới cùng tọa độ với cùng mask mới có thể gộp về khả năng đi tiếp, **nếu không có ràng buộc lịch sử khác**.

Tùy đồ thị có chu trình và cạnh trọng số, bài này có thể cần **BFS/Dijkstra trên đồ thị trạng thái** chứ không phải DP trên DAG; ý tưởng “trạng thái chứa đủ thông tin cho tương lai” vẫn giống nhau.

### 11.5. DP trên chữ số (*digit DP*)

Khi đếm các số thỏa điều kiện theo chữ số, trạng thái thường có:

- `pos`: đang xét chữ số nào.
- `tight`: tiền tố hiện tại còn bằng tiền tố giới hạn hay đã nhỏ hơn.
- `started`: đã bắt đầu chữ số có nghĩa hay còn trong các số 0 đầu.
- Thống kê cần thiết như tổng chữ số, số dư mod m, hoặc chữ số trước, nếu đề ràng buộc chúng.

Bỏ `tight` có thể cho phép sinh số vượt giới hạn; bỏ `started` trong bài mà các số 0 đầu có ngữ nghĩa đặc biệt có thể đếm sai. Không phải mọi digit DP cần đủ cả các cờ ấy; chúng được thêm **khi ràng buộc tương lai phụ thuộc vào chúng**.

### 11.6. Bài có tài nguyên và thời gian chờ

Nếu một quyết định gây **thời gian chờ** (*cooldown*) trước khi được phép chọn lại, trạng thái có thể cần thêm số bước chờ còn lại hoặc một cờ “vừa thực hiện hành động bị giới hạn”. Chỉ lưu chỉ số thời gian i có thể thiếu. Nếu tài nguyên còn lại hoặc trạng thái “đang giữ tài sản” ảnh hưởng tới giao dịch tiếp theo, cần lưu thông tin đó.

Ví dụ trong một bài giao dịch cổ phiếu có phí, trạng thái `(day,holding)` có thể đủ nếu không có cooldown hay giới hạn số giao dịch; khi thêm cooldown hoặc giới hạn số giao dịch, cần xét lại trạng thái. **Không có một bộ tọa độ DP cố định dùng cho mọi biến thể**.

## 12. Nén trạng thái: chỉ sau khi chứng minh được điều gì có thể bỏ

**Nén trạng thái** nhằm giảm số chiều hoặc số tầng bộ nhớ, nhưng không được xóa một biến chỉ vì thấy tốn chỗ.

Có ít nhất ba kiểu tối ưu khác nhau:

1. **Bỏ biến dư:** Nếu một biến suy ra được hoàn toàn từ các biến còn lại, không cần lưu riêng. Ví dụ trong một bài có tổng công việc cố định và tổng ngân sách ban đầu B, `spent=B-remaining` nên không cần lưu cả spent và remaining.
2. **Gộp các lịch sử tương đương:** Hai trạng thái chỉ có thể gộp nếu tập phần tiếp diễn hợp lệ và giá trị tối ưu tương lai tương đương. Trong bài ví dụ, p=0 và p=1 thường **không thể gộp**.
3. **Cuộn lớp bộ nhớ (rolling array):** Nếu `F(i,...)` chỉ phụ thuộc lớp `i+1`, ta có thể lưu hai lớp để giảm bộ nhớ, nhưng vẫn có **các tọa độ logic** `(i,b,p)` trong công thức. Đây là **nén bộ nhớ**, không phải xóa phụ thuộc của bài toán.

Với bài ngân sách + không liền kề:

- Memoization đệ quy dùng O(nB) bộ nhớ cho cả bảng (cộng O(n) stack).
- Nếu chỉ cần **giá trị tối ưu**, có thể tính từ i=n−1 về 0 và dùng **hai lớp** `F(i+1,b,p)` và `F(i,b,p)`, mỗi lớp O(B) ô cho hai giá trị p.
- Khi cần **tái dựng dãy chọn**, chỉ giữ hai lớp thông thường không đủ để truy vết ngược ngay lập tức; phải lưu quyết định, chạy lại một số phép tính, hoặc dùng kỹ thuật truy vết khác.
- Với một DP tiến dùng cập nhật trực tiếp mảng b, cần xem **chiều duyệt b tăng hay giảm** để tránh dùng một món nhiều lần khi chỉ được chọn 0/1 lần.

**Cảnh báo:** “Cuộn lớp” và “xóa p” không tương đương. Cuộn lớp giữ nguyên sự phân biệt p=0/p=1 tại mỗi i; bỏ p làm mất thông tin về tính hợp lệ của hành động chọn tiếp theo.

## 13. Quy trình thiết kế trạng thái áp dụng được cho nhiều bài

### Bước A – Xác định chính xác mục tiêu

Trước tiên viết một câu rõ ràng: “Tối đa tổng lợi ích”, “Tối thiểu chi phí”, “Đếm số cách”, hay “Kiểm tra tồn tại”. Điều này quyết định phép kết hợp ở công thức chuyển: max, min, cộng số cách, hoặc OR logic.

### Bước B – Xác định thứ tự ra quyết định

Quyết định xử lý từng phần tử, từng vị trí, từng ngày hay một đoạn? Nếu mỗi bước xử lý phần tử i, chỉ số i thường là một tọa độ trạng thái tự nhiên. Với DP đoạn (*interval DP*), hai chỉ số trái/phải có thể cần thiết để biết phạm vi con; chỉ một chỉ số i không đủ.

### Bước C – Liệt kê các ràng buộc tương lai

Với mỗi ràng buộc, hỏi **thông tin nào từ quá khứ có thể làm thay đổi quyết định kế tiếp**:

| Ràng buộc/điều kiện | Thông tin thường cần |
| --- | --- |
| Giới hạn ngân sách | Tổng đã dùng hoặc ngân sách còn |
| Không chọn hai phần tử liền kề | Cờ đã chọn phần tử trước |
| Không dùng lại phần tử | Chỉ số đã xử lý hoặc tập đã dùng, tùy thứ tự |
| Không vượt số lần giao dịch | Số lần còn lại hoặc đã dùng |
| Đường đi cần chìa khóa | Bitmask chìa khóa đã có |
| Giới hạn theo tiền tố chữ số | Vị trí và cờ tight |
| Đếm chuỗi tránh mẫu | Trạng thái automaton biểu diễn tiền tố mẫu đã khớp |
| Duy trì thứ tự phụ thuộc hai chuỗi | Hai chỉ số vị trí |

Không nên chọn một biến chỉ vì nó xuất hiện trong đề: chỉ đưa vào trạng thái khi nó ảnh hưởng tới **khả năng tiếp tục hoặc giá trị phần còn lại**.

### Bước D – Định nghĩa câu hỏi chính xác mà dp(state) trả lời

Một định nghĩa tốt nên chỉ ra cả **tập lựa chọn tương lai**, **ràng buộc còn lại**, **đơn vị giá trị** và **điểm kết thúc**. Ví dụ “F(i,b,p) là lợi ích lớn nhất còn kiếm được khi xét các công việc từ i trở đi, còn ngân sách b và p cho biết trạng thái công việc trước” rõ hơn nhiều so với “dp[i][b][p] là đáp án”.

### Bước E – Viết mọi hành động và chuyển trạng thái

Thử liệt kê **đầy đủ** các lựa chọn có thể có. Với từng hành động:

- Điều kiện được phép chọn?
- Chuyển tới trạng thái nào?
- Cộng thêm giá trị gì?
- Có giữ đúng bất biến ràng buộc không?
- Chỉ số hoặc đại lượng nào giảm/tăng để bảo đảm dừng?

Nếu phải hỏi “đã làm gì ba bước trước?” mới tính được chuyển, trạng thái chưa đủ. Hãy thêm đúng thông tin có liên quan, chẳng hạn một trạng thái máy hữu hạn biểu diễn lịch sử cần nhớ.

### Bước F – Tìm phản ví dụ cho thiết kế trạng thái

Tự dựng hai lịch sử H1,H2 có **cùng state** theo định nghĩa nhưng khác khả năng tiếp diễn. Đây là cách mạnh để phát hiện biến bị thiếu. Sau khi thêm biến, thử lặp lại phép kiểm tra.

### Bước G – Chứng minh đúng và đánh giá độ lớn

Chứng minh mỗi trạng thái đại diện đúng cho mọi lịch sử được gộp; mỗi chuyển vừa hợp lệ vừa đầy đủ; trường hợp cơ sở đúng; có thứ tự xử lý không chu trình (hoặc một thuật toán phù hợp nếu có chu trình). Đếm số trạng thái và số chuyển **trước khi triển khai** để biết cách lưu đậm đặc, thưa, hay cần cách tiếp cận khác.

## 14. Những sai lầm thường gặp

1. **Chỉ lưu i vì “đã xử lý tới i”.** Nếu ngân sách hoặc lịch sử ngắn hạn ảnh hưởng tương lai thì trạng thái thiếu.
2. **Lưu `(i,b)` cho bài cấm chọn hai phần tử liên tiếp.** Hai lịch sử cùng b có thể khác ở việc phần tử trước được chọn hay bỏ.
3. **Lưu toàn bộ chuỗi lựa chọn vào state dù chỉ cần một cờ.** Tạo số trạng thái có thể tăng theo cấp số mũ vô ích.
4. **Không phân biệt ngân sách còn lại và ngân sách đã dùng.** Dùng nhầm ý nghĩa có thể khiến điều kiện chọn và công thức chuyển sai.
5. **Không xác định dp trả quá khứ hay tương lai.** Dạng tốt nhất đã đạt đến trạng thái và dạng lợi ích tốt nhất còn lại có base case/cách chuyển khác nhau.
6. **Thêm giá trị lợi ích tích lũy thành một chiều chỉ vì cần tối đa nó.** Trong nhiều bài với mục tiêu cộng tính, lợi ích là **giá trị DP**, không phải tọa độ trạng thái.
7. **Dùng 0 thay cho “chưa tính”.** Giá trị tối ưu 0 hoàn toàn hợp lệ; cần bảng seen hoặc sentinel không mơ hồ.
8. **Dùng kết quả của nhánh chọn mà không kiểm tra p=0.** Phá điều kiện cấm chọn liền kề.
9. **Bỏ kiểm tra ngân sách trước khi lấy nhánh chọn.** Có thể tạo b âm hoặc truy cập ngoài bảng.
10. **Đặt base case sai cho bài đếm.** Đếm số cách hoàn thành ở trạng thái cuối hợp lệ thường trả 1, khác bài tối đa lợi ích trả 0.
11. **Không lưu thông tin chìa khóa/tài nguyên trong bài đi đường.** Hai lịch sử tới cùng ô nhưng khả năng đi tiếp khác nhau.
12. **Dùng DP dạng DAG cho bài có chu trình chưa xử lý.** Có thể tạo phụ thuộc vòng và đệ quy không dừng; cần phương pháp phù hợp với đồ thị trạng thái.
13. **Nén bộ nhớ nhưng vô tình xóa tọa độ logic.** Rolling array chỉ giảm lớp lưu, không làm ràng buộc previousTaken biến mất.
14. **Sai chiều duyệt của cập nhật 0/1.** Trong bài chọn mỗi món tối đa một lần, cập nhật tại chỗ theo chiều sai có thể tái sử dụng cùng một món.
15. **Quên các mục tiêu phụ khi có nhiều nghiệm tối ưu.** Nếu đề yêu cầu ít lựa chọn nhất, thứ tự từ điển hay ổn định, quy tắc hòa phải được định nghĩa.
16. **Giả định budget=0 luôn phải chọn rỗng.** Có thể có công việc cost=0 và value>0; ví dụ Java cho thấy ngân sách 0 vẫn chọn công việc 1.
17. **Cho phép chi phí âm dù công thức dựa trên chi phí không âm.** Chi phí âm có thể làm b tăng và không còn bị chặn trong 0..B; cần mô hình khác.
18. **Không tính chi phí trạng thái theo giá trị B.** O(nB) giả đa thức có thể hết bộ nhớ với B lớn dù n nhỏ.
19. **Coi việc ném StackOverflowError/OutOfMemoryError là lỗi công thức toán học.** Công thức có thể đúng nhưng cần kỹ thuật hiện thực khác cho quy mô dữ liệu.
20. **Dùng biến `p` nhưng không cập nhật khi bỏ.** Sau nhánh bỏ, phần tử trước của bước kế tiếp **không được chọn** nên phải đặt p=0.
21. **Gộp trạng thái mà không so sánh điều kiện tương lai.** Hai lịch sử có cùng chỉ số i nhưng khác resource/last-action không nhất thiết tương đương.
22. **Không phân biệt boolean reachability, count và max/min.** Cùng một tập tọa độ trạng thái có thể cần toán tử chuyển và base khác nhau tùy mục tiêu.
23. **Tạo bảng [n][B+1][2] khi B cực lớn mà không kiểm tra tài nguyên.** Có thể thiếu bộ nhớ; xem xét bảng thưa/map hoặc thuật toán khác với ràng buộc phù hợp.
24. **Gọi một state “tối thiểu” chỉ vì nó có ít chiều.** Ít chiều nhưng thiếu thông tin là sai; đúng nhưng nhiều chiều có thể tối ưu sau bằng chứng.

## 15. Bài tập tự luyện có đáp án

**Bài 1.** Có n phần tử, mỗi phần tử chi phí và lợi ích; ngân sách B; không có ràng buộc giữa các phần tử liền kề. Trạng thái `F(i,b)` có đủ không?

**Đáp án:** Có, nếu mọi phần tử từ i trở đi được chọn tối đa một lần theo thứ tự, chi phí không âm và mục tiêu là tối đa tổng lợi ích trong ngân sách b. Không cần nhớ phần tử trước vì nó không ảnh hưởng tới tính hợp lệ của lựa chọn hiện tại.

**Bài 2.** Thêm điều kiện “không chọn hai phần tử liền kề”. Vì sao phải thêm p?

**Đáp án:** Hai lịch sử cùng (i,b) nhưng khác việc phần tử i−1 được chọn hay không sẽ khác tập hành động hợp lệ: một lịch sử không thể chọn i, lịch sử kia có thể. Vậy trạng thái cần `F(i,b,p)`.

**Bài 3.** Với B=4, chi phí [2,2,2], lợi ích [1,1,100], hãy cho hai lịch sử khác nhau có cùng (i=2,b=2) nhưng khác khả năng chọn phần tử thứ ba.

**Đáp án:** Lịch sử A chọn chỉ số 0, bỏ 1 nên p=0, được phép chọn 2. Lịch sử B bỏ 0, chọn 1 nên p=1, không được phép chọn 2. Đây là phản ví dụ cho state chỉ (i,b).

**Bài 4.** Cho costs=[2,3,2,3,2], values=[6,10,8,9,7], B=6. Phương án tối ưu và lợi ích là gì?

**Đáp án:** Chọn indices [0,2,4], chi phí 2+2+2=6, tổng lợi ích 6+8+7=21. Các phần tử chọn không kề nhau.

**Bài 5.** Vì sao không lưu `totalValueSoFar` như một chiều trạng thái ở ví dụ Java?

**Đáp án:** F được định nghĩa là giá trị tối ưu **từ hiện tại trở đi**. Hai lịch sử có cùng (i,b,p) có cùng tương lai tối ưu; tổng lợi ích đã có được cộng bên ngoài. Việc thêm totalValueSoFar sẽ tạo các trạng thái trùng về khả năng tiếp diễn.

**Bài 6.** Nếu DP đếm số chuỗi nhị phân dài n không chứa "11", ở vị trí i=n trả 0 hay 1?

**Đáp án:** Trả **1** cho trạng thái hợp lệ, vì đã hình thành đúng một cách hoàn thành. Trong DP tối đa lợi ích, trường hợp hết phần tử thường có phần lợi ích còn lại bằng 0. Mục tiêu khác nên base khác.

**Bài 7.** Nếu hai lịch sử đến cùng ô (r,c) nhưng một lịch sử có chìa khóa, một không có, trạng thái `(r,c)` đã đủ chưa?

**Đáp án:** Chưa, nếu có cửa yêu cầu chìa khóa trên đường tương lai. Cần thêm tập chìa khóa, thường mã hóa thành bitmask, hoặc một đại lượng tương đương.

**Bài 8.** Nén `F(i,b,p)` từ n lớp i xuống hai lớp có xóa được biến p không?

**Đáp án:** Không. Có thể giảm **dung lượng lưu theo i** nhưng vẫn phải lưu giá trị ứng với hai trường hợp p=0 và p=1 ở mỗi lớp; nếu gộp chúng sẽ mất điều kiện hợp lệ khi chọn tiếp.

**Bài 9.** Với n=100, B=1000, p có hai giá trị, số ô bảng DP đậm đặc cỡ bao nhiêu (bỏ khác biệt nhỏ do lớp i=n)?

**Đáp án:** Khoảng 2×100×1001 = **200.200** ô cho mỗi bảng memo hoặc seen tại i=0..99. Đây là kích thước O(nB), cần cộng riêng overhead của các mảng đa chiều và stack.

**Bài 10.** Vì sao budget=0 không phải lúc nào cũng trả lợi ích 0?

**Đáp án:** Công việc có cost=0 vẫn có thể chọn. Nếu value>0 và không vi phạm liền kề, việc chọn cải thiện lợi ích mà không tốn ngân sách. Ví dụ cost=[0,0,1], value=[5,7,8], B=0 thì có thể chọn chỉ số 1, nhận 7.

**Bài 11.** Một trạng thái có đủ thông tin nhưng chứa thêm fullHistory. Sai ở đâu?

**Đáp án:** Không nhất thiết sai về **tính đúng**, nhưng gây dư thừa; nhiều lịch sử tương đương bị coi là những trạng thái khác nhau, làm mất lợi ích memoization và có thể tạo số trạng thái quá lớn.

**Bài 12.** Muốn DP cho ràng buộc “khoảng cách giữa hai công việc được chọn phải ít nhất 3 chỉ số”, cờ previousTaken 0/1 có đủ không?

**Đáp án:** Không. Cần biết còn phải chờ bao nhiêu chỉ số trước khi được chọn tiếp, hoặc lưu đủ thông tin về vị trí chọn gần nhất. Ví dụ biến `cooldown` với các giá trị 0,1,2 có thể mô tả số bước tiếp theo bị chặn; chuyển phải được thiết kế theo đúng cách đếm khoảng cách.

## Ghi nhớ

**Trạng thái DP đủ thông tin cho tương lai** là bản tóm tắt của quá khứ khiến mọi lịch sử cùng trạng thái có **cùng lựa chọn tương lai hợp lệ và cùng giá trị tối ưu phần còn lại**. Hãy bắt đầu bằng câu hỏi “Quá khứ còn ảnh hưởng tới những gì?” rồi thử dựng **hai lịch sử cùng state nhưng khác tương lai** để phát hiện biến bị thiếu. Viết rõ ý nghĩa `dp(state)`, chuyển trạng thái, base case, chứng minh tính đầy đủ/hợp lệ, đếm số trạng thái và chi phí. Đối với bài có **ngân sách và cấm chọn hai phần tử liên tiếp**, trạng thái `F(i,remaining,previousTaken)` là đủ, còn `F(i,remaining)` là thiếu. Chỉ nén chiều hoặc cuộn lớp sau khi đã giữ được mọi thông tin ảnh hưởng tới quyết định tiếp theo.
