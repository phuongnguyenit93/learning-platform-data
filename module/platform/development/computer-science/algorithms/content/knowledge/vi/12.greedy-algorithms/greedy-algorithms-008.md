# Bài toán ba lô phân số và giới hạn của lựa chọn theo tỷ lệ

## 1. Bài toán: nên lấy món nào trước?

Cho n loại vật phẩm. Mỗi vật phẩm i có **trọng lượng w[i]** và **giá trị v[i]**. Một ba lô có sức chứa tối đa W. Ta muốn lấy các vật phẩm để **tổng giá trị lớn nhất**, đồng thời tổng trọng lượng không vượt W.

Điểm quan trọng nhất là xác định vật phẩm có **được chia ra hay không**:

- **Ba lô phân số (fractional knapsack):** có thể lấy một tỷ lệ bất kỳ x[i] từ 0 đến 1 của từng vật phẩm. Nếu lấy 40% vật phẩm thì chịu 40% trọng lượng và nhận 40% giá trị.
- **Ba lô 0/1 (0/1 knapsack):** phải lấy trọn hoặc không lấy một vật phẩm; x[i] chỉ được là 0 hoặc 1.

Ở ba lô phân số với các giả thiết thông thường, **chiến lược tham lam theo tỷ lệ giá trị/trọng lượng** là tối ưu. Ở ba lô 0/1, chính chiến lược ấy có thể cho đáp án sai.

Vì hai bài có tên gần giống nhau, đừng viết thuật toán ngay sau khi thấy chữ “ba lô”. Hãy kiểm tra quyền chia vật phẩm, ý nghĩa của giá trị nhận được khi chia, số ràng buộc sức chứa, và các điều kiện chọn cùng/bỏ cùng.

### Mô hình toán học

Cho các trọng lượng w[i] > 0, giá trị v[i] ≥ 0, và W ≥ 0. Với ba lô phân số, đặt x[i] là phần vật phẩm i được lấy:

~~~text
maximize    sum(v[i] * x[i])

subject to  sum(w[i] * x[i]) <= W
            0 <= x[i] <= 1
~~~

Đây là mô hình với **một ràng buộc tài nguyên tuyến tính**, ngoài các cận của x[i]. Khi chia vật phẩm theo tỷ lệ x[i], cả chi phí lẫn lợi ích cũng phải tăng **tuyến tính** theo x[i]. Nếu vật phẩm chỉ phát sinh giá trị khi lấy đủ, có phí kích hoạt cố định hoặc có điều kiện kết hợp với vật phẩm khác, mô hình đã thay đổi.

**Mục tiêu và ràng buộc phải được nói rõ:** “không vượt W” khác “phải dùng chính xác W”. Với giá trị không âm, ta có thể để thừa chỗ nếu vật phẩm đã hết hoặc chỉ còn vật phẩm giá trị 0; không bắt buộc nhét thêm vật phẩm không có ích.

## 2. Mật độ giá trị: tỷ lệ nào đang được tối đa?

Với w[i] > 0, định nghĩa **mật độ giá trị** (value density):

~~~text
density[i] = v[i] / w[i]
~~~

Nó cho biết một đơn vị trọng lượng của vật phẩm i tạo ra bao nhiêu đơn vị giá trị. Đây là tiêu chí phù hợp khi có thể chuyển một lượng trọng lượng nhỏ từ vật phẩm này sang vật phẩm khác mà giá trị tăng giảm tương ứng.

Ví dụ có ba vật phẩm:

| Vật phẩm | Trọng lượng | Giá trị | Giá trị / trọng lượng |
| --- | ---: | ---: | ---: |
| A | 10 | 60 | 6 |
| B | 20 | 100 | 5 |
| C | 30 | 120 | 4 |

Sức chứa ba lô W=50. Mật độ giảm dần là A, B, C. Ta lấy:

1. A trọn: dùng 10 đơn vị trọng lượng, nhận 60 giá trị; còn chỗ 40.
2. B trọn: dùng thêm 20, nhận thêm 100; còn chỗ 20.
3. C chỉ lấy 20/30 = 2/3: dùng nốt 20, nhận (2/3)×120 = 80.

**Tổng giá trị = 60 + 100 + 80 = 240**, tổng trọng lượng = 50.

Nếu chỉ nhìn vào **giá trị tuyệt đối** mà chọn C trước vì C có giá trị 120 lớn nhất, ta có thể bỏ lỡ những phần vật phẩm tạo giá trị tốt hơn trên cùng một đơn vị sức chứa. Nếu chỉ nhìn vào **trọng lượng nhỏ nhất** mà chọn A trước, bước đầu trùng với mật độ trong ví dụ này nhưng không có lý do chung để luôn đúng.

Tỷ lệ được tính trên **cùng đơn vị đo**; nếu một trọng lượng ghi bằng gram và một trọng lượng ghi bằng kilogram, phải chuẩn hóa trước. Nếu giá trị là chi phí cần **giảm thiểu** thay vì lợi ích cần tối đa hóa, không thể dùng nguyên tiêu chí trên mà không đổi bài toán.

## 3. Thuật toán tham lam cho ba lô phân số

Với các vật phẩm độc lập, mỗi vật phẩm lấy tối đa một lần và được chia tùy ý, thuật toán gồm:

1. Kiểm tra W≥0, mọi w[i]>0 và v[i]≥0.
2. Tính hoặc so sánh các tỷ lệ v[i]/w[i], sắp vật phẩm **theo mật độ giảm dần**.
3. Giữ biến remaining = W.
4. Xét từng vật phẩm theo thứ tự. Nếu còn chỗ, lấy lượng trọng lượng t = min(w[i], remaining), tức lấy phần x[i] = t / w[i].
5. Tăng giá trị kết quả thêm v[i] × x[i], giảm remaining đi t.
6. Khi remaining=0, dừng; nếu đã xét hết vật phẩm mà ba lô chưa đầy, trả tổng giá trị đạt được.

Giả mã (miền trọng lượng và giá trị không âm đã được xác nhận):

~~~text
fractionalKnapsack(items, capacity):
    sort items by (value / weight) descending
    remaining = capacity
    answer = 0

    for each item in items:
        if remaining == 0:
            break
        if item.value == 0:
            continue

        takenWeight = min(item.weight, remaining)
        fraction = takenWeight / item.weight
        answer += item.value * fraction
        remaining -= takenWeight

    return answer
~~~

Dòng lấy fraction là **phép chia số thực/rational**, không phải phép chia nguyên bỏ phần thập phân. Trong Java, nếu dùng kiểu nguyên cho takenWeight và weight, phải ép kiểu trước khi chia nếu muốn nhận tỷ lệ nhỏ hơn 1.

### Bất biến khi duyệt

Sau khi xử lý k vật phẩm đầu tiên theo thứ tự mật độ giảm dần:

- Ta không vượt sức chứa ban đầu, và mỗi vật phẩm đã xét chỉ được lấy với tỷ lệ trong [0,1].
- Phần vật phẩm đã chọn ưu tiên mật độ cao hơn trước phần có mật độ thấp hơn; nếu đã lấy một vật phẩm mật độ thấp trong khi vẫn còn vật phẩm mật độ cao chưa lấy đủ thì có thể cải thiện bằng phép trao đổi.
- Giá trị answer đúng bằng tổng v[i]×x[i] của các phần đã lấy; remaining đúng bằng W trừ trọng lượng đã dùng.

Nếu remaining vừa về 0 thì không còn chỗ để nhận thêm vật phẩm; những vật phẩm chưa xét đều không có mật độ cao hơn nhóm đã xét. Nếu hết vật phẩm mà remaining>0, đã lấy hết mọi vật phẩm có giá trị dương và không còn lựa chọn nào cải thiện mục tiêu.

**Tối ưu không đòi hỏi mọi vật phẩm đều được lấy một phần**. Trong lời giải tham lam chuẩn, các vật phẩm mật độ cao được lấy trọn, sau đó nhiều nhất **một** vật phẩm được lấy một phần trước khi ba lô đầy; các vật phẩm còn lại bị bỏ. Khi có nhiều vật phẩm cùng tỷ lệ, có thể tồn tại nhiều nghiệm tối ưu, kể cả nghiệm có nhiều phần vật phẩm; nhưng luôn có thể chọn một nghiệm tối ưu theo cách tham lam vừa nêu.

## 4. Vì sao lựa chọn theo tỷ lệ là tối ưu? Chứng minh trao đổi

Không nên kết luận tham lam đúng chỉ từ vài ví dụ. **Lập luận trao đổi (exchange argument)** cho thấy bất kỳ lời giải phân số khả thi nào cũng có thể được biến đổi để ưu tiên các vật phẩm mật độ cao mà không làm giảm tổng giá trị.

Giả sử đã sắp tỷ lệ d[1] ≥ d[2] ≥ ... ≥ d[n], với d[i]=v[i]/w[i]. Xét một lời giải khả thi bất kỳ và hai vật phẩm i<j:

- Vật phẩm i có mật độ **không thấp hơn** vật phẩm j.
- Vật phẩm i chưa được lấy hết: x[i]<1.
- Vật phẩm j đang được lấy một phần dương: x[j]>0.

Ta có thể chuyển một lượng trọng lượng δ từ j sang i, với:

~~~text
delta = min((1 - x[i]) * w[i], x[j] * w[j])

x[i] = x[i] + delta / w[i]
x[j] = x[j] - delta / w[j]
~~~

Lượng trọng lượng tổng cộng **không đổi**, vì ta thêm δ ở i và bớt δ ở j. Các tỷ lệ vẫn trong [0,1]. Mức tăng giá trị là:

~~~text
delta * (d[i] - d[j]) >= 0
~~~

Nếu d[i]>d[j] và δ>0 thì giá trị tăng nghiêm ngặt. Nếu hai mật độ bằng nhau, tổng giá trị không đổi, nên ta có thể phá hòa theo một quy tắc bất kỳ.

Lặp ý tưởng ấy, có thể biến một nghiệm tối ưu thành nghiệm mà **mọi vật phẩm mật độ cao được lấy trọn trước khi lấy vật phẩm mật độ thấp hơn**, trừ tối đa một vật phẩm ở ranh giới sức chứa. Đó chính là cấu trúc kết quả của thuật toán tham lam.

### Những giả thiết nào đã được dùng?

Lập luận trên phụ thuộc vào tất cả điều kiện:

1. **Có thể lấy phần tùy ý** của mỗi vật phẩm, không bị giới hạn vào 0 hoặc 1.
2. **Giá trị và trọng lượng tuyến tính** theo phần được lấy: x nhân v và x nhân w.
3. **Một ràng buộc sức chứa cộng dồn**, không có quy tắc phụ thuộc giữa các vật phẩm.
4. **Mỗi vật phẩm có trọng lượng dương**, để density xác định và đổi δ/w hợp lệ.
5. **Giá trị không âm**, để việc dùng thêm sức chứa cho phần vật phẩm có lợi không làm giảm mục tiêu.

Bỏ một trong các giả thiết quan trọng ấy có thể làm phép trao đổi không còn hợp lệ. Ví dụ với ba lô 0/1, không thể “rút 5 đơn vị trọng lượng” khỏi một món phải lấy nguyên chiếc; với ràng buộc “chỉ được chọn tối đa một món”, phép chuyển một ít trọng lượng từ món này sang món khác có thể làm vi phạm số món được chọn.

**Greedy-choice property** không đồng nghĩa với mọi tỷ lệ đều đúng. Ta phải xác định đúng tỷ lệ, chứng minh lựa chọn ở bước đầu có thể là một phần của nghiệm tối ưu, rồi chứng minh các bước sau giải phần sức chứa còn lại theo cùng cấu trúc.

## 5. Giới hạn quan trọng nhất: ba lô 0/1

Đổi điều kiện x[i] từ đoạn liên tục [0,1] thành tập rời rạc {0,1}, ta có **bài toán ba lô 0/1**. Giờ mỗi vật phẩm phải được lấy cả món hoặc bỏ cả món.

Xét lại A, B, C và W=50:

| Vật phẩm | Trọng lượng | Giá trị | Mật độ |
| --- | ---: | ---: | ---: |
| A | 10 | 60 | 6 |
| B | 20 | 100 | 5 |
| C | 30 | 120 | 4 |

**Tham lam theo mật độ nhưng bắt buộc lấy nguyên món:**

1. Lấy A, còn 40; tổng giá trị 60.
2. Lấy B, còn 20; tổng giá trị 160.
3. C nặng 30 nên không lấy được; thuật toán dừng với **160**.

**Nghiệm tối ưu 0/1:** lấy B+C, dùng đúng 20+30=50, tổng giá trị 100+120=**220**. Nghiệm này **bỏ qua A dù A có mật độ cao nhất**. Như vậy, tham lam mật độ cho 0/1 thất bại: 160 < 220.

**Cùng dữ liệu nhưng ba loại kết quả:**

- Ba lô **phân số**: A trọn + B trọn + 2/3 C = **240**.
- Ba lô **0/1 dùng greedy mật độ**: A+B = **160**.
- Ba lô **0/1 tối ưu**: B+C = **220**.

Giá trị phân số 240 không phải nghiệm hợp lệ cho bài 0/1 vì C chỉ được lấy một phần. Nhưng nó có thể được dùng làm **cận trên** đối với bài 0/1 dưới cùng dữ liệu và cùng sức chứa: cho phép lấy phần chỉ mở rộng tập nghiệm, nên giá trị tối ưu của bài mở rộng **không nhỏ hơn** giá trị tối ưu 0/1. Cận trên này hữu ích trong một số thuật toán tìm kiếm nhánh-cận (branch and bound), nhưng không tự cho ra nghiệm nguyên tối ưu.

### Tại sao chứng minh trao đổi bị hỏng?

Trong bài phân số, ta có thể giảm một ít C và tăng một ít A để giữ trọng lượng và cải thiện giá trị. Với 0/1, không được lấy một phần hoặc trả lại một phần; sự hoán đổi có thể buộc bỏ cả C, lấy A và để thừa chỗ. Không có bảo đảm rằng tập vật phẩm sau hoán đổi vẫn tốt hơn.

Đây là bài học chung khi đánh giá tham lam: **một phản ví dụ nhỏ đủ bác bỏ tính đúng cho toàn bộ loại bài**, dù thuật toán vẫn cho đáp án đúng trên rất nhiều bộ dữ liệu.

## 6. Các kiểu lựa chọn có vẻ hợp lý nhưng không bảo đảm tối ưu 0/1

Ngoài tỷ lệ v/w, có thể nghĩ tới hai tiêu chí khác. Chúng đều dễ thất bại ở ba lô 0/1.

### Chọn giá trị tuyệt đối lớn nhất trước

Sức chứa W=10, có hai vật phẩm:

- X: trọng lượng 9, giá trị 10.
- Y: trọng lượng 5, giá trị 9.
- Z: trọng lượng 5, giá trị 9.

Chọn X trước theo giá trị lớn nhất được 10, còn chỗ 1. Nhưng chọn Y+Z dùng đúng 10, nhận **18**. Giá trị đơn món lớn không đồng nghĩa với tổ hợp tốt nhất.

### Chọn món nhẹ nhất trước

Sức chứa W=10:

- X: trọng lượng 1, giá trị 1.
- Y: trọng lượng 10, giá trị 100.

Nếu luôn lấy món nhẹ nhất, ta lấy X và còn 9, không thể lấy Y; tổng chỉ **1**, trong khi chọn Y được **100**.

Tất cả ví dụ này nhắc rằng **độ lớn giá trị**, **độ nhẹ** và **mật độ giá trị** là thông tin cục bộ. Bài toán 0/1 phụ thuộc vào tổ hợp rời rạc và cách các trọng lượng ghép với sức chứa. Không có một quy tắc chọn cục bộ trong số ba tiêu chí kể trên giải được mọi trường hợp 0/1.

### Một trường hợp đặc biệt greedy có thể đúng

Nếu mọi vật phẩm có **cùng trọng lượng dương** và chỉ có ràng buộc sức chứa, chọn các vật phẩm giá trị cao nhất trước là tối ưu: mỗi món tiêu hao đúng cùng lượng sức chứa, nên thay một món giá trị thấp bằng một món giá trị cao không làm tăng trọng lượng. Khi mọi trọng lượng bằng nhau, sắp theo giá trị cũng tương đương sắp theo mật độ.

Điều đó không biến quy tắc mật độ thành lời giải tổng quát cho 0/1; nó chỉ chỉ ra **giả thiết bổ sung** có thể làm tham lam trở nên đúng.

## 7. Các giới hạn khác của lựa chọn theo tỷ lệ

### 7.1 Nhiều ràng buộc tài nguyên

Nếu mỗi vật phẩm tiêu hao cả **trọng lượng** lẫn **thể tích**, ta có hai bất đẳng thức, không còn chỉ một W. Tỷ lệ v/w chỉ đo hiệu quả theo trọng lượng và có thể chọn món quá tốn thể tích.

Ví dụ được phép lấy phân số và có sức chứa trọng lượng W=10, thể tích V=5:

| Vật phẩm | Trọng lượng | Thể tích | Giá trị | v/w |
| --- | ---: | ---: | ---: | ---: |
| A | 2 | 5 | 20 | 10 |
| B | 10 | 1 | 50 | 5 |

Greedy chỉ nhìn v/w lấy A trọn, dùng hết V, đạt 20. Nhưng chỉ lấy B trọn đã thỏa cả W và V, đạt **50**. Lựa chọn theo một tỷ lệ đơn lẻ vì thế không giải bài toán **ba lô nhiều chiều** nói chung, kể cả khi cho phép chia vật phẩm.

### 7.2 Ràng buộc nhóm, tiền điều kiện hoặc số lượng món

Nếu yêu cầu “chỉ chọn tối đa một món”, ví dụ A=(w=1,v=2) và B=(w=10,v=15) với W=10, mật độ A là 2 còn B là 1,5. Chọn A theo mật độ được giá trị 2, nhưng chọn B được 15. Nếu bắt buộc chọn cả nhóm, chọn theo từng món riêng có thể tạo tổ hợp không hợp lệ.

Nếu một món chỉ có ích khi một món khác được chọn, hoặc có phí kích hoạt/khoản thưởng khi hoàn thành đủ nhóm, giá trị không còn là tổng tuyến tính v[i]×x[i]. Không thể dùng chứng minh trao đổi tiêu chuẩn.

### 7.3 Giá trị phi tuyến theo phần được lấy

Ví dụ một chai thuốc chỉ có tác dụng khi dùng đủ liều, hoặc một sản phẩm chỉ có giá trị nếu giao đủ nguyên kiện. Lấy 30% khối lượng không chắc mang 30% giá trị. Khi ấy bài toán không phải fractional knapsack tuyến tính, dù về vật lý có thể chia vật phẩm.

### 7.4 Mục tiêu khác tối đa hóa giá trị dưới một sức chứa

Nếu muốn **đạt giá trị tối thiểu với trọng lượng nhỏ nhất**, **phải dùng đúng W**, **cân bằng nhiều ba lô**, hoặc **tối đa hóa một hàm lợi ích có chi phí cố định**, quy tắc sắp v/w có thể không áp dụng trực tiếp. Trước tiên phải viết lại mục tiêu, miền biến, ràng buộc; sau đó mới tìm chứng minh tham lam riêng.

### 7.5 Giá trị âm, trọng lượng bằng 0 và vô hạn

Ở mô hình chuẩn, w>0 và v≥0. Nếu vật phẩm có v<0 và không bắt buộc phải lấy, phần ấy chỉ làm giảm mục tiêu nên có thể bỏ qua; vì vậy thuật toán minh họa **từ chối** giá trị âm để giữ hợp đồng rõ ràng.

Nếu w=0 và v>0, vật phẩm “miễn phí sức chứa” nên lấy trọn có lợi, nhưng tỷ lệ v/w không xác định. Phải tách xử lý riêng nếu đề bài cho phép. Với w=0,v=0 thì lấy hay không đều không ảnh hưởng mục tiêu; với trọng lượng âm, ý nghĩa tài nguyên thay đổi hoàn toàn và không thể áp dụng thuật toán này như cũ.

Nếu W=0, mọi vật phẩm có trọng lượng dương đều không lấy được, đáp án là 0. Nếu W≥tổng mọi trọng lượng, có thể lấy tất cả vật phẩm giá trị dương, và giá trị tối ưu bằng tổng giá trị của chúng. **Không nên** cố ép ba lô phải đầy khi không còn vật phẩm tạo lợi ích.

## 8. So sánh tỷ lệ chính xác và tránh lỗi số học

Một lỗi cài đặt phổ biến là tính tỷ lệ theo **phép chia nguyên**:

~~~java
long ratio = value / weight; // Mat phan thap phan.
~~~

Ví dụ 5/3 và 4/3 cùng bị làm tròn xuống thành 1, mặc dù mật độ thật khác nhau. Nếu dùng double, tỷ lệ có thể bị sai khác do làm tròn, và ở dữ liệu cực trị phép chia double có thể gây mất độ chính xác khi phân biệt hai tỷ lệ rất gần nhau.

Với v,w là **long không âm/dương**, ta có thể so sánh hai mật độ vA/wA và vB/wB bằng cách nhân chéo:

~~~text
vA/wA > vB/wB
    khi va chi khi
vA*wB > vB*wA            (vi wA, wB > 0)
~~~

Nhưng không được nhân trực tiếp bằng long nếu kết quả có thể tràn. Có thể dùng **BigInteger** cho hai tích trong Java để xếp thứ tự một cách chính xác:

~~~java
BigInteger left = BigInteger.valueOf(a.value())
        .multiply(BigInteger.valueOf(b.weight()));
BigInteger right = BigInteger.valueOf(b.value())
        .multiply(BigInteger.valueOf(a.weight()));
int comparison = left.compareTo(right);
~~~

Nếu comparison dương thì A có mật độ lớn hơn B. Dùng BigInteger ở phép so sánh để tránh tràn dù cả v và w riêng lẻ đều nằm trong long.

**Không dùng** comparator dạng (int)(b.value()/b.weight() - a.value()/a.weight()) vì ép kiểu và làm tròn có thể khiến hai tỷ lệ khác nhau bị coi bằng nhau hoặc làm comparator không nhất quán. Với số nguyên rất lớn, cũng không nên xây comparator bằng phép trừ của hai tích long.

### Tính giá trị phần lẻ

Sau khi xác định thứ tự chính xác, giá trị nhận được từ phần vật phẩm là:

~~~text
gained = value * (takenWeight / originalWeight)
~~~

Đây là một số hữu tỷ chính xác nếu mọi thông số là số nguyên. Chuyển sang double giúp minh họa nhưng có sai số số học dấu phẩy động. Trong ứng dụng tính tiền cần chính xác tuyệt đối, cân nhắc **BigDecimal với quy tắc làm tròn rõ ràng**, hoặc giữ tử số/mẫu số bằng BigInteger đến khi xuất kết quả. Không được lẫn giá trị làm tròn của từng phần với tiêu chí so sánh mật độ nếu cần chứng minh tối ưu chính xác.

### Hòa tỷ lệ và tính xác định

Nếu hai vật phẩm có cùng v/w, lấy vật phẩm nào trước trong phần sức chứa còn lại đều cho **cùng giá trị tối ưu** trong mô hình chuẩn, nhưng danh sách món được lấy có thể khác nhau. Để kiểm thử dễ tái lập, có thể phá hòa bằng tên hoặc chỉ số ban đầu. Cách phá hòa không chứng minh tính đúng; tính đúng đến từ việc các mật độ bằng nhau cho cùng giá trị trên mỗi đơn vị trọng lượng.

## 9. Java 17+: thuật toán phân số và phản ví dụ 0/1

Chương trình dưới đây dùng **Java 17** và một ví dụ dữ liệu nhỏ nhưng phân biệt được ba kết quả: greedy phân số 240, greedy mật độ 0/1 chỉ 160 và nghiệm 0/1 tối ưu 220.

- Record Item lưu id, trọng lượng long dương và giá trị long không âm.
- Comparator so sánh tỷ lệ bằng tích chéo BigInteger để tránh tràn và phá hòa theo id.
- fractionalKnapsack dùng một bản sao danh sách đầu vào, không chỉnh sửa dữ liệu nguồn.
- zeroOneGreedyByDensity chỉ minh họa **phương pháp sai trên 0/1 nói chung**.
- bruteForceZeroOneDemo duyệt tất cả tập con để làm đối chứng **chỉ với n≤20**, không phải thuật toán khả thi cho n lớn.

Lưu vào tệp **FractionalKnapsackDemo.java**:

~~~java
import java.math.BigInteger;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Locale;
import java.util.Objects;

public class FractionalKnapsackDemo {

    record Item(String id, long weight, long value) {
        Item {
            Objects.requireNonNull(id, "id");
            if (id.isBlank() || weight <= 0 || value < 0) {
                throw new IllegalArgumentException(
                        "id required; weight > 0; value >= 0");
            }
        }
    }

    record Pick(String id, long takenWeight, long itemWeight,
                double gainedValue) {}

    record Result(List<Pick> picks, double totalValue, long usedWeight) {}

    // Ty le giam dan; khong nhan cheo bang long vi co the tran.
    private static final Comparator<Item> HIGH_DENSITY_FIRST = (a, b) -> {
        BigInteger left = BigInteger.valueOf(b.value())
                .multiply(BigInteger.valueOf(a.weight()));
        BigInteger right = BigInteger.valueOf(a.value())
                .multiply(BigInteger.valueOf(b.weight()));
        int comparison = left.compareTo(right);
        return comparison != 0 ? comparison : a.id().compareTo(b.id());
    };

    static Result fractionalKnapsack(List<Item> items, long capacity) {
        Objects.requireNonNull(items, "items");
        if (capacity < 0) {
            throw new IllegalArgumentException("capacity must be >= 0");
        }

        List<Item> sorted = new ArrayList<>(items);
        for (Item item : sorted) {
            Objects.requireNonNull(item, "item");
        }
        sorted.sort(HIGH_DENSITY_FIRST);

        long remaining = capacity;
        double total = 0.0;
        List<Pick> chosen = new ArrayList<>();

        for (Item item : sorted) {
            if (remaining == 0) {
                break;
            }
            if (item.value() == 0) {
                continue; // Khong can chiem cho cho gia tri bang 0.
            }

            long taken = Math.min(remaining, item.weight());
            double gained = ((double) item.value()) * taken / item.weight();

            chosen.add(new Pick(
                    item.id(), taken, item.weight(), gained));
            total += gained;
            remaining -= taken;
        }
        return new Result(List.copyOf(chosen), total, capacity - remaining);
    }

    // Chi minh hoa: chon nguyen mon theo mat do KHONG toi uu cho 0/1.
    static long zeroOneGreedyByDensity(List<Item> items, long capacity) {
        List<Item> sorted = new ArrayList<>(items);
        sorted.sort(HIGH_DENSITY_FIRST);
        long left = capacity;
        long value = 0;

        for (Item item : sorted) {
            if (item.weight() <= left) {
                left -= item.weight();
                value = Math.addExact(value, item.value());
            }
        }
        return value;
    }

    // Duyet tap con de kiem tra vi du nho; O(n * 2^n).
    static long bruteForceZeroOneDemo(List<Item> items, long capacity) {
        if (items.size() > 20) {
            throw new IllegalArgumentException("demo supports n <= 20");
        }

        long best = 0;
        int combinations = 1 << items.size();
        for (int mask = 0; mask < combinations; mask++) {
            long used = 0;
            long value = 0;
            boolean fits = true;

            for (int i = 0; i < items.size(); i++) {
                if ((mask & (1 << i)) == 0) {
                    continue;
                }
                Item item = items.get(i);
                if (item.weight() > capacity - used) {
                    fits = false;
                    break;
                }
                used += item.weight();
                value = Math.addExact(value, item.value());
            }
            if (fits) {
                best = Math.max(best, value);
            }
        }
        return best;
    }

    public static void main(String[] args) {
        List<Item> items = List.of(
                new Item("A", 10, 60),
                new Item("B", 20, 100),
                new Item("C", 30, 120));

        Result fractional = fractionalKnapsack(items, 50);
        for (Pick p : fractional.picks()) {
            System.out.printf(Locale.ROOT,
                    "%s: %d/%d, gained=%.1f%n",
                    p.id(), p.takenWeight(), p.itemWeight(), p.gainedValue());
        }
        System.out.printf(Locale.ROOT,
                "fractional = %.1f, used = %d%n",
                fractional.totalValue(), fractional.usedWeight());

        System.out.printf(Locale.ROOT,
                "capacity zero = %.1f%n",
                fractionalKnapsack(items, 0).totalValue());

        System.out.println("0/1 greedy = " +
                zeroOneGreedyByDensity(items, 50));
        System.out.println("0/1 optimal = " +
                bruteForceZeroOneDemo(items, 50));
    }
}
~~~

Biên dịch và chạy với JDK 17 trở lên:

~~~bash
javac FractionalKnapsackDemo.java
java FractionalKnapsackDemo
~~~

**Stdout chính xác** cho bộ dữ liệu trong main:

~~~text
A: 10/10, gained=60.0
B: 20/20, gained=100.0
C: 20/30, gained=80.0
fractional = 240.0, used = 50
capacity zero = 0.0
0/1 greedy = 160
0/1 optimal = 220
~~~

### Đọc kết quả và ràng buộc API

Fractional dùng trọng lượng 10+20+20=50; lấy đúng 2/3 vật phẩm C nên thu được 80 từ C. Bài 0/1 dùng greedy mật độ sẽ không thể lấy nguyên C với 20 chỗ còn lại, cho 160. Duyệt các tập con nhỏ xác nhận B+C dùng đúng 50 và có giá trị 220.

Hàm fractionalKnapsack từ chối capacity âm và item null; record Item từ chối id rỗng, trọng lượng không dương, giá trị âm. Danh sách đầu vào không bị sắp xếp tại chỗ. Bản ghi Pick lưu lượng **trọng lượng** đã lấy, không chỉ cờ đã chọn, nên có thể thể hiện một phần vật phẩm; totalValue dùng double để dễ in minh họa và không hứa độ chính xác tiền tệ tuyệt đối.

Hai hàm 0/1 là **phần minh họa trên dữ liệu hợp lệ**. Trong mã, zeroOneGreedyByDensity không kiểm tra lại mọi tiền điều kiện; nó nhận chính danh sách Item được kiểm soát từ main. bruteForceZeroOneDemo chỉ dùng để làm đối chứng với n≤20, vì số tập con tăng theo 2^n.

### Độ phức tạp của mã

| Hàm | Thời gian | Bộ nhớ phụ | Chức năng |
| --- | --- | --- | --- |
| fractionalKnapsack | O(n log n) so sánh tỷ lệ với dữ liệu long có độ rộng cố định + O(n) quét | O(n) cho danh sách đã sắp và các Pick | Tối ưu bài phân số |
| zeroOneGreedyByDensity | O(n log n) | O(n) | Heuristic 0/1, có thể sai |
| bruteForceZeroOneDemo | O(n×2^n) | O(1) ngoài danh sách đầu vào và biến cục bộ | Kiểm tra tối ưu trên ví dụ nhỏ |

Comparator dùng BigInteger nên một lần so sánh có chi phí cao hơn phép so sánh double thường; với các toán hạng long có độ rộng tối đa 64 bit, các tích có số bit bị chặn, nên số phép so sánh vẫn O(n log n) trong mô hình độ rộng máy cố định. Nếu trọng lượng/giá trị là số nguyên độ dài không giới hạn, phải tính thêm chi phí số học lớn.

Nếu không cần danh sách Pick và chỉ cần tổng giá trị, có thể không lưu các lựa chọn và dùng thêm ít bộ nhớ hơn **sau khi đã sắp xếp**; nhưng bản sao danh sách để sắp vẫn có kích thước O(n) trong ví dụ. Các thuật toán sắp xếp trực tiếp trên một mảng sửa được có thể có chi phí bộ nhớ khác.

## 10. Cách giải bài 0/1 thay cho tỷ lệ tham lam

Khi phải lấy nguyên món và **trọng lượng là số nguyên không âm**, một lựa chọn quen thuộc là quy hoạch động (dynamic programming) theo sức chứa:

~~~text
dp[c] = tong gia tri lon nhat voi tong trong luong khong vuot c

khoi tao dp[c] = 0 voi moi c trong [0, W]

for each item (weight, value):
    for c from W down to weight:
        dp[c] = max(dp[c], dp[c - weight] + value)

answer = dp[W]
~~~

Vòng c chạy **giảm dần** để mỗi vật phẩm chỉ được dùng một lần. Nếu duyệt tăng dần, giá trị của cùng vật phẩm có thể đã được cập nhật ở các cận nhỏ hơn và bị dùng lại trong cùng lượt, vô tình biến bài 0/1 thành **unbounded knapsack** (được lấy nhiều lần).

Với n vật phẩm và W sức chứa nguyên, phiên bản DP này cần O(nW) thời gian và O(W) bộ nhớ. Đây là **độ phức tạp giả đa thức (pseudo-polynomial)**: W có thể rất lớn nếu được mã hóa bằng nhiều bit, nên O(nW) không phải thời gian đa thức theo kích thước bit của đầu vào.

Nếu W rất lớn hoặc trọng lượng không phải số nguyên nhỏ, có thể cân nhắc DP theo tổng giá trị (khi giá trị phù hợp), meet-in-the-middle cho n vừa, branch and bound với cận trên phân số, phương pháp xấp xỉ như FPTAS dưới giả thiết phù hợp, hoặc thuật toán tối ưu phù hợp với kích thước và ràng buộc.

**Phân biệt rõ:** ba lô phân số chuẩn có thuật toán tham lam tối ưu O(n log n), trong khi ba lô 0/1 tổng quát là bài toán tổ hợp khó hơn nhiều. Việc hai bài có hàm mục tiêu gần giống nhau không cho phép chuyển chứng minh tham lam từ bài này sang bài kia.

### Upper bound từ thư giãn phân số

Trong tìm kiếm nghiệm 0/1, có thể tính **cận trên giá trị** bằng cách cho phép các vật phẩm chưa quyết định được lấy phân số trong phần sức chứa còn lại. Nếu cận trên này không vượt qua nghiệm nguyên tốt nhất đã biết, không cần duyệt tiếp nhánh ấy. Nhưng **cận trên không phải nghiệm 0/1**; mọi lời giải cuối cùng vẫn phải chọn nguyên món.

## 11. Lặp lại nhiều truy vấn sức chứa: tiền xử lý theo tỷ lệ

Giả sử **cùng một danh sách vật phẩm** được hỏi nhiều lần với các sức chứa W khác nhau. Thay vì sắp lại vật phẩm cho từng W:

1. Sắp vật phẩm một lần theo tỷ lệ giảm dần.
2. Dựng prefixWeight[k] = tổng trọng lượng k vật phẩm đầu, prefixValue[k] = tổng giá trị của chúng.
3. Với truy vấn W, tìm bằng binary search số vật phẩm đầu tiên có thể lấy trọn.
4. Nếu còn sức chứa và còn vật phẩm, lấy phần còn lại của vật phẩm ngay sau nhóm trọn.

Một công thức với k vật phẩm đầu đã lấy trọn là:

~~~text
used = prefixWeight[k]
value = prefixValue[k]

if k < n:
    extra = min(weight[k], W - used)
    value += extra / weight[k] * value[k]
~~~

Với dữ liệu cố định có w>0, prefixWeight tăng nghiêm ngặt. Có thể dùng upper bound trên prefixWeight để tìm số vật phẩm lấy trọn; nếu W≥tổng trọng lượng thì lấy tất cả. Phải xử lý riêng vật phẩm giá trị 0 nếu không muốn điền vô ích.

**Chi phí:** sắp O(n log n) và dựng prefix O(n), sau đó mỗi truy vấn có thể O(log n), bộ nhớ bổ sung O(n). Cần tránh tràn khi cộng các trọng lượng/giá trị long trong prefix; nếu tổng có thể vượt long thì dùng biểu diễn đủ rộng. Trong bài chỉ hỏi **một** sức chứa, tạo cả bảng prefix không nhất thiết có lợi.

Với danh sách vật phẩm thay đổi giữa các truy vấn (giá trị, trọng lượng hoặc việc thêm/xóa món), thứ tự tỷ lệ và các tổng prefix có thể trở nên **lỗi thời**. Phải cập nhật hoặc xây lại, không được dùng dữ liệu cũ rồi tuyên bố kết quả tối ưu.

## 12. Kiểm thử theo thuộc tính, không chỉ theo ví dụ

Một bộ kiểm thử tốt nên xác minh cả điều kiện khả thi, giá trị và **tính tối ưu** trong miền bài phân số.

### Tính khả thi và hậu điều kiện

- Với mỗi vật phẩm, 0≤x[i]≤1; khi có trọng lượng w[i]>0, 0≤takenWeight[i]≤w[i].
- Tổng trọng lượng đã lấy không vượt W.
- Tổng giá trị bằng tổng v[i]×x[i] theo quy ước số học đã chọn.
- Không phát sinh vật phẩm không có trong đầu vào và không lấy cùng vật phẩm quá 100%.
- Nếu W=0, nghiệm rỗng có giá trị 0; nếu n=0, kết quả là 0.
- Khi mọi giá trị không âm, tăng W **không thể làm giảm** giá trị tối ưu.
- Nếu W≥tổng mọi trọng lượng dương và các vật phẩm đều có giá trị không âm, giá trị tối ưu bằng tổng tất cả giá trị dương.

### Kiểm tra tính tối ưu

- Với các vật phẩm đã được lấy một phần, mọi vật phẩm có mật độ **lớn hơn** phải được lấy trọn (trừ trường hợp giá trị bằng 0 không cần lấy).
- Khi W nhỏ hơn tổng trọng lượng của các vật phẩm có giá trị dương, thuật toán chuẩn dùng hết sức chứa; không để chỗ trống khi còn phần vật phẩm mật độ dương có thể lấy.
- Nếu nhiều vật phẩm có cùng mật độ, thay đổi thứ tự giữa chúng không làm đổi tổng giá trị tối ưu, dù danh sách Pick có thể đổi.
- Với n nhỏ, có thể so với một lời giải phân số được xây bằng cách kiểm tra mọi thứ tự biên hoặc một bộ giải quy hoạch tuyến tính chính xác; không được dùng nghiệm 0/1 như “đáp án chuẩn” cho bài phân số.
- Để bác bỏ lời giải tham lam 0/1, dùng phản ví dụ A,B,C đã nêu; kết quả 160 của heuristic khác 220 của tối ưu.

### Bộ ca biên

| Trường hợp | Hành vi mong đợi |
| --- | --- |
| Không có vật phẩm, W≥0 | Giá trị 0, không có Pick |
| W=0 | Giá trị 0, không dùng sức chứa |
| W nhỏ hơn mọi trọng lượng | Có thể lấy một phần vật phẩm mật độ cao nhất |
| W bằng tổng trọng lượng | Lấy toàn bộ vật phẩm có giá trị dương |
| Hai mật độ bằng nhau | Có nhiều nghiệm tối ưu; tổng giá trị không đổi |
| Giá trị 0 | Không cần dùng sức chứa cho món ấy |
| Trọng lượng 0 | Bị từ chối bởi API minh họa; nếu mở rộng, xử lý riêng |
| Giá trị âm | Bị từ chối bởi API minh họa |
| W âm, item null, id trống | Bị từ chối theo hợp đồng |
| Giá trị và trọng lượng long rất lớn | Comparator nhân chéo BigInteger không tràn; totalValue double có thể làm tròn |
| Bài 0/1 dùng A,B,C, W=50 | Greedy mật độ 160, tối ưu nguyên 220 |
| Bài phân số dùng A,B,C, W=50 | Tối ưu 240 |

### Bài tập tự luyện

1. Cho các vật phẩm (w,v) lần lượt là (4,20), (6,18), (10,50), W=12. Tính mật độ, sắp thứ tự, xác định phần được lấy của từng vật phẩm và giá trị tối ưu phân số. Giải thích vì sao chọn theo giá trị tuyệt đối có thể khác chọn theo mật độ.
2. Với A=(10,60), B=(20,100), C=(30,120), W=50, liệt kê mọi tổ hợp 0/1 khả thi và chứng minh tối ưu 220; so với đáp án phân số 240.
3. Tạo phản ví dụ cho ba chiến lược 0/1: chọn món nhẹ nhất, chọn giá trị lớn nhất, chọn tỷ lệ lớn nhất. Nêu rõ điều kiện dung lượng và nghiệm tốt hơn.
4. Cho hai vật phẩm có v/w bằng nhau. Chứng minh đổi một lượng trọng lượng δ từ vật phẩm này sang vật phẩm kia giữ nguyên tổng giá trị khi vẫn giữ tính khả thi.
5. Sửa yêu cầu thành mỗi món còn có thể tích và ba lô bị giới hạn cả W,V. Dùng ví dụ A,B trong bài để giải thích vì sao density theo trọng lượng không đủ.
6. Viết DP 0/1 theo sức chứa nguyên W và giải thích vì sao vòng lặp c cần đi **giảm**. Thử với một món duy nhất để phát hiện lỗi dùng lại cùng món.
7. Với 100.000 vật phẩm và nhiều truy vấn W, đề xuất cách dùng prefixWeight/prefixValue và binary search trên danh sách đã sắp theo mật độ. Phân tích chi phí dựng, chi phí truy vấn và cách invalidation khi vật phẩm đổi.
8. Nếu giá trị và trọng lượng là long gần cực đại, so sánh hai tỷ lệ bằng tích chéo an toàn; giải thích vì sao ép phép tính sang double hoặc nhân long trực tiếp có thể gây sai lệch.

**Kết luận:** ba lô phân số là một bài học mẫu về tham lam vì có **tính chất lựa chọn tham lam được chứng minh bằng trao đổi**: lấy giá trị lớn nhất trên mỗi đơn vị trọng lượng trước không bao giờ làm giảm chất lượng nghiệm khi mọi vật phẩm được chia tuyến tính và chỉ có một tài nguyên. Khi chuyển sang ba lô **0/1**, thêm ràng buộc hoặc đổi hàm giá trị, lập luận trao đổi có thể không còn đúng. Hãy kiểm tra **mô hình và chứng minh** trước khi tin vào một tỷ lệ có vẻ hợp lý.
