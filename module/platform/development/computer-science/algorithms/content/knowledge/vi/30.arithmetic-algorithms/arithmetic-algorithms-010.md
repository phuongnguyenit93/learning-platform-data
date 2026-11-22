# Phân tích thừa số bằng chia thử

**Phân tích thừa số nguyên tố (prime factorization)** là biểu diễn một số nguyên có trị tuyệt đối lớn hơn 1 thành tích các **số nguyên tố** kèm **số mũ**. Cách trực quan nhất để tìm các thừa số ấy là **chia thử (trial division)**: thử các ước khả dĩ từ nhỏ đến lớn, cứ gặp ước nào chia hết thì chia liên tiếp để rút hết số mũ, sau đó tiếp tục cho tới khi phần còn lại không thể có ước nhỏ hơn căn bậc hai của nó.

Bài học thuộc nhóm **Thuật toán số học** của Computer Science Algorithms. Ta sẽ làm rõ định nghĩa và trường hợp biên, đi từ phép chia thử ngây thơ tới cách tối ưu bằng **căn bậc hai**, giải thích tại sao chỉ thử 2 rồi các số lẻ là đủ, chứng minh tính đúng và độ phức tạp, xử lý **số âm, 0, 1, số nguyên tố lớn, lũy thừa và các giới hạn của kiểu `long` trong Java**, tính số lượng ước từ kết quả phân tích, và triển khai một chương trình **Java 17+ hoàn chỉnh** có kết quả mẫu và kiểm thử độc lập.

## 1. Định nghĩa, ký hiệu và định lý cơ bản

**Số nguyên tố** là số nguyên `p>1` chỉ có hai ước dương: 1 và chính nó. Ví dụ 2, 3, 5, 7, 11, 13 là nguyên tố; 1 **không** phải số nguyên tố; 4=2×2 và 9=3×3 là hợp số.

Với số nguyên dương `n>1`, **định lý cơ bản của số học** khẳng định tồn tại cách viết:

`n = p₁^e₁ · p₂^e₂ · … · pₖ^eₖ`,

trong đó:

- `p₁<p₂<…<pₖ` là các số nguyên tố **phân biệt**.
- `eᵢ≥1` là số mũ nguyên.
- Bộ cặp `(pᵢ,eᵢ)` là **duy nhất** nếu bỏ qua thứ tự các thừa số.

**Ví dụ:**

`360 = 2³ · 3² · 5`.

Ta có ba **thừa số nguyên tố phân biệt** 2, 3, 5; nhưng số thừa số nguyên tố **tính cả lặp** là `3+2+1=6`.

Các khái niệm không nên đánh đồng:

| Yêu cầu | Với n=360 | Cách biểu diễn |
| --- | --- | --- |
| Tập số nguyên tố phân biệt | 2, 3, 5 | `[2,3,5]` |
| Phân tích kèm số mũ | 2³·3²·5 | `[(2,3),(3,2),(5,1)]` |
| Danh sách có lặp | 2,2,2,3,3,5 | `[2,2,2,3,3,5]` |
| Ước nguyên tố nhỏ nhất | 2 | Một số |
| Ước nguyên tố lớn nhất | 5 | Một số |
| Tổng số ước dương | 24 | Tính từ các số mũ |

Chương trình Java sẽ lưu dạng **cặp số nguyên tố/số mũ**, được sắp theo thứ tự nguyên tố tăng dần. Đây là cách gọn hơn danh sách lặp và thuận tiện cho nhiều bài toán số học tiếp theo.

### Với số nguyên âm

Ta có thể viết:

`n = (−1) · p₁^e₁ · … · pₖ^eₖ`

khi `n<−1`. Dấu `−1` là **đơn vị (unit)**, **không** phải nguyên tố; nó chỉ ghi nhận dấu âm. Ví dụ:

`−360 = −1 · 2³ · 3² · 5`.

Chương trình biểu diễn dấu dưới dạng cặp `(-1,1)` đứng đầu, sau đó là các thừa số nguyên tố **dương** tăng dần. Các công thức đếm **ước dương của |n|** sẽ **bỏ qua** cặp −1.

## 2. Những trường hợp đặc biệt phải chốt trước

- **`n=0`:** 0 chia hết cho mọi số nguyên dương khác 0, nên **không có một biểu diễn hữu hạn thành tích các số nguyên tố theo định lý trên**. Chương trình chủ động **từ chối 0** bằng `IllegalArgumentException`. Không trả danh sách rỗng rồi ngầm coi 0=1.
- **`n=1`:** tích rỗng của các số nguyên tố bằng 1. Chương trình trả **danh sách cặp rỗng** và khi in hiển thị `1`. Số ước dương của 1 là 1.
- **`n=−1`:** trả một cặp `(−1,1)`, tức chỉ có dấu, không có thừa số nguyên tố dương. Số ước dương của |−1| cũng là 1.
- **`n=2`:** chỉ có một thừa số nguyên tố 2 với số mũ 1.
- **`n=p` là nguyên tố:** phân tích là `p¹`; không được tự thêm 1 như một thừa số nguyên tố.
- **`n=p^e` là lũy thừa nguyên tố:** chỉ có một cặp `(p,e)`, ví dụ `49=7²`.
- **Số âm ngoài −1:** tách −1 trước khi xử lý trị tuyệt đối, nhưng phải cảnh giác giá trị nhỏ nhất của kiểu số nguyên có dấu.

**Quy ước đầu ra:** với `n>0`, tích của các số được in phải đúng bằng n; với `n<0`, tích kể cả −1 phải đúng bằng n. Mọi thừa số khác −1 đều phải thực sự là **số nguyên tố**.

## 3. Từ phương pháp ngây thơ tới chia thử có dừng sớm

Phương pháp chia thử cơ bản nhất là thử các số từ 2 tới n:

~~~text
FACTORS_SLOW(n), n >= 2:
    factorization = []
    d = 2
    while d <= n:
        exponent = 0
        while n % d == 0:
            n = n / d
            exponent = exponent + 1
        if exponent > 0:
            append (d, exponent)
        d = d + 1
    return factorization
~~~

Trong đoạn giả mã trên, `n` là **phần còn lại đang được phân tích**, thay đổi sau mỗi phép chia. Cách làm đúng nhưng có thể rất chậm khi n là **số nguyên tố**: nếu n không có ước nào từ 2 tới n−1, vòng ngoài phải đi qua gần n giá trị. Đây không phải cách cài đặt nên dùng cho dữ liệu lớn.

### Vì sao có thể dừng ở căn bậc hai?

Nếu một số nguyên dương `r>1` là hợp số, tồn tại `r=a·b` với `1<a≤b<r`. Khi ấy:

`a² ≤ a·b=r`, nên `a≤√r`.

Vì thế **mọi hợp số r đều có ít nhất một ước không tầm thường không vượt √r**. Nếu đã kiểm tra tất cả ước khả dĩ tới căn bậc hai mà không tìm được ước nào, **r là số nguyên tố**.

Khi phân tích, `r` liên tục giảm sau khi chia ra các thừa số nhỏ. Ta có thể dùng **căn bậc hai của chính phần còn lại hiện tại**, thay vì luôn dùng căn bậc hai của n ban đầu.

Giả mã cải tiến:

~~~text
FACTORS_SQRT(n), n >= 2:
    result = []
    d = 2

    while d <= n / d:
        exponent = 0
        while n % d == 0:
            n = n / d
            exponent += 1

        if exponent > 0:
            append (d, exponent)
        d += 1

    if n > 1:
        append (n, 1)
    return result
~~~

**Lưu ý:** với `n>0` và `d>0`, điều kiện `d <= n / d` dùng phép chia nguyên, tương đương `d² <= n` nhưng **không cần nhân d·d**.

Ví dụ khi n ban đầu là 97 (nguyên tố), chỉ cần thử d=2,3,…,9. Khi d=10, `10>97/10=9`, dừng và ghi lại 97. Không cần thử mọi d tới 97.

## 4. Tối ưu thực hành: lấy 2 trước, sau đó chỉ thử số lẻ

Mọi số chẵn lớn hơn 2 đều có ước nguyên tố 2. Vì vậy ta có thể:

1. Chia hết các thừa số 2.
2. Phần còn lại giờ là **số lẻ**.
3. Chỉ thử các ước lẻ `3,5,7,9,11,…` cho tới khi `d>r/d`.
4. Nếu `r>1`, đưa r vào kết quả như một nguyên tố cuối.

Giả mã được dùng trong Java:

~~~text
FACTOR_BY_TRIAL_DIVISION(value):
    if value == 0: reject

    result = []
    if value < 0:
        append (-1, 1)
        take positive magnitude safely

    if magnitude == 1: return result

    e = 0
    while magnitude % 2 == 0:
        magnitude /= 2
        e += 1
    if e > 0: append (2, e)

    d = 3
    while d <= magnitude / d:
        e = 0
        while magnitude % d == 0:
            magnitude /= d
            e += 1
        if e > 0: append (d, e)
        d += 2

    if magnitude > 1:
        append (magnitude, 1)

    return result
~~~

### Tại sao chỉ thử số lẻ sau 2 là đủ?

Sau khi đã chia hết các thừa số 2, phần còn lại r **không chia hết cho 2**. Vì vậy không có số chẵn nào có thể là ước của r. Nếu r còn là hợp số thì nó có một ước nguyên tố **lẻ** không vượt √r, và vòng `d=3,5,7,…` sẽ gặp ước đó.

Chương trình vẫn thử một số **ước lẻ hợp số** như 9 hoặc 15. Đây là sự đánh đổi để mã đơn giản. Những số ấy **không thể được ghi thành thừa số nguyên tố**: nếu một hợp số d chia r, một ước nguyên tố nhỏ hơn của d cũng phải chia r, trái với việc đã rút hết các ước nhỏ hơn trước đó. Do vậy mọi d được thêm vào danh sách thực sự là nguyên tố.

### Chia hết theo số mũ

Phải dùng vòng **while**, không chỉ một lần `if`:

~~~text
n = 360
chia 2: 360 -> 180 -> 90 -> 45   (2 xuất hiện 3 lần)
chia 3: 45 -> 15 -> 5             (3 xuất hiện 2 lần)
phần còn lại 5 là nguyên tố       (5 xuất hiện 1 lần)
~~~

Kết quả:

`360 = 2³ · 3² · 5`.

Nếu chỉ chia mỗi ước một lần, thuật toán sẽ sai trên `8=2³`, `36=2²·3²` và mọi số có thừa số lặp.

## 5. Chứng minh tính đúng bằng bất biến

Đặt N là trị tuyệt đối ban đầu (N≥2) và r là phần **chưa phân tích**. Gọi `F` là danh sách các cặp số nguyên tố đã ghi. Bất biến quan trọng:

`N = (Π_{(p,e)∈F} p^e) · r`,

với `r≥1`.

**Khởi tạo:** F rỗng, r=N, đẳng thức đúng.

**Sau khi chia một ước d:** nếu r chia hết cho d, thay r bằng r/d và tăng số mũ của d lên 1. Tích bên phải không đổi. Khi chia hết d, r không còn chia hết cho d và danh sách ghi chính xác số mũ tối đa của d trong r trước đó.

**Tính nguyên tố và thứ tự:** các ước được xét tăng dần; sau khi rút hết 2, chỉ cần xét số lẻ. Nếu d là hợp số mà chia phần còn lại, một nguyên tố q<d chia d cũng phải chia r; nhưng mọi nguyên tố nhỏ hơn d đã được xét và rút hết, mâu thuẫn. Do đó mọi ước d được ghi nhận là nguyên tố. Các d tăng dần nên danh sách thừa số nguyên tố cũng tăng dần.

**Điều kiện dừng:** khi `d>r/d`, tức `d²>r`, nếu r>1 mà r là hợp số thì r phải có một ước nguyên tố q≤√r<d. Ước q ấy đã được xét và loại hết trước đó, mâu thuẫn. Vì thế **r>1 lúc kết thúc là nguyên tố**. Ghi `(r,1)` sẽ hoàn thành phân tích, vẫn giữ bất biến.

**Kết luận:** kết quả chỉ chứa các nguyên tố (ngoại trừ −1 ghi dấu âm), tất cả số mũ chính xác và tích của chúng tái tạo n. Theo tính duy nhất của phân tích nguyên tố, kết quả là lời giải đúng.

### Vì sao r có thể giảm mạnh và giúp dừng sớm?

Với N=360, sau khi rút hết 2 và 3, r chỉ còn 5. Ở đầu vòng d=3, phép thử `3≤5/3` đã sai, nên ta không thử 5 trong vòng nữa; 5 được xác nhận nguyên tố ở bước cuối.

Nếu N là một số nguyên tố lớn, r không giảm chút nào và vòng thử tiếp tục tới √N — đây mới là tình huống xấu với trial division.

## 6. Điều kiện d² ≤ r có thể tràn số

Đoạn mã thường thấy:

~~~java
for (long d = 3; d * d <= remaining; d += 2) {
    // ...
}
~~~

có thể sai khi `d*d` vượt giới hạn của `long`. Trong Java, tràn số nguyên không tự ném ngoại lệ; kết quả có thể âm hoặc không còn đại diện cho giá trị toán học. Một vòng lặp dựa vào tích bị tràn có nguy cơ chạy sai/không dừng đúng.

Khi `remaining>0`, viết:

~~~java
for (long d = 3; d <= remaining / d; d += 2) {
    // ...
}
~~~

Cách này tránh nhân hai số gần căn của một số lớn. Vì d luôn dương, phép chia `remaining/d` không chia cho 0. Đây là phép thử **hoàn toàn bằng số nguyên**, không phụ thuộc `Math.sqrt` dạng `double`.

### Cẩn thận với căn số thực

`Math.sqrt((double)remaining)` có thể hữu ích để ước lượng, nhưng `double` không biểu diễn chính xác mọi số nguyên 64 bit gần `Long.MAX_VALUE`. Nếu dùng căn làm biên quyết định cuối cùng mà không có kiểm tra nguyên chính xác, có thể bỏ lỡ một ước ở vùng biên do làm tròn. Điều kiện `d<=remaining/d` là phương án đơn giản, dễ chứng minh.

### Giới hạn riêng của vòng d+=2

Trong thuật toán này, `remaining≤Long.MAX_VALUE` và d không cần vượt căn của remaining (khoảng 3,04 tỷ với số lớn nhất). Vì d nhỏ hơn rất nhiều `Long.MAX_VALUE`, thao tác `d+=2` không tràn kiểu `long` trong phạm vi input của chương trình.

## 7. Số nguyên âm và bẫy Long.MIN_VALUE

Java `long` là số nguyên có dấu 64 bit:

- `Long.MAX_VALUE = 9 223 372 036 854 775 807`.
- `Long.MIN_VALUE = −9 223 372 036 854 775 808 = −2^63`.

Bẫy nghiêm trọng: `Math.abs(Long.MIN_VALUE)` **vẫn bằng Long.MIN_VALUE** do `2^63` không thể biểu diễn bằng số dương kiểu `long`. Nếu dùng `remaining=Math.abs(value)` mà không kiểm tra giá trị này, phần còn lại vẫn âm và mọi giả thiết về phép chia/căn sẽ sai.

Chương trình giải quyết rõ ràng:

1. Nếu n=0, từ chối.
2. Nếu n<0, thêm cặp `(−1,1)`.
3. Nếu n=`Long.MIN_VALUE`, thêm trực tiếp cặp `(2,63)` vì biết chắc `−2^63`; **không** tính `-n` hoặc `Math.abs(n)`.
4. Với những số âm khác, lấy `−n` an toàn và tiếp tục chia thử.
5. Với số dương, dùng nguyên giá trị.

Ví dụ đầu ra:

`−9 223 372 036 854 775 808 = −1 · 2^63`.

**−1 không phải nguyên tố**; nó là đơn vị mô tả dấu. Với n=−1, kết quả chỉ có dấu `−1`, không có cặp nguyên tố dương.

### Nếu bài chỉ yêu cầu n≥2?

Có thể bỏ nhánh xử lý số âm và 0, nhưng hãy **kiểm tra và thông báo hợp đồng đầu vào**. Việc tự phân tích giá trị âm khi đề yêu cầu số dương hoặc tự trả kết quả cho 0 có thể tạo cách hiểu không thống nhất. Demo hỗ trợ toàn miền `long` trừ 0 để làm rõ các tình huống biên.

## 8. Tính phức tạp của chia thử

Gọi N=|n| đối với n khác 0. Sau khi rút hết 2, thuật toán thử các số lẻ từ 3 tới khoảng √N, nhưng phần còn lại có thể giảm nên nhiều lần dừng sớm.

### Thời gian xấu nhất

Nếu N là số nguyên tố lớn, không có phép chia thành công trước khi d vượt √N. Số ứng viên lẻ cần thử xấp xỉ √N/2, nên số phép kiểm tra chia dư:

`O(√N)`.

Đối với một họ số nguyên tố lớn, việc thử gần √N là không thể tránh trong phiên bản chia thử đơn giản này, do đó cận này phản ánh trường hợp xấu. Các lần chia thành công của một số mũ chỉ có thể xảy ra O(log N) lần, vì mỗi lần chia bởi ít nhất 2 khiến r giảm ít nhất một nửa. Cận tổng vẫn:

`O(√N + log N) = O(√N)` với N≥2.

**Không phải O(log N) cho mọi số:** lũy thừa của 2 thường rất nhanh, nhưng một số nguyên tố lớn có thể buộc kiểm tra hàng triệu hoặc hàng tỷ ứng viên.

### Bộ nhớ

- Một cặp `(p,e)` cho mỗi **nguyên tố phân biệt**; số cặp tối đa O(log N).
- Nếu chỉ muốn xác định một ước hoặc kiểm tra tính nguyên tố, có thể dùng O(1) bộ nhớ phụ.
- Mã Java dùng `ArrayList<Factor>` để lưu kết quả ⇒ **O(k)** không gian đầu ra, k là số nguyên tố phân biệt của |n|, và k≤log₂N.
- Công đoạn `verify` dùng thêm `BigInteger` để tái tạo tích cho mục đích kiểm thử; đó là **bộ nhớ của kiểm tra**, không phải bắt buộc trong thuật toán factorize cơ bản.

### Vì sao không nên thử một nguyên tố gần 2^63?

`√(2^63−1)` xấp xỉ 3,04 tỷ. Nếu một số `long` gần giới hạn này là nguyên tố, trial division thử 2 rồi khoảng **1,5 tỷ số lẻ**. Đây là chi phí thực tế rất lớn; không nên tự tin gọi thuật toán là “nhanh” chỉ vì nó dùng O(√N).

Ngược lại, số `Long.MAX_VALUE` có nhiều ước nhỏ nên chương trình có thể rút hết các ước tương đối sớm. Một số **lớn** không nhất thiết khó như một **số lớn không có ước nhỏ**.

### So sánh với phương pháp khác

| Bối cảnh | Phương pháp thích hợp | Giới hạn/cân nhắc |
| --- | --- | --- |
| Một số vừa/nhỏ, cần đơn giản | Chia thử 2 rồi số lẻ | Ít mã, O(√N) xấu nhất |
| Cần lọc ước nhanh hơn chút | Thử 2,3 rồi các dạng 6k±1 | Giảm ứng viên, vẫn O(√N) |
| Nhiều số trong phạm vi 1..M | **Sàng ước nguyên tố nhỏ nhất SPF** | Tiền xử lý và bộ nhớ O(M), phân tích từng số nhanh |
| Cần danh sách số nguyên tố để chia nhiều lần | Sàng Eratosthenes tới √N | Chỉ chia thử các số nguyên tố, có chi phí sàng |
| Chỉ cần kiểm tra nguyên tố của số lớn | Miller–Rabin với cơ sở phù hợp | Bài toán primality khác bài factorization |
| Phân tích hợp số lớn gần 64 bit với ước lớn | Pollard's rho kết hợp kiểm tra nguyên tố | Phức tạp hơn, thường tốt hơn chia thử cho semiprime lớn |
| Số nguyên tùy ý vượt long | `BigInteger` và thuật toán phù hợp | Thử hết ước bằng BigInteger có thể cực chậm |

**6k±1 chỉ là bộ lọc ứng viên**, không có nghĩa mọi số dạng 6k±1 đều nguyên tố. Ví dụ 25=6·4+1 vẫn là hợp số.

## 9. Tối ưu thêm nhưng không làm phức tạp bài toán

### 9.1. Cập nhật giới hạn theo phần còn lại

Luôn dùng `d <= remaining/d`, không cố định theo `n ban đầu`. Khi r đã bị rút bởi ước nhỏ, biên √r giảm và vòng kết thúc sớm hơn.

### 9.2. Bỏ các số chẵn sau khi xử lý 2

Điều này gần như giảm một nửa số ứng viên khi phần còn lại là nguyên tố lớn. Thuật toán vẫn chính xác vì không có ước chẵn nào cần xét sau khi đã chia hết 2.

### 9.3. Bỏ bội của 2 và 3

Sau khi rút hết 2 và 3, số nguyên tố p>3 phải có dạng `6k−1` hoặc `6k+1`. Có thể thử d=5,7,11,13,17,19,… thay vì mọi số lẻ. Không làm thay đổi cận O(√N) nhưng giảm phép kiểm tra.

**Lưu ý:** nếu bỏ sai một ứng viên hoặc đặt bước nhảy không đúng, có thể tạo bug khó phát hiện. Mã Java chính dùng **d+=2** để ưu tiên khả năng kiểm chứng.

### 9.4. Không cần sàng nguyên tố cho một số nhỏ

Chạy sàng toàn bộ tới √N chỉ để phân tích một số n tương đối nhỏ có thể tốn thêm công đoạn không cần thiết. Nhưng khi phân tích **rất nhiều số** cùng phạm vi, sàng SPF hoặc một danh sách prime dùng lại có thể đem lại lợi ích lớn.

## 10. Những ứng dụng của phân tích thừa số

### 10.1. Đếm số ước dương

Nếu `n=p₁^e₁···pₖ^eₖ`, mỗi ước dương chọn số mũ của pᵢ trong `0..eᵢ`, độc lập giữa các p. Do đó:

`τ(n)=Πᵢ(eᵢ+1)` với n≥1.

Ví dụ:

`360 = 2³·3²·5¹` nên:

`τ(360)=(3+1)(2+1)(1+1)=4·3·2=24`.

Chương trình Java có hàm `positiveDivisorCount`, dùng `Math.multiplyExact` và **bỏ qua cặp dấu −1**. Với n=±1, kết quả là 1; với n=`Long.MIN_VALUE`, |n|=2^63 nên có **64 ước dương**.

**Chú ý:** đây là số ước dương của |n|. Nếu bài hỏi toàn bộ ước nguyên âm và dương của n≠0, số lượng theo quy ước thông thường bằng `2τ(|n|)`.

### 10.2. Tổng các ước dương

Với n≥1:

`σ(n)=Πᵢ (1+pᵢ+...+pᵢ^{eᵢ})`.

Ví dụ:

`σ(360)=(1+2+4+8)(1+3+9)(1+5)=15·13·6=1170`.

Công thức hình học tương đương:

`1+p+...+p^e=(p^{e+1}−1)/(p−1)`.

Khi triển khai cho n lớn, sản phẩm và `p^{e+1}` có thể vượt `long`; dùng `BigInteger` nếu yêu cầu tính chính xác ngoài phạm vi kiểu nguyên gốc.

### 10.3. Hàm Euler phi

Với n≥1:

`φ(n)=n Π_{p|n}(1−1/p)`,

trong đó tích trên các **số nguyên tố phân biệt**. Với 360:

`φ(360)=360·(1−1/2)·(1−1/3)·(1−1/5)=96`.

Khi tính bằng số nguyên, dùng `φ = φ / p * (p−1)` cho từng thừa số nguyên tố phân biệt, với lưu ý chia đúng thứ tự để tránh sai do chia nguyên và kiểm soát tràn khi nhân.

### 10.4. GCD/LCM từ số mũ

Nếu:

`a=Πp^{α_p}`, `b=Πp^{β_p}`,

thì:

`gcd(a,b)=Πp^{min(α_p,β_p)}`,

`lcm(a,b)=Πp^{max(α_p,β_p)}`.

Phân tích thừa số hữu ích khi đã có kết quả cho nhiều phép tính tiếp theo; nhưng nếu **chỉ cần gcd** của hai số, thuật toán Euclid thường đơn giản và nhanh hơn.

### 10.5. Kiểm tra số chính phương và lũy thừa

Một số nguyên dương là **chính phương** khi và chỉ khi mọi số mũ trong phân tích nguyên tố đều **chẵn**. Ví dụ `36=2²·3²` là chính phương, còn `72=2³·3²` không phải.

Tương tự, để n≥2 là lũy thừa bậc k của một số nguyên dương, mọi số mũ nguyên tố của n phải chia hết cho k. Đây là một ứng dụng trực tiếp của tính duy nhất phân tích nguyên tố.

## 11. Java 17+: chương trình đầy đủ, an toàn với số nguyên có dấu

Chương trình dưới đây:

- Nhận `long` khác 0, kể cả số âm và hai cực trị `Long.MIN_VALUE`, `Long.MAX_VALUE`.
- Trả `List<Factor>`, mỗi Factor có `prime` và `exponent`.
- Tách dấu `−1` (không coi đó là prime), xử lý `Long.MIN_VALUE` mà không gọi `Math.abs`.
- Chia 2 trước, chỉ thử các số lẻ sau đó.
- Dừng theo `d <= remaining/d` để không nhân `d*d` có thể tràn.
- Gộp các lần chia hết liên tiếp thành **số mũ**.
- Tính `positiveDivisorCount` theo tích `(e+1)`.
- Có hàm `verify` tái tạo tích bằng `BigInteger` và kiểm tra tính nguyên tố của từng thừa số để phát hiện lỗi.
- Dùng `slowFactorize` thử **từng số từ 2 đến phần còn lại** làm oracle độc lập trên miền nhỏ, và chạy **500 trường hợp ngẫu nhiên** cùng bộ ví dụ xác định.

**Lưu tệp: `TrialDivisionFactorizationDemo.java`**

~~~java
import java.math.BigInteger;
import java.util.ArrayList;
import java.util.List;
import java.util.Random;

public class TrialDivisionFactorizationDemo {
    record Factor(long prime, int exponent) {
        Factor {
            if (exponent < 1 ||
                    (prime != -1 && prime < 2) ||
                    (prime == -1 && exponent != 1)) {
                throw new IllegalArgumentException("Invalid factor");
            }
        }

        @Override
        public String toString() {
            return Long.toString(prime)
                    + (exponent == 1 ? "" : "^" + exponent);
        }
    }

    static List<Factor> factorize(long value) {
        if (value == 0L) {
            throw new IllegalArgumentException(
                    "Zero has no finite prime factorization");
        }

        List<Factor> factors = new ArrayList<>();
        if (value < 0L) {
            factors.add(new Factor(-1L, 1));
        }

        // |-2^63| is not representable as a positive long.
        if (value == Long.MIN_VALUE) {
            factors.add(new Factor(2L, 63));
            return List.copyOf(factors);
        }

        long remaining = value < 0L ? -value : value;
        if (remaining == 1L) {
            return List.copyOf(factors);
        }

        int exponent = 0;
        while (remaining % 2L == 0L) {
            remaining /= 2L;
            exponent++;
        }
        if (exponent > 0) {
            factors.add(new Factor(2L, exponent));
        }

        for (long d = 3L; d <= remaining / d; d += 2L) {
            exponent = 0;
            while (remaining % d == 0L) {
                remaining /= d;
                exponent++;
            }
            if (exponent > 0) {
                factors.add(new Factor(d, exponent));
            }
        }

        // Every composite remaining number would have
        // a prime divisor <= sqrt(remaining).
        if (remaining > 1L) {
            factors.add(new Factor(remaining, 1));
        }

        return List.copyOf(factors);
    }

    static String format(List<Factor> factors) {
        if (factors.isEmpty()) return "1";
        StringBuilder out = new StringBuilder();
        for (Factor f : factors) {
            if (out.length() > 0) out.append(" * ");
            out.append(f);
        }
        return out.toString();
    }

    static long positiveDivisorCount(List<Factor> factors) {
        long count = 1L;
        for (Factor f : factors) {
            if (f.prime() == -1L) continue;
            count = Math.multiplyExact(
                    count, (long) f.exponent() + 1L);
        }
        return count;
    }

    // Only for validation: independent, slow primality check.
    static boolean isPrimeSlow(long p) {
        if (p < 2L) return false;
        for (long d = 2L; d <= p / d; d++) {
            if (p % d == 0L) return false;
        }
        return true;
    }

    static void verify(long original, List<Factor> factors) {
        BigInteger product = BigInteger.ONE;
        boolean signSeen = false;
        long lastPrime = 1L;

        for (int i = 0; i < factors.size(); i++) {
            Factor f = factors.get(i);
            long p = f.prime();

            if (p == -1L) {
                if (i != 0 || signSeen || original >= 0L
                        || f.exponent() != 1) {
                    throw new AssertionError("Invalid sign");
                }
                signSeen = true;
            } else {
                if (p <= lastPrime || !isPrimeSlow(p)) {
                    throw new AssertionError(
                            "Non-prime or unsorted factor");
                }
                lastPrime = p;
            }

            product = product.multiply(
                    BigInteger.valueOf(p).pow(f.exponent()));
        }

        if (signSeen != (original < 0L) ||
                !product.equals(BigInteger.valueOf(original))) {
            throw new AssertionError(
                    "Factors do not reconstruct input");
        }
    }

    // Deliberately slower oracle for the SMALL test range.
    // It tries all divisors, unlike the optimized odd/sqrt loop.
    static List<Factor> slowFactorize(long value) {
        if (value == 0L || value == Long.MIN_VALUE ||
                value < -100_000L || value > 100_000L) {
            throw new IllegalArgumentException(
                    "Oracle is for small nonzero values only");
        }

        List<Factor> answer = new ArrayList<>();
        if (value < 0L) answer.add(new Factor(-1L, 1));
        long remaining = value < 0L ? -value : value;

        for (long d = 2L; d <= remaining; d++) {
            int exponent = 0;
            while (remaining % d == 0L) {
                remaining /= d;
                exponent++;
            }
            if (exponent > 0) {
                answer.add(new Factor(d, exponent));
            }
        }
        return List.copyOf(answer);
    }

    static void show(long value) {
        List<Factor> factors = factorize(value);
        verify(value, factors);
        System.out.println(value + " = " + format(factors)
                + "; divisors=" + positiveDivisorCount(factors));
    }

    static void randomCheck() {
        Random random = new Random(2026L);

        for (int i = 0; i < 500; i++) {
            long x = random.nextInt(200_001) - 100_000L;
            if (x == 0L) x = 1L;

            List<Factor> fast = factorize(x);
            List<Factor> slow = slowFactorize(x);
            if (!fast.equals(slow)) {
                throw new AssertionError(
                        "Factor mismatch for " + x);
            }
            verify(x, fast);
        }
        System.out.println("randomCheck=PASS (500 values)");
    }

    public static void main(String[] args) {
        show(1L);
        show(-1L);
        show(2L);
        show(12L);
        show(360L);
        show(97L);
        show(-360L);
        show(49L);
        show(999_983L);
        show(1_000_000_007L);
        show(1_000_000_000_000L);
        show(999_966_000_289L); // 999983 squared.
        show(Long.MAX_VALUE);
        show(Long.MIN_VALUE);

        try {
            factorize(0L);
            throw new AssertionError(
                    "Expected rejection of zero");
        } catch (IllegalArgumentException expected) {
            System.out.println("zero=rejected");
        }

        randomCheck();
    }
}
~~~

### Biên dịch và chạy

Dùng **JDK 17 trở lên**; lưu mã nguồn theo UTF-8:

~~~bash
javac -encoding UTF-8 TrialDivisionFactorizationDemo.java
java TrialDivisionFactorizationDemo
~~~

**Đầu ra dự kiến chính xác:**

~~~text
1 = 1; divisors=1
-1 = -1; divisors=1
2 = 2; divisors=2
12 = 2^2 * 3; divisors=6
360 = 2^3 * 3^2 * 5; divisors=24
97 = 97; divisors=2
-360 = -1 * 2^3 * 3^2 * 5; divisors=24
49 = 7^2; divisors=3
999983 = 999983; divisors=2
1000000007 = 1000000007; divisors=2
1000000000000 = 2^12 * 5^12; divisors=169
999966000289 = 999983^2; divisors=3
9223372036854775807 = 7^2 * 73 * 127 * 337 * 92737 * 649657; divisors=96
-9223372036854775808 = -1 * 2^63; divisors=64
zero=rejected
randomCheck=PASS (500 values)
~~~

### Giải thích chi tiết đầu ra

**1 và −1:** không có thừa số nguyên tố dương; 1 được biểu diễn bằng tích rỗng, −1 chỉ có cặp dấu.

**2, 12, 360:** kiểm tra khả năng rút lũy thừa của 2, kết hợp nhiều số nguyên tố và số mũ; 360 có đúng 24 ước dương.

**97, 999983, 1000000007:** nguyên tố; sau khi thử ước tới căn của phần còn lại mà không chia được, thuật toán ghi nguyên phần còn lại với số mũ 1.

**−360:** dấu âm đứng riêng và **không** làm thay đổi số ước dương của |n|.

**49 và 999966000289:** số chính phương của một nguyên tố, thuật toán gộp hai lần xuất hiện thành `p²`, không lưu hai cặp trùng `(p,1)`.

**1000000000000:** `10^12=2^12·5^12`, nên số ước dương bằng `13·13=169`.

**Long.MAX_VALUE:** thuật toán không cần gọi căn số thực; kết quả là `7²·73·127·337·92737·649657`, với số ước dương `3·2^5=96`.

**Long.MIN_VALUE:** xử lý riêng `−2^63`, tránh `Math.abs` tràn; số ước dương của `2^63` là 64.

**zero:** n=0 được từ chối có chủ đích; không được coi là số có một phân tích thừa số hữu hạn.

**randomCheck:** sinh **500 giá trị khác 0** trong khoảng [−100000,100000], thay mẫu 0 bằng 1. Kết quả của phiên bản tối ưu được so với `slowFactorize` (thử toàn bộ d từ 2 tới phần còn lại) và được kiểm tra thêm bằng `BigInteger`: tích các thừa số tái tạo giá trị gốc, mỗi thừa số dương là nguyên tố, thứ tự tăng đúng, dấu âm đúng. Dòng PASS chỉ được in khi tất cả test đều vượt qua.

## 12. Hiểu vì sao oracle kiểm thử là độc lập

Một cách dễ sai là viết hai hàm “fast” và “reference” nhưng cùng sao chép điều kiện chia thử tới √n. Nếu cả hai cùng nhầm điều kiện dừng, chương trình vẫn có thể báo PASS giả.

Trong demo:

- **Fast:** rút hết 2, sau đó chỉ kiểm tra số lẻ với điều kiện `d<=remaining/d`.
- **Slow oracle:** thử **từng d liên tiếp từ 2 tới remaining**, không dùng cận căn và không bỏ số chẵn.
- **Product validation:** dùng `BigInteger` tính lại `Π p^e`, không tin vào phép chia của thuật toán fast.
- **Prime validation:** dùng `isPrimeSlow` độc lập với danh sách đã tìm, thử mọi d từ 2 tới căn nguyên bằng điều kiện an toàn.
- **Output validation:** `List<Factor>.equals` so cả thừa số và số mũ, nên phát hiện cả trường hợp đúng tích nhưng số mũ hoặc thứ tự sai.

Đây là các hướng kiểm chứng **tách rời** đủ mạnh để phát hiện nhiều lỗi thông dụng, dù không thay thế chứng minh toán học cho mọi input `long`.

**Lưu ý phạm vi:** `slowFactorize` chỉ dùng được cho |n|≤100000 để tránh chạy quá lâu; nó không nên được gọi cho n cực lớn hay số nguyên tố gần `Long.MAX_VALUE`. Hàm `verify` có bước kiểm tra nguyên tố thử ước, nên cũng là mã **demo/validation**, không phải một bước bắt buộc cho thuật toán phân tích nhanh trong production.

## 13. Những ví dụ phản chứng về tối ưu và độ phức tạp

### 13.1. Chỉ chia một lần mỗi ước

~~~text
n = 72 = 2^3 * 3^2
Sai: lấy 2 một lần -> n=36, tăng d -> bỏ qua 2 còn lại
Đúng: while n%2==0 -> 72->36->18->9; exponent(2)=3
Tiếp: 9->3->1; exponent(3)=2
~~~

Nếu dùng `if` thay `while`, có thể sinh danh sách không đầy đủ hoặc đưa phần còn lại hợp số vào đáp án.

### 13.2. Không thử ước lớn hơn căn sau khi r thay đổi

~~~text
n=21
d=2: không chia hết
d=3: chia hết 21/3=7
Sau đó d=5, nhưng 5>7/5, dừng
Phần còn lại 7>1 -> ghi (7,1)
~~~

Không cần thử d=7, vì sau khi loại mọi ước ≤√7, phần còn lại 7 chắc chắn là nguyên tố.

### 13.3. Phân tích một nguyên tố lớn có thể rất chậm

Với một nguyên tố N≈10^12, số ứng viên lẻ dưới √N có thể xấp xỉ **500.000**. Với một nguyên tố cỡ 10^18, có thể lên tới **hàng trăm triệu ứng viên hoặc hơn**. Điều này giải thích vì sao trial division thích hợp cho cơ sở thuật toán và số nhỏ/vừa, nhưng không phải một giải pháp mặc định để phân tích mọi số nguyên 64 bit trong điều kiện thời gian chặt.

### 13.4. Một số lớn có thể dễ phân tích

`N=10^12=2^12·5^12`: chỉ cần rút 2 liên tục, sau đó rút 5 liên tục, phần còn lại thành 1. Mặc dù N có 13 chữ số, thuật toán rất nhanh vì có các ước nhỏ lặp lại nhiều lần.

**Kết luận:** độ khó không chỉ phụ thuộc **số chữ số của N**, mà phụ thuộc **kích thước và phân bố các ước nguyên tố**.

## 14. Các lỗi thường gặp

1. Coi 1 là nguyên tố và thêm `(1,1)` vào kết quả.
2. Cho n=0 trả danh sách rỗng mà không xác định ngữ nghĩa.
3. Không xử lý n âm nhưng vẫn tính modulo/chia như số dương.
4. Dùng `Math.abs(Long.MIN_VALUE)` và nghĩ đã nhận số dương.
5. Dùng `int` cho giá trị đầu vào có thể vượt 2,1 tỷ.
6. Dùng `d*d<=n` trên `long` mà bỏ qua tràn số.
7. Dùng `Math.sqrt` như biên quyết định tuyệt đối mà không kiểm tra sai số gần giới hạn.
8. Thử từ d=2 tới n thay vì d≤√n, làm số nguyên tố lớn chạy quá lâu.
9. Luôn dùng √N ban đầu dù phần còn lại đã giảm mạnh.
10. Chỉ chia mỗi ước một lần bằng `if` thay vì `while`.
11. Không gộp lặp vào số mũ, khiến danh sách cặp có nhiều `(p,1)` trùng nhau.
12. Quên thêm phần còn lại `r>1` sau vòng lặp.
13. Thêm r=1 thành một thừa số nguyên tố.
14. Cho rằng “chỉ thử số lẻ” được phép bỏ thử 2 ngay cả khi n chẵn.
15. Chạy d+=2 từ d=2, vô tình thử toàn số chẵn và bỏ mọi số lẻ.
16. Tin rằng một ước hợp số như 9 được ghi thành nguyên tố khi các ước nhỏ hơn đã rút hết.
17. Chỉ dùng `d<n/d` thay vì `d<=n/d` và bỏ sót ước bằng căn với số chính phương.
18. Dùng so sánh d≤n/d khi d=0 hoặc r âm, trái điều kiện áp dụng.
19. Không xem số nguyên tố lớn là trường hợp xấu của trial division.
20. Coi O(√N) là nhanh cho mọi số N gần 2^63.
21. Ghi −1 là “số nguyên tố” thay vì đơn vị dấu.
22. Tính số ước bằng tổng số mũ thay vì tích `(e+1)`.
23. Quên bỏ thừa số dấu −1 khi tính số ước dương.
24. Đếm số ước của 1 thành 0 thay vì 1.
25. Tính tổng ước hoặc lũy thừa bằng `long` khi kết quả có thể tràn.
26. Đếm thử một số lớn bằng oracle vét cạn O(n) trong hệ thống production.
27. Không đối chiếu tích nguyên tố với giá trị đầu vào sau khi phân tích.
28. Không xác minh từng thừa số được trả là nguyên tố khi xây bộ kiểm thử.
29. Nhầm “số thừa số phân biệt” với “tổng số thừa số tính cả lặp”.
30. Bỏ qua số chính phương `p²` trong test, khiến sai điều kiện dừng ít bị phát hiện.
31. Không thử `n=1`, `n=−1`, `n=0`, `Long.MIN_VALUE`, `Long.MAX_VALUE`.
32. Giả định phân tích thừa số lớn luôn là kiểm tra nguyên tố nhanh.
33. Xóa phần tử lặp mà không giữ số mũ.
34. Lưu kết quả dưới dạng ký tự hoặc `double` làm mất tính chính xác của phép chia.
35. Quên rằng sàng SPF có tiền xử lý và bộ nhớ, không miễn phí cho một truy vấn.
36. Chỉ kiểm tra ví dụ n=12 hoặc n=360 mà bỏ qua nguyên tố lớn và số lẻ chính phương.
37. Dùng một biến d không tăng sau khi r không còn chia hết d, dẫn tới vòng lặp vô hạn.
38. Gộp không đúng thừa số âm và làm kết quả tích có dấu sai.
39. Dùng điều kiện `d<=original/d` nhưng liên tục chia r: không làm sai tính đúng, nhưng mất tối ưu dừng sớm theo r.
40. Suy ra “mọi số dạng 6k±1 đều là nguyên tố”, dù 25, 35, 49 là phản ví dụ.

## 15. Bài tập có lời giải

**Bài 1.** Phân tích 12. **Đáp án:** `12=2²·3`.

**Bài 2.** Phân tích 18. **Đáp án:** `18=2·3²`.

**Bài 3.** Phân tích 36. **Đáp án:** `36=2²·3²`.

**Bài 4.** Phân tích 72. **Đáp án:** `72=2³·3²`.

**Bài 5.** Phân tích 360. **Đáp án:** `360=2³·3²·5`.

**Bài 6.** Phân tích 1000. **Đáp án:** `1000=2³·5³`.

**Bài 7.** Phân tích 97. **Đáp án:** `97` là nguyên tố, kết quả `97¹`.

**Bài 8.** Phân tích 49. **Đáp án:** `49=7²`. Phải thử d=7 tại đúng biên căn.

**Bài 9.** Phân tích 121. **Đáp án:** `121=11²`.

**Bài 10.** Phân tích 2^10. **Đáp án:** chỉ có `(2,10)`.

**Bài 11.** Phân tích −360. **Đáp án:** `−1·2³·3²·5`; −1 không phải nguyên tố.

**Bài 12.** Phân tích 1. **Đáp án:** tích rỗng, in `1`; số ước dương là 1.

**Bài 13.** N=0 có một phân tích nguyên tố hữu hạn chuẩn không? **Đáp án:** không; trong bài n=0 bị từ chối.

**Bài 14.** Vì sao mọi hợp số N đều có ước không vượt √N? **Đáp án:** nếu N=a·b với 1<a≤b, thì a²≤N.

**Bài 15.** Vì sao sau khi rút hết 2 chỉ thử các số lẻ? **Đáp án:** phần còn lại không còn chia hết cho 2; mọi thừa số nguyên tố tiếp theo đều lẻ.

**Bài 16.** Vì sao phải chia lặp lại một ước? **Đáp án:** để lấy đủ số mũ, chẳng hạn 8=2³.

**Bài 17.** Khi d>remaining/d và remaining>1, kết luận gì? **Đáp án:** phần còn lại là nguyên tố.

**Bài 18.** Nếu còn r=1 sau khi chia, có thêm (1,1) không? **Đáp án:** không; 1 không phải nguyên tố.

**Bài 19.** Với N=360, số nguyên tố phân biệt là bao nhiêu? **Đáp án:** 3 (2,3,5).

**Bài 20.** Với N=360, tổng số thừa số nguyên tố tính lặp? **Đáp án:** 3+2+1=6.

**Bài 21.** Với N=360, số ước dương? **Đáp án:** `(3+1)(2+1)(1+1)=24`.

**Bài 22.** Với N=360, tổng các ước dương? **Đáp án:** 1170.

**Bài 23.** Với N=360, φ(N)? **Đáp án:** 96.

**Bài 24.** Với N=10^12, phân tích nguyên tố và số ước dương? **Đáp án:** `2¹²·5¹²`, `(12+1)^2=169`.

**Bài 25.** `Long.MIN_VALUE` bằng −2^63, phân tích thế nào? **Đáp án:** `−1·2^63`.

**Bài 26.** Vì sao `Math.abs(Long.MIN_VALUE)` sai cho việc lấy trị tuyệt đối dương? **Đáp án:** +2^63 không biểu diễn được trong long có dấu.

**Bài 27.** Vì sao `d*d<=n` có thể nguy hiểm trên long? **Đáp án:** d*d có thể tràn số và biến điều kiện dừng thành sai.

**Bài 28.** Viết điều kiện dừng tránh tràn khi n,d>0. **Đáp án:** `d<=n/d`.

**Bài 29.** Trial division tốt nhất để phân tích một nguyên tố gần 2^63 có nên dùng production không? **Đáp án:** thường không; vòng thử có thể phải duyệt cực nhiều ứng viên tới căn.

**Bài 30.** Một số `n=p^e` có bao nhiêu ước dương? **Đáp án:** `e+1`.

**Bài 31.** Dấu hiệu từ phân tích nguyên tố để nhận biết chính phương? **Đáp án:** mọi số mũ đều chẵn.

**Bài 32.** Với N=72, có phải chính phương không? **Đáp án:** không vì số mũ của 2 là 3 lẻ.

**Bài 33.** Nếu cần gcd(a,b) duy nhất, có nên bắt buộc phân tích a,b? **Đáp án:** không; thuật toán Euclid thường nhanh và đơn giản hơn.

**Bài 34.** Khi phải phân tích mọi số tới M, tiền xử lý nào hữu ích? **Đáp án:** sàng **smallest prime factor (SPF)**.

**Bài 35.** Tại sao 25 có dạng 6k+1 mà không phải nguyên tố? **Đáp án:** 25=5²; dạng 6k±1 chỉ là điều kiện cần cho nguyên tố >3.

**Bài 36.** Vì sao test nên dùng oracle thử hết d trên các n nhỏ? **Đáp án:** phương pháp độc lập khác tiêu chí dừng/nhảy số lẻ, giúp bắt lỗi của bản tối ưu.

## 16. Checklist giải bài chia thử

1. Đã xác định n thuộc **số nguyên dương** hay cho phép cả số âm?
2. Đã quy ước rõ **0 không có phân tích nguyên tố hữu hạn**?
3. Đã xác nhận **1 không phải nguyên tố** và dùng tích rỗng đúng?
4. Với số âm, đã biểu diễn dấu `−1` riêng và không đếm nó là nguyên tố?
5. Với `Long.MIN_VALUE`, đã tránh `Math.abs` hoặc `-n` trực tiếp?
6. Đã dùng `long`/`BigInteger` tương ứng với phạm vi đầu vào?
7. Đã chia hết **toàn bộ số mũ của 2** trước khi thử số lẻ?
8. Đã tăng d theo **2** khi thử `3,5,7,…`?
9. Đã dùng vòng `while` để rút hết một ước, thay vì chia một lần?
10. Đã lưu đúng cặp `(p,e)` với e≥1, không tạo hai cặp cho cùng p?
11. Đã cập nhật **remaining** sau mỗi phép chia?
12. Đã kiểm tra `d <= remaining/d` thay vì `d*d<=remaining` có thể tràn?
13. Đã ghi **remaining>1** làm nguyên tố cuối?
14. Có bỏ hoàn toàn **remaining=1** ở cuối?
15. Có giữ các nguyên tố trong kết quả theo thứ tự tăng dần?
16. Đã thử n nguyên tố, n là chính phương, n là lũy thừa của 2?
17. Đã thử n=1, −1, 0, Long.MIN_VALUE và Long.MAX_VALUE?
18. Đã xác minh tích các thừa số bằng input ban đầu?
19. Đã kiểm tra từng thừa số dương trả về thực sự là nguyên tố?
20. Nếu cần số ước dương, đã tính `Π(e+1)` và bỏ qua dấu âm?
21. Đã đánh giá trường hợp xấu **O(√N)** thay vì suy đoán từ số chữ số?
22. Nếu đầu vào nhiều hoặc n rất lớn, đã cân nhắc SPF/sàng/Miller–Rabin/Pollard rho phù hợp?
23. Đã phân biệt độ phức tạp của **thuật toán factorize** với mã kiểm thử `verify`/oracle?
24. Đã dùng kết quả phân tích đúng định dạng mà đề yêu cầu: danh sách nguyên tố, cặp số mũ hay tích in ra?

**Ghi nhớ:** chia thử thành công nhờ một lập luận ngắn nhưng rất mạnh: **mỗi hợp số đều có ước không vượt căn bậc hai**. Khi rút hết thừa số 2 rồi thử các số lẻ tới `d>remaining/d`, mọi phần còn lại lớn hơn 1 chắc chắn là nguyên tố. Độ đúng dựa vào **chia hết số mũ, cập nhật phần còn lại và bất biến tích**, còn độ an toàn Java phụ thuộc kiểm soát **0, 1, số âm, Long.MIN_VALUE và tràn số trong điều kiện dừng**. Đây là phương pháp nền tảng, rất phù hợp cho số nhỏ/vừa; với số lớn khó phân tích hoặc nhiều truy vấn, hãy chọn thuật toán/sàng nâng cao phù hợp.
