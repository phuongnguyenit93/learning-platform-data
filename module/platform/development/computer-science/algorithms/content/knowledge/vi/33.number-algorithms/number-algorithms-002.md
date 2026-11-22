# Chia đôi khoảng để tìm nghiệm với điều kiện phù hợp

**Chia đôi khoảng để tìm nghiệm (bisection method)** là kỹ thuật tìm gần đúng một nghiệm của phương trình `f(x)=0` bằng cách giữ một **khoảng có căn cứ toán học là chứa nghiệm**, rồi lặp lại việc chia khoảng thành hai nửa và giữ nửa còn bảo toàn điều kiện đó. Đây là phương pháp rất chắc chắn khi biết **hàm liên tục trên khoảng ban đầu** và hai đầu khoảng có **giá trị trái dấu**. Nó không đòi hỏi đạo hàm, không cần hàm đơn điệu để tìm *một* nghiệm, nhưng sẽ không bảo đảm kết quả nếu áp dụng mù quáng cho hàm gián đoạn hay một khoảng không chứa đổi dấu.

Bài học thuộc nhóm **Thuật toán số** của Computer Science Algorithms, tập trung vào **chia đôi khoảng để tìm nghiệm với điều kiện phù hợp**. Nội dung gồm phát biểu bài toán, định lý giá trị trung gian, dấu ở hai đầu khoảng, bất biến bao nghiệm, vai trò của tính đơn điệu và tính duy nhất, điều kiện dừng theo sai số tuyệt đối/tương đối, giới hạn số thực `double`, các phản ví dụ, chương trình Java 17+ có kiểm tra đầu vào và báo trạng thái dừng, kiểm thử độc lập, và phân biệt rõ phương pháp tìm nghiệm thực với tìm đáp án nguyên bằng binary search.

## 1. Bài toán: giải f(x)=0 trên một khoảng

Cho một hàm số thực `f` và một khoảng ban đầu `[a,b]`, `a<b`. Ta cần tìm số `x*∈[a,b]` sao cho:

`f(x*)=0`.

Trong bài toán số học trên máy tính, thường ta không thể biểu diễn nghiệm thực `x*` một cách tuyệt đối chính xác bằng số dấu phẩy động. Vì thế kết quả mong muốn thực tế là:

- Một **xấp xỉ** `x̂` của nghiệm;
- Một **khoảng còn lại** `[l,r]` được bảo toàn chứa ít nhất một nghiệm;
- Một **bảo đảm sai số vị trí** như `|x̂−x*|≤ε`, khi những giả thiết toán học và dừng theo độ rộng khoảng được đáp ứng;
- Một **trạng thái dừng** rõ ràng: phát hiện giá trị hàm bằng 0, đạt dung sai, giới hạn biểu diễn số thực hoặc hết số vòng lặp.

Ví dụ:

`f(x)=x²−2`, tìm nghiệm trên `[1,2]`.

Ta có:

`f(1)=−1<0`,

`f(2)=2>0`.

Hàm liên tục trên [1,2], nên **tồn tại ít nhất một nghiệm** trong khoảng. Nghiệm dương là `√2≈1.4142135623730951`. Chia đôi giúp tìm gần đúng nghiệm này mà không cần dùng trực tiếp `Math.sqrt(2)`.

### Đừng nhầm với tìm điểm có f(x) nhỏ

Mục tiêu `f(x)=0` khác với bài toán **tối ưu hóa** `min f(x)`. Một hàm có thể đạt cực tiểu nhưng không bằng 0. Phép chia đôi theo dấu không tự tìm cực tiểu hoặc cực đại; nếu muốn tối ưu cần một mô hình/thuật toán tương ứng.

## 2. Điều kiện bảo đảm tồn tại nghiệm: định lý giá trị trung gian

**Định lý giá trị trung gian (Intermediate Value Theorem, IVT):** Nếu f liên tục trên đoạn đóng [a,b], thì mọi giá trị nằm giữa f(a) và f(b) đều được f nhận ở ít nhất một điểm trong đoạn.

Áp dụng với giá trị cần đạt là 0:

- Nếu `f(a)=0`, a là một nghiệm.
- Nếu `f(b)=0`, b là một nghiệm.
- Nếu `f(a)·f(b)<0`, tức hai giá trị **trái dấu**, và f **liên tục trên [a,b]**, tồn tại ít nhất một `x*∈(a,b)` với `f(x*)=0`.

Điều kiện **liên tục + trái dấu** là một **điều kiện đủ** để bảo đảm nghiệm nằm trong khoảng. Nó **không phải điều kiện cần** cho mọi phương trình có nghiệm.

Ví dụ hàm:

`f(x)=(x−1)²` trên [0,2].

Nghiệm x=1 tồn tại, nhưng:

`f(0)=1>0`, `f(2)=1>0`.

Hai đầu **cùng dấu**. Phương pháp chia đôi **dựa trên đổi dấu** không thể xác nhận khoảng này, dù nó chứa nghiệm bội chẵn. Chương trình sẽ **từ chối** khoảng có hai đầu cùng dấu, thay vì báo sai rằng phương trình hoàn toàn không có nghiệm.

### Ba câu hỏi phải tách riêng

1. **Hàm có nghiệm hay không?** Cần lập luận từ bài toán.
2. **Khoảng có bảo đảm chứa nghiệm theo IVT không?** Cần liên tục và hai đầu trái dấu, hoặc nghiệm đúng tại đầu mút.
3. **Nghiệm có duy nhất không?** Cần thêm điều kiện, chẳng hạn f **đơn điệu nghiêm ngặt** trên khoảng.

Một hàm không đơn điệu vẫn có thể có nhiều nghiệm, và phép chia đôi có thể tìm **một nghiệm nào đó**, không bảo đảm tìm tất cả nghiệm.

## 3. Vì sao không được bỏ giả thiết liên tục?

Xét hàm bước:

~~~text
f(x) = -1 nếu x < 0
f(x) =  1 nếu x >= 0
~~~

Trên [−1,1]:

`f(−1)=−1`, `f(1)=1` — hai đầu trái dấu.

Nhưng **không có x nào làm f(x)=0**. Hàm bị **gián đoạn tại 0**, nên định lý giá trị trung gian không áp dụng. Một chương trình chỉ nhìn dấu sẽ dồn khoảng quanh điểm nhảy và có thể in một số gần 0 dù **không tìm được nghiệm**.

Ví dụ khác:

`f(x)=1/(x−1)` trên [0,2].

Các đầu mút có dấu đối nhau, nhưng hàm **không xác định tại x=1**. Khi chia đôi, phép tính f(1) có thể trả Infinity hoặc ném ngoại lệ; đây không phải một nghiệm.

**Quy tắc an toàn:**

- Trước khi chạy, phải biết hoặc chứng minh f **liên tục và xác định** trên đoạn xét, không chỉ nhìn hai giá trị đầu mút.
- Khi f(x) trả `NaN` hay `Infinity` ở một điểm được đánh giá, **báo lỗi**; không xem Infinity là một số dương bình thường để tiếp tục.
- Đối với các hàm có miền xác định hạn chế như `log(x)`, `sqrt(x)`, phân thức có mẫu số 0, hãy chọn khoảng hoàn toàn nằm trong **một thành phần liên thông hợp lệ** của miền xác định.
- Tách biệt “khoảng không đổi dấu” với kết luận “không tồn tại nghiệm”: đổi dấu **không phát hiện** được mọi nghiệm bội chẵn.

Chương trình Java ở phần sau nhận hàm thông qua `DoubleUnaryOperator` và kiểm tra giá trị **hữu hạn tại mọi vị trí được gọi**, nhưng nó **không thể tự chứng minh tính liên tục của một hàm tùy ý**. Điều kiện liên tục là **trách nhiệm toán học của người dùng thuật toán**.

## 4. Đơn điệu: đủ để bảo đảm duy nhất, không bắt buộc để tìm một nghiệm

Nếu f **liên tục và tăng nghiêm ngặt** trên [a,b], cùng với `f(a)<0<f(b)`, thì có **đúng một nghiệm**. Tương tự với f giảm nghiêm ngặt và dấu ngược.

Chứng minh tính duy nhất đơn giản: giả sử có hai nghiệm x₁<x₂; tính tăng nghiêm ngặt bắt buộc `f(x₁)<f(x₂)`, mâu thuẫn với cả hai bằng 0.

**Nhưng chia đôi theo dấu không yêu cầu f tăng hoặc giảm!** Ví dụ:

`f(x)=x(x−1)(x+1)`.

Trên [−2,2]:

- `f(−2)=−6`,
- `f(2)=6`,
- f liên tục,
- có **ba nghiệm** `−1,0,1`.

Bisection có thể lấy trung điểm x=0 và gặp nghiệm ngay. Điều đúng là thuật toán tìm được **một nghiệm** khi hai đầu trái dấu và f liên tục; không thể kết luận nghiệm là duy nhất.

### Khi nào monotonicity thực sự giúp ích?

- Khi đề yêu cầu **nghiệm duy nhất**, ta có thể dùng đơn điệu nghiêm ngặt để bảo đảm.
- Khi xây khoảng ban đầu, biết f tăng giúp định hướng tìm phía có f âm/dương.
- Khi tìm **ngưỡng** của một điều kiện đơn điệu trên số nguyên, dùng **binary search trên vị từ**; đó là bài toán khác với IVT trên hàm liên tục, sẽ được giải thích ở mục 13.

## 5. Thuật toán chia đôi theo dấu

Giả sử ban đầu f liên tục trên `[a,b]`, `a<b`, và hai đầu có giá trị trái dấu.

Ở mỗi vòng:

1. Lấy trung điểm `m=(a+b)/2`.
2. Tính `f(m)`.
3. Nếu `f(m)=0` theo phép tính, ta có một điểm mà hàm máy tính trả 0.
4. Nếu `f(a)` và `f(m)` **cùng dấu**, nghiệm được đảm bảo thuộc `[m,b]`: cập nhật `a=m`.
5. Ngược lại, `f(a)` và `f(m)` **trái dấu**, nghiệm được đảm bảo thuộc `[a,m]`: cập nhật `b=m`.
6. Lặp đến khi đạt dung sai hoặc điều kiện dừng an toàn.

Giả mã lý tưởng trên số thực:

~~~text
BISECTION(f, a, b, epsilon):
    require a < b
    require f continuous on [a,b]
    if f(a) == 0: return a
    if f(b) == 0: return b
    require f(a), f(b) have opposite signs

    while (b-a)/2 > epsilon:
        m = a + (b-a)/2
        if f(m) == 0: return m
        if f(m) has the same sign as f(a):
            a = m
        else:
            b = m

    return a + (b-a)/2
~~~

Chương trình thực tế bổ sung kiểm tra `NaN`, Infinity, giới hạn vòng lặp và **không thể chia thêm vì biểu diễn double**.

### Vì sao không nên nhân f(a)·f(m) để xét dấu?

Trong toán học, `f(a)·f(m)>0` tương đương hai giá trị cùng dấu. Nhưng trên `double`:

- Tích của hai số rất lớn có thể thành `Infinity`.
- Tích của hai số rất nhỏ có thể **underflow thành 0.0**, dù từng số khác 0 và cùng dấu.
- `NaN` làm các phép so sánh trả false theo cách khó nhận biết.

Thay vào đó, dùng **so sánh dấu trực tiếp**:

~~~java
static boolean sameSign(double x, double y) {
    return (x < 0.0 && y < 0.0)
            || (x > 0.0 && y > 0.0);
}
~~~

Đây là **mảnh mã minh họa**, chưa phải cả chương trình. Hai giá trị đầu mút khác 0 và hữu hạn đã được kiểm tra trước khi gọi.

## 6. Bất biến quan trọng: luôn giữ một khoảng bao nghiệm

Gọi [l,r] là khoảng hiện tại. Với một hàm liên tục và hai đầu trái dấu, bất biến là:

- `l≤r`;
- f liên tục trên [l,r];
- `f(l)` và `f(r)` trái dấu, trừ trường hợp đã gặp giá trị 0 và kết thúc;
- do đó **tồn tại ít nhất một nghiệm trong [l,r]**.

**Khởi tạo:** đúng do giả thiết đầu vào.

**Bước lặp:** m nằm giữa l và r. Nếu f(m)=0, có nghiệm (theo giá trị hàm đã được đánh giá). Nếu f(l),f(m) cùng dấu, theo IVT nghiệm nằm trong [m,r], và hai đầu m,r có dấu đối nhau. Nếu f(l),f(m) trái dấu, nghiệm nằm trong [l,m]. Trong cả hai trường hợp, khoảng mới dài bằng **một nửa** khoảng cũ trong mô hình số thực.

**Kết thúc:** sau k lần thực sự chia đôi thành công:

`r_k−l_k=(b−a)/2^k`.

Đặt ước lượng `x̂=(l_k+r_k)/2`. Vì tồn tại ít nhất một nghiệm `x*∈[l_k,r_k]`:

`|x̂−x*|≤(r_k−l_k)/2=(b−a)/2^(k+1)`.

Đây là **bảo đảm sai số vị trí nhờ khoảng bao**, không cần f khả vi hoặc đơn điệu. Nếu có nhiều nghiệm, bảo đảm là có **ít nhất một nghiệm** nằm gần x̂, không phải mọi nghiệm khác trên [a,b] đều gần x̂.

### Chứng minh tính hội tụ

Vì chiều dài khoảng giảm theo cấp số nhân và tiến về 0, hai đầu l_k,r_k cùng hội tụ về một điểm x* nằm trong mọi khoảng lồng nhau. Nhờ dấu hai đầu và liên tục, giới hạn ấy là nghiệm. Trong máy tính số thực hữu hạn, quá trình không thể thu hẹp vô hạn, nên cần dừng theo dung sai hoặc phát hiện **stagnation**.

## 7. Một bảng chia đôi cụ thể: tìm √2

Giải `f(x)=x²−2` trên [1,2]. Ta có f(1)<0, f(2)>0. Trong mỗi bước, nếu f(mid)>0 thì giữ nửa **trái**; nếu f(mid)<0 thì giữ nửa **phải**.

| Lượt | Khoảng trước [l,r] | Trung điểm m | f(m) | Khoảng mới |
| ---: | --- | ---: | ---: | --- |
| 1 | [1,2] | 1.5 | 0.25 | [1,1.5] |
| 2 | [1,1.5] | 1.25 | −0.4375 | [1.25,1.5] |
| 3 | [1.25,1.5] | 1.375 | −0.109375 | [1.375,1.5] |
| 4 | [1.375,1.5] | 1.4375 | 0.06640625 | [1.375,1.4375] |
| 5 | [1.375,1.4375] | 1.40625 | −0.0224609375 | [1.40625,1.4375] |
| 6 | [1.40625,1.4375] | 1.421875 | 0.021728515625 | [1.40625,1.421875] |

Các khoảng luôn chứa √2 và cứ nhỏ dần. Sau đủ vòng, kết quả có thể được in tới 9 chữ số sau dấu thập phân là:

`1.414213562`.

**Lưu ý:** số chữ số được in không đồng nghĩa với chứng nhận độ chính xác tới từng chữ số trong mọi hàm; kết quả được chứng nhận bằng **độ rộng bracket** và điều kiện toán học, không bằng cách nhìn số chữ số.

## 8. Chọn sai số dừng: độ rộng khoảng quan trọng hơn |f(x)|

Có nhiều loại “độ chính xác”, không được nhầm:

### 8.1. Sai số tuyệt đối theo biến x

Muốn:

`|x̂−x*|≤ε_abs`.

Khi trả **trung điểm** của khoảng vẫn bao nghiệm, đủ để dừng nếu:

`(r−l)/2≤ε_abs`.

Trong chương trình, kiểm tra **nửa độ rộng** chứ không kiểm tra `r−l≤ε_abs`, vì giới hạn sai số của trung điểm bằng một nửa độ rộng. Cả hai điều kiện đều có thể dùng nếu quy ước báo sai số được thống nhất, nhưng không được dùng lẫn.

### 8.2. Sai số tương đối theo quy mô tọa độ

Khi nghiệm có độ lớn rất lớn, dung sai chỉ tính tuyệt đối có thể không phù hợp. Một quy tắc hỗn hợp là:

`tolerance = max(ε_abs, ε_rel·max(|l|,|r|))`.

Và dừng khi:

`(r−l)/2≤tolerance`.

Điều này có nghĩa là **bảo đảm sai số tuyệt đối không vượt ngưỡng hỗn hợp** (ngưỡng có phần tỉ lệ với độ lớn tọa độ), chứ không tự động bảo đảm `|x̂−x*|/|x*|≤ε_rel` trong mọi trường hợp. Khi nghiệm gần 0, mẫu số |x*| gần 0 khiến sai số tương đối thuần túy thiếu ý nghĩa; **ε_abs** cần được chọn phù hợp.

Mã Java cho phép ε_abs≥0, 0≤ε_rel≤1, ít nhất một trong hai có thể lớn hơn 0; nếu cả hai bằng 0, thuật toán tiếp tục tới khi tính ra 0 hoặc không thể chia thêm ở độ chính xác double.

### 8.3. Độ dư của phương trình |f(x)|

Có thể muốn `|f(x̂)|≤ε_f`. Đây là điều kiện theo **giá trị hàm**, không phải vị trí nghiệm. Hai chuẩn không tương đương nếu không biết thêm tính chất của f.

Ví dụ:

`f(x)=(x−100)³`.

Tại x=99.9, độ dư:

`|f(99.9)|=0.001`,

trông nhỏ nhưng **sai số vị trí** là 0.1. Một hàm rất **phẳng** gần nghiệm có thể cho độ dư cực nhỏ dù x còn xa nghiệm. Ngược lại, hàm rất dốc có thể có độ dư lớn khi x khá gần nghiệm.

Nếu muốn suy ra sai số vị trí từ residual, thường cần **giới hạn dưới của độ dốc** hoặc bất đẳng thức ổn định khác, chẳng hạn `|f'(x)|≥m>0` ở vùng liên quan. Do đó bản demo dừng theo **khoảng bao nghiệm**, không tùy tiện dừng chỉ vì `|f(m)|` nhỏ.

### 8.4. Số chữ số và khả năng biểu diễn double

Ngay cả khi yêu cầu `ε_abs=10^(−20)`, một số double quanh 1 có độ phân giải khoảng 2.22×10^(−16). Có thể đến lúc trung điểm tính bằng double **bằng một đầu mút**, dù hai đầu khác nhau. Khi ấy không còn một double nằm giữa để chia, nên không được tuyên bố đã đạt dung sai chưa thỏa. Chương trình trả `PRECISION_LIMIT`.

## 9. Cần tối đa bao nhiêu vòng chia?

Với khoảng ban đầu dài `W=b−a>0` và dung sai tuyệt đối `ε>0`, sau k lượt chia đôi lý tưởng, sai số trung điểm không quá:

`W / 2^(k+1)`.

Muốn ≤ ε, chọn:

`k≥log₂(W/(2ε))`.

Một giới hạn đủ là:

`k= max(0, ceil(log₂(W/(2ε))))`.

Ví dụ W=1 và ε=10^(−6):

`log₂(1/(2·10^(−6)))≈18.93`,

nên **19 bước chia đôi** đủ cho bound nửa độ rộng ≤10^(−6) trong mô hình số thực. Nếu giữa chừng f(mid)=0, thuật toán có thể dừng **sớm hơn**.

Vì số vòng tăng **logarit** với tỉ số W/ε, bisection là phương pháp ổn định nhưng chỉ đạt **hội tụ tuyến tính** (bán kính khoảng bị chia đôi mỗi vòng), thường chậm hơn Newton ở gần nghiệm khi Newton có điều kiện thuận lợi. Đổi lại, bisection không cần đạo hàm và có bracket bảo đảm.

### Giới hạn vòng là một trạng thái riêng

Nếu chỉ cho chạy, chẳng hạn, 1 lượt trên [1,2] cho `f(x)=x²−2`, khoảng mới là [1,1.5]. Trung điểm được báo là 1.25, **không** đạt dung sai `10^(−15)`. Chương trình phải báo `ITERATION_LIMIT` thay vì in “đã tìm nghiệm chính xác”.

Việc hiển thị một ước lượng **không chứng minh** đã đạt tolerance. Hãy kiểm tra trạng thái dừng.

## 10. Trung điểm an toàn với số thực double

Cách viết trực tiếp:

`m=(l+r)/2`

có nguy cơ overflow khi l,r cùng rất lớn dù trung điểm còn biểu diễn được. Cách thường dùng là:

`m=l+(r−l)/2`.

Với giả thiết `l<r` và `r−l` hữu hạn, cách thứ hai tránh tràn do **cộng l+r**, đồng thời giữ m nằm trong khoảng xét (có thể trùng đầu mút khi đã hết độ phân giải).

Bản Java:

- Yêu cầu `l,r` là số hữu hạn, `l<r`, và **r−l hữu hạn**. Hạn chế này được công bố thay vì âm thầm xử lý không đầy đủ các khoảng dài quá giới hạn double.
- Dùng `mid = l + (r-l)/2.0`.
- Nếu `mid==l` hoặc `mid==r`, trả `PRECISION_LIMIT` với bracket hiện tại.
- Kiểm tra `Double.isFinite(f(mid))` trước khi quyết định dấu.
- Sau cập nhật, kiểm tra **nửa độ rộng** và dừng khi đủ tolerance.

Đối với khoảng rất nhỏ quanh giá trị lớn, có thể **không tồn tại số double biểu diễn được ở giữa**. Đây không phải một phản ví dụ cho định lý giá trị trung gian trên số thực, mà là **giới hạn biểu diễn của máy tính**.

### Tại sao không mặc định dùng epsilon cố định cho mọi bài?

Nếu nghiệm dự kiến quanh 10^12, chọn sai số tuyệt đối 10^(−20) không thực tế với double; nếu nghiệm gần 0, chỉ dùng relative epsilon sẽ không bảo đảm xấp xỉ. Một chương trình đáng tin cho phép người gọi chọn dung sai theo **thang đo biến** và phân biệt **độ chính xác máy** với **chứng minh khoảng bao nghiệm**.

## 11. Xử lý các đầu vào đặc biệt

### Nghiệm đúng tại đầu mút

Nếu `f(a)==0.0` hoặc `f(b)==0.0` theo phép tính, có thể trả ngay điểm ấy với 0 lượt. Không được bác bỏ một khoảng chỉ vì không có **trái dấu nghiêm ngặt** trước khi kiểm tra hai đầu mút bằng 0.

### Trung điểm làm giá trị hàm bằng 0

Với `f(x)=x³` trên [−1,1], mid=0, giá trị hàm máy tính bằng 0 sau một lượt; trả `ZERO_VALUE` và khoảng suy biến [0,0].

**Cần tinh tế:** `ZERO_VALUE` chỉ khẳng định **phép đánh giá bằng double đã trả 0.0**. Nếu biểu thức f được tính gần đúng và bị underflow/cancellation, nó không nhất thiết là chứng minh toán học x là nghiệm chính xác của hàm lý tưởng. Vì vậy chương trình không đặt tên trạng thái là “PROVEN_EXACT_ROOT”.

### Hai đầu không đổi dấu

Với `f(x)=x²+1` trên [−1,1], cả hai đầu dương, không có bracket IVT. Với `f(x)=(x−1)²` trên [0,2], cũng cùng dấu **nhưng thực sự có nghiệm**. Vì vậy báo `NO_SIGN_BRACKET` hoặc ngoại lệ nghĩa là **không đủ điều kiện áp dụng phương pháp**, không có nghĩa đã chứng minh phương trình vô nghiệm.

### Hàm không hữu hạn

`NaN` và `Infinity` phải bị từ chối ngay. Ví dụ nếu f(mid) trả `Double.NaN`, không được rơi vào nhánh else “dấu khác nên chọn khoảng này”; các phép so sánh với NaN đều false và sẽ phá bất biến.

### Khoảng ban đầu sai

Nếu a≥b, hoặc a,b không hữu hạn, hoặc b−a không hữu hạn, chương trình báo lỗi tham số. Nó không tự hoán vị hai đầu vì đề bài và cách hiển thị có thể phụ thuộc thứ tự khoảng.

### Hàm không liên tục

Ngay cả khi giá trị của hàm bước luôn hữu hạn và hai đầu trái dấu, phép chia đôi không chứng minh sự tồn tại của một nghiệm. Kiểm tra `isFinite` là **điều kiện kiểm soát tính toán**, không phải chứng minh tính liên tục toán học.

## 12. Chương trình Java 17+: chia đôi với trạng thái và kiểm chứng

Lưu tệp **`BisectionRootDemo.java`** bằng UTF-8. Chương trình chạy độc lập, không cần thư viện ngoài JDK.

Thiết kế:

- `bisect(f,left,right,absTol,relTol,maxIterations)`: tìm một điểm f(x)=0 gần đúng dựa trên **bracket có thay đổi dấu**.
- `Result` ghi estimate, hai đầu khoảng còn lại, số lượt và lý do dừng.
- `Stop.ZERO_VALUE`: f tại một điểm được máy tính đánh giá bằng 0.
- `Stop.TOLERANCE`: nửa độ rộng bracket ≤ dung sai hỗn hợp.
- `Stop.PRECISION_LIMIT`: trung điểm không còn nằm giữa hai số double.
- `Stop.ITERATION_LIMIT`: đã hết số lượt nhưng chưa đạt tiêu chí mong muốn.
- `sameSign` kiểm tra dấu trực tiếp, tránh phép nhân hai số thực rất nhỏ/lớn.
- `evaluateFinite` từ chối NaN, Infinity.
- `floorSqrt` minh họa **binary search vị từ nguyên đơn điệu** khác với bisection IVT.
- `randomCheck` kiểm tra 500 hàm tuyến tính có nghiệm biết trước, 400 bài toán căn bậc hai, và 1000 giá trị `long` cho `floorSqrt` đối chiếu bằng `BigInteger`. Các oracle không gọi lại logic chọn nửa khoảng của bisection.

### Mã nguồn

~~~java
import java.math.BigInteger;
import java.util.Locale;
import java.util.Objects;
import java.util.Random;
import java.util.function.DoubleUnaryOperator;

public class BisectionRootDemo {
    enum Stop {
        ZERO_VALUE,
        TOLERANCE,
        PRECISION_LIMIT,
        ITERATION_LIMIT
    }

    record Result(
            double estimate,
            double left,
            double right,
            int iterations,
            Stop stop) {}

    static boolean sameSign(double x, double y) {
        return (x < 0.0 && y < 0.0)
                || (x > 0.0 && y > 0.0);
    }

    static double evaluateFinite(
            DoubleUnaryOperator f, double x) {
        double y = f.applyAsDouble(x);
        if (!Double.isFinite(y)) {
            throw new IllegalArgumentException(
                    "Function must be finite at evaluated points");
        }
        return y;
    }

    static double tolerance(
            double l, double r,
            double absoluteTolerance,
            double relativeTolerance) {
        return Math.max(
                absoluteTolerance,
                relativeTolerance *
                        Math.max(Math.abs(l), Math.abs(r)));
    }

    // This API requires a finite bracket length and
    // mathematical continuity on [left, right].
    static Result bisect(
            DoubleUnaryOperator f,
            double left,
            double right,
            double absoluteTolerance,
            double relativeTolerance,
            int maxIterations) {

        Objects.requireNonNull(f, "f");
        if (!Double.isFinite(left)
                || !Double.isFinite(right)
                || !(left < right)
                || !Double.isFinite(right - left)) {
            throw new IllegalArgumentException(
                    "Invalid finite bracket");
        }
        if (!Double.isFinite(absoluteTolerance)
                || absoluteTolerance < 0.0
                || !Double.isFinite(relativeTolerance)
                || relativeTolerance < 0.0
                || relativeTolerance > 1.0
                || maxIterations <= 0) {
            throw new IllegalArgumentException(
                    "Invalid tolerance or iteration limit");
        }

        double l = left, r = right;
        double fl = evaluateFinite(f, l);
        double fr = evaluateFinite(f, r);

        // Exact equality of COMPUTED function values to zero.
        if (fl == 0.0) {
            return new Result(l, l, l, 0, Stop.ZERO_VALUE);
        }
        if (fr == 0.0) {
            return new Result(r, r, r, 0, Stop.ZERO_VALUE);
        }
        if (sameSign(fl, fr)) {
            throw new IllegalArgumentException(
                    "Endpoint values have no sign change");
        }

        double mid = l + (r - l) / 2.0;
        if ((r - l) / 2.0 <= tolerance(
                l, r, absoluteTolerance, relativeTolerance)) {
            return new Result(
                    mid, l, r, 0, Stop.TOLERANCE);
        }

        for (int iteration = 1;
                iteration <= maxIterations; iteration++) {
            mid = l + (r - l) / 2.0;

            // No representable double strictly inside (l, r).
            if (mid == l || mid == r) {
                return new Result(
                        mid, l, r, iteration - 1,
                        Stop.PRECISION_LIMIT);
            }

            double fm = evaluateFinite(f, mid);
            if (fm == 0.0) {
                return new Result(
                        mid, mid, mid, iteration,
                        Stop.ZERO_VALUE);
            }

            // After the update, endpoint signs remain opposed.
            if (sameSign(fl, fm)) {
                l = mid;
                fl = fm;
            } else {
                r = mid;
                fr = fm;
            }

            if ((r - l) / 2.0 <= tolerance(
                    l, r,
                    absoluteTolerance, relativeTolerance)) {
                return new Result(
                        l + (r - l) / 2.0,
                        l, r, iteration,
                        Stop.TOLERANCE);
            }
        }

        return new Result(
                l + (r - l) / 2.0,
                l, r, maxIterations,
                Stop.ITERATION_LIMIT);
    }

    // A DIFFERENT binary search: largest integer x>=0
    // satisfying x*x <= n, avoiding overflow via x <= n/x.
    static long floorSqrt(long n) {
        if (n < 0L)
            throw new IllegalArgumentException("Negative input");
        if (n < 2L) return n;

        long low = 1L;
        long high = n;
        long answer = 1L;

        while (low <= high) {
            long middle = low + (high - low) / 2L;
            // middle >= 1, so division is safe.
            if (middle <= n / middle) {
                answer = middle;
                low = middle + 1L;
            } else {
                high = middle - 1L;
            }
        }
        return answer;
    }

    static void show(
            String label,
            DoubleUnaryOperator f,
            double a, double b,
            double absoluteTolerance,
            int maxIterations) {
        Result result = bisect(
                f, a, b,
                absoluteTolerance, 0.0,
                maxIterations);
        System.out.printf(
                Locale.ROOT,
                "%s root=%.9f stop=%s iterations=%d%n",
                label,
                result.estimate(),
                result.stop(),
                result.iterations());
    }

    static void verifyBracket(
            Result r, double knownRoot,
            double maximumError) {
        if (!Double.isFinite(r.estimate())
                || !(r.left() <= knownRoot
                        && knownRoot <= r.right())
                || Math.abs(r.estimate() - knownRoot)
                        > maximumError) {
            throw new AssertionError(
                    "Wrong root estimate or lost bracket");
        }
    }

    static void randomCheck() {
        Random random = new Random(2026L);

        // Independent analytical roots of random lines.
        for (int test = 0; test < 500; test++) {
            int root = random.nextInt(2001) - 1000;
            int magnitude = 1 + random.nextInt(10);
            double slope = random.nextBoolean()
                    ? magnitude : -magnitude;
            DoubleUnaryOperator f =
                    x -> slope * (x - root);
            Result r = bisect(
                    f, root - 3.0, root + 5.0,
                    1.0e-10, 0.0, 100);
            verifyBracket(r, root, 1.0e-10);
            if (r.stop() == Stop.ITERATION_LIMIT
                    || r.stop() == Stop.PRECISION_LIMIT) {
                throw new AssertionError("Unexpected stop on line");
            }
        }
        System.out.println(
                "linearCheck=PASS (500 equations)");

        // Independent Math.sqrt reference, not binary search.
        for (int test = 0; test < 400; test++) {
            int number = 1 + random.nextInt(1_000_000);
            DoubleUnaryOperator f = x -> x * x - number;
            Result r = bisect(
                    f, 0.0, number + 1.0,
                    1.0e-9, 0.0, 120);
            verifyBracket(
                    r, Math.sqrt(number), 2.0e-9);
            if (r.stop() == Stop.ITERATION_LIMIT
                    || r.stop() == Stop.PRECISION_LIMIT) {
                throw new AssertionError(
                        "Unexpected stop on square root");
            }
        }
        System.out.println(
                "sqrtCheck=PASS (400 equations)");

        // Integer binary search checked by exact BigInteger
        // inequalities to avoid x*x overflow near Long.MAX_VALUE.
        for (int test = 0; test < 1000; test++) {
            long number = random.nextLong()
                    & Long.MAX_VALUE;
            long answer = floorSqrt(number);
            BigInteger n = BigInteger.valueOf(number);
            BigInteger x = BigInteger.valueOf(answer);
            BigInteger next = x.add(BigInteger.ONE);
            if (x.multiply(x).compareTo(n) > 0
                    || next.multiply(next).compareTo(n) <= 0) {
                throw new AssertionError(
                        "Wrong integer square root");
            }
        }
        System.out.println(
                "integerSqrtCheck=PASS (1000 values)");
    }

    public static void main(String[] args) {
        show("sqrt2",
                x -> x * x - 2.0,
                1.0, 2.0, 1.0e-12, 200);
        show("cubic",
                x -> x * x * x - x - 2.0,
                1.0, 2.0, 1.0e-12, 200);
        show("cos",
                x -> Math.cos(x) - x,
                0.0, 1.0, 1.0e-12, 200);
        show("endpoint",
                x -> x - 5.0,
                5.0, 9.0, 1.0e-12, 200);
        show("exactMid",
                x -> x * x * x,
                -1.0, 1.0, 1.0e-12, 200);
        show("limited",
                x -> x * x - 2.0,
                1.0, 2.0, 1.0e-15, 1);

        show("precision",
                x -> x - 1.0 - Double.MIN_VALUE,
                1.0, Math.nextUp(1.0), 0.0, 200);

        try {
            bisect(x -> x * x + 1.0,
                    -1.0, 1.0, 1.0e-12, 0.0, 80);
            throw new AssertionError(
                    "Expected same-sign rejection");
        } catch (IllegalArgumentException expected) {
            System.out.println("sameSign=rejected");
        }

        try {
            bisect(x -> (x - 1.0) * (x - 1.0),
                    0.0, 2.0, 1.0e-12, 0.0, 80);
            throw new AssertionError(
                    "Expected tangent-bracket rejection");
        } catch (IllegalArgumentException expected) {
            System.out.println("tangent=rejected");
        }

        try {
            bisect(x -> x == 0.0 ? Double.NaN : x,
                    -1.0, 1.0, 1.0e-12, 0.0, 80);
            throw new AssertionError(
                    "Expected non-finite function rejection");
        } catch (IllegalArgumentException expected) {
            System.out.println("nonFinite=rejected");
        }

        // Step functions are NOT continuous and cannot
        // justify a root via the Intermediate Value Theorem.
        System.out.println("stepFunction=notAValidIVTExample");

        long[] integers = {
            0L, 1L, 2L, 15L, 16L, 17L,
            Long.MAX_VALUE
        };
        for (long n : integers) {
            System.out.println(
                    "isqrt(" + n + ")=" + floorSqrt(n));
        }

        randomCheck();
    }
}
~~~

### Biên dịch và chạy

~~~bash
javac -encoding UTF-8 BisectionRootDemo.java
java BisectionRootDemo
~~~

**Đầu ra kỳ vọng** của chương trình trên:

~~~text
sqrt2 root=1.414213562 stop=TOLERANCE iterations=39
cubic root=1.521379707 stop=TOLERANCE iterations=39
cos root=0.739085133 stop=TOLERANCE iterations=39
endpoint root=5.000000000 stop=ZERO_VALUE iterations=0
exactMid root=0.000000000 stop=ZERO_VALUE iterations=1
limited root=1.250000000 stop=ITERATION_LIMIT iterations=1
precision root=1.000000000 stop=PRECISION_LIMIT iterations=0
sameSign=rejected
tangent=rejected
nonFinite=rejected
stepFunction=notAValidIVTExample
isqrt(0)=0
isqrt(1)=1
isqrt(2)=1
isqrt(15)=3
isqrt(16)=4
isqrt(17)=4
isqrt(9223372036854775807)=3037000499
linearCheck=PASS (500 equations)
sqrtCheck=PASS (400 equations)
integerSqrtCheck=PASS (1000 values)
~~~

### Ý nghĩa từng nhóm kiểm thử

**sqrt2:** f(x)=x²−2 liên tục, hai đầu [1,2] trái dấu; 39 lượt đủ để có bracket nửa độ rộng ≤10^(−12). Ước lượng in ra 1.414213562.

**cubic:** phương trình `x³−x−2=0`, có một nghiệm trong [1,2], gần 1.5213797068. Dùng cùng dung sai và đạt sau 39 lượt. Kiểm thử này chứng minh thuật toán không chỉ dành cho căn bậc hai.

**cos:** nghiệm của `cos(x)=x` trong [0,1], gần 0.7390851332. Với hàm liên tục và đổi dấu, cùng mô hình chia đôi hoạt động dù f có hàm lượng giác.

**endpoint:** f(5)=0, trả ngay `ZERO_VALUE` với 0 vòng. Đây là **giá trị hàm bằng 0 theo phép đánh giá**, không phải kết luận chung về mọi lỗi làm tròn.

**exactMid:** f(x)=x³ trên [−1,1], trung điểm 0 được tính ra đúng 0, dừng sau một vòng.

**limited:** tối đa 1 vòng cho sqrt2 không đạt dung sai 10^(−15), nên kết quả 1.25 kèm `ITERATION_LIMIT`; không được hiểu nhầm số 1.25 là nghiệm gần đúng đạt yêu cầu.

**precision:** trên [1.0,Math.nextUp(1.0)], không có số double nào nằm giữa. Khi dung sai bằng 0, thuật toán trả `PRECISION_LIMIT`, không báo đã hoàn thành phép chia vô hạn.

**sameSign:** hai đầu của f(x)=x²+1 cùng dương, nên không thể tạo bracket theo IVT.

**tangent:** f(x)=(x−1)² thực sự có nghiệm, nhưng không đổi dấu trên [0,2]; việc từ chối ở đây là **không đủ giả thiết**, không chứng minh “vô nghiệm”.

**nonFinite:** hàm được thiết kế trả NaN tại trung điểm, chương trình chủ động ném ngoại lệ và từ chối kết quả không có ý nghĩa.

**stepFunction:** chỉ nhắc trường hợp gián đoạn có hai đầu trái dấu mà không có nghiệm; **không chạy bisection** trên ví dụ vi phạm IVT.

**isqrt:** tính phần nguyên của căn bậc hai bằng **binary search vị từ nguyên**, an toàn ngay cả với `Long.MAX_VALUE` nhờ điều kiện `mid<=n/mid`.

**randomCheck:** 500 hàm tuyến tính có nghiệm nguyên được xác định trước và hệ số góc dương/âm được đối chiếu với nghiệm đại số, 400 phương trình `x²−n=0` được đối chiếu với `Math.sqrt(n)` và bracket trả về, 1000 phép căn nguyên được kiểm tra bằng bất đẳng thức BigInteger chính xác. Dòng PASS chỉ in khi tất cả kiểm chứng thành công.

**Ghi rõ phạm vi:** test ngẫu nhiên không chứng minh tính liên tục của một `DoubleUnaryOperator` tùy ý. Chứng minh bằng IVT và bất biến bao nghiệm chỉ có hiệu lực khi người dùng bảo đảm giả thiết. `ZERO_VALUE`, `TOLERANCE`, `PRECISION_LIMIT`, `ITERATION_LIMIT` là trạng thái **tính toán**, không thay cho đặc tả toán học của f.

## 13. Chia đôi khoảng nghiệm thực khác binary search đáp án nguyên

Hai phương pháp cùng lấy trung điểm và bỏ một nửa không gian tìm kiếm, nhưng **bất biến toán học khác nhau**.

### 13.1. Bisection để giải f(x)=0

- Không gian: các số thực trong [a,b].
- Chứng nhận: f **liên tục**, f(a),f(b) đổi dấu.
- Bất biến: luôn còn **ít nhất một nghiệm f(x)=0** bên trong bracket.
- Dừng: nửa độ rộng, số lượt, giới hạn double hoặc gặp giá trị 0.
- Kết quả: xấp xỉ thực cùng bracket.

### 13.2. Binary search trên vị từ đơn điệu

Cho `P(x)` trên các số nguyên, dạng:

`false,false,…,false,true,true,…`

hoặc đảo lại. Ta tìm vị trí đầu tiên/ cuối cùng của miền đúng. Không cần một hàm số thực liên tục hoặc định lý giá trị trung gian; chỉ cần **P đơn điệu** theo thứ tự các giá trị nguyên xét.

Ví dụ **căn bậc hai nguyên**:

`isqrt(n)=max{x∈Z, x≥0, x²≤n}`.

Vị từ `P(x): x²≤n` đúng với các x nhỏ rồi sai với các x lớn. Code tìm **x đúng cuối cùng**. Thay vì nhân `x*x` có thể tràn long, với x>0 ta kiểm tra:

`x≤n/x`.

### 13.3. Đừng dùng sai phương pháp vì cả hai cùng gọi “nhị phân”

- Hàm f gián đoạn nhưng một predicate ngưỡng vẫn đơn điệu: **integer/real binary search predicate** có thể hợp lệ, nhưng **IVT root bisection** không được dùng chỉ dựa trên dấu f.
- Hàm liên tục có nhiều nghiệm: root bisection vẫn có thể tìm một nghiệm từ bracket trái dấu, nhưng predicate `f(x)<0` có thể **không đơn điệu** trên toàn miền, không thể dùng binary search toàn cục cho “ngưỡng đổi từ false sang true”.
- Hàm có nghiệm tiếp xúc bội chẵn: không bảo đảm hai đầu trái dấu, nhưng tối ưu hoặc phân tích đạo hàm/đặc điểm hàm có thể phát hiện nghiệm.
- Một bài toán “tìm x nhỏ nhất thỏa điều kiện” cần **chứng minh tính đơn điệu của điều kiện**, không phải chỉ nhìn biểu thức f(x)=0.

## 14. So với Newton và dây cung

| Phương pháp | Thông tin cần | Điểm mạnh | Điểm cần cảnh giác |
| --- | --- | --- | --- |
| **Chia đôi theo dấu** | Hàm liên tục, bracket trái dấu | Giữ khoảng bao nghiệm, không cần đạo hàm | Chậm hơn các phương pháp hội tụ nhanh; không tự tìm nghiệm bội chẵn nếu thiếu đổi dấu |
| **Newton–Raphson** | Đạo hàm hoặc xấp xỉ đạo hàm; điểm bắt đầu đủ tốt | Có thể hội tụ bậc hai gần nghiệm đơn | Có thể phân kỳ, vượt miền, đạo hàm bằng/ gần 0 |
| **Secant (dây cung)** | Hai xấp xỉ ban đầu | Không cần đạo hàm, thường nhanh | Không tự bảo toàn bracket trong phiên bản thông thường |
| **Brent** | Bracket hợp lệ và các giá trị hàm | Kết hợp độ tin cậy của bracket với nội suy nhanh | Cài đặt phức tạp hơn; vẫn cần xử lý miền/gián đoạn |

**Chia đôi là phương án mặc định tốt** khi độ ổn định và chứng minh error bound quan trọng, không cần nhiều giả thiết về đạo hàm. Khi hiệu năng cao là mục tiêu, một phương án **lai** có thể dùng Newton/secant khi an toàn và dùng bisection dự phòng để giữ bracket.

Không nên quảng cáo một thuật toán là luôn nhanh hơn: chi phí đánh giá f, độ dốc, điều kiện ban đầu và giới hạn chính xác đều ảnh hưởng tới lựa chọn.

## 15. Tìm khoảng ban đầu đúng cách

Không phải đề bài nào cũng cho sẵn [a,b]. Muốn tạo **bracket hợp lệ**, có thể:

1. Dựa vào hiểu biết về miền xác định và xu hướng dấu của f để chọn a,b.
2. Đánh giá f(a), f(b); kiểm tra hữu hạn.
3. Nếu một đầu bằng 0, đó là kết quả theo phép tính.
4. Nếu hai đầu trái dấu **và đã biết f liên tục trên đoạn**, bracket hợp lệ.
5. Nếu cùng dấu, thử các đoạn khác hoặc một cách tiếp cận khác; **không** kết luận “vô nghiệm”.

### Mở rộng khoảng khi có bảo đảm phù hợp

Với một hàm đơn điệu và miền xác định không bị giới hạn theo một hướng, có thể mở rộng b theo cấp số nhân (doubling/exponential search) cho tới khi vượt qua điểm đổi dấu, miễn kiểm tra giá trị hữu hạn và không vượt miền. Nhưng “cứ nhân đôi đầu mút cho đến khi đổi dấu” **không bảo đảm thành công trên mọi hàm** và có thể đi vào tiệm cận, tràn double hoặc bỏ sót nghiệm tiếp xúc.

### Quét lưới (scanning) cũng có giới hạn

Quét một số điểm chia lưới để tìm hai điểm trái dấu hữu ích khi muốn tìm **nhiều bracket**. Tuy nhiên:

- Một khoảng quét có thể chứa **hai nghiệm** khiến dấu hai đầu giống nhau.
- Nghiệm bội chẵn có thể không đổi dấu.
- Hàm gián đoạn vẫn có thể đổi dấu mà không có nghiệm.
- Lưới thô có thể bỏ sót nghiệm gần nhau.

Do đó quét lưới chỉ là công cụ **phát hiện ứng viên bracket**, không thay thế kiểm tra toán học.

## 16. Các lỗi thường gặp

1. Đổi dấu hai đầu nhưng **không kiểm tra tính liên tục** trên khoảng.
2. Cho rằng hai đầu trái dấu luôn đủ đối với mọi hàm, kể cả hàm bước hoặc phân thức có cực.
3. Cho rằng hai đầu cùng dấu chứng minh phương trình vô nghiệm.
4. Quên kiểm tra f(a)=0, f(b)=0 trước khi bắt buộc đổi dấu nghiêm ngặt.
5. Quên rằng nghiệm bội chẵn có thể **không làm đổi dấu**.
6. Giả định một nghiệm duy nhất mà chưa có điều kiện đơn điệu hoặc chứng minh khác.
7. Cho rằng phải có đơn điệu mới được dùng chia đôi để tìm **một** nghiệm.
8. Dùng sai quy tắc cập nhật nửa khoảng khi f giảm.
9. Đặt cố định “f(mid)<0 thì tăng a” mà không xét dấu f(a).
10. Không giữ invariant dấu khác nhau của hai đầu sau mỗi vòng.
11. Dùng `(a+b)/2` với a,b rất lớn, gây overflow không cần thiết.
12. Dùng `a+(b-a)/2` mà không biết b-a cũng có thể overflow nếu khoảng quá rộng; demo từ chối trường hợp đó.
13. Không kiểm tra `Double.isFinite` đối với đầu mút hoặc f(mid).
14. Dùng dấu của `f(a)*f(mid)` có thể underflow hoặc overflow thay vì so dấu.
15. Nhầm số chữ số in ra với sai số được bảo đảm.
16. Dừng chỉ vì `|f(mid)|<eps` khi không có điều kiện liên hệ residual với sai số vị trí.
17. Dùng ngưỡng tương đối thuần túy khi nghiệm bằng 0.
18. Đặt epsilon tuyệt đối nhỏ hơn độ phân giải double ở miền số đang xét nhưng vẫn yêu cầu thuật toán “phải đạt”.
19. Không phát hiện mid==a hoặc mid==b và lặp vô hạn.
20. Có maxIterations nhưng vẫn báo đạt tolerance khi hết lượt.
21. Dùng maxIterations=0 mà không xác định rõ chính sách.
22. Trả một giá trị hàm tính ra 0 do underflow và tuyên bố nghiệm đại số chính xác trong mọi trường hợp.
23. Tính độ rộng bracket nhưng quên chia 2 khi báo bound sai số trung điểm.
24. Không phân biệt bảo đảm tồn tại **ít nhất một** nghiệm gần estimate với bảo đảm nghiệm **duy nhất**.
25. Trả riêng estimate mà bỏ mất bracket và reason trong API cần độ tin cậy.
26. Quên rằng f có thể không xác định trong khoảng dù xác định tại hai đầu.
27. Đánh giá f tại điểm nằm ngoài domain mà không báo.
28. Giả định `Math.sqrt`/`Math.log` hợp lệ trên mọi real input.
29. Áp chia đôi nghiệm thực để tìm nghiệm nguyên mà không chứng minh predicate đơn điệu.
30. Dùng `mid*mid<=n` với integer long, gây tràn thay vì `mid<=n/mid`.
31. Cho rằng mọi binary search là cùng một thuật toán và cần cùng điều kiện IVT.
32. Dùng sai kiểu dấu làm cho binary search nguyên bỏ mất phần tử cuối cùng đúng.
33. Không kiểm thử trường hợp nghiệm đúng tại đầu, đúng trung điểm và không đổi dấu.
34. Chỉ test hàm tăng, không test hàm giảm.
35. Không thử maxIterations thấp để kiểm tra trạng thái chưa hội tụ.
36. Không thử hai double kề nhau để thấy giới hạn phân giải.
37. Không kiểm thử gần vùng giá trị khiến f trả Infinity/NaN.
38. Coi bộ test ngẫu nhiên là bằng chứng một hàm bất kỳ liên tục.
39. Bỏ qua khả năng nhiều nghiệm trong khoảng khi diễn giải kết quả.
40. Dùng bisection thay cho tìm cực trị mà không có phép biến đổi bài toán hợp lệ.

## 17. Bài tập có lời giải

**Bài 1.** Cho f(x)=x²−2 trên [1,2], có bracket hợp lệ không? **Đáp án:** có; hàm liên tục và f(1)<0, f(2)>0.

**Bài 2.** Trung điểm đầu tiên của [1,2]? **Đáp án:** 1.5.

**Bài 3.** Với f(x)=x²−2, f(1.5) bằng bao nhiêu? **Đáp án:** 0.25 >0.

**Bài 4.** Sau bước 1, giữ nửa nào? **Đáp án:** [1,1.5].

**Bài 5.** Ở m=1.25, f(m) bằng bao nhiêu? **Đáp án:** −0.4375, nên giữ [1.25,1.5].

**Bài 6.** Sau k bước chia đôi lý tưởng, độ rộng bracket? **Đáp án:** (b−a)/2^k.

**Bài 7.** Sai số vị trí tối đa khi trả trung điểm? **Đáp án:** một nửa độ rộng bracket, tức (b−a)/2^(k+1).

**Bài 8.** Với W=1 và ε=10^(−6), khoảng bao nhiêu bước đủ? **Đáp án:** 19 bước lý tưởng.

**Bài 9.** Hàm liên tục, f(a)f(b)<0 thì có ít nhất một nghiệm hay duy nhất? **Đáp án:** ít nhất một nghiệm; duy nhất cần thêm điều kiện.

**Bài 10.** Tính đơn điệu nghiêm ngặt có bắt buộc để bisection tìm một nghiệm không? **Đáp án:** không.

**Bài 11.** Tính đơn điệu nghiêm ngặt cùng bracket giúp kết luận thêm gì? **Đáp án:** nghiệm duy nhất.

**Bài 12.** f(x)=(x−1)² trên [0,2] có nghiệm không? **Đáp án:** có, x=1; nhưng không có đổi dấu hai đầu.

**Bài 13.** Bisection dựa trên đổi dấu có được kết luận “vô nghiệm” từ bài 12 không? **Đáp án:** không; chỉ kết luận không có bracket phù hợp.

**Bài 14.** Hàm bước f(x)=−1 nếu x<0, +1 nếu x≥0 trên [−1,1] có nghiệm không? **Đáp án:** không; trái dấu không đủ do gián đoạn.

**Bài 15.** f(x)=1/(x−1) trên [0,2] có hợp lệ để dùng IVT không? **Đáp án:** không; không xác định ở x=1.

**Bài 16.** Vì sao nên kiểm tra `Double.isFinite`? **Đáp án:** tránh dùng NaN/Infinity làm căn cứ chọn nửa bracket.

**Bài 17.** Tại sao không so dấu bằng `f(a)*f(m)>0` khi dùng double? **Đáp án:** tích có thể overflow/underflow.

**Bài 18.** Nếu f(a),f(m) cùng dấu, giữ đoạn nào? **Đáp án:** [m,b], vì f(m) và f(b) trái dấu.

**Bài 19.** Nếu f(a),f(m) trái dấu, giữ đoạn nào? **Đáp án:** [a,m].

**Bài 20.** Khi f(mid)==0 theo máy tính, trạng thái nào? **Đáp án:** ZERO_VALUE; nó mô tả phép đánh giá, không nhất thiết chứng minh nghiệm đại số trong mọi hoàn cảnh.

**Bài 21.** Khi đạt nửa độ rộng ≤ tolerance, trạng thái nào? **Đáp án:** TOLERANCE.

**Bài 22.** Khi mid bằng một đầu vì double không có giá trị trung gian, trạng thái nào? **Đáp án:** PRECISION_LIMIT.

**Bài 23.** Khi hết số vòng mà chưa đạt dung sai, trạng thái nào? **Đáp án:** ITERATION_LIMIT.

**Bài 24.** Vì sao residual nhỏ không bảo đảm sai số vị trí nhỏ? **Đáp án:** hàm có thể phẳng gần nghiệm; ví dụ (x−100)³.

**Bài 25.** Với epsilon tương đối nhưng nghiệm gần 0, nên làm gì? **Đáp án:** phối hợp dung sai tuyệt đối và định nghĩa rõ chuẩn sai số.

**Bài 26.** Cách lấy mid tránh overflow từ cộng a+b? **Đáp án:** `a+(b−a)/2` khi b−a hữu hạn.

**Bài 27.** Bài toán isqrt(n) có cần IVT không? **Đáp án:** không; dùng tính đơn điệu của điều kiện số nguyên `x²≤n`.

**Bài 28.** Làm sao tránh tràn khi kiểm tra `x²≤n` cho x>0? **Đáp án:** `x≤n/x`.

**Bài 29.** floorSqrt(Long.MAX_VALUE) bằng bao nhiêu? **Đáp án:** 3037000499.

**Bài 30.** Khi một hàm có ba nghiệm −1,0,1 trên [−2,2], bisection trái dấu tìm được tất cả nghiệm không? **Đáp án:** không; nó tìm một nghiệm, trong ví dụ mid=0 dừng ngay.

**Bài 31.** Tại sao scan lưới có thể bỏ sót một nghiệm bội chẵn? **Đáp án:** dấu không đổi khi đi qua nghiệm tiếp xúc.

**Bài 32.** Cho hàm giảm nghiêm ngặt với f(a)>0>f(b), bisection theo dấu còn đúng không? **Đáp án:** có; chỉ so dấu với f(a) hiện hành, không hardcode chiều tăng.

**Bài 33.** Nếu f(a)=0 thì cần chạy vòng lặp không? **Đáp án:** không; trả ngay a.

**Bài 34.** Khi một số double đứng sát nhau, yêu cầu epsilon=0 có bảo đảm dừng bằng zero-value không? **Đáp án:** không; có thể dừng PRECISION_LIMIT.

**Bài 35.** Nếu muốn tìm nghiệm nhưng không tìm được bracket đổi dấu, nên làm gì? **Đáp án:** phân tích đặc tính hàm, thử khoảng khác, tìm cực trị/nghiệm bội, hoặc dùng phương pháp thích hợp khác; không khẳng định vô nghiệm.

## 18. Checklist trước khi dùng chia đôi

1. Đã xác định đúng bài là **f(x)=0** hay tìm ngưỡng của một predicate?
2. f có **xác định và liên tục** trên toàn [a,b] không?
3. a,b là số hữu hạn, có a<b và chiều rộng b−a hợp lệ cho kiểu số không?
4. Đã tính f(a),f(b) và xác nhận chúng hữu hạn chưa?
5. Đã xử lý trường hợp f(a)==0 hoặc f(b)==0 chưa?
6. Nếu hai đầu không đổi dấu, đã ghi rõ đây là **thiếu bracket**, không phải chắc chắn vô nghiệm?
7. Có hiểu nghiệm bội chẵn không thể được phát hiện chỉ bằng đổi dấu không?
8. Có cần nghiệm **duy nhất** không; nếu cần, có chứng minh tính đơn điệu nghiêm ngặt hoặc điều kiện khác không?
9. Có cập nhật nửa khoảng theo **dấu so với đầu hiện tại**, dùng được cả hàm tăng lẫn giảm không?
10. Có giữ bất biến hai đầu trái dấu sau mỗi bước?
11. Có dùng trung điểm an toàn cho kiểu số đang chọn?
12. Có kiểm tra f(mid) không phải NaN/Infinity trước khi quyết định?
13. Có tránh so dấu bằng phép nhân f(a)*f(mid) có thể overflow/underflow?
14. Sai số mong muốn đo theo **x**, theo **f(x)** hay cả hai?
15. Nếu dùng nửa độ rộng để dừng, có báo được bound sai số của trung điểm không?
16. Dung sai tuyệt đối có phù hợp với thang độ lớn của nghiệm không?
17. Nếu dùng dung sai tương đối, có phương án khi nghiệm gần 0 không?
18. Có giới hạn số lượt và phân biệt “hết lượt” với “đạt tolerance” không?
19. Có phát hiện **mid trùng đầu mút** khi double hết độ phân giải không?
20. Kết quả API có gồm **estimate, bracket, iterations, stop reason** để người dùng đánh giá độ tin cậy không?
21. Khi f đánh giá gần đúng thành 0, có tránh tuyên bố “nghiệm toán học chính xác tuyệt đối” không?
22. Nếu có nhiều nghiệm, có hiểu bisection chỉ bảo đảm **một nghiệm trong bracket còn lại** không?
23. Đã test hàm tăng, hàm giảm, nghiệm ở đầu, nghiệm ở giữa, và không đổi dấu?
24. Đã test hàm không liên tục để biết rằng thuật toán phải được **áp dụng có điều kiện**?
25. Với bài integer binary search, đã chứng minh predicate đơn điệu và tránh overflow khi nhân/cộng chỉ số?
26. Có đối chiếu kết quả với nghiệm biết trước hoặc phép kiểm độc lập, và không nhầm test với chứng minh IVT?

**Ghi nhớ:** chia đôi khoảng tìm nghiệm thực chỉ đáng tin khi biết **f liên tục** và khoảng đầu có **hai giá trị trái dấu**, hoặc nghiệm được đánh giá ngay tại đầu mút. Mỗi lượt giữ **nửa khoảng còn chứa nghiệm**; trung điểm của bracket có sai số vị trí bị chặn bởi **nửa độ rộng**. Tính đơn điệu giúp bảo đảm **tính duy nhất**, không bắt buộc để tìm một nghiệm. Trong Java, cần kiểm tra NaN/Infinity, so dấu không dùng tích, giới hạn vòng, và dừng trung thực khi không thể chia thêm bằng `double`.
