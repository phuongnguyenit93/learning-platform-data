# Tìm đoạn con có tổng lớn nhất bằng chia để trị

**Bài toán đoạn con có tổng lớn nhất (maximum subarray sum)** yêu cầu tìm một đoạn **liên tiếp** của dãy sao cho tổng các phần tử trong đoạn là lớn nhất. Phương pháp **chia để trị (divide and conquer)** giải bài toán bằng cách chia dãy thành hai nửa, giải độc lập từng nửa, rồi xem xét đoạn tối ưu **đi qua ranh giới** giữa hai nửa. Bước kết hợp này làm rõ một ý tưởng quan trọng: nghiệm tối ưu toàn cục có thể không nằm trọn trong bất kỳ bài toán con nào.

Bài học sử dụng **đoạn không rỗng** cho mảng có ít nhất một phần tử, chỉ số Java bắt đầu từ 0, và định nghĩa thêm quy tắc xử lý kết quả khi nhiều đoạn có cùng tổng. Mục tiêu không chỉ là nhớ công thức độ phức tạp `O(n log n)` mà còn phải tự suy ra ba trường hợp, viết hàm tính tổng vượt ranh giới, chứng minh đúng, phân tích bộ nhớ và nhận biết khi nào nên thay bằng thuật toán tuyến tính như Kadane.

**Sau bài học, bạn có thể:** phát biểu đúng hợp đồng đầu vào/đầu ra; phân biệt đoạn liên tiếp với dãy con không liên tiếp; giải thích quan hệ truy hồi; xử lý số âm, mảng một phần tử và nhiều nghiệm tối ưu; cài đặt Java 17+ trả về tổng và hai đầu đoạn; tự đối chiếu với lời giải O(n) và liệt kê các lỗi phổ biến.

## 1. Phát biểu bài toán và quy ước kết quả

Cho mảng số nguyên `a[0..n−1]` với `n≥1`. Tìm hai chỉ số `L,R` thỏa `0≤L≤R<n` để tối đa hóa:

**`S(L,R) = a[L] + a[L+1] + ... + a[R]`.**

Đoạn này là **subarray**: mọi vị trí từ L tới R phải xuất hiện liên tiếp. Nó khác với **subsequence**: dãy con không liên tiếp được phép bỏ một số phần tử giữa đường.

Ví dụ:

`a = [-2, 1, -3, 4, -1, 2, 1, -5, 4]`.

Đoạn `[4,-1,2,1]` tại chỉ số **`[3,6]`** có tổng `4+(-1)+2+1=6`. Đây là tổng đoạn liên tiếp lớn nhất của toàn mảng. Nếu tùy ý chọn các phần tử dương không liên tiếp thì bài toán đã thay đổi và có thể cho đáp án khác.

### Trường hợp nhiều đoạn cùng tổng lớn nhất

Có thể có nhiều nghiệm. Để ví dụ và mã chạy có **một kết quả xác định**, đặt quy tắc:

1. Ưu tiên **tổng lớn nhất**.
2. Nếu cùng tổng, ưu tiên **L nhỏ nhất**.
3. Nếu vẫn cùng L, ưu tiên **R nhỏ nhất**.

Đây là thứ tự từ điển của cặp `(L,R)` sau khi đã tối đa hóa tổng. Ví dụ `a=[2,-2,2]` có các đoạn `[0,0]`, `[0,2]` và `[2,2]` cùng tổng 2; quy tắc chọn `[0,0]` vì cùng L=0 với `[0,2]` nhưng R nhỏ hơn, và L=0 nhỏ hơn 2.

Đề bài chỉ yêu cầu **tổng số học** thì không bắt buộc quy tắc phá hòa; nhưng một khi trả cả chỉ số hoặc kiểm thử kết quả chính xác, cần nêu rõ quy ước để các cách cài đặt nhất quán.

### Mảng chỉ gồm số âm và mảng rỗng

Với định nghĩa **đoạn không rỗng**, dãy `[-8,-3,-6,-2,-5,-4]` có tổng lớn nhất **-2** tại đoạn `[3,3]`. Trả 0 bằng cách “không chọn phần tử nào” sẽ **sai** với hợp đồng này.

Bài toán toán học ở đây chỉ định nghĩa trên `n≥1`. Để API Java an toàn và có thể thử mảng rỗng, ví dụ ở phần sau **chọn một hợp đồng riêng cho mảng rỗng**: trả bản ghi `(sum=0, left=-1, right=-1)` như dấu hiệu **không có đoạn hợp lệ**. Không diễn giải cặp `(-1,-1)` là một đoạn không rỗng có tổng 0. Những đề bài khác có thể yêu cầu ném lỗi hoặc cho phép đoạn rỗng; phải tuân theo hợp đồng của đề.

## 2. Ý tưởng chia để trị: ba khả năng bao phủ mọi nghiệm

Xét bài toán con tìm đoạn tốt nhất trong phần mảng `a[lo..hi]`, gồm cả hai đầu, với `lo≤hi`.

- **Cơ sở:** nếu `lo==hi`, chỉ có một đoạn không rỗng là `[lo,lo]`; kết quả có tổng `a[lo]`.
- **Chia:** chọn `mid = lo + (hi-lo)/2`, chia thành nửa trái `[lo,mid]` và nửa phải `[mid+1,hi]`. Khi `lo<hi`, cả hai nửa đều không rỗng.
- **Trị:** đệ quy tìm đoạn tốt nhất hoàn toàn nằm trong nửa trái và hoàn toàn nằm trong nửa phải.
- **Kết hợp:** tính đoạn tốt nhất **cắt qua ranh giới**, nghĩa là chứa phần tử ở `mid` **và** phần tử ở `mid+1`, rồi chọn kết quả tốt nhất trong ba ứng viên.

Tại sao chỉ có ba trường hợp? Với một đoạn liên tiếp `[L,R]` thuộc `[lo,hi]`, chỉ có:

1. `R≤mid`: nằm hoàn toàn bên trái.
2. `L≥mid+1`: nằm hoàn toàn bên phải.
3. `L≤mid<R`: đi qua cả hai nửa.

Ba khả năng loại trừ lẫn nhau và bao phủ tất cả các đoạn hợp lệ. Nếu không xét trường hợp thứ ba, thuật toán có thể bỏ lỡ nghiệm tối ưu.

Ví dụ trên dãy kinh điển:

~~~text
Chỉ số:    0   1   2   3   4 |  5   6   7   8
Giá trị:  -2   1  -3   4  -1 |  2   1  -5   4
                               ranh giới 4 | 5
~~~

Ở mức chia đầu tiên, nửa trái `[0,4]` có đoạn tốt nhất `[3,3]` tổng 4; nửa phải `[5,8]` có đoạn tốt nhất `[8,8]` tổng 4. Nhưng đoạn đi qua ranh giới `[3,6]` có tổng 6, **lớn hơn cả hai nghiệm con**. Vì vậy chỉ lấy `max(left,right)` là không đủ.

## 3. Tính đoạn tốt nhất đi qua ranh giới

Mọi đoạn đi qua ranh giới đều có dạng:

`[L,R] = [L,mid] ∪ [mid+1,R]`, với `lo≤L≤mid` và `mid+1≤R≤hi`.

Tổng đoạn bằng:

`sum(L,R) = sum(L,mid) + sum(mid+1,R)`.

Hai thành phần dùng những phần tử ở hai nửa **không chồng lấn**, nên tối ưu hóa chúng độc lập:

- Tìm **hậu tố (suffix) có tổng lớn nhất của nửa trái**, bắt buộc kết thúc tại `mid`.
- Tìm **tiền tố (prefix) có tổng lớn nhất của nửa phải**, bắt buộc bắt đầu tại `mid+1`.
- Ghép hai đoạn để được đoạn cắt ranh giới có tổng lớn nhất.

Không được thay “hậu tố trái” bằng “đoạn tốt nhất ở nửa trái”: đoạn tốt nhất ấy có thể kết thúc trước `mid` và không tiếp giáp ranh giới. Tương tự, phải dùng **tiền tố phải**, không phải đoạn tốt nhất bất kỳ trong nửa phải.

### 3.1. Quét hậu tố nửa trái

Bắt đầu `running=0`, đi từ `mid` ngược về `lo`. Sau khi thêm `a[i]`, `running` là tổng `a[i]+...+a[mid]`. Ghi lại tổng lớn nhất và chỉ số bắt đầu `i`.

Ví dụ với nửa trái `[-2,1,-3,4,-1]`, `mid=4`:

| Điểm bắt đầu i | Hậu tố `a[i..4]` | Tổng |
|---:|---|---:|
| 4 | `[-1]` | -1 |
| 3 | `[4,-1]` | 3 |
| 2 | `[-3,4,-1]` | 0 |
| 1 | `[1,-3,4,-1]` | 1 |
| 0 | `[-2,1,-3,4,-1]` | -1 |

Hậu tố tốt nhất là `[3,4]`, tổng 3. Khởi tạo giá trị tốt nhất bằng **`Long.MIN_VALUE`** thay vì 0 để kết quả luôn là một đoạn không rỗng, kể cả khi mọi phần tử âm.

### 3.2. Quét tiền tố nửa phải

Đặt lại `running=0`, đi từ `mid+1` tới `hi`. Sau khi thêm `a[j]`, `running` là tổng `a[mid+1]+...+a[j]`. Giữ tổng lớn nhất và chỉ số kết thúc `j`.

Với nửa phải `[2,1,-5,4]`, bắt đầu ở chỉ số 5:

| Điểm kết thúc j | Tiền tố `a[5..j]` | Tổng |
|---:|---|---:|
| 5 | `[2]` | 2 |
| 6 | `[2,1]` | 3 |
| 7 | `[2,1,-5]` | -2 |
| 8 | `[2,1,-5,4]` | 2 |

Tiền tố tốt nhất là `[5,6]`, tổng 3. Ghép hậu tố trái `[3,4]` và tiền tố phải `[5,6]` được đoạn `[3,6]` tổng **6**.

### 3.3. Quy tắc phá hòa ngay trong phép ghép

Nếu hai hậu tố trái có cùng tổng tốt nhất, hãy chọn hậu tố có **chỉ số bắt đầu nhỏ hơn**. Nếu hai tiền tố phải có cùng tổng tốt nhất, chọn tiền tố có **chỉ số kết thúc nhỏ hơn**. Khi đó, đoạn cắt ranh giới được chọn đúng quy tắc: tổng lớn nhất, rồi L nhỏ nhất, rồi R nhỏ nhất.

Điều này đặc biệt quan trọng với các số 0. Ví dụ nếu một hậu tố kết thúc tại mid có tổng 0 và mở rộng thêm các phần tử 0 về bên trái mà vẫn tổng 0, chọn L nhỏ hơn tương ứng đoạn bắt đầu sớm hơn.

Vì mỗi phía chỉ được quét một lần, bước kết hợp với đoạn cắt ranh giới dài `s=hi-lo+1` dùng **Θ(s)** thời gian và **O(1)** trạng thái tạm ngoài kết quả trả về.

## 4. Công thức thuật toán và quan hệ truy hồi

Gọi `Solve(lo,hi)` trả về một bản ghi gồm:

- `sum`: tổng lớn nhất của một đoạn không rỗng trong `[lo,hi]`.
- `left`, `right`: hai chỉ số của đoạn đạt tổng đó theo quy tắc phá hòa.

Khi `lo==hi`:

`Solve(lo,hi) = (a[lo],lo,lo)`.

Khi `lo<hi`, đặt `mid=lo+(hi-lo)/2`:

`leftAnswer = Solve(lo,mid)`

`rightAnswer = Solve(mid+1,hi)`

`crossAnswer = BestSuffix(lo,mid) + BestPrefix(mid+1,hi)`

`Solve(lo,hi) = Best(leftAnswer,rightAnswer,crossAnswer)`.

Trong đó `Best` so sánh tổng trước, sau đó so L và R; `crossAnswer` cần mang tổng và chỉ số của đoạn ghép, không chỉ một con số.

### Pseudocode độc lập với Java

~~~text
Solve(a, lo, hi):
    if lo == hi:
        return (a[lo], lo, hi)

    mid = lo + (hi - lo) / 2
    left  = Solve(a, lo, mid)
    right = Solve(a, mid+1, hi)

    bestLeftSum = -infinity
    running = 0
    for i from mid down to lo:
        running += a[i]
        if better suffix (larger sum, or same sum and smaller i):
            bestLeftSum = running
            leftStart = i

    bestRightSum = -infinity
    running = 0
    for j from mid+1 up to hi:
        running += a[j]
        if better prefix (larger sum, or same sum and smaller j):
            bestRightSum = running
            rightEnd = j

    cross = (bestLeftSum+bestRightSum, leftStart, rightEnd)
    return Best(left, right, cross)
~~~

Đây là **pseudocode**, không phải tệp Java. Mã Java có thể biên dịch ở phần 8.

## 5. Chứng minh tính đúng đắn của chia để trị

Có thể chứng minh bằng quy nạp theo độ dài `s=hi-lo+1` của bài toán con.

### Cơ sở: độ dài một

Nếu `s=1`, chỉ có duy nhất một đoạn không rỗng `[lo,lo]`. Hàm trả đúng tổng `a[lo]` và đúng tọa độ. Quy tắc phá hòa không tạo khác biệt vì chỉ có một ứng viên.

### Giả thiết quy nạp

Giả sử với mọi đoạn đầu vào ngắn hơn s, lời gọi `Solve` trả về một đoạn tối ưu và, nếu có hòa, chọn cặp chỉ số `(L,R)` nhỏ nhất theo quy ước.

### Bước quy nạp

Xét `[lo,hi]` độ dài s>1 và ranh giới `mid | mid+1`. Mọi đoạn tối ưu đều thuộc đúng một trong ba loại:

1. **Nằm trọn nửa trái:** theo giả thiết quy nạp, `leftAnswer` tối ưu trong loại này.
2. **Nằm trọn nửa phải:** `rightAnswer` tối ưu trong loại này.
3. **Cắt qua ranh giới:** mọi đoạn trong loại này gồm một hậu tố trái bắt buộc kết thúc tại mid và một tiền tố phải bắt buộc bắt đầu tại mid+1. Vì tổng là tổng của hai phần độc lập, chọn phần có tổng lớn nhất ở mỗi bên tạo ra tổng lớn nhất trong loại. Quy tắc phá hòa khi quét bảo đảm chọn đúng cặp tọa độ tốt nhất của loại này.

Lấy `Best` trên ba đại diện tối ưu của ba loại sẽ trả đoạn có tổng lớn nhất trong toàn bộ `[lo,hi]`. Nếu tổng hòa, quy tắc so L/R chọn cặp tọa độ nhỏ nhất trong toàn bộ các ứng viên. Như vậy hàm đúng cho đoạn dài s.

### Vì sao thuật toán dừng?

Mỗi lời gọi với `lo<hi` chia thành hai đoạn **ngắn hơn** và **không rỗng**. Cuối cùng các đoạn có độ dài 1, nên đệ quy dừng. Các vòng quét từ mid về lo và từ mid+1 tới hi đều hữu hạn; chỉ số đi đúng một bước mỗi lượt.

**Điều kiện cần:** các tổng được tính **chính xác** trong kiểu số đã chọn, không bị tràn khiến phép so sánh tổng sai. Với mảng Java `int[]` có độ dài thực tế và dùng `long` cho tổng, đây là một lựa chọn an toàn cho tổng các phần tử mảng có độ dài biểu diễn được bằng chỉ số `int`; nếu mở rộng sang `long[]` với giá trị tùy ý, phải chứng minh miền tổng hoặc dùng số nguyên tùy ý.

## 6. Phân tích thời gian: T(n) = 2T(n/2) + Θ(n)

Gọi `n` là số phần tử của đoạn đang xét. Khi n>1:

- Chia hai nửa và tính mid: O(1).
- Đệ quy trên hai nửa: `T(⌊n/2⌋) + T(⌈n/2⌉)`.
- Tìm đoạn tốt nhất cắt ranh giới: quét hai nửa, tổng cộng Θ(n) bước.
- So sánh ba kết quả: O(1).

Quan hệ truy hồi là:

**`T(n) = T(⌊n/2⌋) + T(⌈n/2⌉) + Θ(n)`**, với `T(1)=Θ(1)`.

Có thể viết gọn thành `T(n)=2T(n/2)+Θ(n)` khi bỏ qua làm tròn.

### Giải theo cây đệ quy

Ở mức gốc, tổng chi phí quét kết hợp xấp xỉ n. Ở mức tiếp theo có hai bài toán con tổng kích thước n, nên tổng quét vẫn xấp xỉ n. Mức sau nữa có bốn bài toán con tổng kích thước n, và cứ như vậy.

Số mức chia tới các đoạn một phần tử là **Θ(log n)** với n≥2. Mỗi mức thực hiện tổng cộng Θ(n) công việc kết hợp trong các nút có thể chia (ngoại trừ mức lá, tốn Θ(n) tổng cộng). Vì vậy:

**`T(n)=Θ(n log n)`** cho n≥2, hoặc viết `Θ(n log(n+1))` khi muốn biểu diễn cả n=1 mà không có log 1 bằng 0.

Theo định lý Master cho trường hợp hai nửa bằng nhau: `a=2`, `b=2`, `f(n)=Θ(n)`, nên thuộc trường hợp `f(n)=Θ(n^{log_b a})` và cho `Θ(n log n)`.

**Chi phí xấu nhất và tốt nhất của chính cài đặt này cùng bậc Θ(n log n)** khi n lớn: các lời gọi đệ quy và hai vòng quét vẫn chạy đầy đủ bất kể giá trị phần tử. Một đoạn tốt xuất hiện sớm không khiến mã tự dừng trước khi kiểm tra các trường hợp còn lại.

### Bộ nhớ phụ

Hàm **không tạo bản sao của hai nửa mảng**: chỉ truyền tham chiếu `a` và hai chỉ số. Độ sâu lời gọi là **O(log n)**, mỗi lời gọi giữ một số hằng biến, nên bộ nhớ phụ đang hoạt động cho lời gọi đệ quy là **O(log n)**.

Nếu Java trả bản ghi `Result` mới ở nhiều nút, tổng số đối tượng kết quả **được cấp phát trong cả quá trình** là O(n), dù số đối tượng kết quả cần giữ đồng thời cùng ngăn xếp chỉ tăng theo độ sâu đệ quy. Việc cấp phát, thu gom rác và kích thước record là chi phí thực tế đáng lưu ý; không được đồng nhất “O(log n) bộ nhớ sống do thuật toán” với “chỉ O(log n) đối tượng từng được cấp phát”.

Nếu một bản cài đặt dùng `Arrays.copyOfRange` để sao chép từng nửa ở các mức, chi phí bộ nhớ và thời gian thực tế sẽ khác; mã mẫu tránh sao chép.

## 7. Bảng truy vết trên ví dụ kinh điển

Dùng `a = [-2,1,-3,4,-1,2,1,-5,4]` với n=9, bài toán gốc `Solve(0,8)`.

| Thành phần của lời gọi gốc | Đoạn | Tổng | Lý do |
|---|---|---:|---|
| Nửa trái `[0,4]` | `[3,3]` chứa `[4]` | 4 | Tối ưu hoàn toàn ở nửa trái |
| Nửa phải `[5,8]` | `[8,8]` chứa `[4]` | 4 | Tối ưu hoàn toàn ở nửa phải |
| Hậu tố trái kết thúc tại 4 | `[3,4]` chứa `[4,-1]` | 3 | Không thể bỏ phần tử chỉ số 4 |
| Tiền tố phải bắt đầu tại 5 | `[5,6]` chứa `[2,1]` | 3 | Không thể bỏ phần tử chỉ số 5 |
| Kết hợp cắt ranh giới | `[3,6]` chứa `[4,-1,2,1]` | 6 | Tổng hai phần bắt buộc tiếp giáp |
| Kết quả cuối | **`[3,6]`** | **6** | Lớn hơn 4 và 4 |

Bước quét hậu tố trái và tiền tố phải mỗi bên **không bỏ qua ranh giới**. Nếu vô tình cho phép “hậu tố rỗng” có tổng 0, khi tất cả giá trị âm thuật toán có thể chọn một đoạn không hợp lệ hoặc làm sai định nghĩa trường hợp cắt qua cả hai nửa.

### Ví dụ toàn âm

Với `[-8,-3,-6,-2,-5,-4]`, không tồn tại đoạn có tổng dương hay bằng 0. Tất cả đoạn chứa nhiều phần tử đều có tổng không lớn hơn phần tử lớn nhất trong các số âm này. Đáp án là đoạn `[-2]` tại `[3,3]`, tổng **-2**. Đây là bài kiểm thử tối thiểu để phát hiện thuật toán khởi tạo tổng tốt nhất bằng 0 không đúng quy ước.

### Ví dụ nhiều nghiệm hòa

Với `[2,-2,2]`:

- `[0,0]` có tổng 2.
- `[0,2]` cũng có tổng 2.
- `[2,2]` cũng có tổng 2.

Nếu chỉ tối đa hóa tổng thì cả ba đều đúng. Với quy tắc phá hòa L rồi R, chọn **`[0,0]`**. Khi so sánh kết quả nửa trái, nửa phải và cắt ranh giới, không được chỉ dùng phép `>=` tùy tiện mà bỏ qua quy tắc tọa độ.

## 8. Chương trình Java 17+ hoàn chỉnh

Chương trình sau cung cấp:

- `maximumDivideAndConquer`: trả kết quả bằng phương pháp chia để trị và quét đoạn vượt ranh giới.
- `maximumKadane`: lời giải tham chiếu tuyến tính trên cùng hợp đồng và cùng quy tắc phá hòa.
- `Result(sum,left,right)`: bản ghi chứa tổng `long` và hai chỉ số bao gồm.
- `better`: hàm so sánh tập trung, dùng cho cả hai thuật toán để xử lý các trường hợp hòa nhất quán.
- `show`: in kết quả của phương pháp chia để trị, đồng thời kiểm tra kết quả bằng Kadane; nếu khác nhau, báo lỗi kiểm chứng.
- Mảng rỗng được báo bằng `sum=0, range=[-1,-1]` theo **hợp đồng API riêng**, không phải một đoạn không rỗng.

**Đầu vào hợp lệ:** `int[]` khác `null`. Tổng sử dụng kiểu `long`. Mã không thay đổi mảng ban đầu; các giới hạn RAM và chỉ số mảng Java vẫn áp dụng.

Lưu thành tệp **`MaximumSubarrayDivideConquerDemo.java`**:

~~~java
public final class MaximumSubarrayDivideConquerDemo {
    record Result(long sum, int left, int right) {}

    private static final Result EMPTY = new Result(0, -1, -1);

    // Ưu tiên tổng lớn, rồi chỉ số trái nhỏ, rồi chỉ số phải nhỏ.
    private static Result better(Result a, Result b) {
        if (a.sum() != b.sum()) {
            return a.sum() > b.sum() ? a : b;
        }
        if (a.left() != b.left()) {
            return a.left() < b.left() ? a : b;
        }
        return a.right() <= b.right() ? a : b;
    }

    static Result maximumDivideAndConquer(int[] values) {
        if (values == null) {
            throw new IllegalArgumentException("Null input");
        }
        if (values.length == 0) {
            return EMPTY;
        }
        return solve(values, 0, values.length - 1);
    }

    private static Result solve(int[] values, int lo, int hi) {
        if (lo == hi) {
            return new Result(values[lo], lo, lo);
        }

        int mid = lo + (hi - lo) / 2;

        Result left = solve(values, lo, mid);
        Result right = solve(values, mid + 1, hi);
        Result cross = crossing(values, lo, mid, hi);

        return better(better(left, right), cross);
    }

    private static Result crossing(
            int[] values, int lo, int mid, int hi) {

        long running = 0;
        long bestLeftSum = Long.MIN_VALUE;
        int leftStart = mid;

        // Hậu tố trái phải kết thúc tại mid.
        for (int i = mid; i >= lo; i--) {
            running += values[i];
            if (running > bestLeftSum
                    || (running == bestLeftSum && i < leftStart)) {
                bestLeftSum = running;
                leftStart = i;
            }
        }

        running = 0;
        long bestRightSum = Long.MIN_VALUE;
        int rightEnd = mid + 1;

        // Tiền tố phải phải bắt đầu tại mid+1.
        for (int j = mid + 1; j <= hi; j++) {
            running += values[j];
            if (running > bestRightSum
                    || (running == bestRightSum && j < rightEnd)) {
                bestRightSum = running;
                rightEnd = j;
            }
        }

        return new Result(
                bestLeftSum + bestRightSum, leftStart, rightEnd);
    }

    // Lời giải O(n) với cùng quy tắc phá hòa.
    static Result maximumKadane(int[] values) {
        if (values == null) {
            throw new IllegalArgumentException("Null input");
        }
        if (values.length == 0) {
            return EMPTY;
        }

        long endingSum = values[0];
        int endingStart = 0;
        Result best = new Result(endingSum, 0, 0);

        for (int i = 1; i < values.length; i++) {
            long extend = endingSum + values[i];
            long restart = values[i];

            if (restart > extend) {
                endingSum = restart;
                endingStart = i;
            } else {
                // Nếu hòa, giữ điểm bắt đầu cũ nhỏ hơn.
                endingSum = extend;
            }

            best = better(
                    best, new Result(endingSum, endingStart, i));
        }

        return best;
    }

    private static void show(String name, int[] values) {
        Result divide = maximumDivideAndConquer(values);
        Result linear = maximumKadane(values);

        if (!divide.equals(linear)) {
            throw new AssertionError("Mismatch for " + name);
        }

        System.out.printf(
                "%s: sum=%d, range=[%d,%d]%n",
                name, divide.sum(), divide.left(), divide.right());
    }

    public static void main(String[] args) {
        show("Classic", new int[] {
                -2, 1, -3, 4, -1, 2, 1, -5, 4
        });
        show("All negative", new int[] {
                -8, -3, -6, -2, -5, -4
        });
        show("All zero", new int[] {0, 0, 0});
        show("Ties", new int[] {2, -2, 2});
        show("Single", new int[] {7});
        show("All positive", new int[] {1, 2, 3});
        show("Empty", new int[] {});
    }
}
~~~

Biên dịch và chạy trong cùng thư mục, với JDK 17 hoặc mới hơn:

~~~bash
javac MaximumSubarrayDivideConquerDemo.java
java MaximumSubarrayDivideConquerDemo
~~~

**Kết quả đầu ra chính xác:**

~~~text
Classic: sum=6, range=[3,6]
All negative: sum=-2, range=[3,3]
All zero: sum=0, range=[0,0]
Ties: sum=2, range=[0,0]
Single: sum=7, range=[0,0]
All positive: sum=6, range=[0,2]
Empty: sum=0, range=[-1,-1]
~~~

### Đọc mã và kiểm tra tính đúng

- `mid` được tính bằng `lo + (hi-lo)/2` để tránh cộng trực tiếp `lo+hi` có thể tràn trong những thuật toán chỉ số tổng quát.
- `solve` luôn chia hai đoạn không rỗng khi `lo<hi`; không có vòng đệ quy vô hạn.
- `crossing` khởi tạo `bestLeftSum` và `bestRightSum` bằng `Long.MIN_VALUE`, vì hai phía **bắt buộc có ít nhất một phần tử**. Nếu dùng 0, bài toàn âm có thể bị sai.
- Khi hai tổng hậu tố trái bằng nhau, lấy chỉ số bắt đầu nhỏ hơn; khi hai tổng tiền tố phải bằng nhau, lấy chỉ số kết thúc nhỏ hơn.
- `better` áp dụng đúng quy tắc tổng rồi L rồi R, không phụ thuộc thứ tự truyền đối số trừ khi hai kết quả giống hệt theo các trường đó.
- `maximumKadane` khi so sánh “mở rộng” với “bắt đầu mới” dùng phép lớn hơn nghiêm ngặt `restart > extend`. Nếu bằng nhau, chọn mở rộng vì có chỉ số bắt đầu **sớm hơn**, đúng quy tắc phá hòa.
- `Result` là `record` trong Java 17, có `equals` so sánh các thành phần. `show` báo `AssertionError` nếu hai thuật toán cho kết quả khác nhau, nên ví dụ còn kiểm tra tính nhất quán trên bộ dữ liệu mẫu.
- Hai thuật toán đều dùng kiểu `long` cho tổng; phép cộng `int` vào `long` được thực hiện theo kiểu `long`. Đối với `int[]`, trị tuyệt đối của mọi phần tử không vượt `2³¹` và số phần tử biểu diễn được bằng chỉ số `int`, nên tổng độ lớn của một đoạn không vượt `(2³¹−1)·2³¹ < 2⁶²`; không vượt miền `long`.

**Lưu ý:** so sánh kết quả hai thuật toán trên bộ dữ liệu mẫu chỉ là **một mức kiểm thử**, không thay thế chứng minh bất biến. Hai thuật toán có thể cùng mắc lỗi nếu cùng sai về hợp đồng. Nên tiếp tục kiểm thử bằng lời giải liệt kê trên mảng nhỏ như phần sau.

## 9. Kiểm thử độc lập bằng vét cạn

Để xác nhận cả tổng lẫn chỉ số, với mảng ngắn có thể thử **mọi cặp chỉ số `L≤R`** và tính tổng theo vòng lặp tăng dần:

~~~java
// Pseudocode Java ở trong một phương thức nhận int[] a và trả Result.
Result best = null;
for (int l = 0; l < a.length; l++) {
    long running = 0;
    for (int r = l; r < a.length; r++) {
        running += a[r];
        Result candidate = new Result(running, l, r);
        best = best == null ? candidate : better(best, candidate);
    }
}
// Nếu mảng rỗng, dùng EMPTY theo hợp đồng riêng.
~~~

Đoạn trên **không phải một lớp Java độc lập**; nó chỉ minh họa cách làm kiểm thử tham chiếu. Có `n(n+1)/2` đoạn không rỗng trong mảng độ dài n. Với mỗi l, cập nhật `running` khi r tăng, nên liệt kê và tính tổng tất cả đoạn trong **Θ(n²)** thời gian, O(1) trạng thái cộng thêm (không kể các đối tượng kết quả tạo tạm).

Nếu tính lại tổng bằng một vòng lặp mới cho **từng** cặp `(L,R)` thì độ phức tạp sẽ thành O(n³) trong trường hợp xấu. Dùng tổng chạy `running` giảm chi phí của cách kiểm thử xuống Θ(n²).

### Bộ test quan trọng

| Dãy | Tổng lớn nhất | Đoạn theo quy tắc phá hòa |
|---|---:|---|
| `[7]` | 7 | `[0,0]` |
| `[-7]` | -7 | `[0,0]` |
| `[1,2,3]` | 6 | `[0,2]` |
| `[-8,-3,-6,-2,-5,-4]` | -2 | `[3,3]` |
| `[0,0,0]` | 0 | `[0,0]` |
| `[2,-2,2]` | 2 | `[0,0]` |
| `[-1,0,-1]` | 0 | `[1,1]` |
| `[1,-1,1,-1,1]` | 1 | `[0,0]` |
| `[0,1,0]` | 1 | `[0,1]` |
| `[-2,1,-3,4,-1,2,1,-5,4]` | 6 | `[3,6]` |

Thử các trường hợp này giúp phát hiện lỗi: không xử lý đoạn một phần tử, trả 0 cho toàn âm, sai dấu chỉ số, phá hòa không nhất quán, quên đoạn cắt ranh giới hoặc làm phép cộng với kiểu `int`.

**Đối chiếu ngẫu nhiên:** sinh mảng nhỏ độ dài 0..12 với các giá trị -5..5; kết quả đệ quy và Kadane phải khớp với vét cạn về cả `sum`, `left` và `right`, sau khi áp dụng cùng hợp đồng mảng rỗng. Không cần sinh mảng lớn để kiểm chứng trường hợp biên, nhưng cần mảng lớn khi đo chi phí hiệu năng.

## 10. Phương pháp tuyến tính Kadane và sự đánh đổi

**Kadane** sử dụng quy hoạch động theo vị trí cuối của đoạn. Đặt:

`ending[i]` = tổng lớn nhất của một đoạn không rỗng **kết thúc đúng tại i**.

Với `i≥1`:

**`ending[i] = max(a[i], ending[i−1] + a[i])`**,

và `ending[0]=a[0]`. Ở mỗi chỉ số, đoạn tốt nhất kết thúc tại i chỉ có hai dạng: bắt đầu tại i, hoặc nối thêm `a[i]` vào một đoạn tốt nhất kết thúc tại i−1. Đáp án toàn cục là tổng lớn nhất trong các `ending[i]`.

Mỗi phần tử được xử lý một lần, nên thời gian **Θ(n)**, bộ nhớ phụ **Θ(1)** nếu chỉ giữ trạng thái cần thiết. Để trả tọa độ, theo dõi điểm bắt đầu của đoạn tốt nhất kết thúc tại i và cập nhật đáp án toàn cục khi cần. Nếu đề yêu cầu phá hòa, phải giữ quy tắc nhất quán; mã mẫu đã làm điều đó.

### So sánh giữa hai cách

| Tiêu chí | Chia để trị với quét đoạn cắt | Kadane |
|---|---|---|
| Ý tưởng | Giải tối ưu trái, tối ưu phải, tối ưu cắt ranh giới | Tối ưu của đoạn kết thúc tại từng vị trí |
| Thời gian | **Θ(n log n)** | **Θ(n)** |
| Bộ nhớ phụ hoạt động | **O(log n)** cho đệ quy; không sao chép mảng | **O(1)** trạng thái |
| Có thể trả chỉ số? | Có; mang tổng và hai đầu đoạn qua đệ quy | Có; theo dõi đầu đoạn đang chạy |
| Xử lý toàn âm | Đúng nếu bắt buộc hai phần cắt ranh giới không rỗng và base đúng | Đúng nếu khởi tạo bằng phần tử đầu, không mặc định tổng tốt nhất là 0 |
| Điểm học thuật | Chia–trị–kết hợp, chứng minh trường hợp cắt ranh giới, truy hồi | Quy hoạch động, tối ưu một lượt, trạng thái |
| Tình huống thực dụng | Cần minh họa chia để trị hoặc mở rộng sang cấu trúc phân đoạn | Tìm max subarray một lần trên dãy tĩnh, thường thích hợp hơn |

**Không nên tuyên bố O(n log n) là tốt hơn O(n)** vì cùng là thuật toán chuẩn. Nếu chỉ cần tìm đoạn có tổng lớn nhất một lần trên dãy và dữ liệu có thể duyệt tuần tự, Kadane đạt cận tốt hơn. Giá trị chính của lời giải chia để trị là phương pháp thiết kế và khả năng mở rộng sang những bài có phép **gộp thông tin hai nửa**.

## 11. Mở rộng: gộp bốn thông tin để đạt O(n)

Có một biến thể chia để trị khác **không cần quét toàn bộ đoạn cắt ranh giới ở mỗi mức**. Thay vào đó, mỗi nút trả bốn thông tin:

1. **Total:** tổng của toàn bộ đoạn.
2. **Prefix:** tổng lớn nhất của đoạn không rỗng bắt đầu tại đầu đoạn.
3. **Suffix:** tổng lớn nhất của đoạn không rỗng kết thúc tại cuối đoạn.
4. **Best:** tổng lớn nhất của đoạn không rỗng bất kỳ trong đoạn.

Với nửa trái A và nửa phải B:

- `Total(A+B) = Total(A) + Total(B)`.
- `Prefix(A+B) = max(Prefix(A), Total(A)+Prefix(B))`.
- `Suffix(A+B) = max(Suffix(B), Total(B)+Suffix(A))`.
- `Best(A+B) = max(Best(A), Best(B), Suffix(A)+Prefix(B))`.

Các phép gộp trên cần **O(1)** phép toán số học mỗi nút khi đã có bốn thông tin của hai con. Vì vậy quan hệ truy hồi là:

`T(n)=2T(n/2)+O(1)=Θ(n)`.

Đây là **một thuật toán chia để trị khác**, không phải chi phí của lời giải quét đoạn cắt ranh giới đã triển khai ở trên. Để trả **chỉ số** và thực hiện phá hòa theo L/R, mỗi trường Prefix/Suffix/Best phải mang thêm tọa độ phù hợp và quy tắc gộp nhất quán. Không chỉ đổi công thức số học rồi mặc nhiên cho rằng chỉ số vẫn đúng.

Cách gộp bốn thông tin còn là nền tảng của **segment tree cho maximum subarray**: mỗi nút lưu tổng, tiền tố tốt nhất, hậu tố tốt nhất và đoạn tốt nhất; khi cập nhật một phần tử, chỉ phải cập nhật các nút trên đường từ lá tới gốc, thường O(log n) bước. Nếu không có cập nhật và chỉ cần kết quả một lần, Kadane vẫn đơn giản hơn.

## 12. Mở rộng: quan hệ với tổng tiền tố

Đặt `P[0]=0` và `P[i+1]=P[i]+a[i]`. Tổng đoạn đóng `[L,R]` có thể viết:

**`S(L,R)=P[R+1]-P[L]`**.

Với mỗi vị trí kết thúc `R`, ta cần chọn `L≤R` sao cho `P[L]` nhỏ nhất. Vì vậy có thể duyệt từ trái qua phải, lưu **giá trị tiền tố nhỏ nhất đã gặp trước vị trí hiện tại**, lấy hiệu với `P[R+1]` để có tổng lớn nhất kết thúc tại R. Sau đó chọn tốt nhất qua mọi R.

Cách này cũng đạt **Θ(n)** thời gian và có thể dùng O(1) trạng thái nếu không lưu cả mảng P. Nếu cần phá hòa bằng L nhỏ nhất, khi có nhiều vị trí tiền tố nhỏ nhất bằng nhau nên giữ vị trí xuất hiện sớm nhất. Sau đó xét R theo thứ tự tăng giúp xử lý tie của R đúng quy tắc.

**Liên hệ tư duy:** Kadane tối ưu một đoạn theo **điểm kết thúc**; cách tổng tiền tố tối ưu bằng cách chọn **điểm bắt đầu có tiền tố nhỏ nhất**; chia để trị tối ưu bằng cách phân loại nghiệm theo **ranh giới chia**. Ba góc nhìn giải cùng bài toán nhưng có đặc tính triển khai và độ phức tạp khác nhau.

## 13. Sai lầm thường gặp và cách tránh

1. **Trả 0 cho mảng toàn âm dù đề yêu cầu đoạn không rỗng.** Phải lấy tổng lớn nhất trong những đoạn có ít nhất một phần tử; đáp án có thể âm.
2. **Quên trường hợp cắt ranh giới.** Chỉ xét đáp án bên trái và bên phải sẽ bỏ lỡ các đoạn như `[4,-1,2,1]`.
3. **Gộp hậu tố/trước tố sai.** Đoạn cắt ranh giới phải sử dụng hậu tố **kết thúc tại mid** và tiền tố **bắt đầu tại mid+1**. Đoạn tốt nhất nội bộ từng nửa không nhất thiết nối được với nhau.
4. **Khởi tạo tổng hậu tố/tiền tố tốt nhất bằng 0.** Điều đó cho phép bên trái hoặc bên phải rỗng, vi phạm định nghĩa đoạn cắt qua cả hai nửa.
5. **Tạo hai nửa bằng sao chép mảng ở mọi mức.** Tăng chi phí cấp phát; chỉ cần truyền `lo,hi` và mảng gốc.
6. **Lỗi chỉ số ranh giới:** nửa trái dùng `[lo,mid]`, nửa phải dùng `[mid+1,hi]`, không có phần tử bị bỏ hoặc đếm hai lần.
7. **Trộn chỉ số 0-based với 1-based:** vị trí đầu trong Java là 0. Nếu đề cần 1-based, chuyển chỉ số sau khi tìm xong.
8. **Sai quy tắc hòa:** nếu trả chỉ số, hai cài đặt có cùng tổng nhưng chọn cặp khác không nhất thiết “sai” khi đề không quy định tie; nhưng sẽ không khớp bài này vì đã đặt quy tắc L rồi R.
9. **Dùng int cho tổng lớn:** một `int` có thể đủ cho mỗi phần tử nhưng tổng nhiều phần tử có thể vượt `Integer.MAX_VALUE`. Dùng `long` cho tổng.
10. **Quên n=0 khi API cho phép rỗng:** không gọi `solve(a,0,-1)`; phải xử lý rỗng theo một hợp đồng riêng trước khi đệ quy.
11. **Nói lời giải chia để trị chuẩn là O(n) chỉ vì chia đôi n:** bước tìm đoạn cắt ranh giới quét Θ(n) tại mỗi mức, nên tổng Θ(n log n).
12. **Nói thuật toán luôn dùng O(n) bộ nhớ phụ:** nếu chỉ truyền chỉ số, bộ nhớ ngăn xếp hoạt động O(log n); nhưng bản cài đặt tạo O(n) đối tượng `Result` qua toàn bộ quá trình.
13. **Dùng Kadane dạng cho phép đoạn rỗng trong khi so sánh với chia để trị không rỗng:** hai thuật toán sẽ bất đồng trên dãy toàn âm. Phải đồng bộ hợp đồng.
14. **So sánh kết quả Java `record` không đúng kiểu:** với record, `equals` so sánh các thành phần theo định nghĩa sinh tự động. Với lớp tự định nghĩa không override `equals`, không được mặc nhiên dựa vào `Object.equals` để kiểm tra giá trị các trường.

## 14. Checklist trước khi hoàn thành bài toán

- Đề yêu cầu **đoạn liên tiếp** hay tập con không liên tiếp?
- Đoạn có bắt buộc **không rỗng** không? Nếu mảng rỗng, API báo bằng cách nào?
- Có cần trả **chỉ số** hay chỉ tổng? Nếu nhiều nghiệm cùng tổng, quy tắc phá hòa là gì?
- Với mỗi lời gọi `Solve(lo,hi)`, cơ sở `lo==hi` đã trả đúng phần tử đơn lẻ chưa?
- Khi `lo<hi`, hai nửa có bao phủ toàn bộ và không trùng nhau không?
- Bước kết hợp có lấy **hậu tố trái buộc chạm mid** và **tiền tố phải buộc chạm mid+1** không?
- Các tổng đều tính bằng kiểu `long` và không có tràn số trong phạm vi dữ liệu hợp lệ không?
- Hàm chọn đáp án có so **tổng, L, R** theo đúng thứ tự và dùng thống nhất trong mọi nhánh không?
- Đã chứng minh ba loại đoạn bao phủ mọi nghiệm và thuật toán luôn dừng chưa?
- Đã tính chi phí quét Θ(n) ở mỗi mức, dẫn tới Θ(n log n) và bộ nhớ đệ quy O(log n) chưa?
- Đã thử mảng một phần tử, toàn âm, toàn 0, toàn dương, nhiều nghiệm hòa, và đoạn tốt nhất cắt ranh giới chưa?
- Khi chỉ cần đáp án trên mảng tĩnh một lần, có nên dùng Kadane Θ(n) thay vì chia để trị Θ(n log n) không?

**Ghi nhớ:** với bài toán đoạn con liên tiếp có tổng lớn nhất, chia để trị thành công vì mọi đoạn tối ưu hoặc nằm trọn bên trái, nằm trọn bên phải, hoặc **bắt buộc đi qua ranh giới**. Đoạn cắt ranh giới được tạo từ **hậu tố tốt nhất của nửa trái** và **tiền tố tốt nhất của nửa phải**; việc quét này ở mỗi mức khiến lời giải cơ bản tốn **Θ(n log n)**, còn Kadane hoặc phép gộp bốn thông tin có thể đạt **Θ(n)**.