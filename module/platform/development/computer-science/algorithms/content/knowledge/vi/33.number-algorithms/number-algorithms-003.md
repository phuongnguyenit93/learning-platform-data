# Tìm kiếm tam phân trên hàm đơn đỉnh và giới hạn áp dụng

**Tìm kiếm tam phân (ternary search)** là kỹ thuật **thu hẹp khoảng tìm cực trị** của một hàm có cấu trúc **đơn đỉnh (unimodal)**. Trên một đoạn, nếu hàm giảm rồi tăng đúng một lần thì ta có thể tìm **cực tiểu toàn cục**; nếu hàm tăng rồi giảm thì tìm **cực đại toàn cục**. Ở mỗi bước, thuật toán chọn hai điểm bên trong đoạn và so sánh giá trị hàm tại hai điểm đó để loại phần chắc chắn không chứa cực trị.

Kỹ thuật này thường được trình bày với công thức chia đoạn thành **ba phần**. Nhưng việc dùng được hay không **không nằm ở con số ba**: điều quyết định là liệu **hình dạng hàm có cho phép suy ra nhánh chứa nghiệm từ hai giá trị**.

Bài học thuộc nhóm **Thuật toán số**, tập trung vào:

- Định nghĩa đơn đỉnh cho hàm liên tục và dãy rời rạc, trường hợp cực tiểu/cực đại.
- Công thức chọn m₁,m₂, quy tắc bỏ đoạn và chứng minh an toàn.
- Triển khai cho **miền số thực** và **miền số nguyên**.
- Cách xử lý hai giá trị **bằng nhau**, đoạn cực trị phẳng và các plateau khác.
- Phân biệt **hàm lồi**, **hàm đơn đỉnh nghiêm ngặt**, **hàm đơn đỉnh yếu**.
- Độ phức tạp theo số lần gọi hàm; sai số số thực và tràn số chỉ số.
- Khi nào **binary search theo độ dốc** phù hợp hơn tam phân.
- Phản ví dụ cho tính đơn đỉnh không đủ mạnh, hàm nhiều cực trị, hàm rời rạc có nhiễu.
- Chương trình **Java 17+ độc lập**, kết quả chạy mẫu và kiểm thử bằng oracle.

**Cảnh báo quan trọng:** không được coi mọi hàm “không tăng rồi không giảm” là một trường hợp có thể tùy ý thu hẹp đoạn khi **f(m₁)=f(m₂)**. Nếu có plateau ở ngoài đáy, hai điểm bằng nhau có thể đều nằm trên một đoạn cao, trong khi cực tiểu nằm ngoài khoảng giữa chúng. Một cách cài đặt tam phân thông thường khi đó có thể **trả kết quả sai**.

## 1. Bài toán tối ưu một biến trên một đoạn

Cho một hàm f và đoạn đầu vào:

**[L,R]**, với L≤R.

Ta có thể cần:

- **argmin f(x):** một giá trị x tại đó f(x) nhỏ nhất trên đoạn.
- **min f(x):** giá trị nhỏ nhất của hàm.
- **argmax f(x):** một giá trị x tại đó f(x) lớn nhất.
- **max f(x):** giá trị lớn nhất.

Hai bài toán **trả vị trí** và **trả giá trị** khác nhau: hàm có thể có nhiều điểm tối ưu. Nếu đề yêu cầu **điểm tối ưu nhỏ nhất theo chỉ số**, phải có quy tắc xử lý tie rõ ràng.

Ví dụ:

**f(x)=(x−7)²+3** trên các số nguyên từ −20 đến 20.

Cực tiểu duy nhất là **x=7**, giá trị **3**.

Ví dụ cực đại:

**g(x)=100−(x+4)²**.

Cực đại duy nhất là **x=−4**, giá trị **100**.

Các hàm bậc hai này là các trường hợp đơn đỉnh điển hình, nhưng không phải mọi hàm đều có cùng cấu trúc ấy.

## 2. Đơn đỉnh nghiêm ngặt và đơn đỉnh yếu

Với mục tiêu **tìm cực tiểu**, một định nghĩa mạnh, dễ chứng minh thuật toán là:

Tồn tại x* sao cho:

- f **giảm nghiêm ngặt** khi x tăng trên phần [L,x*].
- f **tăng nghiêm ngặt** khi x tăng trên phần [x*,R].

Ta gọi đây là **đơn đỉnh nghiêm ngặt cho cực tiểu**. Trường hợp x*=L hoặc x*=R được chấp nhận: khi đó hàm có thể chỉ tăng hoặc chỉ giảm trên cả đoạn.

Với cực đại, đảo hai chiều:

- **Tăng nghiêm ngặt** tới x*.
- Sau đó **giảm nghiêm ngặt**.

Đây là loại hàm mà cách so sánh hai điểm và thu hẹp ba đoạn hoạt động rõ ràng.

### Đơn đỉnh yếu

Định nghĩa yếu hơn cho cực tiểu:

- f **không tăng** tới một khoảng/điểm đáy.
- Sau đó f **không giảm**.

Nó cho phép các **đoạn phẳng** ở nhiều mức cao khác nhau. Các đoạn phẳng này có thể nằm **trước hoặc sau** cực tiểu.

Với định nghĩa yếu, việc so sánh hai điểm bằng nhau **không đủ chứng minh** cực tiểu nằm ở giữa. Đây là một trong những giới hạn dễ bị bỏ qua nhất của ternary search.

### Đáy phẳng nhưng hai phía nghiêm ngặt

Một trường hợp trung gian rất hữu ích:

- f giảm nghiêm ngặt trước một khoảng đáy [a,b].
- f đạt cùng giá trị nhỏ nhất tại mọi điểm trong [a,b].
- f tăng nghiêm ngặt sau khoảng đáy.

Tam phân có thể tìm được **một** điểm tối ưu khi xử lý bằng nhau hợp lý. Nhưng nó **không tự bảo đảm tìm được điểm tối ưu có chỉ số nhỏ nhất** trong toàn bộ [a,b].

## 3. Hàm lồi và tính đơn đỉnh

Một hàm **lồi (convex)** trên đoạn thỏa:

**f(λx+(1−λ)y) ≤ λf(x)+(1−λ)f(y)**

cho mọi x,y trong đoạn và λ∈[0,1].

Hàm lồi trên một đoạn có thể có:

- Cực tiểu duy nhất.
- Một đoạn cực tiểu phẳng.
- Cực tiểu ở đầu hoặc cuối đoạn.

Với hàm lồi hữu hạn trên đoạn, các giá trị bằng nhau tại m₁<m₂ không cho phép một cực tiểu **thấp hơn** nằm hẳn bên trái m₁ hoặc hẳn bên phải m₂; có thể giữ lại [m₁,m₂] để tìm một cực tiểu. Đây là thuộc tính mạnh hơn điều kiện đơn đỉnh yếu nói chung.

**Hàm lồi không đồng nghĩa với hàm đơn đỉnh nghiêm ngặt.** Hàm hằng là lồi nhưng có vô số điểm cực tiểu.

### Hàm đơn đỉnh không nhất thiết lồi

Ví dụ f(x)=|x|^(1/2) có cực tiểu tại x=0 và giảm rồi tăng trên một đoạn chứa 0. Nó có thể dùng để minh họa tìm cực tiểu bằng phép so sánh, nhưng không lồi trên toàn đoạn.

Vì vậy có thể sử dụng ternary search cho nhiều hàm **đơn đỉnh nghiêm ngặt** mà không cần chứng minh lồi. Ngược lại, khi chứng minh được **lồi**, có thêm công cụ như tìm theo độ dốc hoặc đạo hàm.

### Cực đại của hàm lõm

Nếu g lõm (concave), thì −g lồi. Tìm max g tương đương tìm min (−g) nếu phép đổi dấu tính toán an toàn.

Trong code, có thể dùng một cờ **maximize** và đảo hướng so sánh, không cần thực sự lấy −g; cách này tránh overflow nếu g là long bằng Long.MIN_VALUE.

## 4. Hai điểm m₁ và m₂ chia đoạn thành ba phần

Với miền số thực:

**m₁=L+(R−L)/3**.

**m₂=R−(R−L)/3**.

Ta có:

**L<m₁<m₂<R**, miễn đoạn đủ rộng và phép tính floating-point còn phân biệt được các số.

Ba phần là:

**[L,m₁]**, **[m₁,m₂]**, **[m₂,R]**.

Đối với **tìm cực tiểu** của hàm đơn đỉnh nghiêm ngặt, so:

- **f(m₁)>f(m₂):** cực tiểu không nằm ở bên trái m₁; giữ **[m₁,R]**.
- **f(m₁)<f(m₂):** cực tiểu không nằm ở bên phải m₂; giữ **[L,m₂]**.
- **f(m₁)=f(m₂):** cực tiểu nằm trong **[m₁,m₂]** nếu giả thiết hình dạng đủ mạnh (ví dụ đơn đỉnh nghiêm ngặt hoặc hàm lồi); giữ đoạn giữa.

Đối với **tìm cực đại**, đảo dấu của hai trường hợp bất đẳng thức:

- **f(m₁)<f(m₂):** giữ [m₁,R].
- **f(m₁)>f(m₂):** giữ [L,m₂].
- **Bằng nhau:** giữ [m₁,m₂] chỉ nếu giả thiết bảo đảm tính an toàn của trường hợp bằng nhau.

### Pseudocode liên tục

~~~text
TERNARY_MIN_REAL(f, L, R):
    require suitable shape on [L,R]

    repeat a fixed number of iterations:
        m1 = L + (R-L)/3
        m2 = R - (R-L)/3

        if f(m1) > f(m2):
            L = m1
        else if f(m1) < f(m2):
            R = m2
        else:
            L = m1
            R = m2

    return (L+R)/2
~~~

Pseudocode là mô hình toán học; một bản triển khai floating-point còn phải kiểm tra **NaN, vô cực, mất tiến triển và sai số**.

## 5. Vì sao nhánh f(m₁)>f(m₂) an toàn?

Giả sử f giảm nghiêm ngặt rồi tăng nghiêm ngặt và ta đang tìm min.

Cho L<m₁<m₂<R và **f(m₁)>f(m₂)**.

Nếu x*≤m₁, toàn đoạn [m₁,m₂] sẽ nằm phía **không giảm** sau điểm tối ưu, nên:

**f(m₁)≤f(m₂)**.

Điều này trái với **f(m₁)>f(m₂)**.

Vậy x*>m₁, và giữ **[m₁,R]** không loại mất nghiệm.

Với định nghĩa **đơn đỉnh yếu**, nhánh bất đẳng thức nghiêm ngặt cũng vẫn an toàn: nếu một cực tiểu nằm bên trái m₁, f phải không giảm từ m₁ tới m₂, không thể có f(m₁)>f(m₂).

### Nhánh f(m₁)<f(m₂)

Đối xứng: nếu x*≥m₂, f phải không tăng từ m₁ tới m₂. Khi thấy f(m₁)<f(m₂), điều này không thể xảy ra. Do đó giữ **[L,m₂]** an toàn.

### Trường hợp bằng nhau cần điều kiện bổ sung

Với giả thiết **giảm nghiêm ngặt rồi tăng nghiêm ngặt**, nếu x*<m₁ thì f(m₁)<f(m₂); nếu x*>m₂ thì f(m₁)>f(m₂). Vì vậy:

**f(m₁)=f(m₂) ⇒ x*∈[m₁,m₂]**.

Tương tự, với f lồi, có thể chứng minh tồn tại một cực tiểu ở [m₁,m₂]. Nhưng với đơn đỉnh yếu **không có tính lồi hoặc nghiêm ngặt ở hai phía**, mệnh đề này có thể sai.

## 6. Phản ví dụ: plateau cao che giấu cực tiểu

Xét dãy trên chỉ số **0..11**:

~~~text
index:  0  1  2  3  4  5  6  7  8  9 10 11
f(i):  10 10 10 10 10 10 10 10 10  0  1  2
~~~

Dãy này **không tăng** từ 0 đến 9, sau đó **tăng** từ 9 đến 11, nên nó thỏa định nghĩa **đơn đỉnh yếu** cho cực tiểu.

Điểm tối ưu duy nhất là **i=9**, f(9)=0.

Tam phân trên [0,11]:

**m₁=0+floor(11/3)=3**.

**m₂=11−floor(11/3)=8**.

Ta thấy:

**f(3)=f(8)=10**.

Nếu cài đặt theo nhánh bằng nhau:

**L=m₁=3**, **R=m₂=8**,

thì ta đã **loại mất i=9**, điểm tối ưu thật.

Kết quả của một thuật toán tiếp tục tìm trên đoạn [3,8] chắc chắn không thể là nghiệm đúng.

### Đây không phải lỗi làm tròn

Mọi giá trị đều là số nguyên nhỏ và được tính chính xác. Nguyên nhân là **giả thiết về hình dạng hàm chưa đủ mạnh**.

Cũng có phản ví dụ đối xứng với một plateau cao nằm phía phải, cực tiểu nằm bên trái m₁. Do đó không thể luôn chọn bỏ phần trái hay phải khi hai giá trị bằng nhau mà vẫn đúng trên **mọi** dãy đơn đỉnh yếu.

### Bài học thực hành

Không nên viết “ternary search luôn đúng với mọi dãy giảm không nghiêm ngặt rồi tăng không nghiêm ngặt” nếu không bổ sung quy tắc/giả thiết xử lý plateau.

Nếu chỉ biết một dãy **đơn đỉnh yếu** và có thể có plateau cao ở bất kỳ đâu, cách an toàn tổng quát là **quét O(n)** hoặc thu thập thêm cấu trúc để chứng minh thuật toán nhanh hơn. Trường hợp gần như mọi phần tử bằng nhau và chỉ một phần tử thấp hơn có thể buộc tìm kiếm kiểm tra rất nhiều vị trí.

## 7. Ví dụ liên tục: hàm bậc hai có đáy tại x=2,5

Xét:

**f(x)=(x−2,5)²+1**.

Hàm giảm nghiêm ngặt trước 2,5 và tăng nghiêm ngặt sau 2,5.

Cực tiểu chính xác:

**x*=2,5**, **f(x*)=1**.

Trên đoạn [−20,20], chia thành ba phần ở hai điểm. Lần đầu:

**m₁=−20+40/3≈−6,6667**.

**m₂=20−40/3≈6,6667**.

Tính:

**f(m₁)≈85,0278**.

**f(m₂)≈18,3611**.

Vì **f(m₁)>f(m₂)**, bỏ phần bên trái m₁; cực tiểu vẫn nằm trong đoạn mới [m₁,20].

Lặp lại quá trình, đoạn chứa nghiệm thu hẹp dần quanh 2,5.

### Đầu ra thực tế nên hiểu là xấp xỉ

Ở miền số thực, chương trình dùng double. Giá trị trả về thường **rất gần 2,5**, không phải cam kết biểu diễn đúng tuyệt đối mọi x* vô tỉ hoặc mọi hàm số.

Ví dụ in sáu chữ số thập phân:

~~~text
Continuous minimum: x=2.500000, value=1.000000
~~~

Để tránh gây nhầm lẫn, “đúng đến sáu chữ số” chỉ mô tả format và ca thử minh họa; độ chính xác của thuật toán trong bài toán bất kỳ phải được phân tích theo điều kiện số học và shape của f.

## 8. Ví dụ tìm cực đại

Cho:

**g(x)=12−(x+3)²**.

Đây là một parabol quay xuống, tăng trước x=−3 và giảm sau đó. Cực đại toàn cục trên đoạn chứa −3 là:

**x*=−3**, **g(x*)=12**.

Khi chạy tìm cực đại:

- Nếu **g(m₁)<g(m₂)**, điểm tốt hơn ở bên phải, giữ [m₁,R].
- Nếu **g(m₁)>g(m₂)**, điểm tốt hơn ở bên trái, giữ [L,m₂].
- Nếu bằng nhau, với hình dạng đủ mạnh, giữ [m₁,m₂].

Ví dụ in:

~~~text
Continuous maximum: x=-3.000000, value=12.000000
~~~

### Không cần nhân giá trị hàm với −1

Có thể chuyển bài max g thành min (−g), nhưng nếu g trả **long** gần Long.MIN_VALUE, phép đổi dấu có thể overflow.

Một hàm tổng quát với cờ **maximize** và **đổi chiều so sánh** giúp tránh thao tác −g khi không cần.

## 9. Trường hợp cực trị nằm ở biên

Hàm đơn điệu trên cả đoạn cũng có thể được xem là dạng đơn đỉnh có cực trị ở biên.

Ví dụ:

**f(x)=2x+3** trên [−5,5].

Hàm tăng nghiêm ngặt, nên cực tiểu tại:

**x=−5**, **f(−5)=−7**.

Tam phân liên tục liên tục giữ phần bên trái và hội tụ về biên trái.

Trường hợp ngược lại, nếu hàm giảm nghiêm ngặt trên cả đoạn, cực tiểu nằm tại **biên phải**.

### Không loại endpoints khi quét dãy rời rạc

Với miền nguyên, thuật toán phải kiểm tra cả **L và R** nếu còn nằm trong đoạn cuối. Chỉ xét các điểm ở giữa rồi loại endpoints có thể bỏ đáp án chính xác.

Nếu chỉ có một điểm L=R, trả trực tiếp điểm đó; không cần tính m₁,m₂.

## 10. Sai số số thực, EPS và số vòng lặp

Đối với miền liên tục, hai cách dừng phổ biến:

1. **Lặp số lần cố định**, ví dụ 120–200 lần với double trong bài có tọa độ vừa phải.
2. **Dừng khi R−L≤EPS**.

Cách thứ nhất dễ viết, nhưng không có nghĩa mọi bài đều cần 200 vòng. Cách thứ hai trực tiếp liên hệ đến **độ chính xác theo trục x**.

### Tốc độ co đoạn

Nếu luôn giữ [m₁,R] hoặc [L,m₂], độ dài đoạn mới xấp xỉ:

**2/3 độ dài cũ**.

Sau k vòng:

**width_k≤(2/3)^k·width_0**,

trong số học thực lý tưởng.

Muốn width_k≤EPS, cần khoảng:

**k≥log(width_0/EPS)/log(3/2)**.

Vì vậy số vòng là:

**O(log((R−L)/EPS))**.

### Sai số của x không đồng nghĩa sai số f(x)

Nếu f có hằng số Lipschitz K trên đoạn quan tâm:

**|f(x)−f(y)|≤K|x−y|**,

thì khoảng sai số x có thể suy ra cận sai số giá trị hàm theo K. Nếu không có điều kiện trơn hoặc cận thay đổi, chỉ từ “đoạn đã ngắn” không được tự suy ra sai số f(x) nhỏ một cách định lượng.

### Double có giới hạn độ phân giải

Khi L,R rất gần nhau so với độ lớn tuyệt đối của chúng, có thể xảy ra:

- m₁ làm tròn thành L.
- m₂ làm tròn thành R.
- m₁ và m₂ bị làm tròn thành cùng một số.
- f(m₁) và f(m₂) trở thành cùng một giá trị double dù toán học khác nhau.

Chương trình minh họa kiểm tra các điểm phải **phân biệt rõ** rồi mới cập nhật. Nếu không, việc thu hẹp có thể ngừng tiến triển hoặc vòng lặp lặp lại cùng bộ giá trị.

### Quy tắc đặt EPS

EPS nên xuất phát từ **yêu cầu đáp án và thang đo dữ liệu**, không phải copy một hằng số máy móc. Với tọa độ cỡ 10^15, EPS=10^−12 có thể nhỏ hơn khoảng cách giữa hai số double lân cận; yêu cầu ấy có thể không khả thi bằng double thông thường.

## 11. Miền số nguyên: không thể chỉ dùng EPS

Với miền rời rạc:

**x∈{L,L+1,...,R}**.

Không có khái niệm “dừng khi độ dài nhỏ hơn 10^−9 rồi lấy trung điểm” để trả chính xác chỉ số nguyên. Ta phải:

1. Thu hẹp đoạn bằng các chỉ số nguyên m₁,m₂.
2. Bảo đảm số phần tử giảm thật sự sau mỗi vòng.
3. Khi còn rất ít chỉ số, **duyệt tất cả** và chọn giá trị f tốt nhất.

Công thức:

**third=floor((R−L)/3)**.

**m₁=L+third**.

**m₂=R−third**.

Khi R−L>3, ta có ít nhất third≥1 và m₁<m₂, nên hai điểm không chồng nhau.

### Quy tắc cho min rời rạc

Với hàm đơn đỉnh nghiêm ngặt hoặc một lớp hàm đủ mạnh như **hàm lồi rời rạc**:

- f(m₁)>f(m₂) ⇒ bỏ các chỉ số ≤m₁, giữ **[m₁+1,R]**.
- f(m₁)<f(m₂) ⇒ bỏ các chỉ số ≥m₂, giữ **[L,m₂−1]**.
- f(m₁)=f(m₂) ⇒ giữ **[m₁,m₂]** theo giả thiết bảo đảm tồn tại điểm tối ưu trong đoạn này.

Khi **R−L≤3**, còn tối đa **4 chỉ số**; quét trực tiếp chúng để lấy đáp án.

### Vì sao được dùng +1 hoặc −1?

Khi **f(m₁)>f(m₂)**, m₁ **không thể là điểm cực tiểu** vì ngay tại m₂ đã có giá trị nhỏ hơn. Ta có thể loại m₁.

Đối xứng, nếu f(m₁)<f(m₂) thì m₂ không thể là điểm cực tiểu.

Điều này chỉ đúng nếu phép so sánh/truy xuất hàm thật sự chính xác và hàm đáp ứng điều kiện hình dạng phù hợp.

## 12. Đáy phẳng trong miền số nguyên

Xét hàm:

**f(x)=2+dist(x,[4,6])²**,

với dist(x,[4,6]) bằng:

- 4−x nếu x<4.
- 0 nếu 4≤x≤6.
- x−6 nếu x>6.

Hàm có các điểm tối ưu:

**x=4,5,6**, cùng giá trị **2**.

Nó giảm nghiêm ngặt trước 4, phẳng tại đáy và tăng nghiêm ngặt sau 6; đồng thời là một hàm lồi rời rạc.

Một phép tìm kiếm tam phân hợp lệ có thể trả **4, 5 hoặc 6**.

Nếu bài yêu cầu **bất kỳ argmin**, cả ba đều đúng.

Nếu bài yêu cầu **argmin nhỏ nhất**, đáp án bắt buộc là **4**, nhưng quy tắc thu hẹp [m₁,m₂] khi bằng nhau có thể bỏ qua các điểm tối ưu ở rìa trái của plateau.

### Quy tắc tie-break ở đoạn quét cuối

Trong code, khi hai giá trị bằng nhau, vòng quét cuối chỉ cập nhật khi giá trị **tốt hơn nghiêm ngặt**. Điều này giữ chỉ số nhỏ nhất **trong đoạn cuối còn lại**.

Nó **không** bảo đảm chỉ số tối ưu nhỏ nhất của **toàn bộ đoạn ban đầu** nếu quá trình co đoạn đã bỏ các điểm tối ưu khác.

Để tìm **đầu trái của plateau cực tiểu**, nếu f là lồi rời rạc, dùng binary search theo quan hệ f(mid)≤f(mid+1) được trình bày ở phần sau.

## 13. Hàm lồi rời rạc và độ dốc

Một dãy f trên chỉ số nguyên là **lồi rời rạc** nếu sai phân tiến:

**Δf(i)=f(i+1)−f(i)**

không giảm khi i tăng.

Tức là:

**Δf(i+1)≥Δf(i)**.

Với hàm lồi rời rạc, những sai phân có thể âm, rồi bằng 0, rồi dương; thứ tự không đảo ngược lại.

### Binary search tìm argmin trái nhất

Trên đoạn [L,R] gồm chỉ số nguyên:

~~~text
while L < R:
    mid = L + floor((R-L)/2)

    if f(mid) <= f(mid+1):
        R = mid
    else:
        L = mid+1

return L
~~~

Vì các sai phân không giảm, khi f(mid)≤f(mid+1), một điểm cực tiểu trái nhất nằm ở hoặc trước mid. Ngược lại, nếu f(mid)>f(mid+1), tất cả điểm cực tiểu nằm sau mid.

Đây là **O(log(R−L+1)) lần so sánh**, mỗi lần dùng hai giá trị hàm.

### Vì sao không áp dụng cho mọi unimodal yếu?

Với phản ví dụ plateau cao:

~~~text
10 10 10 10 10 10 10 10 10 0 1 2
~~~

f(mid)=f(mid+1) trên vùng phẳng cao. Quy tắc ≤ có thể cắt bỏ phần bên phải nơi cực tiểu thật sự nằm.

Dãy đó **không lồi rời rạc** vì sai phân đang 0 rồi bất ngờ thành −10: dãy sai phân đã giảm.

**Chứng minh lồi rời rạc** mới là cơ sở hợp lệ cho binary search độ dốc khi có những đoạn phẳng tùy ý.

## 14. Vì sao tam phân cần tính hàm ít lần hơn/khác với tìm kiếm đạo hàm?

Ternary search tìm cực trị **chỉ từ giá trị f**, không đòi:

- Công thức đạo hàm.
- Gradient.
- Khả năng tính sai phân một cách ổn định nếu hàm liên tục phức tạp.

Mỗi vòng thường gọi f tại **hai điểm**. Với những hàm có chi phí đánh giá lớn (ví dụ một lần chạy mô phỏng), số lần gọi hàm có thể quan trọng hơn vài phép cộng/nhân.

### Binary search theo dấu đạo hàm

Nếu f khả vi và **f' có tính đơn điệu phù hợp**, có thể tìm nghiệm f'(x)=0 bằng binary search trên dấu đạo hàm. Nhưng:

- Đạo hàm có thể không tồn tại tại cực tiểu dạng |x|.
- Đạo hàm có thể khó hoặc tốn kém để tính.
- Nếu f có nhiều cực trị, dấu đạo hàm không đủ để suy ra cực trị toàn cục.

### Golden-section search

**Golden-section search** cũng thu hẹp khoảng chứa cực trị cho hàm đơn đỉnh và có thể **tái sử dụng một giá trị hàm** từ vòng trước, giúp giảm số lần đánh giá f khi đánh giá rất đắt.

Ternary search chia ba theo công thức đơn giản, dễ chứng minh và lập trình; không nhất thiết tối ưu số lần evaluation trong mọi bối cảnh.

Cần chọn theo điều kiện bài: số lượng queries, chi phí f, sai số và shape, không chọn chỉ vì thuật toán có tên ngắn.

## 15. Hàm có nhiều cực trị: tam phân không bảo đảm toàn cục

Ví dụ:

**f(x)=sin(x)** trên [0,10π].

Hàm có nhiều cực tiểu và cực đại. Khi so hai điểm m₁,m₂, vị trí có giá trị tốt hơn **không đủ cho biết** cực tiểu toàn cục cần tìm đang ở phần nào.

Một nhánh bị loại có thể chứa cực tiểu toàn cục khác.

Tương tự, nếu f có hai “thung lũng” ngăn nhau bởi một “đồi”, việc loại một phía theo hai mẫu thử có thể bỏ đáp án.

### Không phải cứ liên tục là đơn đỉnh

Tính liên tục chỉ bảo đảm (dưới điều kiện đoạn đóng bị chặn) có cực trị theo định lý Weierstrass. Nó **không bảo đảm cấu trúc một đáy hoặc một đỉnh**.

Muốn dùng ternary search, cần có **chứng minh từ công thức**, từ tính lồi/lõm, đạo hàm, hoặc cấu trúc bài toán rằng hình dạng đúng trên **toàn đoạn đang xét**.

### Không phải cứ biểu đồ “nhìn như một đỉnh” là đủ

Dữ liệu lấy mẫu ít điểm có thể bỏ qua một cực trị hẹp. Một số hàm có nhiễu, gián đoạn hoặc đo lường sai cũng có thể phá điều kiện đơn đỉnh.

Nếu không chứng minh được shape, thuật toán cần một chiến lược khác: quét, chia đoạn dựa trên cấu trúc, tối ưu hóa toàn cục có giả định hoặc phương pháp số chuyên biệt.

## 16. Các ứng dụng có thể gặp

### Tối ưu một đại lượng hình học theo tham số

Ví dụ điểm P di chuyển dọc một đường thẳng, cần chọn tham số t để **tổng bình phương khoảng cách** đến một nhóm điểm là nhỏ nhất. Hàm mục tiêu bậc hai theo t, lồi và có một đáy.

Nếu bài cần cực tiểu một chiều và công thức mục tiêu xác định, ternary search là một lựa chọn dễ triển khai.

### Chọn thời điểm làm tổng chi phí thấp nhất

Một chi phí có thể gồm một phần **giảm theo thời gian** và một phần **tăng theo thời gian**. Tổng không tự động đơn đỉnh chỉ vì từng thành phần đơn điệu ngược chiều; cần xem **tốc độ thay đổi** hoặc chứng minh lồi/đơn đỉnh.

Ví dụ:

**f(t)=a(t−t₀)²+c** với a>0 là lồi và có cực tiểu t=t₀.

### Tối ưu độ dài/giá trị trong một dãy rời rạc

Nếu điểm số theo chỉ số k thực sự tăng rồi giảm nghiêm ngặt, có thể tam phân để tìm **đỉnh** thay vì duyệt toàn bộ.

Nhưng nếu điểm số sinh từ một quy hoạch động phức tạp, không được tự suy đoán tính đơn đỉnh chỉ từ vài test nhỏ.

### Trường hợp không nên dùng

- Hàm có nhiều vùng tăng giảm.
- Có điều kiện ràng buộc tạo **nhiều đoạn khả thi rời rạc**.
- Dãy chỉ biết “không tăng rồi không giảm” nhưng có plateau cao trước cực tiểu.
- Đánh giá f tốn thời gian mà không có bound số lần gọi.
- Đề đòi sai số quá nhỏ so với độ phân giải double.
- Bài rời rạc cần **toàn bộ các vị trí cực tiểu** hoặc tie-break biên trái mà tam phân không bảo toàn.

## 17. Java 17+ hoàn chỉnh: liên tục, rời rạc, lồi và phản ví dụ

Chương trình độc lập gồm:

1. **ternaryReal** cho hàm số thực nghiêm ngặt một đáy/đỉnh hoặc trường hợp có bảo đảm thu hẹp tương đương; trả một vị trí x xấp xỉ và giá trị f(x).
2. **ternaryInt** cho miền int đóng [left,right], dùng phép trừ chỉ số trên long để tránh overflow và **quét tối đa bốn điểm** cuối.
3. **leftmostConvexMin** cho một dãy lồi rời rạc, trả **vị trí nhỏ nhất** đạt cực tiểu.
4. Các ví dụ bậc hai, hàm trị tuyệt đối, cực trị tại biên, plateau cực tiểu và trường hợp **plateau cao** cố tình vi phạm điều kiện an toàn.

Cả hai hàm tam phân đều **dựa trên hợp đồng hình dạng**: caller phải cung cấp một hàm có tính đơn đỉnh đủ mạnh. Chúng **không tự nhận diện hoặc chứng minh tính đơn đỉnh** của f.

**Lưu tệp: TernarySearchUnimodalDemo.java**

~~~java
import java.util.Locale;
import java.util.function.DoubleUnaryOperator;
import java.util.function.IntToLongFunction;

public class TernarySearchUnimodalDemo {

    record RealResult(double arg, double value) {}

    record IntResult(int arg, long value) {}

    // For continuous strictly unimodal functions, or another
    // shape assumption that justifies the equality branch.
    static RealResult ternaryReal(
            DoubleUnaryOperator f,
            double left, double right,
            boolean maximize) {

        if (!Double.isFinite(left)
                || !Double.isFinite(right)
                || left > right) {
            throw new IllegalArgumentException(
                    "Invalid real interval");
        }

        for (int iteration = 0; iteration < 180; iteration++) {
            double third = (right - left) / 3.0;
            double m1 = left + third;
            double m2 = right - third;

            // Stop if floating-point rounding prevents progress.
            if (!(left < m1 && m1 < m2 && m2 < right)) {
                break;
            }

            double y1 = f.applyAsDouble(m1);
            double y2 = f.applyAsDouble(m2);

            if (!Double.isFinite(y1)
                    || !Double.isFinite(y2)) {
                throw new ArithmeticException(
                        "Function returned non-finite value");
            }

            if (maximize ? y1 < y2 : y1 > y2) {
                left = m1;
            } else if (maximize ? y1 > y2 : y1 < y2) {
                right = m2;
            } else {
                // Safe only under the declared shape assumption.
                left = m1;
                right = m2;
            }
        }

        double arg = left + (right - left) / 2.0;
        double value = f.applyAsDouble(arg);

        if (!Double.isFinite(value)) {
            throw new ArithmeticException(
                    "Non-finite optimum value");
        }

        return new RealResult(arg, value);
    }

    // Inclusive integer interval; O(log N) comparisons under
    // strict unimodality or suitable discrete convexity.
    static IntResult ternaryInt(
            IntToLongFunction f,
            int left, int right,
            boolean maximize) {

        if (left > right) {
            throw new IllegalArgumentException(
                    "Empty integer interval");
        }

        while ((long) right - left > 3L) {
            long third = ((long) right - left) / 3L;
            int m1 = (int) (left + third);
            int m2 = (int) (right - third);

            long y1 = f.applyAsLong(m1);
            long y2 = f.applyAsLong(m2);

            if (maximize ? y1 < y2 : y1 > y2) {
                left = m1 + 1;
            } else if (maximize ? y1 > y2 : y1 < y2) {
                right = m2 - 1;
            } else {
                // Not safe for arbitrary weak unimodality.
                left = m1;
                right = m2;
            }
        }

        int best = left;
        long bestValue = f.applyAsLong(left);

        // Use a long loop counter to avoid overflow at MAX_VALUE.
        for (long x = (long) left + 1; x <= right; x++) {
            long value = f.applyAsLong((int) x);
            if (maximize ? value > bestValue
                         : value < bestValue) {
                best = (int) x;
                bestValue = value;
            }
        }

        return new IntResult(best, bestValue);
    }

    // For DISCRETE CONVEX f only:
    // delta(i) = f(i+1) - f(i) is nondecreasing.
    // Returns the globally leftmost minimizer.
    static IntResult leftmostConvexMin(
            IntToLongFunction f, int left, int right) {

        if (left > right) {
            throw new IllegalArgumentException(
                    "Empty integer interval");
        }

        while (left < right) {
            int mid = (int) (
                    (long) left + ((long) right - left) / 2L);

            long a = f.applyAsLong(mid);
            long b = f.applyAsLong(mid + 1);

            if (a <= b) {
                right = mid;
            } else {
                left = mid + 1;
            }
        }

        return new IntResult(left, f.applyAsLong(left));
    }

    static long quadratic(int x) {
        long d = x - 7L;
        return d * d + 3L;
    }

    static long plateau(int x) {
        long distance = x < 4 ? 4L - x
                : x > 6 ? (long) x - 6L : 0L;
        return 2L + distance * distance;
    }

    static void showReal(
            String title, RealResult result) {
        System.out.printf(Locale.ROOT,
                "%s: x=%.6f, value=%.6f%n",
                title, result.arg(), result.value());
    }

    static void showInt(
            String title, IntResult result) {
        System.out.println(title + ": arg=" + result.arg()
                + ", value=" + result.value());
    }

    public static void main(String[] args) {

        showReal("Continuous minimum",
                ternaryReal(
                        x -> (x - 2.5) * (x - 2.5) + 1.0,
                        -20.0, 20.0, false));

        showReal("Continuous maximum",
                ternaryReal(
                        x -> 12.0 - (x + 3.0) * (x + 3.0),
                        -20.0, 20.0, true));

        showReal("Continuous absolute value",
                ternaryReal(
                        x -> Math.abs(x - 4.25),
                        -10.0, 10.0, false));

        showReal("Continuous boundary minimum",
                ternaryReal(
                        x -> 2.0 * x + 3.0,
                        -5.0, 5.0, false));

        showInt("Discrete quadratic",
                ternaryInt(
                        TernarySearchUnimodalDemo::quadratic,
                        -30, 30, false));

        showInt("Discrete flat minimum",
                ternaryInt(
                        TernarySearchUnimodalDemo::plateau,
                        -20, 20, false));

        showInt("Discrete maximum",
                ternaryInt(
                        x -> {
                            long d = x + 4L;
                            return 100L - d * d;
                        },
                        -20, 20, true));

        showInt("Discrete boundary minimum",
                ternaryInt(
                        x -> 2L * x + 3L,
                        -5, 5, false));

        showInt("Discrete singleton",
                ternaryInt(
                        TernarySearchUnimodalDemo::quadratic,
                        9, 9, false));

        showInt("Convex leftmost flat minimum",
                leftmostConvexMin(
                        TernarySearchUnimodalDemo::plateau,
                        -20, 20));

        // This function is only WEAKLY unimodal:
        // a high plateau hides a narrow dip at index 9.
        long[] weak = {
                10, 10, 10, 10, 10, 10,
                10, 10, 10, 0, 1, 2
        };

        IntResult incorrect = ternaryInt(
                index -> weak[index], 0, weak.length - 1,
                false);

        System.out.println(
                "Weak counterexample: f(3)=" + weak[3]
                + ", f(8)=" + weak[8]
                + ", ternary arg=" + incorrect.arg()
                + ", ternary value=" + incorrect.value()
                + ", true arg=9, true value=0");
    }
}
~~~

Biên dịch và chạy bằng **JDK 17 trở lên**:

~~~bash
javac -encoding UTF-8 TernarySearchUnimodalDemo.java
java TernarySearchUnimodalDemo
~~~

**Đầu ra mẫu chính xác theo chương trình:**

~~~text
Continuous minimum: x=2.500000, value=1.000000
Continuous maximum: x=-3.000000, value=12.000000
Continuous absolute value: x=4.250000, value=0.000000
Continuous boundary minimum: x=-5.000000, value=-7.000000
Discrete quadratic: arg=7, value=3
Discrete flat minimum: arg=4, value=2
Discrete maximum: arg=-4, value=100
Discrete boundary minimum: arg=-5, value=-7
Discrete singleton: arg=9, value=7
Convex leftmost flat minimum: arg=4, value=2
Weak counterexample: f(3)=10, f(8)=10, ternary arg=4, ternary value=10, true arg=9, true value=0
~~~

Dòng cuối là **minh họa lỗi có chủ đích**: một hàm chỉ đáp ứng đơn đỉnh yếu có plateau cao **không nằm trong hợp đồng của hàm ternaryInt**. Chương trình chạy và cho thấy kết quả của ternaryInt không tối ưu, không phải ví dụ “thành công” của thuật toán.

### Tại sao ternaryInt dùng long cho phép tính chỉ số?

Nếu right=Integer.MAX_VALUE và left=Integer.MIN_VALUE, hiệu **right−left** không vừa int.

Code dùng:

~~~java
(long) right - left
~~~

để tính span, và cast sau khi đã tính hai điểm trong phạm vi hợp lệ. Vòng quét cuối dùng **long x** để tránh overflow khi tăng x qua Integer.MAX_VALUE.

### Tại sao không lấy Math.abs(f(x)) hay −f(x) cho cực đại?

Cực đại không đồng nghĩa cực tiểu của trị tuyệt đối. Và với long, −Long.MIN_VALUE overflow.

Code thực hiện **so sánh đảo chiều khi maximize=true**, giữ nguyên giá trị gốc của hàm.

### Chi phí của hàm mục tiêu

Trong demo, f chỉ là vài phép toán, nhưng trong bài thực tế f có thể là một phép mô phỏng tốn O(K), do đó tổng chi phí tam phân rời rạc là:

**O(K·log N)**,

với N=R−L+1, cộng việc quét tối đa 4 điểm cuối.

Trong miền liên tục, nếu dùng T vòng thì cần O(T) lần gọi f; với mỗi f tốn O(K), tổng O(KT).

## 18. Chi tiết triển khai miền rời rạc và số nguyên lớn

Với miền int, số lượng chỉ số tối đa khoảng 2³² dù mỗi chỉ số là signed int. Chênh lệch phải tính trên **long**, như code.

Nếu miền là long từ Long.MIN_VALUE đến Long.MAX_VALUE, hiệu R−L cũng có thể vượt long. Khi đó cần:

- Dùng BigInteger cho chỉ số/các phép cộng chia ba, hoặc
- Biến đổi bài toán để giảm miền về số phần tử không gây overflow, hoặc
- Dùng công thức midpoint/third có kiểm tra toán học phù hợp.

Không được chỉ đổi kiểu m₁,m₂ sang long rồi cho rằng mọi phép trừ long đều an toàn.

### Tràn số trong f

Bản code trả **long value**. Nếu f tự tính:

~~~java
return (x - 7) * (x - 7);
~~~

với x là int, hai phép tính có thể diễn ra ở int và overflow trước khi trả về long.

Đúng hơn:

~~~java
long d = x - 7L;
return d * d;
~~~

và vẫn phải bảo đảm d*d nằm trong long. Với input hoặc giá trị f vượt long, có thể dùng **BigInteger** và so qua compareTo, hoặc chứng minh một bound an toàn.

### Không cần lưu toàn bộ f(i)

Ternary search chỉ gọi f ở những chỉ số được chọn, không cần tạo một mảng giá trị đầy đủ. Nếu f rất đắt và một chỉ số có thể được hỏi lại, có thể memoize kết quả, nhưng bộ nhớ đánh đổi theo số distinct queries.

## 19. Kịch bản nhiều điểm tối ưu và quy tắc chọn đáp án

Nếu f(x)=0 cho mọi x trong đoạn, thì:

**Mọi x là argmin và argmax**.

Với hàm lồi phẳng hoàn toàn, tam phân giữ đoạn giữa ở mỗi lần bằng nhau và cuối cùng trả một điểm ở giữa. Điều đó **vẫn tối ưu theo giá trị** nhưng không phải vị trí **nhỏ nhất** trong đoạn.

Nếu đề cần:

- **Một điểm tối ưu:** tam phân phù hợp với giả thiết shape mạnh.
- **Điểm tối ưu trái nhất/phải nhất:** cần phương pháp tìm biên của plateau theo cấu trúc đơn điệu của đạo hàm/sai phân, ví dụ leftmostConvexMin.
- **Số lượng điểm tối ưu:** cần tìm hai biên của tập nghiệm nếu tập ấy liên tiếp và có cách tìm biên chính xác.
- **Tất cả điểm tối ưu:** có thể phải xuất O(K) kết quả, không thể tốt hơn kích thước output.

### Tie không phải “luôn bỏ đoạn giữa”

Với các so sánh bằng nhau, nên có một chứng minh cụ thể bảo đảm đoạn giữ lại còn ít nhất một điểm tối ưu. Không có một quy tắc xử lý equality nào tự động đúng trên mọi dãy không tăng rồi không giảm.

## 20. Khi hàm không xác định ở một số điểm

Trong tối ưu một biến có thể có các giá trị x **không hợp lệ**, ví dụ chia cho 0 hoặc vi phạm một ràng buộc.

Nếu miền khả thi là **một đoạn liên tục** [L,R] và f đơn đỉnh trên đoạn ấy, có thể tìm trực tiếp trong miền đó.

Nhưng nếu miền khả thi gồm nhiều đoạn rời nhau:

**[a,b] ∪ [c,d]** với b<c,

thì không thể gọi ternary search trên toàn khoảng [a,d] rồi lấy f tại vùng không hợp lệ.

Các cách xử lý:

- Tách các thành phần khả thi, tối ưu riêng từng phần, so kết quả.
- Biến đổi bài toán để hàm luôn xác định và bảo toàn cấu trúc đơn đỉnh.
- Sử dụng phương pháp tối ưu có xử lý ràng buộc phù hợp.

### NaN và vô cực

Trong Java:

- **Double.NaN** không có thứ tự thông thường; các phép so >, < với NaN đều false.
- **Double.POSITIVE_INFINITY** và NEGATIVE_INFINITY có thể làm hai nhánh so sánh kém ý nghĩa nếu không nằm trong hợp đồng hàm.
- Các phép cộng/trừ khi tính midpoint cũng có thể overflow thành Infinity.

Bản demo từ chối input interval không hữu hạn và giá trị hàm không hữu hạn tại các điểm thử. Với bài thực tế có infinity như một “giá trị cấm”, nên thiết kế API rõ thay vì để logic ternary tự rẽ nhánh dựa trên NaN.

## 21. Độ phức tạp và số phép gọi hàm

### Miền liên tục

Sau mỗi vòng, đoạn có độ dài tối đa 2/3 đoạn trước trong số học thực, nên để đạt khoảng rộng EPS cần:

**O(log((R−L)/EPS)) vòng**.

Mỗi vòng đánh giá f(m₁), f(m₂), tức **hai phép gọi f** nếu không cache, cộng một phép gọi khi trả giá trị tại điểm cuối.

Nếu số vòng cố định là T, số lần đánh giá là **O(T)**.

### Miền nguyên

Gọi N=R−L+1.

Khi span>3, các nhánh an toàn giảm số vị trí còn lại theo một tỉ lệ hằng số. Vì vậy cần **O(log N) vòng**, cộng O(1) phép đánh giá trong đoạn cuối.

Nếu f tính mất O(K), tổng thời gian **O(K log N)**.

Bộ nhớ phụ **O(1)** cho bản lặp khi biểu diễn chỉ số và giá trị hàm bằng các kiểu cố định.

### Cảnh báo về dữ liệu lặp

Ngay cả khi có hàng triệu phần tử, không nên tự động kết luận tam phân sẽ đúng. **Độ phức tạp thấp không thay thế được giả thiết tính đúng**. Một thuật toán O(log N) nhưng loại nhầm cực tiểu không phải lời giải hợp lệ.

## 22. Kiểm thử bằng oracle vét cạn

Đối với miền nguyên và các hàm f có cấu trúc đã biết, oracle dễ nhất là quét toàn bộ:

~~~text
BRUTE_MIN(f, L, R):
    best = L
    for i from L+1 to R:
        if f(i) < f(best):
            best = i
    return (best, f(best))
~~~

Tương tự, với max dùng >.

Khi có nhiều điểm tối ưu, so **giá trị tối ưu** và kiểm tra chỉ số trả về thật sự đạt giá trị ấy. Không bắt buộc so vị trí argmin bằng nhau trừ khi đề yêu cầu cùng tie-break.

### Bộ test có giá trị

1. f(x)=(x−c)²+d, với c là số nguyên ngẫu nhiên trong đoạn.
2. g(x)=d−(x−c)², để thử cực đại.
3. Hàm chữ V f(x)=|x−c|, có cực tiểu duy nhất.
4. Hàm đáy phẳng: distance(x,[a,b])²+d.
5. Hàm đơn điệu tăng/giảm, cực trị tại biên.
6. Đoạn chỉ có **một** hoặc **hai** chỉ số.
7. Miền chứa số âm.
8. Miền có chỉ số gần Integer.MIN_VALUE hoặc Integer.MAX_VALUE, với hàm f được tính tránh tràn.
9. Hàm hằng trên đoạn: một điểm tối ưu bất kỳ hợp lệ, nhưng không chắc là leftmost.
10. Phản ví dụ **plateau cao**: dùng để xác nhận tài liệu không tuyên bố sai về miền áp dụng.

### So với binary search convex

Với hàm lồi rời rạc, so:

- Giá trị tối ưu của ternaryInt.
- Giá trị tối ưu từ brute.
- Chỉ số **trái nhất** từ leftmostConvexMin.

Điều này kiểm tra cả hai API với hai hợp đồng hơi khác nhau.

## 23. Kiểm thử miền liên tục

Với hàm có nghiệm giải tích, có thể so x được trả về với đáp án đã biết:

- f(x)=(x−c)²+d ⇒ argmin=c.
- f(x)=|x−c| ⇒ argmin=c.
- g(x)=d−(x−c)² ⇒ argmax=c.
- f(x)=ax+b với a>0 ⇒ min ở L, max ở R.
- f(x)=ax+b với a<0 ⇒ min ở R, max ở L.

Thử nhiều c ngẫu nhiên nằm trong đoạn, nhiều độ rộng [L,R] và kiểm tra **độ sai lệch của x**.

### Chọn ngưỡng test phù hợp

Nếu in sáu chữ số thập phân, ngưỡng so x có thể là 10^−5 trong các test tọa độ vừa phải. Nhưng nếu c hoặc miền đầu vào rất lớn, tolerance tuyệt đối như thế có thể không khả thi do giới hạn double.

Không nên dùng điều kiện:

~~~java
actual == expected
~~~

cho mọi đáp án số thực. Thay vào đó, kiểm tra **|actual−expected|≤EPS** với EPS được chọn theo đặc tả và tính điều kiện của bài.

### Đừng suy diễn từ random test

Random test có thể bắt nhiều lỗi indexing nhưng **không chứng minh** một hàm tùy ý luôn đơn đỉnh. Điều đó cần chứng minh từ toán học hoặc hợp đồng bài toán.

Đặc biệt, các phép thử ngẫu nhiên trên parabol không thể phát hiện lỗi khi code được áp dụng cho **plateau cao** nếu không có một test có chủ đích.

## 24. Những lỗi thường gặp

1. **Áp dụng tam phân cho hàm nhiều cực trị**, bỏ mất cực trị toàn cục.
2. **Nhầm đơn đỉnh yếu với đơn đỉnh nghiêm ngặt**, cho phép plateau cao che giấu nghiệm.
3. **Khi f(m₁)=f(m₂), luôn giữ [m₁,m₂]** mà không chứng minh điều kiện shape đủ mạnh.
4. **Coi f(m₁)>f(m₂) trong bài min là phải dịch R**, thực tế phải dịch L.
5. **Không đảo chiều khi tìm max**, nên tối ưu sai hướng.
6. **Lấy −f(x) trên long để chuyển max thành min**, có thể overflow với Long.MIN_VALUE.
7. **Chỉ xét m₁,m₂ mà không duyệt các điểm cuối trong miền nguyên**, bỏ nghiệm ở biên.
8. **Dừng miền nguyên bằng EPS**, không bảo đảm trả chỉ số chính xác.
9. **Dùng while(left<right) với m₁=m₂ hoặc m₁=left**, vòng không tiến triển.
10. **Tính right−left bằng int** khi hai đầu gần cực trị signed int, overflow.
11. **Cho cả hai điểm m₁,m₂ bằng nhau do làm tròn double** nhưng vẫn cập nhật, có thể lặp vô hạn.
12. **Dùng Double.NaN trong phép so sánh** mà không kiểm tra, mọi nhánh quan hệ có thể sai.
13. **Đánh giá f có overflow long**, thuật toán so sánh những giá trị đã sai.
14. **Quên rằng f có thể tốn O(K)**, báo O(log N) thời gian tổng sai khi K lớn.
15. **Cho rằng ternaryInt luôn trả argmin trái nhất khi có plateau**, không có bảo đảm.
16. **Áp dụng binary slope search cho dãy yếu có plateau cao**, sai dù không dùng ternary.
17. **Không chứng minh giá trị f(mid) và f(mid+1) có quan hệ đơn điệu**, suy ra nhánh sai.
18. **Quên trường hợp L=R**, truy cập chỉ số ngoài đoạn.
19. **Dùng midpoint (L+R)/2 trên int** mà không chống overflow.
20. **Đặt EPS nhỏ hơn độ phân giải double quanh miền xét**, gây tiêu chí dừng không khả thi.
21. **Nhầm sai số của x với sai số của f(x)** khi không có cận thay đổi của f.
22. **Coi hàm liên tục là mặc nhiên đơn đỉnh**, trong khi có thể có nhiều cực trị.
23. **Coi tất cả bài có dạng “đầu tiên giảm rồi tăng” cho phép bất kỳ cách xử lý equality**, không xét nghiêm ngặt.
24. **Tối ưu trên cả đoạn có điểm không hợp lệ**, dẫn tới NaN hoặc Infinity.
25. **Đặt điểm m₁=L+(R−L)/2 và m₂ giống m₁**, không còn đủ hai phép so sánh tam phân.
26. **Không duy trì đoạn chứa nghiệm**, làm sai chứng minh invariant.
27. **Cho rằng ternary search luôn tốt hơn binary search**, dù bài có tính lồi và sai phân đơn điệu.
28. **Xác nhận thuật toán bằng vài ví dụ parabola nhưng không thử cực trị ở biên**, bỏ lỗi off-by-one.
29. **Mong một điểm cực trị trả về chính xác toán học bằng double**, bỏ qua làm tròn số thực.
30. **Không phân biệt local optimum và global optimum**, tin một cực trị bất kỳ là đáp án.
31. **Không giới hạn số lần gọi hàm tốn kém**, có thể vượt thời gian dù chỉ O(log N) vòng.
32. **Không nói rõ miền giả thiết là toàn đoạn [L,R]**, một hàm có thể đơn đỉnh trên đoạn hẹp nhưng không đơn đỉnh trên miền rộng.
33. **Bỏ qua dấu bằng khi so sánh** hoặc xử lý nhánh bằng nhau tùy tiện, khiến mất nghiệm trong trường hợp plateau.
34. **Giữ f(m₁) nhưng so sai với f(R) thay vì f(m₂)**, không đúng với công thức chứng minh.
35. **Đánh giá hàm không thuần (stateful/random) ở các điểm khác nhau**, so sánh không đại diện cùng một hàm tĩnh.
36. **Không kiểm tra hằng số đầu vào hữu hạn**, m₁,m₂ có thể là NaN/Infinity.
37. **Nhầm thuật toán tối ưu hoá 1D bằng tam phân với tìm kiếm ternary trong cây tìm kiếm**, hai khái niệm không giống nhau.
38. **Không xử lý yêu cầu output nhiều vị trí cực trị**, trong khi thuật toán chỉ trả một điểm.

## 25. Câu hỏi và bài tập tự luyện

**Câu 1.** Ternary search tìm min cần giả thiết gì?  
**Đáp án:** Hàm có cấu trúc giảm rồi tăng đủ mạnh để loại một phần đoạn dựa trên hai phép so sánh; với equality cần bảo đảm giữ đoạn vẫn chứa một argmin, ví dụ đơn đỉnh nghiêm ngặt hoặc lồi.

**Câu 2.** Công thức m₁,m₂ trên [L,R]?  
**Đáp án:** m₁=L+(R−L)/3, m₂=R−(R−L)/3.

**Câu 3.** Nếu f(m₁)>f(m₂) trong bài min, giữ phía nào?  
**Đáp án:** Giữ [m₁,R] trong miền thực; trong miền nguyên có thể giữ [m₁+1,R] dưới giả thiết thích hợp.

**Câu 4.** Nếu f(m₁)<f(m₂) trong bài max?  
**Đáp án:** Giữ [m₁,R].

**Câu 5.** Có phải mọi hàm “không tăng rồi không giảm” đều xử lý equality bằng đoạn giữa được không?  
**Đáp án:** Không; plateau cao có thể nằm trước một cực tiểu hẹp.

**Câu 6.** Vì sao dãy [10,10,10,10,10,10,10,10,10,0,1,2] là phản ví dụ?  
**Đáp án:** m₁=3,m₂=8 có giá trị bằng 10 nhưng min tại i=9, bị loại nếu giữ [3,8].

**Câu 7.** Hàm f(x)=(x−7)²+3 trên số nguyên có argmin nào?  
**Đáp án:** x=7, giá trị 3.

**Câu 8.** Hàm g(x)=100−(x+4)² có argmax nào?  
**Đáp án:** x=−4, giá trị 100.

**Câu 9.** Nếu chỉ còn bốn chỉ số nguyên, cách an toàn nhất?  
**Đáp án:** Quét cả bốn chỉ số và chọn giá trị tối ưu.

**Câu 10.** Nếu f hằng trên cả đoạn, tất cả điểm có tối ưu không?  
**Đáp án:** Có; một điểm bất kỳ đều tối ưu nhưng không tự động là leftmost.

**Câu 11.** Điều kiện lồi rời rạc theo sai phân?  
**Đáp án:** Δf(i)=f(i+1)−f(i) là dãy không giảm.

**Câu 12.** Nếu f lồi rời rạc và f(mid)≤f(mid+1), leftmost argmin nằm đâu?  
**Đáp án:** Không nằm sau mid; có thể giữ [L,mid].

**Câu 13.** Với miền thực, số vòng để đạt width≤EPS?  
**Đáp án:** O(log((R−L)/EPS)) dưới mô hình số học thực và nhánh thu hẹp hợp lệ.

**Câu 14.** Khi f được tính trong O(K), chi phí tam phân nguyên?  
**Đáp án:** O(K log N) với N số chỉ số trong đoạn.

**Câu 15.** Tại sao phải dùng long để tính (intRight−intLeft)?  
**Đáp án:** Hiệu của hai số int hợp lệ có thể vượt giới hạn int.

**Câu 16.** Một hàm sin(x) trên đoạn nhiều chu kỳ có thích hợp không?  
**Đáp án:** Không, vì có nhiều cực trị, không thỏa đơn đỉnh trên toàn đoạn.

**Câu 17.** Tại sao chọn EPS theo x chưa chắc bảo đảm sai số f nhỏ?  
**Đáp án:** Cần thêm cận biến thiên của f, ví dụ Lipschitz, để suy ra sai số giá trị.

**Câu 18.** Nếu hàm có plateau cực tiểu, tam phân chắc trả điểm trái nhất không?  
**Đáp án:** Không. Với lồi rời rạc, có thể dùng binary slope để tìm trái nhất.

**Câu 19.** Nếu DoubleUnaryOperator trả NaN tại một điểm thử thì sao?  
**Đáp án:** Phải xử lý theo hợp đồng API; code minh họa báo lỗi, không tiếp tục so sánh vô nghĩa.

**Câu 20.** Khi nào nên quét O(n) thay vì tam phân?  
**Đáp án:** Khi không đủ giả thiết loại đoạn an toàn, chẳng hạn một dãy đơn đỉnh yếu có plateau cao ẩn trước cực tiểu.

## 26. Checklist giải bài và kết luận

Trước khi dùng tìm kiếm tam phân:

1. **Xác định rõ miền:** số thực hay số nguyên, đoạn đóng hay miền rời.
2. **Xác định cực trị:** min hay max; trả một argopt hay cần leftmost/rightmost.
3. **Chứng minh hình dạng f:** nghiêm ngặt, lồi/lõm, hoặc điều kiện khác bảo đảm các nhánh cắt đúng.
4. **Kiểm tra equality:** nếu f(m₁)=f(m₂), chứng minh còn một nghiệm trong [m₁,m₂]. Đừng dựa vào tên “unimodal” mà bỏ qua plateau.
5. **Duy trì khoảng chứa nghiệm:** m₁,m₂ nằm đúng bên trong và sau mỗi vòng đoạn phải ngắn đi.
6. **Miền nguyên:** dùng phép tính chỉ số chống overflow, dừng khi còn ít điểm và quét hết.
7. **Miền thực:** chọn EPS/iteration count hợp lý, chặn NaN/Infinity và phát hiện không tiến triển do làm tròn.
8. **Nếu f là lồi rời rạc**, cân nhắc binary search theo f(mid)≤f(mid+1) để tìm trái nhất.
9. **Nếu f có nhiều cực trị hoặc miền khả thi rời nhau**, không áp dụng tam phân mù quáng.
10. **Kiểm soát chi phí đánh giá f**, nhất là khi mỗi điểm là một bài toán con lớn.
11. **Kiểm thử bằng brute-force** trên miền nguyên nhỏ và nghiệm giải tích trên hàm thực có công thức.
12. **Thử ca phản chứng plateau cao**, không chỉ parabola và các hàm trơn điển hình.
13. **Trả đúng điều đề yêu cầu**: giá trị tối ưu, vị trí tối ưu, sai số cho phép và tie-breaking.
14. **Ghi rõ giả thiết** trong comment hoặc lời giải: O(log N) chỉ có ý nghĩa khi thuật toán được chứng minh giữ lại nghiệm.

**Kết luận:** tìm kiếm tam phân là kỹ thuật thu hẹp khoảng nhanh cho hàm một biến có cực trị được cấu trúc hóa. Nó đơn giản, trực quan và hiệu quả khi **hình dạng hàm đủ mạnh**. Giới hạn quan trọng nhất là **không thể dựa vào hai giá trị bằng nhau để loại đoạn trên mọi hàm đơn đỉnh yếu**; việc chứng minh điều kiện co đoạn và xử lý plateau quan trọng hơn bản thân ba phép chia khoảng.
