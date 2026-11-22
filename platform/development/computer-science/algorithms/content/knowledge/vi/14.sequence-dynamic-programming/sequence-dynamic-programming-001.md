# Dãy con tăng dài nhất và phiên bản không giảm

**Dãy con tăng dài nhất** (*Longest Increasing Subsequence – LIS*) và **dãy con không giảm dài nhất** (*Longest Non-Decreasing Subsequence – LNDS*) là hai bài toán kinh điển trong **quy hoạch động dãy**. Chúng giống nhau ở cách chọn một **dãy con** bằng cách giữ lại một số phần tử theo **thứ tự chỉ số gốc**; điểm khác biệt quyết định là cách xử lý **hai giá trị bằng nhau**:

- **LIS – tăng nghiêm ngặt:** mỗi phần tử sau phải **lớn hơn** phần tử trước, `a[i_1] < a[i_2] < ... < a[i_L]`.
- **LNDS – không giảm:** mỗi phần tử sau có thể **bằng hoặc lớn hơn** phần tử trước, `a[i_1] <= a[i_2] <= ... <= a[i_L]`.

Các chỉ số được chọn luôn thỏa `0 <= i_1 < i_2 < ... < i_L < n`. Không cần các chỉ số liên tiếp. Ta thường tìm **độ dài tối đa L**; nhiều bài còn yêu cầu xuất **một dãy con đạt độ dài ấy** hoặc những **chỉ số gốc** của nó.

Bài học xây dựng hai cách giải: quy hoạch động **O(n²)** dễ hiểu và có công thức rõ ràng; kỹ thuật **tails + tìm kiếm nhị phân O(n log n)** khi n lớn. Với cả hai cách, ta có thể lưu **con trỏ phần tử đứng trước** để truy vết một lời giải. Sự khác biệt giữa **lower bound** và **upper bound** là trọng tâm để không nhầm LIS và LNDS.

## 1. Dãy con khác đoạn con, và “tăng” khác “không giảm”

Một **dãy con** (*subsequence*) được hình thành bằng cách xóa tùy ý một số phần tử nhưng **không đổi thứ tự các phần tử còn lại**. Một **đoạn con** (*subarray/subsegment*) phải gồm các vị trí **liên tiếp**. LIS và LNDS nói về **subsequence**, không phải đoạn liên tục dài nhất.

Ví dụ:

```text
a = [3, 1, 2, 2, 4, 3, 5]
i =  0  1  2  3  4  5  6

Một LIS:  indices [1, 3, 5, 6] -> values [1, 2, 3, 5], L = 4.
Một LNDS: indices [1, 2, 3, 5, 6] -> [1, 2, 2, 3, 5], L = 5.

LIS không được lấy hai số 2 liên tiếp vì 2 < 2 là sai.
LNDS được lấy cả hai vì 2 <= 2 là đúng.
```

Có thể có **nhiều** dãy con tối ưu. Chẳng hạn LIS ở ví dụ có thể là `[1,2,4,5]` hoặc `[1,2,3,5]`, cùng độ dài 4. Nếu đề không đưa tiêu chí phụ, việc trả **bất kỳ một** dãy con tối ưu hợp lệ đều đúng.

### Các trường hợp nhỏ cho thấy sự khác nhau

| Dữ liệu | Độ dài LIS | Độ dài LNDS | Giải thích |
| --- | ---: | ---: | --- |
| `[]` | 0 | 0 | Không có phần tử |
| `[7]` | 1 | 1 | Một phần tử |
| `[2,2,2,2]` | 1 | 4 | LIS không dùng hai bản sao bằng nhau; LNDS dùng được hết |
| `[1,2,3,4]` | 4 | 4 | Đã tăng nghiêm ngặt |
| `[4,3,2,1]` | 1 | 1 | Mọi phần tử sau đều nhỏ hơn |
| `[1,1,2,2]` | 2 | 4 | LIS chỉ lấy một 1 và một 2 |
| `[-3,-1,0,2]` | 4 | 4 | Số âm được so sánh như bình thường |

**Định nghĩa “dài nhất”** ở đây là **nhiều phần tử nhất**, không phải có tổng giá trị lớn nhất. Dãy con có thể chứa số âm và 0; không được giả sử kết quả là một dãy các số dương.

## 2. Vì sao đây là bài toán quy hoạch động?

Nếu muốn chọn một dãy con kết thúc tại phần tử `a[i]`, phần tử đứng trước nó (nếu có) phải nằm tại một vị trí `j < i` và thỏa quy tắc tăng. Một dãy con dài nhất kết thúc tại i có thể được tạo bằng cách lấy **một dãy con dài nhất kết thúc tại j** rồi thêm `a[i]`.

Đây là **cấu trúc con tối ưu**: nếu phần dãy con trước i không dài nhất trong những dãy kết thúc ở j, thay bằng dãy dài hơn ở j vẫn tạo dãy hợp lệ kết thúc ở i và cải thiện kết quả, mâu thuẫn với tính tối ưu.

Quan hệ phụ thuộc chỉ đi từ chỉ số nhỏ đến chỉ số lớn, nên ta có thể tính giá trị cho i theo thứ tự `0,1,...,n−1`. Cần nhớ rõ:

- DP ở đây chọn **các phần tử của mảng** theo thứ tự chỉ số.
- Nó không sắp lại mảng đầu vào.
- Việc chọn một phần tử có thể bỏ qua nhiều phần tử nằm giữa.
- Giá trị DP là **độ dài**, không phải giá trị số của phần tử.

## 3. Giải pháp O(n²): DP kết thúc tại mỗi vị trí

Định nghĩa:

```text
dp[i] = độ dài dãy con tăng (hoặc không giảm)
        dài nhất mà phần tử cuối là a[i].
```

Với mọi i, ít nhất có thể chọn riêng `a[i]`, nên `dp[i] >= 1` và khởi tạo `dp[i]=1`.

**LIS nghiêm ngặt:**

```text
dp[i] = 1 + max(dp[j]) với mọi j < i và a[j] < a[i]
dp[i] = 1 nếu không có j nào như vậy.
Đáp án = max(dp[i]); với n=0, đáp án = 0.
```

**LNDS không giảm:**

```text
dp[i] = 1 + max(dp[j]) với mọi j < i và a[j] <= a[i]
dp[i] = 1 nếu không có j nào như vậy.
```

Chỉ khác **một dấu so sánh**: LIS dùng `<`, LNDS dùng `<=`. Thay bằng `<=` trong LIS sẽ khiến các phần tử bằng nhau nối tiếp và cho đáp án của **bài toán khác**.

### Minh họa trên cùng dữ liệu

Với `a=[3,1,2,2,4,3,5]`:

| i | a[i] | LIS `dp[i]` | LNDS `dp[i]` | Lý do ngắn |
| ---: | ---: | ---: | ---: | --- |
| 0 | 3 | 1 | 1 | Bắt đầu dãy |
| 1 | 1 | 1 | 1 | Không có phần tử trước nhỏ/bằng thích hợp |
| 2 | 2 | 2 | 2 | Ghép sau 1 |
| 3 | 2 | 2 | 3 | LNDS nối tiếp 2 bằng nhau; LIS không |
| 4 | 4 | 3 | 4 | Nối sau dãy kết thúc tại 2 |
| 5 | 3 | 3 | 4 | Nối sau 2; LNDS có thể dùng hai số 2 |
| 6 | 5 | 4 | 5 | Nối tiếp dãy con dài nhất trước đó |

Đáp án là **LIS=4** và **LNDS=5**. Không được lấy `dp[n−1]` làm đáp án trong mọi trường hợp: dãy con tối ưu có thể kết thúc ở **bất kỳ vị trí nào**, ví dụ `[1,2,3,0]` có LIS dài 3 kết thúc ở phần tử 3, không phải ở 0 cuối mảng.

### Lưu đường đi để lấy dãy con

Dùng thêm `parent[i]` lưu chỉ số j trước i đã tạo nên `dp[i]` tốt nhất; mặc định -1 khi `a[i]` tự đứng một mình. Khi nâng `dp[i]` bằng `dp[j]+1`, đặt `parent[i]=j`.

Sau khi tính xong:

1. Chọn chỉ số `bestEnd` có `dp[bestEnd]` lớn nhất.
2. Bắt đầu tại `bestEnd`, theo `parent` ngược về -1.
3. Đảo danh sách chỉ số để có thứ tự xuất hiện từ trái sang phải.

**Điều kiện nâng cấp:** Dùng `dp[j]+1 > dp[i]` để chỉ cập nhật khi tìm được lời giải **dài hơn thật sự**. Nếu bằng nhau, giữ lựa chọn trước có thể tạo kết quả ổn định theo thứ tự duyệt, nhưng không bắt buộc là dãy con tối ưu nhỏ nhất theo thứ tự từ điển.

### Giả mã DP bậc hai

```text
QUADRATIC-MONOTONE-SUBSEQUENCE(a, allowEqual):
    n = length(a)
    dp = array(n, fill=1)
    parent = array(n, fill=-1)
    bestLength = 0
    bestEnd = -1

    for i = 0 .. n-1:
        for j = 0 .. i-1:
            ok = allowEqual ? (a[j] <= a[i]) : (a[j] < a[i])
            if ok and dp[j] + 1 > dp[i]:
                dp[i] = dp[j] + 1
                parent[i] = j
        if dp[i] > bestLength:
            bestLength = dp[i]
            bestEnd = i

    reconstruct indices from bestEnd using parent
    return bestLength and one valid subsequence
```

**Chi phí:** Tổng số phép xét cặp là `0+1+...+(n−1)=n(n−1)/2`, tức **Θ(n²)** thời gian trong phiên bản hai vòng lặp, và hai mảng dp/parent dài n tốn **O(n)** bộ nhớ phụ. Truy vết mất O(L) thời gian và O(L) bộ nhớ để chứa lời giải dài L.

## 4. Chứng minh DP bậc hai đúng

**Mệnh đề:** Sau khi hoàn thành vòng xử lý i, `dp[i]` là độ dài tối đa của mọi dãy con hợp lệ **kết thúc tại i**.

**Cơ sở:** Với i=0, chỉ có dãy [a[0]], nên `dp[0]=1`.

**Bước quy nạp:** Giả sử các `dp[j]` với j<i đúng. Một dãy con hợp lệ kết thúc tại i hoặc chỉ có một phần tử a[i], hoặc có phần tử áp chót tại một chỉ số j<i. Khi đó giá trị a[j] phải <a[i] đối với LIS hoặc ≤a[i] đối với LNDS. Theo giả thiết quy nạp, phần dãy con kết thúc tại j có độ dài không lớn hơn dp[j]. Vì vậy mọi dãy kết thúc ở i có độ dài không vượt quá `1+max dp[j]` trên các j hợp lệ. Ngược lại, nối a[i] vào một dãy tối ưu kết thúc tại j hợp lệ tạo dãy độ dài đúng bằng biểu thức ấy. Do đó công thức đạt **đúng tối ưu**.

Lấy max trên mọi i bao quát mọi dãy con không rỗng, vì bất cứ dãy nào cũng có phần tử cuối. Đối với n=0, đáp án 0 theo định nghĩa.

**Tính đúng truy vết:** Mỗi parent[i] đều <i, thỏa điều kiện quan hệ giá trị, và được lưu khi tăng dp[i]. Theo parent cho chuỗi chỉ số **giảm nghiêm ngặt** khi truy ngược, nên dừng; đảo chuỗi cho dãy con có chỉ số tăng và giá trị đúng quy tắc. Số nút theo parent là dp[bestEnd].

## 5. Từ O(n²) xuống O(n log n): ý tưởng “đuôi tốt nhất”

DP bậc hai xét mọi j trước i. Để nhanh hơn, ta không giữ toàn bộ lựa chọn kết thúc trong mỗi mức độ dài, mà giữ một thông tin đại diện:

```text
tails[L-1] = giá trị kết thúc nhỏ nhất có thể
             trong các dãy con hợp lệ dài L
             tạo từ tiền tố đã xử lý.
```

Một dãy con cùng độ dài nhưng có **phần tử cuối nhỏ hơn** là lựa chọn **không kém khi mở rộng về sau**:

- Với LIS, mọi giá trị x có thể nối sau phần tử kết thúc lớn hơn cũng có thể nối sau phần tử kết thúc nhỏ hơn, nếu cả hai thỏa `tail < x`.
- Với LNDS, logic tương tự dùng `tail <= x`.

Vì thế ta có thể giữ **một giá trị đuôi nhỏ nhất cho mỗi độ dài**, thay vì giữ mọi dãy có cùng độ dài.

**Lưu ý cực kỳ quan trọng:** Dãy `tails` **không nhất thiết chính là một dãy con thực sự của đầu vào**, vì các phần tử đuôi thuộc những dãy con ứng viên **khác nhau**. Nó là bảng mô tả **giới hạn kết thúc tốt nhất**, không phải đường đi kết quả. Muốn truy vết phải lưu thêm các chỉ số và predecessor.

### Duy trì tails theo từng phần tử

Duyệt a từ trái sang phải. Với phần tử hiện tại x:

1. Tìm vị trí `pos` thích hợp trong tails bằng tìm kiếm nhị phân.
2. Nếu `pos` đã nằm trong tails, thay `tails[pos]=x` (x tạo phần tử cuối tốt hơn hoặc tương đương cho độ dài pos+1).
3. Nếu `pos==length`, thêm x vào cuối tails, tăng độ dài lớn nhất lên 1.
4. Lặp đến hết.

Ở mỗi thời điểm, **length = số đuôi đang theo dõi = độ dài lớn nhất của dãy con tìm được trong tiền tố**.

Không sắp xếp lại đầu vào; mỗi phần tử chỉ được dùng **một lần theo thứ tự gốc**, và việc thêm x dựa trên một dãy con hợp lệ trong tiền tố đã xét.

## 6. Lower bound cho LIS, upper bound cho LNDS

Cả hai bài dùng cùng bảng tails nhưng **khác tiêu chí tìm vị trí**.

### LIS nghiêm ngặt: tìm phần tử đầu tiên ≥ x

Ta cần dãy con dài L có phần tử cuối **< x** mới nối được x và thành độ dài L+1. Vì tails tăng nghiêm ngặt ở LIS, vị trí cần cập nhật là:

```text
pos = lower_bound(tails, x)
    = vị trí nhỏ nhất có tails[pos] >= x;
      nếu không có, pos = length.
```

Vì vậy khi x **bằng** một giá trị trong tails, x **thay thế** đuôi đó, **không được tăng độ dài**.

Ví dụ:

```text
a = [2, 2, 2]
LIS strict:

x=2 -> tails=[2], length=1
x=2 -> thay tails[0]=2, length=1
x=2 -> thay tails[0]=2, length=1
Đáp án LIS=1.
```

Trong tìm kiếm nhị phân viết tay, ta giữ điều kiện:

```java
// Cho LIS: dich trai qua moi tail < x.
if (tails[mid] < x) {
    left = mid + 1;
} else {
    right = mid;
}
```

### LNDS không giảm: tìm phần tử đầu tiên > x

Với LNDS, có thể nối x sau một phần tử cuối **≤ x**, vì các giá trị bằng nhau được phép liền nhau. Vị trí phải cập nhật là:

```text
pos = upper_bound(tails, x)
    = vị trí nhỏ nhất có tails[pos] > x;
      nếu không có, pos = length.
```

Do đó nếu x **bằng** giá trị cuối hiện có, x có thể **mở rộng dãy thêm một phần tử**.

```text
a = [2, 2, 2]
LNDS nondecreasing:

x=2 -> tails=[2], length=1
x=2 -> tails=[2,2], length=2
x=2 -> tails=[2,2,2], length=3
Đáp án LNDS=3.
```

Tìm kiếm nhị phân tương ứng:

```java
// Cho LNDS: dich trai qua moi tail <= x.
if (tails[mid] <= x) {
    left = mid + 1;
} else {
    right = mid;
}
```

| Bài toán | Quan hệ giữa hai phần tử liên tiếp | Tìm vị trí trong tails | Tính chất của tails |
| --- | --- | --- | --- |
| LIS | Trước **<** sau | **lower_bound:** đầu tiên **≥ x** | Tăng nghiêm ngặt |
| LNDS | Trước **≤** sau | **upper_bound:** đầu tiên **> x** | Không giảm |

**Tránh mẹo sai:** Không được chỉ viết “hai bài đều dùng binary search giống nhau” mà không kiểm tra dấu. Chỉ một dấu `<` đổi thành `<=` trong vòng tìm kiếm nhị phân làm thay đổi hoàn toàn việc xử lý bản sao bằng nhau.

## 7. Theo dõi tails trên ví dụ

Với `a=[3,1,2,2,4,3,5]`:

| i | x | tails sau khi xử lý x – LIS | tails sau khi xử lý x – LNDS |
| ---: | ---: | --- | --- |
| 0 | 3 | [3] | [3] |
| 1 | 1 | [1] | [1] |
| 2 | 2 | [1,2] | [1,2] |
| 3 | 2 | [1,2] | [1,2,2] |
| 4 | 4 | [1,2,4] | [1,2,2,4] |
| 5 | 3 | [1,2,3] | [1,2,2,3] |
| 6 | 5 | [1,2,3,5] | [1,2,2,3,5] |

Do đó `length=4` cho LIS và `length=5` cho LNDS.

### Tails không phải dãy kết quả

Ví dụ `a=[1,6,2,3,4,0]` với LIS:

```text
Sau 1,6,2,3,4: tails=[1,2,3,4]
Sau 0:         tails=[0,2,3,4]
```

Mảng tails cuối `[0,2,3,4]` **không phải dãy con của đầu vào**: số 0 xuất hiện **sau** số 2, 3, 4. Độ dài 4 vẫn đúng vì dãy con `[1,2,3,4]` tồn tại. Để in ra dãy con thật, chỉ lấy `tails` sẽ sai; cần **truy vết chỉ số**.

## 8. Truy vết O(n log n): tailsIndex và parent

Thay vì chỉ lưu giá trị tails[L−1], ta lưu:

- `tailsIndex[L−1]`: chỉ số của phần tử có giá trị đuôi nhỏ nhất cho độ dài L.
- `parent[i]`: chỉ số phần tử đứng trước i trong **một dãy con hợp lệ** kết thúc tại i với độ dài được gán cho i khi xử lý.

Ở bước xét `a[i]=x`, sau khi tìm `pos` bằng nhị phân:

1. Nếu `pos>0`, đặt `parent[i] = tailsIndex[pos−1]` (trước khi ghi đè đuôi ở vị trí pos). Nếu pos=0, parent[i]=-1.
2. Đặt `tailsIndex[pos] = i` để lưu đuôi ứng viên mới.
3. Nếu pos bằng độ dài hiện tại, tăng length.

Cuối cùng, lấy chỉ số `tailsIndex[length−1]` và lần theo parent ngược về -1, rồi đảo ngược các chỉ số. Dãy con được khôi phục có **đúng length phần tử**, chỉ số tăng và giá trị thỏa quan hệ yêu cầu.

**Tại sao parent có hiệu lực dù tailsIndex có thể thay đổi về sau?** Khi xử lý i, parent[i] trỏ tới **một chỉ số thuộc tiền tố đã xét** tạo được dãy có độ dài pos. Sau này bảng tailsIndex có thể đổi đầu mút đại diện, nhưng **parent[i] vẫn trỏ tới phần tử lịch sử thực sự**, không trỏ tới vị trí logic trong tails. Vì thế chuỗi parent giữ được một dãy con hợp lệ.

**Quy tắc hòa:** Khi giá trị bằng nhau ở LIS, triển khai đơn giản có thể thay tailsIndex bằng chỉ số xuất hiện muộn hơn. Điều này vẫn đúng độ dài và lời giải nhưng có thể đổi **chỉ số được chọn**. Nếu đề yêu cầu lời giải nhỏ nhất theo thứ tự từ điển hoặc ưu tiên chỉ số xuất hiện sớm nhất, cần thiết kế riêng chính sách hòa và chứng minh phù hợp. Không nên tự hứa tính chất ấy từ thuật toán chuẩn.

### Giả mã n log n dùng chung

```text
FAST-MONOTONE-SUBSEQUENCE(a, allowEqual):
    tailsIndex = array(n)
    parent = array(n, fill=-1)
    length = 0

    for i = 0 .. n-1:
        x = a[i]
        left = 0
        right = length

        while left < right:
            mid = left + (right-left)/2
            tail = a[tailsIndex[mid]]

            if allowEqual ? (tail <= x) : (tail < x):
                left = mid + 1
            else:
                right = mid

        pos = left
        if pos > 0:
            parent[i] = tailsIndex[pos-1]
        tailsIndex[pos] = i
        if pos == length:
            length++

    reconstruct from tailsIndex[length-1] using parent
    return length and one valid subsequence
```

Không truy cập `tailsIndex[length−1]` nếu n=0; khi length=0, trả dãy rỗng ngay.

## 9. Chứng minh thuật toán tails + tìm kiếm nhị phân

Đặt `bestTail[L]` là **giá trị kết thúc nhỏ nhất có thể** của một dãy con hợp lệ độ dài L trong tiền tố đã xử lý. Một cách chứng minh đúng là duy trì bất biến:

1. Với mọi `1<=L<=length`, tồn tại một dãy con hợp lệ độ dài L kết thúc ở `bestTail[L]`.
2. Không có dãy con hợp lệ độ dài L kết thúc bằng giá trị **nhỏ hơn** `bestTail[L]`.
3. `length` bằng độ dài lớn nhất trong tiền tố.
4. Dãy các bestTail được sắp tăng nghiêm ngặt ở LIS; được sắp không giảm ở LNDS.

**Khởi tạo:** Chưa có phần tử, length=0, các điều kiện đúng rỗng.

**Duy trì khi đọc x:** Tìm vị trí pos là số đuôi cho phép nối x:

- LIS: các đuôi nhỏ hơn x thuộc các vị trí trước lower_bound.
- LNDS: các đuôi nhỏ hơn hoặc bằng x thuộc các vị trí trước upper_bound.

Vì vậy có thể nối x vào dãy có độ dài pos (nếu pos>0), tạo dãy có độ dài pos+1. Đối với độ dài ấy, x **không lớn hơn** đuôi đang lưu tại pos (nếu pos đã tồn tại); thay đuôi bằng x giữ hoặc cải thiện khả năng mở rộng. Nếu pos==length, ta vừa tạo được một dãy có độ dài mới length+1.

**Vì sao không bỏ sót một dãy dài hơn?** Mọi dãy con hợp lệ kết thúc ở x phải có tiền tố kết thúc bằng giá trị <x hoặc <=x tùy bài. Nếu tồn tại một dãy tiền tố dài hơn pos với giá trị cuối phù hợp, đuôi tối thiểu đã lưu cho độ dài đó cũng sẽ phù hợp, mâu thuẫn với việc pos là vị trí đầu tiên không còn phù hợp. Do đó pos+1 là độ dài lớn nhất có thể gắn với x; cập nhật này đúng cho mọi x.

**Kết thúc:** Sau khi duyệt toàn bộ mảng, length là độ dài tối ưu. Các parent được tạo bằng những dãy có chỉ số nhỏ hơn i nên truy vết cho một dãy con thật và đúng chiều thời gian.

**Chi phí:** Có n lượt xử lý, mỗi lượt tìm vị trí trong mảng tails dài ≤n bằng **O(log n)** so sánh rồi cập nhật O(1). Tổng **O(n log n)** thời gian; ba mảng lưu chỉ số/parent/kết quả tốn **O(n)** bộ nhớ. Nếu chỉ cần độ dài, không cần parent và chỉ cần tails values; vẫn O(n) bộ nhớ trường hợp xấu.

### Có phải mọi đầu vào đều tốn Θ(n log n)?

Thuật toán mã chuẩn thực hiện n vòng và nhị phân trên length hiện có, nên cận trên là O(n log n); với một số dãy, length nhỏ và các lượt tìm kiếm rất ngắn. Trên dãy giá trị giống nhau, LIS có length=1, mỗi lượt tìm gần như O(1); LNDS có length tăng dần và các lượt nhị phân có thể tốn O(log n). Khi nói về thuật toán này, nên dùng **cận trên tổng quát** O(n log n), không suy ra mỗi lượt đều đúng log n phép so sánh.

## 10. Chương trình Java 17+ hoàn chỉnh

Chương trình cung cấp:

- `quadratic(a, allowEqual)`: DP O(n²), lưu parent, trả một dãy con tối ưu.
- `fast(a, allowEqual)`: tailsIndex + nhị phân O(n log n), lưu parent để truy vết.
- `Result(length, indices, values)`: độ dài, chỉ số trong mảng gốc, giá trị tương ứng.
- `validSubsequence`: kiểm tra chỉ số tăng, giá trị khớp đầu vào, và quan hệ < hoặc <=.
- `show`: chạy hai thuật toán trên cùng đầu vào, đối chiếu **độ dài** và kiểm tra dãy con đã truy vết. Hai thuật toán **không bắt buộc trả cùng bộ chỉ số**, vì có thể có nhiều lời giải tối ưu.

Mã chỉ đọc mảng input, **không sắp hoặc sửa input**. Với số nguyên cực trị, dùng phép so sánh trực tiếp, không dùng hiệu hai số có thể tràn.

Lưu file **`LongestMonotoneSubsequence.java`**:

```java
import java.util.Arrays;
import java.util.Objects;

public class LongestMonotoneSubsequence {
    record Result(int length, int[] indices, int[] values) {}

    // Truy vet parent tu phan tu cuoi ve dau.
    private static Result restore(
            int[] a, int endIndex, int[] parent, int length) {
        int[] indices = new int[length];
        int[] values = new int[length];
        for (int p = length - 1; p >= 0; p--) {
            indices[p] = endIndex;
            values[p] = a[endIndex];
            endIndex = parent[endIndex];
        }
        return new Result(length, indices, values);
    }

    // O(n^2): dp[i] = do dai tot nhat ket thuc tai i.
    static Result quadratic(int[] a, boolean allowEqual) {
        Objects.requireNonNull(a, "input must not be null");
        if (a.length == 0) {
            return new Result(0, new int[0], new int[0]);
        }

        int n = a.length;
        int[] dp = new int[n];
        int[] parent = new int[n];
        Arrays.fill(parent, -1);
        int bestLength = 0;
        int bestEnd = -1;

        for (int i = 0; i < n; i++) {
            dp[i] = 1;
            for (int j = 0; j < i; j++) {
                boolean canFollow = allowEqual
                        ? a[j] <= a[i]
                        : a[j] < a[i];
                if (canFollow && dp[j] + 1 > dp[i]) {
                    dp[i] = dp[j] + 1;
                    parent[i] = j;
                }
            }
            if (dp[i] > bestLength) {
                bestLength = dp[i];
                bestEnd = i;
            }
        }
        return restore(a, bestEnd, parent, bestLength);
    }

    // O(n log n): tailsIndex[L-1] la chi so
    // cua duoi nho nhat cua day con do dai L.
    static Result fast(int[] a, boolean allowEqual) {
        Objects.requireNonNull(a, "input must not be null");
        int n = a.length;
        if (n == 0) {
            return new Result(0, new int[0], new int[0]);
        }

        int[] tailsIndex = new int[n];
        int[] parent = new int[n];
        Arrays.fill(parent, -1);
        int length = 0;

        for (int i = 0; i < n; i++) {
            int left = 0;
            int right = length;

            while (left < right) {
                int mid = left + (right - left) / 2;
                int tail = a[tailsIndex[mid]];

                // LIS: lower_bound (tail >= x).
                // LNDS: upper_bound (tail > x).
                boolean moveRight = allowEqual
                        ? tail <= a[i]
                        : tail < a[i];
                if (moveRight) {
                    left = mid + 1;
                } else {
                    right = mid;
                }
            }

            int pos = left;
            if (pos > 0) {
                parent[i] = tailsIndex[pos - 1];
            }
            tailsIndex[pos] = i;
            if (pos == length) {
                length++;
            }
        }
        return restore(a, tailsIndex[length - 1], parent, length);
    }

    static boolean validSubsequence(
            int[] a, Result result, boolean allowEqual) {
        if (result.length() != result.indices().length
                || result.length() != result.values().length) {
            return false;
        }
        int previousIndex = -1;
        int previousValue = 0;

        for (int p = 0; p < result.length(); p++) {
            int idx = result.indices()[p];
            int value = result.values()[p];
            if (idx <= previousIndex || idx < 0
                    || idx >= a.length || a[idx] != value) {
                return false;
            }
            if (p > 0) {
                boolean ok = allowEqual
                        ? previousValue <= value
                        : previousValue < value;
                if (!ok) {
                    return false;
                }
            }
            previousIndex = idx;
            previousValue = value;
        }
        return true;
    }

    static void show(String name, int[] input) {
        Result lis = fast(input, false);
        Result lnds = fast(input, true);
        Result lisSlow = quadratic(input, false);
        Result lndsSlow = quadratic(input, true);

        if (lis.length() != lisSlow.length()
                || lnds.length() != lndsSlow.length()
                || !validSubsequence(input, lis, false)
                || !validSubsequence(input, lnds, true)
                || !validSubsequence(input, lisSlow, false)
                || !validSubsequence(input, lndsSlow, true)) {
            throw new AssertionError(
                    "DP and binary search results disagree");
        }

        System.out.println(name + " LIS: length=" + lis.length()
                + ", indices=" + Arrays.toString(lis.indices())
                + ", values=" + Arrays.toString(lis.values()));
        System.out.println(name + " LNDS: length=" + lnds.length()
                + ", indices=" + Arrays.toString(lnds.indices())
                + ", values=" + Arrays.toString(lnds.values()));
    }

    public static void main(String[] args) {
        show("Example", new int[]{3, 1, 2, 2, 4, 3, 5});
        show("Duplicates", new int[]{2, 2, 2, 2});
        show("Decreasing", new int[]{9, 7, 5, 3});
        show("Increasing", new int[]{-3, -1, 0, 2});
        show("Extremes", new int[]{
                Integer.MAX_VALUE, Integer.MIN_VALUE,
                Integer.MIN_VALUE, 0, Integer.MAX_VALUE
        });
        show("Negatives", new int[]{-1, -3, -2, -2, 0});
        show("Empty", new int[0]);
        show("Single", new int[]{42});
        show("Mixed", new int[]{0, 0, 1, 0, 1});
    }
}
```

Lệnh biên dịch/chạy với JDK 17 trở lên:

```bash
javac LongestMonotoneSubsequence.java
java LongestMonotoneSubsequence
```

**Stdout chính xác:**

```text
Example LIS: length=4, indices=[1, 3, 5, 6], values=[1, 2, 3, 5]
Example LNDS: length=5, indices=[1, 2, 3, 5, 6], values=[1, 2, 2, 3, 5]
Duplicates LIS: length=1, indices=[3], values=[2]
Duplicates LNDS: length=4, indices=[0, 1, 2, 3], values=[2, 2, 2, 2]
Decreasing LIS: length=1, indices=[3], values=[3]
Decreasing LNDS: length=1, indices=[3], values=[3]
Increasing LIS: length=4, indices=[0, 1, 2, 3], values=[-3, -1, 0, 2]
Increasing LNDS: length=4, indices=[0, 1, 2, 3], values=[-3, -1, 0, 2]
Extremes LIS: length=3, indices=[2, 3, 4], values=[-2147483648, 0, 2147483647]
Extremes LNDS: length=4, indices=[1, 2, 3, 4], values=[-2147483648, -2147483648, 0, 2147483647]
Negatives LIS: length=3, indices=[1, 3, 4], values=[-3, -2, 0]
Negatives LNDS: length=4, indices=[1, 2, 3, 4], values=[-3, -2, -2, 0]
Empty LIS: length=0, indices=[], values=[]
Empty LNDS: length=0, indices=[], values=[]
Single LIS: length=1, indices=[0], values=[42]
Single LNDS: length=1, indices=[0], values=[42]
Mixed LIS: length=2, indices=[3, 4], values=[0, 1]
Mixed LNDS: length=4, indices=[0, 1, 3, 4], values=[0, 0, 0, 1]
```

**Phân tích output:**

- `Example`: khác nhau duy nhất ở việc LNDS được phép lấy cả hai số 2. Hai dãy được truy vết theo thứ tự chỉ số gốc.
- `Duplicates`: LIS có độ dài 1; code tails khi gặp số 2 bằng nhau có thể dùng **chỉ số cuối** vì mỗi lần ghi đè đuôi. LNDS giữ cả bốn bản sao, dài 4.
- `Decreasing`: không có hai phần tử theo thứ tự chỉ số thỏa tăng hoặc không giảm, nên độ dài 1. Mã chọn phần tử cuối theo cách cập nhật đuôi, vẫn đúng.
- `Increasing`: mọi phần tử của input nằm trong dãy con tối ưu cho cả hai biến thể.
- `Extremes`: mã dùng so sánh số nguyên trực tiếp, nên xử lý an toàn cả `Integer.MIN_VALUE` và `Integer.MAX_VALUE`.
- `Negatives`: số âm có thể nằm trong dãy con và được so sánh bình thường.
- `Empty`: hai hàm trả `Result(0, [], [])`; không được truy cập tailsIndex[-1] khi n=0.
- `Mixed`: LNDS có thể dùng ba số 0 trước số 1, trong khi LIS không được chọn quá một số 0.

**Kiểm tra chéo trong chương trình:** Hàm `show` gọi cả DP O(n²) lẫn tails O(n log n), xác minh **cùng độ dài tối ưu** và kiểm tra dãy con theo các chỉ số gốc. Hai cách có thể chọn những dãy con khác nhau nhưng cùng tối ưu; chương trình chỉ so độ dài, không đòi mảng chỉ số giống nhau.

### Vì sao parent được gán trước khi ghi đè tailsIndex[pos]?

Trong code:

```java
if (pos > 0) {
    parent[i] = tailsIndex[pos - 1];
}
tailsIndex[pos] = i;
```

Bước đầu phải đọc đầu mút của dãy độ dài pos **đã có trong tiền tố**, rồi mới cập nhật đại diện dãy độ dài pos+1. Nếu ghi đè sai vị trí trước khi tính predecessor, có nguy cơ tự trỏ đến i hoặc dùng một đại diện không thuộc quá khứ. Hai dòng đúng thứ tự đảm bảo `parent[i] < i` và cho chuỗi truy vết hợp lệ.

## 11. Những trường hợp biên quan trọng

| Trường hợp | Cách xử lý đúng |
| --- | --- |
| Mảng rỗng | LIS=LNDS=0, kết quả là dãy rỗng |
| Một phần tử | Độ dài 1 |
| Tất cả phần tử bằng nhau | LIS=1, LNDS=n nếu n>0 |
| Dãy tăng nghiêm ngặt | LIS=LNDS=n |
| Dãy giảm nghiêm ngặt | LIS=LNDS=1 nếu n>0 |
| Số âm và 0 | Không có quy tắc đặc biệt; so sánh trực tiếp |
| `Integer.MIN_VALUE`, `Integer.MAX_VALUE` | Không so sánh bằng phép trừ dễ tràn |
| Nhiều LIS/LNDS tối ưu | Trả bất kỳ một dãy hợp lệ nếu không có tiêu chí phụ |
| Chỉ cần độ dài | Không nhất thiết phải lưu parent |
| Muốn số lượng LIS | Bài toán khác: cần thêm cách đếm, không lấy trực tiếp từ tails |
| Muốn tổng lớn nhất trên dãy con tăng | Bài toán khác: độ dài và tổng là hai mục tiêu khác nhau |
| Muốn đoạn con liên tục tăng dài nhất | Bài toán khác: thường quét một lần O(n) |

### LIS không giống LCS

**LIS** trên một mảng số chọn dãy con theo quan hệ tăng của **giá trị**. **LCS** (*longest common subsequence*) giữa **hai** dãy chọn dãy con có **cùng giá trị theo cùng thứ tự** ở hai đầu vào. Hai bài có DP khác nhau. Có thể giảm một số trường hợp của LIS về LCS với dãy đã sắp và loại trùng thích hợp, nhưng không nên xem đó là cách mặc định hoặc nhầm các định nghĩa khi có phần tử lặp.

## 12. Tùy chọn mở rộng và lựa chọn thuật toán

### Khi n nhỏ

Nếu n chỉ vài trăm đến vài nghìn và thời gian cho phép, DP O(n²) thường dễ trình bày, dễ kiểm chứng, dễ thay đổi điều kiện chuyển. Nó đặc biệt hữu ích khi bài có thêm ràng buộc khiến chiến lược tails tối ưu **không còn áp dụng trực tiếp**.

### Khi n lớn

Nếu chỉ quan tâm LIS/LNDS thuần túy theo thứ tự giá trị, cách tails + binary search có độ phức tạp O(n log n) và bộ nhớ O(n), phù hợp với n lớn hơn đáng kể. Cần hiểu rõ lower_bound/upper_bound và việc parent lưu **chỉ số của phần tử trong dữ liệu gốc**.

### Khi cần đếm số dãy con tối ưu

Số lượng LIS là một bài toán khác: có thể dùng DP lưu **cặp (độ dài tốt nhất, số cách)** theo từng vị trí, cộng số cách của các tiền nhiệm dẫn tới cùng độ dài tốt nhất. Cần quy ước đếm theo **chuỗi chỉ số** hay theo **chuỗi giá trị phân biệt**: nếu giá trị lặp, hai định nghĩa cho kết quả khác nhau.

Một số bài đếm LIS có thể tăng tốc với **nén tọa độ + Fenwick tree / segment tree**, lưu cặp (bestLength, count) cho các giá trị nhỏ hơn x. Trong trường hợp strict phải truy vấn các giá trị **nhỏ hơn x**, trong LNDS truy vấn **không lớn hơn x**; cần cẩn thận cách cập nhật khi có nhiều giá trị bằng nhau. Không được kết luận công thức đếm số cách chỉ từ kích thước `tails`.

### Khi tìm dãy con giảm hoặc không tăng

Có thể đổi hướng so sánh:

- **LDS (giảm nghiêm ngặt):** phần tử sau phải < phần tử trước.
- **LNIS (không tăng):** phần tử sau phải <= phần tử trước.

Một cách quy đổi trên số nguyên là đổi phép so sánh thay vì **lấy số đối `-x`**, bởi `-Integer.MIN_VALUE` bị tràn kiểu int và không tạo giá trị đối hợp lệ. Nếu chọn quy đổi bằng biến đổi khóa, phải xử lý miền giá trị cẩn thận.

### Mục tiêu có ràng buộc phụ

Nếu đề thêm điều kiện giới hạn tổng chi phí, khoảng cách chỉ số, số phần tử được chọn, hoặc yêu cầu tối đa tổng thay vì độ dài, trạng thái DP có thể cần thay đổi. Kỹ thuật tails phát huy khi tính chất “đuôi nhỏ hơn thì không kém cho mọi tương lai” còn đúng; nếu thêm ràng buộc làm tính chất này sai, không thể bê nguyên thuật toán O(n log n) vào bài mới.

## 13. Những lỗi thường gặp

1. **Dùng đoạn con liên tiếp thay vì dãy con.** LIS được phép bỏ qua vị trí, nhưng không được đảo thứ tự chỉ số.
2. **Nhầm `<` và `<=` trong DP.** LIS nghiêm ngặt loại hai giá trị bằng nhau; LNDS cho phép.
3. **Dùng lower_bound cho cả LNDS.** Khi có phần tử bằng nhau, điều này không tăng độ dài và vô tình tính LIS.
4. **Dùng upper_bound cho LIS.** Điều này cho phép các giá trị bằng nhau nối tiếp và có thể tăng độ dài sai.
5. **Coi tails là dãy con cần trả.** Tails lưu đuôi tốt nhất của **các dãy khác nhau**, không nhất thiết tương ứng một dãy con thật.
6. **Không lưu parent và tailsIndex khi đề yêu cầu xuất dãy.** Chỉ lưu giá trị tails thường không đủ để truy vết chính xác chỉ số gốc.
7. **Lưu parent[i] bằng giá trị thay vì chỉ số.** Khi giá trị trùng, không thể phân biệt vị trí; nên lưu chỉ số.
8. **Không xử lý n=0.** Dùng `tailsIndex[length−1]` với length=0 dẫn tới truy cập chỉ số âm.
9. **Chỉ lấy dp[n−1] làm đáp án.** Dãy con tối ưu có thể kết thúc trước vị trí cuối; phải lấy max mọi dp[i].
10. **Cập nhật dp[i] khi chưa có j hợp lệ.** dp[i] khởi tạo 1 cho dãy chỉ gồm a[i], không được bằng 0.
11. **Coi mọi subsequence cùng độ dài có thể đổi chỗ tùy ý.** Tính đúng phụ thuộc thứ tự chỉ số gốc, không được sort đầu vào trước khi chọn.
12. **Đếm số cách bằng length của tails.** length chỉ là độ dài tối đa, không cho biết số dãy con tối ưu.
13. **Quên phân biệt chỉ số và giá trị ở kết quả.** Khi nhiều giá trị bằng nhau, đầu ra theo chỉ số có thể khác nhau dù dãy giá trị giống nhau.
14. **Tự cho rằng mã tìm dãy nhỏ nhất theo thứ tự từ điển.** Thuật toán cơ bản trả một dãy tối ưu, không cam kết tiêu chí phụ nếu chưa thiết kế tie-break.
15. **So sánh bằng hiệu hai int.** `a[i]-a[j]` có thể tràn; dùng dấu so sánh trực tiếp.
16. **Dùng thư viện binarySearch không hiểu quy tắc bản sao.** Một hàm tìm phần tử bằng có thể trả vị trí bất kỳ giữa các bản sao; LIS/LNDS cần biên đầu tiên >= hoặc > chính xác.
17. **Gán parent từ một đuôi không tồn tại.** Chỉ gán `parent[i]=tailsIndex[pos−1]` khi pos>0.
18. **Ghi đè phần tử đầu vào khi cập nhật tails.** Cập nhật bảng chỉ số đuôi hoặc bảng values, không thay đổi `a`.
19. **Không thử dãy toàn giá trị bằng nhau.** Đây là ca dễ phát hiện việc lẫn LIS và LNDS.
20. **Không chứng minh chiến lược chọn đuôi nhỏ nhất.** Việc giữ đuôi nhỏ hơn an toàn vì nó không làm mất khả năng nối phần tử mới phù hợp, nhưng lập luận này không tự đúng cho mọi bài có ràng buộc.
21. **Nhầm chi phí DP O(n²) với tails O(n log n).** Hai cách có cùng mục tiêu nhưng độ phức tạp khác nhau.
22. **Bỏ qua việc truy vết cũng cần bộ nhớ.** Nếu trả chỉ số gốc, cần parent hoặc một cách tái dựng khác; chỉ cần length thì đơn giản hơn.
23. **Gọi dãy không giảm là tăng nghiêm ngặt.** Tên/định nghĩa trong đề phải quyết định dấu, không đoán từ tên hàm.
24. **Chọn một kết quả tối ưu rồi khẳng định nó là duy nhất.** Có thể tồn tại nhiều dãy con có cùng độ dài tối đa.

## 14. Bài tập và đáp án

**Bài 1.** Với `a=[3,1,2,2,4,3,5]`, LIS và LNDS dài bao nhiêu? Hãy nêu một dãy con cho mỗi loại.

**Đáp án:** LIS=4, ví dụ `[1,2,3,5]`. LNDS=5, ví dụ `[1,2,2,3,5]`. Hai số 2 bằng nhau chỉ được cùng xuất hiện trong LNDS.

**Bài 2.** `a=[2,2,2,2]`. Vì sao LIS=1 nhưng LNDS=4?

**Đáp án:** Mọi cặp giá trị liên tiếp đều bằng nhau. Quan hệ `x<y` không cho ghép hai giá trị bằng, còn `x<=y` cho phép. LNDS lấy toàn bộ bốn phần tử.

**Bài 3.** Viết công thức dp[i] cho LIS.

**Đáp án:** `dp[i]=1+max(dp[j])` trên mọi j<i có a[j]<a[i], hoặc 1 nếu không có j phù hợp. Kết quả là max dp[i], với mảng rỗng là 0.

**Bài 4.** Trong giải pháp tails, khi xử lý x có giá trị bằng phần tử cuối của tails, điều gì xảy ra?

**Đáp án:** Với LIS, lower_bound trả vị trí của phần tử **>=x**, nên thay ở vị trí ấy, **không kéo dài chỉ vì bằng nhau**. Với LNDS, upper_bound tìm phần tử đầu tiên **>x**; nếu x bằng tail cuối, nó được thêm sau và length có thể tăng.

**Bài 5.** Dữ liệu `[1,6,2,3,4,0]` có tails cuối [0,2,3,4] (strict). Có được in tails như một LIS không?

**Đáp án:** Không. Số 0 xuất hiện sau các số 2,3,4 nên [0,2,3,4] không phải dãy con theo thứ tự gốc. Dãy [1,2,3,4] mới là một LIS thật; cần parent để truy vết.

**Bài 6.** Với n=100.000, DP hai vòng lặp cần cỡ bao nhiêu lượt kiểm tra cặp trước khi tính điều kiện tăng?

**Đáp án:** Khoảng n(n−1)/2 ≈ **4.999.950.000** cặp, rất lớn. Tails + binary search O(n log n) phù hợp hơn nếu bài là LIS/LNDS cơ bản.

**Bài 7.** Tại sao kỹ thuật tails lưu đuôi nhỏ nhất của mỗi độ dài mà không lưu đuôi lớn nhất?

**Đáp án:** Với hai dãy cùng độ dài, dãy có đuôi nhỏ hơn có thể nối được với **ít nhất** những giá trị tương lai mà dãy có đuôi lớn hơn nối được. Do đó giữ đuôi nhỏ hơn không mất cơ hội tìm độ dài tối đa.

**Bài 8.** Với `a=[9,7,5,3]`, LIS/LNDS đều bằng mấy? Trong code fast, giá trị nào có thể được dùng làm dãy con độ dài 1 cuối cùng?

**Đáp án:** Đều bằng 1. Mã luôn thay đuôi độ dài 1 bằng giá trị nhỏ hơn, nên sau khi duyệt xong, dãy con trả có thể là [3] tại chỉ số 3, vẫn tối ưu.

**Bài 9.** Vì sao hai hàm O(n²) và O(n log n) không nhất thiết trả đúng cùng bộ chỉ số?

**Đáp án:** Bài toán có thể có nhiều lời giải tối ưu; chính sách chọn predecessor và thay đuôi khác nhau tạo dãy con khác nhau, miễn là độ dài và điều kiện giá trị/chỉ số đều đúng.

**Bài 10.** Cho `a=[0,0,1,0,1]`. Độ dài LIS và LNDS là bao nhiêu?

**Đáp án:** LIS=2, ví dụ [0,1]. LNDS=4, ví dụ [0,0,0,1] với chỉ số [0,1,3,4]. Các giá trị 0 bằng nhau được nối trong LNDS.

**Bài 11.** Với hai đầu vào có cùng tập giá trị nhưng thứ tự khác, LIS có thể khác nhau không?

**Đáp án:** Có. `[1,2,3]` có LIS=3, còn `[3,2,1]` có LIS=1; LIS phụ thuộc **thứ tự xuất hiện**, không chỉ vào đa tập giá trị.

**Bài 12.** Bài toán đòi “dãy con tăng có **tổng** lớn nhất” thay vì “nhiều phần tử nhất”; có thể dùng nguyên công thức dp[i] đếm độ dài không?

**Đáp án:** Không. Mục tiêu đã đổi, nên phải thiết kế giá trị DP khác: ví dụ tổng tối đa kết thúc tại i và chuyển qua tiền nhiệm hợp lệ, xử lý riêng trường hợp tổng âm và yêu cầu dãy có ít nhất một phần tử. Độ dài lớn nhất không đồng nghĩa tổng lớn nhất.

## Ghi nhớ

**LIS** yêu cầu dấu tăng **<**, **LNDS** cho phép **<=**; cả hai là **dãy con**, không phải đoạn con liên tiếp. DP O(n²) dùng `dp[i]` = độ dài tốt nhất kết thúc tại i, xét mọi j<i rồi truy vết `parent`. Cách nhanh O(n log n) giữ **đuôi kết thúc nhỏ nhất cho mỗi độ dài** và dùng binary search: LIS tìm **vị trí đầu tiên có đuôi ≥ x** (*lower bound*), LNDS tìm **đầu tiên có đuôi > x** (*upper bound*). **Đừng in mảng tails như một dãy con**; muốn khôi phục chỉ số/giá trị thật phải giữ `tailsIndex` và `parent`. Nhiều phần tử trùng là bộ kiểm tra quan trọng nhất để phân biệt đúng hai phiên bản.
