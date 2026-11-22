# Bucket sort và giả thiết về phân bố dữ liệu

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích **bucket sort (sắp xếp theo thùng)**: ánh xạ khóa vào các khoảng giá trị, sắp xếp từng thùng và nối kết quả.
2. Phân biệt **đúng đắn của thuật toán** với **giả thiết phân bố dữ liệu để đạt hiệu năng tốt**.
3. Thiết kế hàm ánh xạ phần tử vào thùng với biên rõ ràng; xử lý giá trị biên, âm, trùng, mảng rỗng và tính ổn định.
4. Phân tích số lượng phần tử trong mỗi thùng, chi phí dự kiến khi đầu vào độc lập và phân bố đều, cùng **trường hợp xấu khi dữ liệu lệch mạnh**.
5. Cài đặt bucket sort trong Java 17+ cho một miền số nguyên đã quy định, kiểm thử và so sánh với counting sort, radix sort và sắp xếp so sánh.

## 1. Bucket sort là gì?

Bucket sort là một kỹ thuật thuộc nhóm **sắp xếp phân phối (distribution sorting)**. Thay vì so sánh trực tiếp tất cả phần tử với nhau trong một cấu trúc duy nhất, ta sử dụng **thông tin về miền giá trị** để chia dãy thành nhiều **thùng (bucket)**.

Quy trình tiêu biểu:

1. **Chọn miền khóa và các khoảng thùng.** Ví dụ miền số nguyên từ 0 đến 99 được chia thành năm khoảng gần bằng nhau.
2. **Phân phối:** với mỗi phần tử đầu vào, tính chỉ số thùng rồi đưa phần tử vào thùng đó.
3. **Sắp xếp nội bộ:** sắp từng thùng bằng một thuật toán thích hợp, thường là insertion sort khi mỗi thùng dự kiến chứa ít phần tử.
4. **Ghép kết quả:** duyệt các thùng theo thứ tự giá trị tăng dần và nối các phần tử đã sắp trong mỗi thùng.

Sơ đồ:

```text
Input: [42, 5, 19, 80, 62, 41, 21, 99, 40, 20]
                         |
                Phân phối theo khóa
                         |
Bucket 0 [0,20):     [5, 19]
Bucket 1 [20,40):    [21, 20]
Bucket 2 [40,60):    [42, 41, 40]
Bucket 3 [60,80):    [62]
Bucket 4 [80,100):   [80, 99]
                         |
                Sắp xếp từng bucket
                         |
Bucket 0: [5, 19]
Bucket 1: [20, 21]
Bucket 2: [40, 41, 42]
Bucket 3: [62]
Bucket 4: [80, 99]
                         |
                     Nối lại
                         v
[5, 19, 20, 21, 40, 41, 42, 62, 80, 99]
```

Hai sự thật cần tách biệt:

- **Đúng đắn:** nếu tất cả phần tử trong thùng đứng trước không lớn hơn tất cả phần tử trong thùng đứng sau, đồng thời mỗi thùng đã được sắp xếp đúng, thì kết quả nối các thùng có thứ tự toàn cục.
- **Hiệu năng:** nếu phần tử được phân bố tương đối đều vào nhiều thùng, các bài toán sắp xếp nội bộ trở nên nhỏ. Nếu gần như mọi phần tử rơi vào cùng một thùng, phép phân phối không giúp giảm đáng kể chi phí sắp xếp nội bộ.

Vì vậy, tên “bucket sort” không tự bảo đảm thời gian chạy tuyến tính. **Mô hình phân bố dữ liệu, số thùng và thuật toán sắp xếp trong thùng** quyết định hiệu năng.

## 2. Mô hình bài toán và hợp đồng đầu vào

Trong ví dụ chính, ta xét:

- Mảng `a` có `n` số nguyên, có thể trùng.
- Miền hợp lệ: `0 <= a[i] < B`, với `B` là số nguyên dương.
- Có `k >= 1` thùng đánh chỉ số `0, 1, ..., k-1`.
- Yêu cầu đầu ra là mảng mới chứa đúng các giá trị ban đầu với đúng số lần xuất hiện, sắp tăng dần không giảm.
- Mảng gốc giữ nguyên (chương trình Java minh họa dùng mảng kết quả mới).
- Nếu phần tử không thuộc miền đã công bố thì báo lỗi, **không** âm thầm bỏ qua hoặc ép vào một thùng sai.

Công thức ánh xạ chỉ số thùng:

\[
b(x)=\left\lfloor\frac{kx}{B}\right\rfloor,\qquad 0\le x<B.
\]

Vì `0 <= x < B` nên `0 <= kx/B < k`, do đó luôn có `0 <= b(x) < k`. Đặc biệt, nếu `x=B-1` thì `b(x)` không vượt `k-1`.

Ví dụ `B=100`, `k=5`:

| Chỉ số thùng | Khoảng giá trị của thùng | Một số giá trị |
| ---: | --- | --- |
| 0 | `[0,20)` | 0, 5, 19 |
| 1 | `[20,40)` | 20, 21, 39 |
| 2 | `[40,60)` | 40, 41, 42, 59 |
| 3 | `[60,80)` | 60, 62, 79 |
| 4 | `[80,100)` | 80, 99 |

Với `B` không chia hết cho `k`, các khoảng chứa số nguyên có thể lệch nhau một ít về kích thước. Công thức vẫn đúng vì chỉ số thùng tăng **không giảm** khi `x` tăng.

**Không được lấy tùy tiện `b(x)=x/k`**, trừ khi `k` đồng thời được định nghĩa là **bề rộng** chứ không phải **số thùng**. Trong bài này, `k` luôn biểu thị **số lượng thùng**, còn `B` là giới hạn trên không bao gồm của miền giá trị.

### Ánh xạ cho số thực chuẩn hóa

Dạng kinh điển trong sách thuật toán xét các khóa thực `x` nằm trong khoảng nửa mở `[0,1)`:

\[
b(x)=\lfloor kx\rfloor.
\]

Ví dụ `k=5` thì `x=0.62` rơi vào thùng `3`, vì `floor(5 * 0.62)=3`.

**Giới hạn `1` không thuộc miền `[0,1)`.** Nếu `x=1.0` mà vẫn dùng công thức này, chỉ số thu được là `k` — nằm ngoài mảng thùng `0..k-1`. Phải chọn một hợp đồng rõ ràng: loại giá trị `1`, hoặc dùng miền đóng `[0,1]` và xử lý riêng giá trị tại cận trên. Không âm thầm dùng phép nhân rồi truy cập phần tử vượt giới hạn.

Với miền tổng quát `[min, max)` và `max > min`, công thức lý tưởng cho số thực là:

\[
b(x)=\left\lfloor k\,\frac{x-min}{max-min}\right\rfloor.
\]

Khi lập trình cần kiểm tra các giới hạn, phép toán tràn, độ chính xác số thực và `NaN`/vô cực. Với số nguyên, nên dùng kiểu rộng khi tính tử số trước phép chia để tránh tràn `int`.

## 3. Giả mã thuật toán

Giả sử có một hàm `bucketIndex(x)` bảo đảm tính **đơn điệu theo khóa**: nếu `x < y` thì `bucketIndex(x) <= bucketIndex(y)`; quan trọng hơn, nếu hai phần tử ở hai thùng khác nhau thì khóa trong thùng có chỉ số nhỏ hơn phải đứng trước khóa trong thùng có chỉ số lớn hơn.

```text
BUCKET_SORT(a, B, k):
    yêu cầu:
        a không null
        B > 0, k >= 1
        mọi phần tử x thỏa 0 <= x < B

    tạo k thùng rỗng buckets[0..k-1]

    for mỗi x trong a theo thứ tự đầu vào:
        index <- floor(k * x / B)
        đưa x vào cuối buckets[index]

    for index từ 0 đến k-1:
        sắp xếp tăng dần buckets[index]

    tạo result là mảng mới có cùng độ dài a
    for index từ 0 đến k-1:
        chép các phần tử của buckets[index] vào cuối result

    return result
```

Với mô hình thùng là danh sách động, việc **đưa vào cuối thùng** có thể thực hiện trong thời gian khấu hao hằng số mỗi phần tử. Trong phân tích chuẩn, ta coi chi phí phân phối và ghép là `O(n+k)`, với giả định cấp phát/ghi danh sách hợp lý. Nếu chọn cấu trúc thùng khác, phải phân tích lại chi phí thao tác tương ứng.

**Thuật toán sắp xếp nội bộ không bắt buộc là insertion sort.** Bạn có thể chọn insertion sort cho thùng nhỏ, một thuật toán `O(m log m)` cho thùng lớn, hoặc một chiến lược thích nghi. Khi thay cách sắp xếp thùng, **kết quả đúng đắn** vẫn theo cùng lập luận, nhưng **độ phức tạp và tính ổn định** phải xét lại.

## 4. Vết chạy đầy đủ theo năm thùng

Xét:

```text
a = [42, 5, 19, 80, 62, 41, 21, 99, 40, 20]
B = 100
k = 5
```

Với công thức `b(x) = floor(5*x/100)`:

| Phần tử `x` | Chỉ số `b(x)` | Thùng |
| ---: | ---: | --- |
| 42 | 2 | Thùng 2 |
| 5 | 0 | Thùng 0 |
| 19 | 0 | Thùng 0 |
| 80 | 4 | Thùng 4 |
| 62 | 3 | Thùng 3 |
| 41 | 2 | Thùng 2 |
| 21 | 1 | Thùng 1 |
| 99 | 4 | Thùng 4 |
| 40 | 2 | Thùng 2 |
| 20 | 1 | Thùng 1 |

Kết thúc pha phân phối:

```text
bucket[0] = [5, 19]
bucket[1] = [21, 20]
bucket[2] = [42, 41, 40]
bucket[3] = [62]
bucket[4] = [80, 99]
```

Pha sắp xếp nội bộ bằng insertion sort:

```text
bucket[0] = [5, 19]
bucket[1] = [20, 21]
bucket[2] = [40, 41, 42]
bucket[3] = [62]
bucket[4] = [80, 99]
```

Ghép lần lượt từ thùng 0 đến thùng 4:

```text
result = [5, 19, 20, 21, 40, 41, 42, 62, 80, 99]
```

Không cần so sánh trực tiếp phần tử 19 ở thùng 0 với 20 ở thùng 1, vì **ranh giới thùng đã bảo đảm** mọi khóa thùng 0 nhỏ hơn mọi khóa thùng 1. Đó là lợi ích của việc sử dụng thông tin miền giá trị: các thao tác so sánh nội bộ chỉ diễn ra giữa những phần tử rơi vào cùng thùng.

## 5. Chứng minh tính đúng

Cần chứng minh **cả thứ tự** lẫn **bảo toàn đa tập phần tử**.

### 5.1. Không mất, thêm hoặc thay đổi phần tử

Mỗi phần tử đầu vào được duyệt một lần và đưa vào **đúng một thùng**. Điều kiện `0<=b(x)<k` bảo đảm phần tử có thùng hợp lệ. Sắp xếp nội bộ chỉ thay đổi vị trí, không thay đổi số lần xuất hiện của mỗi giá trị. Giai đoạn ghép chép tất cả phần tử của từng thùng đúng một lần. Vì vậy dãy đầu ra là **một hoán vị (theo đa tập)** của dãy đầu vào.

### 5.2. Thứ tự trong từng thùng

Giả sử thuật toán nội bộ sắp thùng `j` theo cùng quan hệ tăng dần của khóa. Khi hoàn tất pha này, mọi cặp phần tử liên tiếp bên trong thùng `j` đều không giảm. Điều này phải được bảo đảm bởi thuật toán nội bộ, không tự suy ra từ phép phân phối.

### 5.3. Thứ tự giữa các thùng

Với công thức `b(x)=floor(kx/B)`, nếu `b(x)<b(y)` thì phải có `x<y`. Thật vậy, giả sử ngược lại `x>=y`; do phép nhân với `k/B>0` và hàm floor không giảm, sẽ có `b(x)>=b(y)`, mâu thuẫn.

Bởi vậy mọi phần tử của thùng có chỉ số nhỏ hơn đều **nhỏ hơn** mọi phần tử của thùng có chỉ số lớn hơn. Sau khi các thùng được sắp riêng, nối chúng theo thứ tự chỉ số tăng dần cho dãy tăng dần toàn cục.

Kết hợp với tính bảo toàn, ta có đáp án đúng cho mọi đầu vào hợp lệ, **không cần giả định dữ liệu ngẫu nhiên hoặc phân bố đều**.

### 5.4. Tính dừng

Giai đoạn phân phối duyệt hữu hạn `n` phần tử; có `k` thùng, mỗi thùng chứa hữu hạn phần tử; insertion sort nội bộ có các vòng lặp chỉ số tiến hoặc giảm có giới hạn; giai đoạn ghép chép hữu hạn `n` phần tử. Vì vậy chương trình dừng.

**Kết luận quan trọng:** giả thiết phân bố đều giúp chứng minh **hiệu năng kỳ vọng**, không phải điều kiện cần để bảo đảm **tính đúng** của bucket sort.

## 6. Chi phí theo số phần tử trong từng thùng

Gọi:

- `n`: số phần tử đầu vào.
- `k`: số thùng.
- `b_j`: số phần tử rơi vào thùng thứ `j`, với `0<=j<k`.
- Luôn có `b_0+b_1+...+b_{k-1}=n`.

Giả sử sắp mỗi thùng bằng insertion sort, có chặn trên `O(b_j^2)` trên thùng chứa `b_j` phần tử. Pha khởi tạo thùng tốn `O(k)`, phân phối tốn `O(n)` và ghép tốn `O(n)`.

Do đó:

\[
T(n,k)=O\left(n+k+\sum_{j=0}^{k-1} b_j^2\right).
\]

Đây là **một chặn theo lượng phần tử thực tế trong từng thùng**. Nó giải thích rõ tại sao phải quan tâm đến phân bố:

- Nếu nhiều thùng đều nhỏ, tổng các bình phương `b_j^2` nhỏ.
- Nếu một thùng chứa gần như toàn bộ `n` phần tử, `b_j^2` có thể tới `n^2`.
- Nếu chọn quá nhiều thùng, phần `O(k)` để khởi tạo và duyệt thùng cũng tốn đáng kể.

### Phân bố cân bằng

Giả sử `n` phần tử được chia gần đều vào `k` thùng, mỗi thùng có xấp xỉ `n/k` phần tử. Khi ấy:

\[
\sum b_j^2 \approx k\left(\frac nk\right)^2=\frac{n^2}{k}.
\]

Chặn chi phí tương ứng:

\[
O\left(n+k+\frac{n^2}{k}\right).
\]

Nếu `k` cùng bậc với `n` và mỗi thùng chứa số phần tử bị chặn bởi một hằng số, thời gian là `O(n)`. Nhưng **không có chuyện một dãy bất kỳ tự động tạo ra cân bằng** chỉ vì ta chọn `k=n`: mọi phần tử vẫn có thể rơi vào một thùng.

### Trường hợp xấu với insertion sort

Nếu gần như tất cả phần tử rơi vào một thùng và thứ tự bên trong thùng là đảo ngược với các khóa phân biệt, insertion sort trên thùng đó có thể phải thực hiện `Theta(n^2)` phép so sánh/dịch chuyển.

Ví dụ với `B=100`, `k=5`:

```text
Input = [19, 18, 17, 16, 15]
Mọi giá trị đều thuộc bucket[0], vì đều ở [0,20).
Bucket[0] trước sắp = [19,18,17,16,15].
```

Thuật toán thực chất phải insertion sort một nhóm năm phần tử đảo ngược. Ví dụ mở rộng cho kích thước tùy ý: lấy `B=n^2`, `k=n` và dãy đầu vào `[n-1,n-2,...,0]` với `n>=2`; tất cả vẫn rơi vào thùng 0, vì `floor(nx/n^2)=floor(x/n)=0` khi `0<=x<n`. Khi đó chi phí sắp thùng 0 bằng insertion sort là `Theta(n^2)`, **dù số thùng bằng số phần tử**.

Vì vậy với insertion sort nội bộ, trường hợp xấu tổng quát có chặn **`O(n^2+k)`**, và có những họ đầu vào đạt phần bậc hai đó. Không được phát biểu “bucket sort luôn `O(n)`” mà không nêu mô hình phân bố và lựa chọn số thùng.

### Bộ nhớ phụ

Nếu dùng `k` danh sách thùng và lưu lại toàn bộ `n` phần tử trong các danh sách, cần `O(n+k)` chỗ lưu cho thùng và phần tử. Chương trình bên dưới còn tạo mảng kết quả độ dài `n`; tổng vẫn là `O(n+k)` bộ nhớ phụ, không phải `O(1)`.

Chi phí cấp phát của một cấu trúc danh sách cụ thể, boxing `int` thành `Integer` trong Java và overhead đối tượng có thể lớn hơn nhiều so với số đếm phần tử đơn giản, nhưng không làm thay đổi biểu thức bậc `O(n+k)` theo mô hình chuẩn.

## 7. Giả thiết nào giúp thời gian kỳ vọng tuyến tính?

Một phân tích kinh điển giả sử:

1. Mỗi khóa `X_i` được lấy **độc lập** với các khóa khác.
2. Mỗi `X_i` có phân bố **đều** trên khoảng `[0,1)`.
3. Dùng `k` khoảng con có độ rộng bằng nhau; mỗi khóa có xác suất `1/k` đi vào một thùng.
4. Sắp từng thùng bằng insertion sort.
5. Chi phí phân phối và chèn vào cuối một danh sách thùng được tính như ở mục 6.

Khi đó số phần tử `b_j` của từng thùng có phân bố nhị thức `Binomial(n,1/k)`. Mặc dù các `b_j` không độc lập với nhau vì tổng luôn bằng `n`, ta **không cần chúng độc lập** để tính kỳ vọng tổng bình phương.

Với `b_j = sum_i I(X_i rơi vào thùng j)` và các chỉ báo của **những phần tử khác nhau** độc lập:

\[
\mathbb E[b_j^2]
 = \mathbb E[b_j]+\mathbb E[b_j(b_j-1)]
 =\frac nk+\frac{n(n-1)}{k^2}.
\]

Cộng theo `k` thùng:

\[
\mathbb E\left[\sum_{j=0}^{k-1} b_j^2\right]
 =n+\frac{n(n-1)}{k}.
\]

Do đó:

\[
\mathbb E[T(n,k)]
=O\left(n+k+\frac{n^2}{k}\right).
\]

Nếu chọn `k=n` với `n>=1`:

\[
\mathbb E\left[\sum b_j^2\right]=2n-1,
\qquad
\mathbb E[T(n,n)]=O(n).
\]

Đó là cơ sở của câu “bucket sort có thể đạt **thời gian kỳ vọng tuyến tính**”.

**Không được đánh tráo giả thiết:** nếu mỗi phần tử có phân bố đều nhưng chúng **phụ thuộc hoàn toàn**, chẳng hạn mọi phần tử có cùng một giá trị ngẫu nhiên `U`, thì các thùng không nhận các mẫu độc lập. Tất cả phần tử có thể rơi vào cùng một thùng. Phép tính xác suất `1/k^2` cho hai phần tử cùng vào một thùng không còn hợp lệ. Do đó “đều” mà không nói rõ tính độc lập là chưa đủ cho chứng minh trên.

Một thận trọng khác: `E[T]=O(n)` là một phát biểu về **kỳ vọng trên mô hình dữ liệu**, không bảo đảm mỗi lần chạy đều nhanh; một mẫu hiếm hoặc đầu vào đối kháng vẫn có thể gây lệch lớn.

### Nếu k cố định khi n tăng?

Giả sử chọn đúng năm thùng bất kể số lượng phần tử và các phần tử thực sự được phân phối đều. Khi đó chi phí sắp xếp nội bộ theo chặn bình phương có:

\[
O\left(n+5+\frac{n^2}{5}\right)=O(n^2).
\]

Vì vậy không nên ghi “dữ liệu đều ⇒ `O(n)`” mà bỏ mất điều kiện **số thùng phải tăng phù hợp với `n`** (khi vẫn sử dụng insertion sort). Ví dụ Java dưới đây dùng năm thùng để **quan sát thuật toán trên mảng ngắn**, không nhằm khẳng định năm thùng luôn tối ưu cho mọi kích thước.

## 8. Phân bố không đều: vì sao bucket sort có thể kém?

Dữ liệu trong thực tế hiếm khi có phân bố đều hoàn hảo:

- Điểm thi có thể tập trung quanh vùng trung bình.
- Thời gian phản hồi thường lệch phải, có nhiều giá trị nhỏ và ít ngoại lệ lớn.
- Giá hàng hóa, giao dịch hoặc chiều cao có thể tập trung theo cụm.
- Rất nhiều bản ghi có cùng một khóa, chẳng hạn cùng trạng thái hoặc cùng mã.
- Một tác nhân đối kháng có thể cố ý tạo đầu vào làm quá tải một thùng.

Nếu dùng **những khoảng có độ rộng bằng nhau** mà dữ liệu tập trung ở một vùng hẹp, tải giữa các thùng trở nên mất cân bằng. Một thùng lớn có thể chi phối toàn bộ chi phí.

**Phân biệt hai tình huống:**

1. **Nhiều khóa phân biệt tập trung một thùng, theo thứ tự nghịch:** insertion sort trên thùng dễ chạm trường hợp xấu bậc hai.
2. **Rất nhiều khóa bằng hệt nhau:** chúng cũng tập trung một thùng, nhưng insertion sort với điều kiện dịch `previous > key` thường không phải dịch nhiều khi các khóa hoàn toàn bằng nhau. Vì vậy “mọi phần tử bằng nhau” **không tự chứng minh** một lượt chạy có chi phí `Theta(n^2)`; chặn tổng quát theo `b_j^2` có thể không chặt đối với đầu vào ấy.

Về hiệu năng, vấn đề là **khối lượng và thứ tự dữ liệu trong từng thùng**, không chỉ số thùng khác rỗng. Khi mô phỏng/benchmark, cần xem cả độ lớn thùng và số so sánh/dịch chuyển.

### Biện pháp khi không biết hoặc không có phân bố đều

- **Khảo sát trước:** lấy mẫu dữ liệu và ước lượng phân bố, tỷ lệ trùng, min/max, điểm bất thường; cân nhắc chi phí lấy mẫu.
- **Chia thùng theo quantile (phân vị):** nếu biết phân bố đáng tin, có thể chọn ranh giới sao cho xác suất mỗi thùng gần bằng nhau. Điều này khác với chia đều **giá trị**. Cần bảo đảm ánh xạ thùng vẫn đơn điệu và quản lý các khóa trùng ngay ranh giới.
- **Chọn bộ sắp xếp thùng thích nghi:** nếu thùng lớn, dùng thuật toán có chặn tốt hơn insertion sort thay vì để một thùng trở thành nút thắt.
- **Giới hạn số thùng:** số thùng quá nhiều làm tăng cấp phát và quét, thậm chí phần lớn thùng rỗng.
- **Đổi thuật toán:** nếu không có giả thiết phân bố và cần bảo đảm worst-case `O(n log n)`, cân nhắc một thuật toán sắp xếp so sánh phù hợp; nếu miền khóa nguyên nhỏ, cân nhắc counting sort; nếu khóa có cấu trúc chữ số/byte, cân nhắc radix sort.

Các biện pháp này có chi phí và yêu cầu riêng. Đặc biệt, ước lượng phân vị không tự giải quyết được chuyện **rất nhiều khóa trùng**: không thể vừa chia một giá trị khóa duy nhất vào nhiều khoảng giá trị khác nhau vừa mặc định bảo toàn tính ổn định bằng cách nối thùng, trừ khi có thêm quy tắc phân phối và xử lý hòa chính xác.

## 9. Chương trình Java 17+ hoàn chỉnh

Ví dụ lưu dưới tên **`BucketSortDemo.java`**. Chương trình dùng mảng `int[]` với miền `[0, upperExclusive)`, ánh xạ theo công thức ở mục 2, dùng `ArrayList<Integer>` cho từng thùng và **insertion sort ổn định** trong thùng. Mảng đầu vào không bị thay đổi.

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

public class BucketSortDemo {

    // Stable insertion sort within one bucket.
    private static void insertionSort(List<Integer> bucket) {
        for (int i = 1; i < bucket.size(); i++) {
            int key = bucket.get(i);
            int j = i - 1;

            while (j >= 0 && bucket.get(j) > key) {
                bucket.set(j + 1, bucket.get(j));
                j--;
            }

            bucket.set(j + 1, key);
        }
    }

    // Returns a NEW sorted array; does not modify input.
    public static int[] bucketSort(
            int[] input, int upperExclusive, int bucketCount) {

        if (input == null || upperExclusive <= 0 || bucketCount <= 0) {
            throw new IllegalArgumentException(
                    "Require non-null input, upperExclusive > 0, "
                            + "bucketCount > 0");
        }

        List<List<Integer>> buckets = new ArrayList<>(bucketCount);
        for (int i = 0; i < bucketCount; i++) {
            buckets.add(new ArrayList<>());
        }

        for (int value : input) {
            if (value < 0 || value >= upperExclusive) {
                throw new IllegalArgumentException(
                        "Value outside [0, upperExclusive): " + value);
            }

            // Multiply as long to avoid int overflow.
            int index = (int) (
                    ((long) value * bucketCount) / upperExclusive);
            buckets.get(index).add(value);
        }

        for (List<Integer> bucket : buckets) {
            insertionSort(bucket);
        }

        int[] result = new int[input.length];
        int write = 0;

        for (List<Integer> bucket : buckets) {
            for (int value : bucket) {
                result[write++] = value;
            }
        }

        return result;
    }

    public static void main(String[] args) {
        int[] input = {42, 5, 19, 80, 62, 41, 21, 99, 40, 20};

        int[] result = bucketSort(input, 100, 5);
        System.out.println("Original: " + Arrays.toString(input));
        System.out.println("Sorted: " + Arrays.toString(result));

        int[] duplicateKeys = {50, 0, 50, 99, 0, 0};
        System.out.println("Duplicates: " + Arrays.toString(
                bucketSort(duplicateKeys, 100, 5)));

        System.out.println("Empty: " + Arrays.toString(
                bucketSort(new int[0], 100, 5)));
    }
}
```

Biên dịch/chạy bằng JDK 17 trở lên từ thư mục chứa tệp:

```bash
javac BucketSortDemo.java
java BucketSortDemo
```

Đầu ra chuẩn:

```text
Original: [42, 5, 19, 80, 62, 41, 21, 99, 40, 20]
Sorted: [5, 19, 20, 21, 40, 41, 42, 62, 80, 99]
Duplicates: [0, 0, 0, 50, 50, 99]
Empty: []
```

### Vì sao code đúng theo hợp đồng?

- `bucketCount` phải dương nên có ít nhất một thùng.
- `upperExclusive` dương và mọi giá trị phải trong `[0, upperExclusive)`, nên ánh xạ không sinh chỉ số âm hoặc vượt giới hạn.
- Biểu thức `((long)value * bucketCount)` nâng tích sang `long` **trước** khi nhân, tránh lỗi tràn `int` khi cả hai số lớn. Vì `value<upperExclusive` và `bucketCount>0`, kết quả phép chia nằm trong `[0,bucketCount)`. Với hai toán hạng là `int` không âm, tích tối đa vẫn nằm trong miền `long`.
- Mỗi phần tử được thêm **đúng một lần** vào danh sách của thùng tương ứng.
- `insertionSort` dùng phép so sánh `>`, chỉ dịch phần tử có khóa lớn hơn; phần tử bằng khóa không bị cố ý dịch qua nhau trong một thùng.
- `result` có độ dài bằng input và được lấp đầy bằng toàn bộ phần tử của từng thùng theo chỉ số tăng dần.
- Mảng `input` không bị sửa: ta chỉ đọc giá trị của nó khi phân phối.
- Mảng rỗng hợp lệ, tạo các thùng rỗng, rồi trả `[]`.
- `0` đi vào thùng đầu; `upperExclusive - 1` đi vào một thùng hợp lệ cuối miền. Giá trị bằng `upperExclusive` bị từ chối.

**Giới hạn của minh họa:** tạo `bucketCount` đối tượng thùng có thể tốn đáng kể bộ nhớ khi số thùng cực lớn. Không được suy rằng phương thức này tự động là phương án tối ưu về bộ nhớ hoặc chạy được với mọi `bucketCount` do người dùng nhập; một ứng dụng thật cần giới hạn tài nguyên.

### Tại sao dùng insertion sort cho từng thùng?

Với mỗi thùng nhỏ, insertion sort đơn giản, chi phí cấu hình thấp, có thể sắp nhanh khi số phần tử ít hoặc gần có thứ tự. Nhưng nếu thùng lớn, chi phí tệ nhất bậc hai có thể trở thành vấn đề. Đổi sang một phương pháp sắp xếp có giới hạn tốt hơn trong từng thùng làm thay đổi phân tích ở mục 6–7; không được lấy công thức kỳ vọng của **insertion sort** áp lên mọi cách sắp thùng.

## 10. Bucket sort có ổn định không?

**Có thể ổn định, nhưng không mặc định.** Một thuật toán sắp xếp ổn định phải giữ nguyên thứ tự tương đối của các **bản ghi khác nhau có cùng khóa so sánh**.

Bucket sort ổn định nếu đồng thời thỏa:

1. Mọi bản ghi có khóa bằng nhau được ánh xạ vào **cùng một thùng** (ví dụ chỉ số thùng là một hàm xác định của khóa).
2. Bản ghi được đưa vào thùng theo đúng **thứ tự duyệt đầu vào**.
3. Thuật toán sắp **bên trong thùng là ổn định**.
4. Ghép thùng từ chỉ số thấp đến cao mà không đổi thứ tự nội bộ đã có.

Ví dụ có hai bản ghi `(A,score=42)` và `(B,score=42)`, A xuất hiện trước B. Cả hai vào cùng thùng theo score. Nếu thùng lưu theo thứ tự đến và sắp nội bộ ổn định, A vẫn đứng trước B.

Ngược lại, nếu dùng thuật toán nội bộ không ổn định, hoặc phân phối các bản ghi đồng khóa vào thùng khác nhau theo cách thiếu quy tắc, toàn bộ bucket sort có thể mất tính ổn định. Với chương trình `int[]` trong mục 9, hai giá trị 42 là không phân biệt được về danh tính; muốn **kiểm tra ổn định**, cần test trên bản ghi mang `id` cùng khóa số.

**Ổn định không liên quan trực tiếp đến phân bố đều**: một phương án có thể ổn định trên dữ liệu lệch và vẫn chậm; một phương án được phân bố đều có thể nhanh nhưng không ổn định.

## 11. So sánh với counting sort, radix sort và comparison sort

| Thuật toán | Điều kiện / cách làm | Hiệu năng và điểm cần chú ý |
| --- | --- | --- |
| **Bucket sort** | Phân phối khóa vào các thùng theo khoảng, sắp nội bộ rồi nối | Có thể kỳ vọng `O(n)` với giả thiết phân bố và `k≈n`; worst-case phụ thuộc cách sắp nội bộ; bộ nhớ `O(n+k)` trong minh họa |
| **Counting sort** | Đếm số lần xuất hiện của từng khóa nguyên trong một miền rời rạc đủ nhỏ, rồi tạo đầu ra | Thời gian `O(n+R)` và bộ nhớ `O(n+R)` với phiên bản ổn định dùng mảng đầu ra; `R` là số giá trị trong miền |
| **Radix sort** | Xử lý từng chữ số/byte theo từng lượt bằng phân phối ổn định | Chi phí phụ thuộc số lượt chữ số và cơ số; yêu cầu biểu diễn khóa/chiến lược xử lý dấu và độ ổn định của các lượt |
| **Merge sort** | Chia, sắp và trộn theo so sánh | `O(n log n)` worst-case với thiết kế chuẩn; có thể ổn định; không đòi dữ liệu phân bố đều |

Một hiểu nhầm phổ biến: “Bucket sort là non-comparison sort nên đương nhiên vượt giới hạn `Omega(n log n)`.” Thực tế **bucket sort thường vẫn so sánh phần tử trong mỗi thùng**. Tính hiệu quả đến từ **thông tin miền và giả thiết phân bố**, không phải một phép màu loại bỏ mọi phép so sánh đối với đầu vào tùy ý.

Nếu miền khóa chỉ gồm vài giá trị nguyên, counting sort có thể hợp lý hơn. Nếu các khóa là chuỗi số dài hoặc có cấu trúc chữ số, radix sort có thể phù hợp khi thiết kế lượt phân phối chính xác. Nếu không có giới hạn miền và không có giả thiết xác suất, một thuật toán so sánh có worst-case `O(n log n)` thường cho bảo đảm dễ dự đoán hơn.

## 12. Cách chọn số thùng và ranh giới trong thực tế

Giả sử dữ liệu có `n` phần tử và miền `[min,max)`. Trước khi chọn `k`:

1. **Xác định miền hợp lệ thật sự.** Có giá trị âm, giá trị ở cận trên, `NaN`, phần tử `null` hoặc khóa không số hay không?
2. **Ước lượng phân bố.** Nếu tập trung lệch hoặc có cụm, chia đều miền giá trị có thể không cân bằng.
3. **Chọn số thùng theo kích thước dữ liệu và overhead.** Mục tiêu `k≈n` có ý nghĩa trong mô hình phân bố đều khi dùng insertion sort nội bộ, nhưng tạo hàng triệu thùng có thể không thực tế.
4. **Đặt quy tắc biên nửa mở.** Ví dụ `[0,20),[20,40),...` để giá trị tại ranh giới thuộc đúng một thùng.
5. **Đảm bảo tính đơn điệu của ánh xạ.** Các thùng phải tương ứng với những khoảng giá trị tăng dần để ghép kết quả không cần so sánh lại giữa thùng.
6. **Chọn cách sắp nội bộ phù hợp tải thực.** Không coi mọi thùng đều nhỏ chỉ vì số thùng lớn.
7. **Kiểm tra tiêu chí ổn định và dữ liệu trùng.** Các khóa bằng nhau phải được xử lý có chủ ý.
8. **Đo và kiểm thử:** ghi nhận số phần tử mỗi thùng, thùng lớn nhất, số thùng rỗng, số so sánh/dịch chuyển, thời gian, bộ nhớ, và chạy trên nhiều phân bố dữ liệu.

Khi muốn dùng **quantile buckets**, có thể xây ranh giới sao cho các khoảng có xác suất xấp xỉ `1/k` theo phân bố ước lượng. Tuy nhiên, chi phí học/duy trì ranh giới, sai lệch phân bố theo thời gian và các khóa trùng ở biên phải được tính vào tổng chi phí.

### Bảo vệ trước dữ liệu lệch nặng

Một chiến lược thực dụng là **chuyển sang thuật toán nội bộ tốt hơn khi một thùng quá lớn**, chẳng hạn dùng thuật toán sắp xếp `O(m log m)` worst-case cho một thùng có `m` phần tử. Với giả định thao tác phân phối/ghép `O(n+k)`, tổng chặn khi đó có dạng:

\[
O\left(n+k+\sum_j b_j\log(b_j+1)\right)
\subseteq O(n+k+n\log(n+1)).
\]

Chiến lược này giảm rủi ro bình phương từ một thùng lớn, nhưng làm thay đổi đặc tính ổn định và overhead tùy bộ sắp xếp được chọn. Phải mô tả chính xác thuật toán được dùng, không chỉ nói “có thể tối ưu”.

## 13. Kiểm thử và các lỗi phổ biến

### Bộ kiểm thử cơ bản

| Dữ liệu | Tham số | Kết quả / điều kiện cần kiểm tra |
| --- | --- | --- |
| `[]` | `B=100,k=5` | `[]`, không truy cập ngoài mảng |
| `[0]` | `B=100,k=5` | `[0]`, thuộc bucket 0 |
| `[99]` | `B=100,k=5` | `[99]`, thuộc bucket 4 |
| `[20,19,40,39]` | `B=100,k=5` | `[19,20,39,40]`, ranh giới giữa các thùng đúng |
| `[50,0,50,99,0,0]` | `B=100,k=5` | `[0,0,0,50,50,99]`, giữ số lần xuất hiện |
| `[19,18,17,16,15]` | `B=100,k=5` | `[15,16,17,18,19]`, trường hợp lệch một thùng |
| `[100]` | `B=100,k=5` | Từ chối vì 100 không thuộc `[0,100)` |
| `[-1]` | `B=100,k=5` | Từ chối vì giá trị âm ngoài miền |
| `[5]` | `B=100,k=0` | Từ chối vì không có thùng |
| `null` | `B=100,k=5` | Từ chối theo hợp đồng |

Một bộ kiểm thử có thể tạo ngẫu nhiên nhiều mảng **trong miền hợp lệ**, chạy `bucketSort` và đối chiếu với `Arrays.sort` trên bản sao. Đồng thời kiểm tra mảng nguồn **không đổi**, đầu ra không giảm và có đúng đa tập phần tử gốc.

**Kiểm thử hiệu năng cần thêm các phân bố khác nhau:** đều, lệch trái, lệch phải, tập trung một cụm, nhiều khóa trùng, đảo ngược trong cùng một thùng. Chỉ chạy một dãy ngẫu nhiên rồi kết luận “bucket sort tuyến tính trong mọi trường hợp” là sai.

### Lỗi thường gặp

1. **Nhầm số thùng với bề rộng thùng.** Ánh xạ sai có thể bỏ giá trị hoặc đảo thứ tự giữa thùng.
2. **Quên xử lý cận trên.** Với `[0,1)`, `x=1` không hợp lệ; với `[0,B)`, `x=B` không hợp lệ.
3. **Ánh xạ không đơn điệu.** Nếu thùng có chỉ số nhỏ lại chứa một khóa lớn hơn khóa ở thùng sau, nối các thùng chưa chắc đã sắp đúng.
4. **Không sắp nội bộ thùng.** Phân phối theo khoảng không tự làm mọi phần tử trong cùng thùng có thứ tự.
5. **Nối thùng sai thứ tự.** Duyệt thùng 4 trước thùng 2 sẽ phá thứ tự tăng dần.
6. **Coi phân bố đều là điều kiện đúng đắn.** Thuật toán vẫn đúng khi dữ liệu lệch; thứ bị ảnh hưởng là thời gian.
7. **Coi dữ liệu đều là đủ để chắc chắn `O(n)`.** Phân tích kỳ vọng còn phụ thuộc tính độc lập, số thùng và chi phí sắp nội bộ.
8. **Dùng phép nhân `int` trực tiếp khi tính chỉ số.** `value*bucketCount` có thể tràn trước khi chia; dùng kiểu rộng.
9. **Không có chiến lược cho thùng quá lớn.** Với insertion sort, một thùng đảo ngược có thể tạo nhiều phép dịch.
10. **Nhầm dữ liệu cùng khóa với cùng bản ghi.** Nếu cần ổn định, phải lưu và giữ thứ tự bản ghi có khóa trùng.
11. **Quên overhead thùng rỗng.** Khởi tạo và duyệt `k` thùng vẫn tốn `O(k)` dù chỉ có rất ít phần tử.
12. **Quên phân biệt độ phức tạp kỳ vọng và worst-case.** Cùng một thuật toán có thể đạt kỳ vọng `O(n)` nhưng worst-case `Theta(n^2)` với insertion sort nội bộ.

## 14. Bài tập tự kiểm tra

**Bài 1 — Phân phối.** Với `B=100` và `k=5`, hãy tìm thùng của các giá trị `0,19,20,39,40,79,80,99`. Giải thích vì sao giá trị 100 không được phép.

**Bài 2 — Mô phỏng.** Với `a=[42,5,19,80,62,41,21,99,40,20]`, hãy viết nội dung cả năm thùng **trước** và **sau** insertion sort nội bộ, rồi ghi kết quả cuối.

**Bài 3 — Chặn theo kích thước thùng.** Với mảng `n=10` có kích thước thùng `[2,2,3,1,2]`, tính `sum_j b_j^2`. Nếu `n=10` nhưng kích thước thùng `[10,0,0,0,0]` thì tổng bình phương đổi thế nào? Điều đó gợi ý gì?

**Bài 4 — Kỳ vọng.** Giả sử `n=10` phần tử độc lập và đều trên `[0,1)`, `k=5`. Tính `E[sum_j b_j^2]` theo công thức đã học. Khi `k=n` và `n` lớn, chặn kỳ vọng thay đổi ra sao?

**Bài 5 — Phản ví dụ.** Một bạn khẳng định “cứ chọn `k=n` thùng thì mọi đầu vào đều được sắp trong `O(n)`”. Hãy phản bác bằng một họ đầu vào tập trung một thùng, gồm nhiều khóa phân biệt theo thứ tự giảm.

**Bài 6 — Tính ổn định.** Cho ba bản ghi `(A,42)`, `(B,42)`, `(C,13)` với thứ tự đầu vào A, B, C. Nêu điều kiện để kết quả bucket sort giữ A đứng trước B.

**Bài 7 — Chọn thuật toán.** Khi khóa là số nguyên trong miền rất nhỏ, nên cân nhắc thuật toán nào thay cho bucket sort? Khi miền lớn và phân bố lệch nặng nhưng phải có worst-case tốt, bạn sẽ thay đổi gì ở cách sắp nội bộ hoặc thuật toán tổng thể?

### Đáp án gợi ý

1. Giá trị `0,19` vào thùng 0; `20,39` vào thùng 1; `40` vào thùng 2; `79` vào thùng 3; `80,99` vào thùng 4. Giá trị 100 nằm ngoài cận trên không bao gồm `[0,100)`.
2. Trước sắp: `[5,19]`; `[21,20]`; `[42,41,40]`; `[62]`; `[80,99]`. Sau sắp: `[5,19]`; `[20,21]`; `[40,41,42]`; `[62]`; `[80,99]`. Kết quả `[5,19,20,21,40,41,42,62,80,99]`.
3. `2²+2²+3²+1²+2²=4+4+9+1+4=22`; nếu `[10,0,0,0,0]` thì tổng bằng `100`. Mất cân bằng tăng chặn chi phí sắp nội bộ theo bình phương.
4. `E[sum b_j²]=10+10·9/5=28`. Với `k=n`, kỳ vọng tổng bình phương bằng `2n-1`, dẫn đến kỳ vọng `O(n)` theo các giả thiết đã nêu.
5. Lấy `B=n²`, `k=n` và mảng giảm `[n-1,n-2,...,0]` với `n≥2`. Tất cả khóa vào thùng 0; insertion sort trên thùng ấy tốn `Theta(n²)`.
6. Phải đưa các bản ghi khóa 42 vào cùng thùng, duy trì thứ tự đưa vào và dùng bộ sắp nội bộ **ổn định**, rồi ghép thùng đúng thứ tự.
7. Với miền khóa nguyên nhỏ, cân nhắc counting sort. Với dữ liệu lệch và yêu cầu giới hạn trường hợp xấu, dùng thuật toán nội bộ có worst-case `O(m log m)` cho thùng lớn, hoặc chọn một thuật toán so sánh có worst-case `O(n log n)` trên toàn dãy.

## Ghi nhớ

Bucket sort gồm **phân phối theo miền khóa → sắp xếp từng thùng → ghép thùng theo thứ tự**. Điều kiện đúng đắn là **ánh xạ thùng nhất quán với thứ tự khóa** và **mỗi thùng được sắp đúng**; không cần phân bố đều để kết quả chính xác. Với insertion sort nội bộ, chi phí có chặn `O(n+k+sum b_j²)`; nếu các khóa **độc lập, phân bố đều** và `k≈n`, thời gian có thể đạt **kỳ vọng `O(n)`**. Ngược lại, dữ liệu tập trung một thùng có thể làm thời gian tệ nhất bậc hai. Khi áp dụng thực tế, hãy công bố miền đầu vào, số thùng, quy tắc biên, giả thiết phân bố, thuật toán nội bộ, tính ổn định và giới hạn tài nguyên.
