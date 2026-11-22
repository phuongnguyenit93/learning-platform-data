# Ngẫu nhiên hóa việc chọn pivot và phân bố khóa

## 1. Ngẫu nhiên hóa giải quyết vấn đề gì?

Trong các thuật toán phụ thuộc mạnh vào thứ tự dữ liệu, một lựa chọn cố định có thể vô tình biến một đầu vào bình thường thành trường hợp xấu nhất. Ví dụ, QuickSort luôn chọn phần tử đầu làm pivot dễ phân hoạch lệch khi đầu vào đã tăng dần hoặc giảm dần. Với bảng băm, hàm h(k)=k mod m có thể dồn tất cả các khóa là bội số của m vào cùng một bucket.

**Ngẫu nhiên hóa** đưa lựa chọn ngẫu nhiên vào thuật toán để hành vi ít phụ thuộc vào cách sắp đặt đầu vào và tạo cơ sở phân tích thời gian **kỳ vọng**. Hai ví dụ trọng tâm:

- **Chọn pivot ngẫu nhiên:** chọn một chỉ số trong đoạn QuickSort hoặc Quickselect đang xét, rồi phân hoạch theo giá trị tại chỉ số ấy.
- **Phân bố khóa ngẫu nhiên:** chọn một hàm băm có tham số ngẫu nhiên từ một họ hàm đã phân tích; cùng tập khóa có thể được rải vào các bucket khác nhau theo seed.

Điều cần nhớ: ngẫu nhiên hóa **không biến worst-case thành điều không thể xảy ra**. QuickSort vẫn có thể mất O(n²), các bucket hash vẫn có thể va chạm, và một seed đã bị lộ không phải lá chắn chống đối thủ chủ động điều chỉnh khóa.

### 1.1. Xác suất nằm ở đâu?

Đối với **thuật toán Las Vegas**, kết quả phải đúng trên mọi dãy lựa chọn ngẫu nhiên hợp lệ; ngẫu nhiên chỉ ảnh hưởng thời gian chạy/đường thực thi. Randomized QuickSort và Quickselect trong bài là Las Vegas: kết quả sắp xếp hoặc chọn thứ hạng luôn đúng, chỉ số lượng phép so sánh khác nhau.

Đối với **thuật toán Monte Carlo**, có thể đánh đổi một xác suất sai nhỏ để đạt tốc độ mong muốn. Ví dụ một phép kiểm đồng nhất dựa vào fingerprint ngẫu nhiên có xác suất va chạm, nên không được trình bày như kiểm chứng tuyệt đối.

Việc đặt một seed cố định cho bài kiểm thử là để **tái hiện** lỗi; khi muốn chống các đầu vào bị thiết kế sẵn theo seed, cần hạt giống mới khó đoán hoặc một cơ chế chống đối thủ thích hợp.

## 2. Pivot: phân hoạch và sự khác nhau giữa chỉ số với giá trị

Trong QuickSort, chọn pivot p, rồi chia đoạn thành ba nhóm:

**nhỏ hơn p | bằng p | lớn hơn p**.

Ta chỉ sắp xếp đệ quy hai nhóm nhỏ hơn và lớn hơn; nhóm bằng p đã đứng đúng vùng theo thứ tự giá trị. Với Quickselect tìm phần tử có thứ hạng k (0-based), ta chỉ tiếp tục ở nhóm chứa k, hoặc trả ngay p nếu k rơi vào vùng bằng.

**Pivot được chọn đều trên các vị trí** còn lại, không nhất thiết đều trên các *giá trị phân biệt*. Ví dụ dãy [5,5,5,5,8] có xác suất chọn giá trị 5 là 4/5 khi lấy vị trí đều, và giá trị 8 là 1/5. Điều này là đúng theo thuật toán; nhầm lựa chọn vị trí với lựa chọn giá trị sẽ dẫn đến phân tích xác suất sai.

### 2.1. Chọn pivot đúng trong Java

Đối với đoạn nửa mở [lo,hi), có hi>lo, gọi rng.nextInt(hi-lo) để nhận một số nguyên trong [0,hi-lo). Do đó chỉ số pivot là lo + rng.nextInt(hi-lo).

```java
int index = lo + rng.nextInt(hi - lo);
int pivot = a[index];
```

Không lấy rng.nextInt() % (hi-lo) vì modulo số âm có thể âm và phép lấy dư trực tiếp có thể tạo bias. Không dùng Math.abs(rng.nextInt()) vì Math.abs(Integer.MIN_VALUE) vẫn âm. API nextInt(bound) xử lý việc lấy mẫu trên đoạn giới hạn an toàn hơn.

Đừng tạo lại new Random(cùngSeed) **ở mỗi phân hoạch**: như vậy có thể lặp một kiểu lựa chọn có tính hệ thống. Truyền một RNG nhất quán xuống các lời gọi, hoặc sử dụng nguồn ngẫu nhiên phù hợp với môi trường chạy.

## 3. Phân hoạch ba chiều (Dutch National Flag)

Đặt p là pivot, và bốn vùng trong đoạn [lo,hi):

```text
[lo,lt)    : các phần tử < p
[lt,i)     : các phần tử = p
[i,gt)     : chưa phân loại
[gt,hi)    : các phần tử > p
```

Khởi tạo lt=i=lo và gt=hi. Khi i<gt:

- Nếu a[i]<p, đổi chỗ a[i] với a[lt], tăng cả lt và i.
- Nếu a[i]>p, giảm gt rồi đổi chỗ a[i] với a[gt]; **không tăng i** vì phần tử vừa đổi vào vị trí i chưa được xét.
- Nếu a[i]==p, chỉ tăng i.

Khi vòng lặp dừng, i=gt và mọi phần tử đã phân loại. Hai ranh giới trả về là lt,gt: vùng bằng pivot là [lt,gt), phần tử nhỏ hơn ở trước lt và phần tử lớn hơn từ gt trở đi.

### 3.1. Ví dụ có nhiều khóa trùng

```text
Dữ liệu      : [7,2,7,-3,0,8,2,2]
Chọn pivot 2 : [-3,0] | [2,2,2] | [7,7,8]
Trước lt     : <2
Vùng [lt,gt) : =2
Sau gt       : >2
```

Thứ tự **bên trong** nhóm nhỏ/lớn không nhất thiết đã được sắp xếp; ví dụ chỉ minh họa ba tập giá trị sau phân hoạch. QuickSort tiếp tục hai nhóm ngoài. Nếu toàn bộ dãy bằng nhau, chỉ một lần phân hoạch O(n) là đủ và không có nhánh đệ quy lớn nào.

Đối với 2-way partition thiếu xử lý bằng, n khóa trùng nhau có thể tiếp tục tạo các phân hoạch lệch và rơi vào O(n²), dù pivot được chọn ngẫu nhiên. **3-way partition** là giải pháp quan trọng cho dữ liệu nhiều duplicate.

### 3.2. Chứng minh đúng của bước phân hoạch

Trong mỗi vòng, bốn vùng trên duy trì bất biến: phần tử trước lt nhỏ hơn p, từ lt đến i-1 bằng p, từ i đến gt-1 chưa xét, từ gt tới hi-1 lớn hơn p. Mỗi trường hợp dịch ranh giới đúng theo giá trị phần tử được xét. Độ dài vùng chưa xét (gt-i) giảm đúng một đơn vị ở mỗi vòng nên thuật toán kết thúc sau O(hi-lo) phép phân loại.

Kết thúc khi i=gt, vùng chưa xét rỗng; mảng là một hoán vị của đầu vào vì chỉ dùng swap. Không thể mất hoặc tạo thêm khóa. Việc phân hoạch có thể thay đổi thứ tự của những phần tử bằng nhau, nên **QuickSort này không ổn định (unstable)**.

## 4. Randomized QuickSort

Chọn một pivot đều trên các chỉ số của đoạn hiện tại, 3-way partition, rồi sắp xếp riêng nhóm <p và >p:

```text
sort(a, lo, hi):
    nếu hi-lo <= 1: return
    p = a[lo + randomInt(hi-lo)]
    (lt,gt) = partition3(a,lo,hi,p)
    sort(a,lo,lt)
    sort(a,gt,hi)
```

**Đúng đắn:** nhóm bên trái chứa toàn bộ giá trị <p, nhóm giữa toàn bộ giá trị =p, nhóm phải toàn bộ giá trị >p. Theo quy nạp, sau khi hai nhóm ngoài được sắp xếp, nối ba nhóm cho một đoạn đã sắp xếp.

### 4.1. Kỳ vọng O(n log n) và worst-case O(n²)

Với n khóa phân biệt và pivot có hạng được chọn đều ở mỗi phân hoạch, thời gian kỳ vọng của QuickSort là O(n log n). Nếu các pivot liên tục cực lệch (nhỏ nhất hoặc lớn nhất), công thức thời gian có thể thành T(n)=T(n-1)+O(n), tức O(n²). Ngẫu nhiên hóa làm chuỗi xấu khó xảy ra dưới giả thiết lựa chọn độc lập nhưng **không xóa worst-case**.

Một cách phân tích số phép so sánh: sắp các khóa phân biệt là z1<z2<...<zn. Hai khóa zi và zj (i<j) được đem so sánh trực tiếp trong dạng phân hoạch chuẩn theo pivot nếu một trong hai được chọn làm pivot trước các khóa nằm giữa chúng. Xác suất là 2/(j-i+1). Do tuyến tính của kỳ vọng:

**E[comparisons] = tổng với i<j của 2/(j-i+1) = O(n log n).**

Đối với 3-way partition và khóa trùng, cách đếm cặp theo hạng phân biệt cần điều chỉnh; khẳng định O(n log n) kỳ vọng là mô hình thông thường với chọn pivot đều và phân hoạch cân đối theo phân bố khóa. Với các khóa đều bằng nhau, 3-way đạt O(n), thường tốt hơn công thức n log n.

### 4.2. Giới hạn bộ nhớ ngăn xếp

Đệ quy cả hai phía theo cách ngây thơ có thể sâu O(n) khi phân hoạch lệch. Có thể **đệ quy phía nhỏ hơn và xử lý phía lớn hơn bằng vòng while**. Vì mỗi lần đệ quy xử lý một đoạn không quá một nửa kích thước hiện tại, độ sâu call stack là O(log(n+1)) ngay cả trong chuỗi pivot xấu; worst-case thời gian vẫn có thể O(n²). Mã Java áp dụng mẹo này.

Để có bảo đảm worst-case O(n log n) cho sort, một giải pháp công nghiệp là introsort: nếu độ sâu phân hoạch vượt ngưỡng thì chuyển sang heapsort. Randomized QuickSort thuần túy không tự có bound worst-case này.

## 5. Randomized Quickselect

Quickselect trả phần tử có hạng k trong mảng sau khi sắp tăng dần (**k là chỉ số 0-based**). Nó cũng chọn pivot ngẫu nhiên và 3-way partition, nhưng sau phân hoạch:

- Nếu k<lt, chỉ tiếp tục trên [lo,lt).
- Nếu lt<=k<gt, trả pivot ngay vì k nằm trong các phần tử bằng pivot.
- Nếu k>=gt, chỉ tiếp tục trên [gt,hi).

Ví dụ với [7,2,7,-3,0,8,2,2], dãy đã sort là [-3,0,2,2,2,7,7,8]. Vậy k=3 trả 2; k=6 trả 7. Quickselect **làm thay đổi thứ tự mảng đầu vào**, nhưng không bắt buộc sắp toàn bộ.

### 5.1. Kỳ vọng O(n) và worst-case

Mỗi phân hoạch tốn tuyến tính theo chiều dài đoạn hiện tại. Pivot có thứ hạng nằm trong phần giữa tương đối đều đặn với xác suất không đổi, khiến đoạn còn lại thu nhỏ đáng kể đủ thường xuyên; tổng chi phí kỳ vọng là O(n) với lựa chọn đều, độc lập. Nếu cứ chọn pivot cực lệch nhiều lần, chỉ bỏ một phần tử mỗi lần, dẫn tới O(n²).

**Không nói Quickselect bảo đảm O(n) mọi đầu vào/mọi lựa chọn ngẫu nhiên**. Nếu bài bắt buộc worst-case tuyến tính, có thể dùng median-of-medians (BFPRT) theo cách cài phù hợp; nếu cần nhanh và bảo đảm thời gian có thể dùng lựa chọn nội suy/hybrid với ngưỡng an toàn.

### 5.2. Pivot với nhiều duplicate

3-way partition cho phép bỏ hẳn vùng bằng pivot. Nếu phần tử hạng k rơi vào vùng này, không cần chạy tiếp dù vùng bằng có hàng nghìn phần tử. Đây là khác biệt quan trọng so với một bản Quickselect 2-way sơ sài.

## 6. Fisher–Yates: ngẫu nhiên hóa thứ tự trước khi xử lý

Thay vì lấy pivot ngẫu nhiên trong mỗi bước, một cách thường gặp khác là **xáo trộn toàn bộ dãy** bằng Fisher–Yates rồi dùng một chiến lược pivot cố định thích hợp. Phép xáo trộn đúng được viết:

```text
for i = n-1 down to 1:
    j = randomInt(i+1)   // j đều trên [0,i]
    swap(a[i],a[j])
```

Giả sử mỗi lần chọn j là đều và các lựa chọn độc lập, mỗi hoán vị có xác suất 1/n!: ở lượt i có i+1 cách, toàn bộ tích n*(n-1)*...*2=n!. Mọi bước chỉ đổi chỗ nên vẫn bảo toàn đa tập giá trị.

**Cẩn trọng:** Fisher–Yates ngẫu nhiên hóa thứ tự, không ngẫu nhiên hóa *giá trị* của khóa và không làm biến mất những khóa trùng. Không được sử dụng cách sort với comparator ngẫu nhiên: comparator có thể mất tính bắc cầu và vi phạm hợp đồng sắp xếp.

Không nhất thiết vừa shuffle vừa chọn random pivot; đó là hai nguồn ngẫu nhiên khác nhau và có thể là công việc thừa nếu mục tiêu chỉ là randomized Quicksort.

## 7. Phân bố khóa và hash bucket

Một bảng băm có m bucket ánh xạ khóa k thành chỉ số h(k) trong [0,m). Với khóa phân bố đều và n phần tử, tải trung bình là **alpha=n/m**. Trong mô hình băm độc lập và gần đều, độ dài chain trung bình liên quan đến alpha; xác suất có va chạm tăng khi n gần m.

Hàm đơn giản h(k)=k%m có thể rất tệ nếu k có cấu trúc. Ví dụ m=5 và khóa [0,5,10,15]: mọi khóa đều vào bucket 0. Điều đó không có nghĩa mọi đầu vào đều xấu, mà cho thấy **phân bố khóa** là một phần của bài toán, không thể nhìn chỉ số lượng phần tử.

### 7.1. Randomized hashing: chọn hàm thay vì cố định hàm

Chọn một họ hàm h_{a,b} bằng hai tham số ngẫu nhiên, rồi dùng cùng hàm cho toàn bộ vòng đời bảng (hoặc tới lần rehash). Khóa cố định có thể được phân tán khác nhau khi đổi a,b. Ta đang lấy kỳ vọng theo **hàm băm ngẫu nhiên**, chứ không giả định người dùng gửi khóa ngẫu nhiên.

Một họ dễ phân tích trên trường nguyên tố P:

**H_{a,b}(k) = (a*k+b) mod P**, với k thuộc {0,...,P-1}, a,b chọn độc lập đều trong {0,...,P-1}.

Để đưa về m bucket, tính **h(k)=H_{a,b}(k) mod m**.

Ở cấp phần tử trường F_P, với hai khóa **khác nhau** k1!=k2, cặp (H(k1),H(k2)) độc lập và đều trên F_P^2. Nguyên nhân: hệ hai phương trình u=a*k1+b, v=a*k2+b có nghiệm duy nhất (a,b) cho mọi u,v vì k1-k2 khác 0 modulo P.

Điểm tinh tế: sau phép lấy dư m, vì P thường không chia hết cho m, xác suất mỗi bucket **không hoàn toàn bằng 1/m**. Nếu P=q*m+r với 0<=r<m, có r bucket nhận q+1 số dư trường và m-r bucket nhận q số dư. Với hai khóa phân biệt, xác suất hai bucket trùng là:

**Pr[h(k1)=h(k2)] = 1/m + r*(m-r)/(m*P*P).**

Vì P rất lớn so với m, sai khác thường rất nhỏ. **Không** khẳng định modulo m bảo toàn chính xác phân bố đều nếu P không chia hết cho m.

### 7.2. Ví dụ một seed cụ thể

Chọn môđun đồ chơi P=17, a=3, b=2, m=5. Với khóa [0,5,10,15]:

| k | (3k+2) mod 17 | Bucket mod 5 |
|---:|---:|---:|
| 0 | 2 | 2 |
| 5 | 0 | 0 |
| 10 | 15 | 0 |
| 15 | 13 | 3 |

Khác với h(k)=k mod 5 dồn cả bốn khóa vào bucket 0, lần chọn affine này phân vào bucket 0,2,3. **Đây chỉ là một ví dụ**, không có bảo đảm mọi seed đều rải đều. Nếu chọn a=0 trong họ, hàm là hằng số; điều ấy có xác suất 1/P dưới mô hình lý tưởng, rất nhỏ nhưng không phải không thể. Giữ a=0 trong họ nêu trên giúp tính độc lập từng cặp ở cấp trường là chính xác.

### 7.3. Cùng khóa có thể trùng và khác khóa có thể va chạm

Với khóa trùng nhau, ví dụ k=10 xuất hiện hai lần, hai lần băm luôn ra **cùng bucket**; ngẫu nhiên hóa không thể thay đổi định nghĩa bằng nhau của khóa. Với hai khóa khác nhau, phân bố ngẫu nhiên giúp xác suất va chạm thấp theo giả thiết nhưng **không** loại va chạm.

Giả sử có n khóa phân biệt và xác suất va chạm của một cặp là p_coll, kỳ vọng số cặp va chạm là C(n,2)*p_coll theo tuyến tính kỳ vọng; **không cần** giả định các cặp va chạm độc lập với nhau. Với khóa trùng, thêm những cặp trùng bắt buộc vào số va chạm.

### 7.4. Mô hình xác suất và PRNG thực tế

Phép chứng minh độc lập từng cặp ở trên giả định a,b là hai biến ngẫu nhiên **độc lập và đều lý tưởng** trên F_P. Mã Java dùng java.util.Random để tái hiện và học thuật; nó là PRNG hữu hạn trạng thái, **không phải nguồn entropy mật mã**, nên không thể coi là chứng nhận bảo mật của hệ thống trực tiếp trước người tấn công có khả năng quan sát/đoán seed.

Đối với khóa do đối thủ chủ động chọn, có thể cần một hàm băm có khóa bí mật hoặc phương án chống tấn công độ phức tạp dữ liệu; chỉ đổi java.util.Random sang SecureRandom mà giữ nguyên toàn bộ mô hình yếu hoặc để lộ tham số cũng chưa đảm bảo phòng vệ hoàn chỉnh.

## 8. Miền khóa, kiểu dữ liệu và tràn số

Để minh họa chính xác, mã Java chỉ nhận khóa **int không âm trong [0,P)** với P=1_000_000_007. Điều này là **hợp đồng đầu vào**, không phải hàm băm tổng quát cho mọi int hay String. Khóa âm hoặc >=P bị từ chối thay vì âm thầm co về cùng phần dư và làm mất giả thiết khóa phân biệt ở F_P.

Vì a,k,b đều nhỏ hơn P, biểu thức long a*k+b có giá trị nhỏ hơn khoảng 10^18+10^9, vẫn thấp hơn Long.MAX_VALUE≈9.22e18, nên phép nhân modulo P trong mã không tràn long. Nếu nâng P lên gần 2^32 hoặc dùng các khóa unsigned 32/64-bit, tích có thể tràn; khi đó cần thuật toán nhân modulo an toàn, BigInteger hoặc họ băm 64-bit được chứng minh riêng.

Giới hạn minh họa m<=100000 bucket để việc cấp phát mảng histogram không gây bộ nhớ khổng lồ. Nếu cần cấu trúc bảng băm thực tế, còn phải tính chi phí collision resolution, rehash, resizing và đặc tính của khóa.

## 9. Seed, công bằng, độc lập và khả năng tái lập

### 9.1. Seed dùng để làm gì?

Seed cố định giúp chạy lại chính xác cùng dữ liệu, cùng code và cùng chuỗi lựa chọn giả ngẫu nhiên, hữu ích cho regression tests. Seed thay đổi giữa các lần chạy làm đường thực thi và hàm hash thay đổi, nhưng không sửa được những lỗi logic như phân hoạch sai hoặc comparator không bắc cầu.

### 9.2. Cơ chế lấy mẫu không thiên lệch

java.util.Random.nextInt(bound) trả số trong [0,bound) bằng cơ chế tránh thiên lệch modulo; điều kiện bound>0 phải được bảo đảm. Fisher–Yates dùng bound=i+1. Pivot trong [lo,hi) dùng bound=hi-lo. Đừng ép ngẫu nhiên về một phạm vi bằng % với số nguyên signed rồi xem là đều.

### 9.3. Ngẫu nhiên độc lập trong phân tích

Phân tích QuickSort giả định những lựa chọn pivot có phân bố đều thích hợp cho mỗi đoạn khi điều kiện trên lựa chọn trước đó; phân tích hash giả định a,b độc lập đều trên trường. Một PRNG có seed hữu hạn giúp **mô phỏng** mô hình, nhưng không thể biến các giả thiết xác suất lý tưởng thành bảo đảm mật mã vô điều kiện.

### 9.4. Tương quan giữa khóa và seed

Nếu tập khóa được cố định **trước** khi chọn hàm bí mật ngẫu nhiên, phân tích va chạm kỳ vọng theo hàm có ý nghĩa. Nếu đối thủ biết tham số a,b và được chọn khóa **sau**, họ có thể tìm các khóa rơi vào cùng bucket trong miền đủ lớn; không được dùng công thức kỳ vọng cho khóa được chọn thích nghi như một bảo đảm an ninh.

## 10. Giám sát phân bố khóa trên hệ thống thật

Đừng chỉ nhìn trung bình alpha=n/m. Với chained hash, nên xem **số phần tử mỗi bucket**, bucket lớn nhất, histogram độ dài chain, tổng số cặp va chạm và thời gian truy vấn. Với open addressing, theo dõi load factor, probe length, cụm hóa và chiến lược xử lý va chạm (linear/quadratic probing, double hashing), vì các chỉ số này có ý nghĩa vận hành khác nhau.

**Số cặp va chạm** trong mảng đếm c[0..m-1] là:

**Collisions = sum_j c[j]*(c[j]-1)/2.**

Đây là số cặp vị trí khóa có cùng bucket, **không phải** số lần probing hoặc số lần thực sự gọi equals. Với m=7, n=12, theo nguyên lý Dirichlet, ngay cả phân bố cân đối nhất vẫn có ít nhất 5 cặp va chạm (năm bucket có 2 phần tử, hai bucket có 1).

Khi quá tải, tăng kích thước bảng, chọn seed/hàm mới phù hợp và rehash có thể tốt hơn việc chỉ thử thêm những khóa. Một seed tốt không thay thế thiết kế capacity và chiến lược giải quyết collision.

## 11. So sánh ngẫu nhiên hóa pivot và phân bố hash

| Khía cạnh | Pivot ngẫu nhiên | Hàm băm ngẫu nhiên |
|---|---|---|
| Biến ngẫu nhiên | Vị trí pivot mỗi lần chia | Tham số hàm chọn cho bảng |
| Đầu ra | Cùng thứ tự sort/giá trị kth | Bucket có thể khác giữa seed |
| Độ chính xác | Không phụ thuộc pivot nếu partition đúng | Lookup vẫn phải kiểm equality khi collision |
| Phân tích | Expected comparisons / time | Expected occupancy / collisions |
| Trường hợp xấu | O(n²) QuickSort/Quickselect | Nhiều khóa cùng bucket |
| Cách giảm rủi ro | 3-way; giới hạn depth; introsort/BFPRT | Capacity, rehash, bucket balancing, keyed security |
| Đầu vào trùng | 3-way giúp gộp cả vùng bằng | Khóa giống nhau luôn cùng bucket |
| Seed cố định | Debug dễ nhưng đường chạy dự đoán được | Phân bố cố định, đối thủ có thể khai thác nếu biết |

**Không nhầm ngẫu nhiên hóa với sửa thuật toán:** dù pivot chọn đều, nếu partition sai dấu hoặc xử lý i/gt sai thì kết quả có thể sai. Dù hash có seed, nếu không giải quyết collision bằng so sánh khóa thì tra cứu sẽ sai. Ngẫu nhiên hóa chủ yếu ảnh hưởng chi phí kỳ vọng, không miễn kiểm tính đúng.


## 12. Chương trình Java 17+ độc lập

Tệp Java sau cài **3-way randomized QuickSort**, **3-way randomized Quickselect**, Fisher–Yates, affine randomized hashing trên miền khóa giới hạn, histogram bucket, số cặp va chạm, và bộ oracle so sánh với thư viện Java/số học BigInteger. Tệp cần lưu có tên `RandomPivotAndKeysDemo.java`.

```java
import java.math.BigInteger;
import java.util.Arrays;
import java.util.Objects;
import java.util.Random;

public final class RandomPivotAndKeysDemo {
    private RandomPivotAndKeysDemo() {}

    private static final int PRIME = 1_000_000_007;

    private static void swap(int[] a, int i, int j) {
        int tmp = a[i];
        a[i] = a[j];
        a[j] = tmp;
    }

    // Fisher-Yates: each nextInt bound is positive.
    public static void shuffle(int[] a, Random rng) {
        Objects.requireNonNull(a, "a");
        Objects.requireNonNull(rng, "rng");
        for (int i = a.length - 1; i > 0; i--) {
            int j = rng.nextInt(i + 1);
            swap(a, i, j);
        }
    }

    // Invariant:
    // [lo,lt) < p; [lt,i) == p; [i,gt) unknown; [gt,hi) > p.
    private static int[] partition3(
            int[] a, int lo, int hi, int pivot) {
        int lt = lo, i = lo, gt = hi;

        while (i < gt) {
            if (a[i] < pivot) {
                swap(a, lt++, i++);
            } else if (a[i] > pivot) {
                swap(a, i, --gt);
            } else {
                i++;
            }
        }
        return new int[] {lt, gt};
    }

    // Recurse on smaller side; loop over larger side.
    // O(log n) call-stack depth even with very unbalanced pivots.
    private static void sortSegment(
            int[] a, int lo, int hi, Random rng) {
        while (hi - lo > 1) {
            int pivot = a[lo + rng.nextInt(hi - lo)];
            int[] mid = partition3(a, lo, hi, pivot);

            int left = mid[0] - lo;
            int right = hi - mid[1];
            if (left < right) {
                sortSegment(a, lo, mid[0], rng);
                lo = mid[1];
            } else {
                sortSegment(a, mid[1], hi, rng);
                hi = mid[0];
            }
        }
    }

    public static void quickSort3(int[] a, Random rng) {
        Objects.requireNonNull(a, "a");
        Objects.requireNonNull(rng, "rng");
        sortSegment(a, 0, a.length, rng);
    }

    // k is 0-based order statistic; modifies the input array.
    public static int quickSelect3(int[] a, int k, Random rng) {
        Objects.requireNonNull(a, "a");
        Objects.requireNonNull(rng, "rng");
        if (k < 0 || k >= a.length) {
            throw new IllegalArgumentException(
                "k must satisfy 0 <= k < a.length"
            );
        }

        int lo = 0, hi = a.length;
        while (true) {
            int pivot = a[lo + rng.nextInt(hi - lo)];
            int[] mid = partition3(a, lo, hi, pivot);

            if (k < mid[0]) {
                hi = mid[0];
            } else if (k >= mid[1]) {
                lo = mid[1];
            } else {
                return pivot;
            }
        }
    }

    // Domain: integer keys k in [0, PRIME).
    // Ideal a,b uniform in F_p -> pairwise independent field outputs.
    // Random is a reproducible educational PRNG, NOT crypto.
    static final class AffineHash {
        final long a, b;
        final int bucketCount;

        AffineHash(int bucketCount, Random rng) {
            Objects.requireNonNull(rng, "rng");
            if (bucketCount < 1 || bucketCount > 100_000) {
                throw new IllegalArgumentException(
                    "bucketCount must be 1..100000"
                );
            }

            this.bucketCount = bucketCount;
            this.a = rng.nextInt(PRIME);
            this.b = rng.nextInt(PRIME);
        }

        int bucket(int key) {
            if (key < 0 || key >= PRIME) {
                throw new IllegalArgumentException(
                    "key outside [0, PRIME)"
                );
            }
            // a*key + b < about 10^18, within signed long.
            long field = (a * key + b) % PRIME;
            return (int) (field % bucketCount);
        }
    }

    static int[] bucketCounts(int[] keys, AffineHash h) {
        Objects.requireNonNull(keys, "keys");
        Objects.requireNonNull(h, "h");
        int[] count = new int[h.bucketCount];
        for (int key : keys) count[h.bucket(key)]++;
        return count;
    }

    static long collisionPairs(int[] count) {
        long pairs = 0;
        for (int c : count) {
            pairs += (long) c * (c - 1) / 2;
        }
        return pairs;
    }

    // Independent arithmetic oracle: BigInteger, not long product.
    private static int hashOracle(int key, AffineHash h) {
        BigInteger p = BigInteger.valueOf(PRIME);
        BigInteger v = BigInteger.valueOf(h.a)
            .multiply(BigInteger.valueOf(key))
            .add(BigInteger.valueOf(h.b))
            .mod(p);
        return v.mod(BigInteger.valueOf(h.bucketCount))
            .intValueExact();
    }

    private static void check(boolean ok, String why) {
        if (!ok) throw new AssertionError(why);
    }

    public static void main(String[] args) {
        int[] sample = {7, 2, 7, -3, 0, 8, 2, 2};
        int[] sorted = sample.clone();
        quickSort3(sorted, new Random(452L));

        System.out.println(
            "Sorted sample: " + Arrays.toString(sorted)
        );
        System.out.println(
            "k=3 (0-based): " +
            quickSelect3(sample.clone(), 3, new Random(452L))
        );
        System.out.println(
            "k=6 (0-based): " +
            quickSelect3(sample.clone(), 6, new Random(453L))
        );

        int[] equal = {5, 5, 5, 5};
        quickSort3(equal, new Random(452L));
        System.out.println(
            "All equal: " + Arrays.toString(equal)
        );

        int[] shuffledA = sample.clone();
        int[] shuffledB = sample.clone();
        shuffle(shuffledA, new Random(452L));
        shuffle(shuffledB, new Random(452L));

        int[] sortedShuffle = shuffledA.clone();
        Arrays.sort(sortedShuffle);
        check(Arrays.equals(sortedShuffle, sorted),
            "shuffle must preserve the multiset");
        System.out.println(
            "Shuffle preserves multiset: true"
        );
        System.out.println(
            "Shuffle same seed: " +
            Arrays.equals(shuffledA, shuffledB)
        );

        int[] keys = {0, 1, 2, 3, 4, 5,
                      6, 7, 8, 9, 10, 10};
        AffineHash h1 = new AffineHash(
            7, new Random(452L)
        );
        AffineHash h2 = new AffineHash(
            7, new Random(452L)
        );

        int[] counts1 = bucketCounts(keys, h1);
        int[] counts2 = bucketCounts(keys, h2);
        System.out.println(
            "Hash same seed: " +
            Arrays.equals(counts1, counts2)
        );
        System.out.println(
            "Hash total keys: " + Arrays.stream(counts1).sum()
        );
        System.out.println(
            "Hash collision pairs >= 5: " +
            (collisionPairs(counts1) >= 5)
        );

        boolean rejected = false;
        try {
            h1.bucket(-1);
        } catch (IllegalArgumentException expected) {
            rejected = true;
        }
        System.out.println(
            "Hash rejects negative key: " + rejected
        );

        Random random = new Random(2026452L);
        for (int trial = 0; trial < 2_500; trial++) {
            int n = 1 + random.nextInt(70);
            int[] values = new int[n];

            for (int i = 0; i < n; i++) {
                int special = random.nextInt(17);
                if (special == 0) {
                    values[i] = Integer.MIN_VALUE;
                } else if (special == 1) {
                    values[i] = Integer.MAX_VALUE;
                } else {
                    values[i] = random.nextInt(61) - 30;
                }
            }

            int[] expected = values.clone();
            Arrays.sort(expected);

            int[] actual = values.clone();
            quickSort3(actual, new Random(random.nextLong()));
            check(Arrays.equals(expected, actual),
                "QuickSort trial=" + trial);

            int k = random.nextInt(n);
            int selected = quickSelect3(
                values.clone(), k, new Random(random.nextLong())
            );
            check(selected == expected[k],
                "Quickselect trial=" + trial);
        }

        for (int trial = 0; trial < 1_500; trial++) {
            int buckets = 1 + random.nextInt(101);
            AffineHash h = new AffineHash(buckets, random);

            for (int j = 0; j < 20; j++) {
                int key = random.nextInt(PRIME);
                check(h.bucket(key) == hashOracle(key, h),
                    "hash arithmetic trial=" + trial);
            }

            int[] testKeys = new int[20];
            for (int j = 0; j < testKeys.length; j++) {
                testKeys[j] = random.nextInt(PRIME);
            }
            int[] frequencies = bucketCounts(testKeys, h);
            check(Arrays.stream(frequencies).sum() == 20,
                "bucket-count total trial=" + trial);
        }

        System.out.println("Sort oracle: 2500 PASS");
        System.out.println("Select oracle: 2500 PASS");
        System.out.println("Hash BigInteger oracle: 1500 PASS");
    }
}
```

### 12.1. Biên dịch và chạy

```bash
javac -encoding UTF-8 RandomPivotAndKeysDemo.java
java RandomPivotAndKeysDemo
```

**Đầu ra xác định:**

```text
Sorted sample: [-3, 0, 2, 2, 2, 7, 7, 8]
k=3 (0-based): 2
k=6 (0-based): 7
All equal: [5, 5, 5, 5]
Shuffle preserves multiset: true
Shuffle same seed: true
Hash same seed: true
Hash total keys: 12
Hash collision pairs >= 5: true
Hash rejects negative key: true
Sort oracle: 2500 PASS
Select oracle: 2500 PASS
Hash BigInteger oracle: 1500 PASS
```

### 12.2. Các bất biến và hợp đồng cần hiểu

- `partition3` không chọn pivot trong hàm này; nó nhận *giá trị pivot* và phân loại mọi vị trí của đoạn. Đảm bảo [lo,lt)<p, [lt,gt)=p, [gt,hi)>p, không làm mất phần tử.
- `quickSort3` chọn pivot ngẫu nhiên trên đoạn hiện tại rồi xử lý phía nhỏ hơn bằng đệ quy; worst-case thời gian vẫn O(n²), độ sâu call stack O(log n).
- `quickSelect3` nhận k từ 0 đến n-1 và thay đổi mảng. Với k nằm trong đoạn bằng pivot, trả ngay pivot. Với mảng rỗng, mọi k đều không hợp lệ và hàm ném lỗi.
- `shuffle` bảo toàn đa tập khóa, không đổi giá trị phần tử; cùng seed và cùng đầu vào cho cùng hoán vị.
- `AffineHash` nhận khóa nguyên trong [0,P) và m từ 1 tới 100000; không nhận trực tiếp khóa âm, String hay toàn bộ miền 32-bit. Một seed cố định làm h có thể lặp lại để debug.
- `bucketCounts` đếm số phần tử được ánh xạ tới từng bucket; tổng tất cả count bằng số phần tử đầu vào, kể cả duplicates.
- `collisionPairs` tính tổng c*(c-1)/2 theo bucket, không tính trực tiếp số probe trong một bảng open addressing.
- `hashOracle` dùng BigInteger cho phép nhân và modulo độc lập với phép nhân long ở `bucket`, giúp kiểm các giá trị sát cận.

### 12.3. Ý nghĩa của bộ kiểm thử

Chương trình tạo **2.500** mảng có độ dài 1..70, gồm nhiều khóa trùng và đôi khi có Integer.MIN_VALUE/Integer.MAX_VALUE. Kết quả QuickSort được so với Arrays.sort trên mảng sao; Quickselect được so với phần tử tại vị trí k trong mảng tham chiếu đã sort.

Với băm affine, chương trình tạo **1.500** bộ tham số/kích thước bucket, mỗi bộ thử 20 khóa với oracle BigInteger và kiểm tổng histogram 20. Đây là kiểm thử **tính đúng phép tính** chứ không tự chứng minh phân bố đều thống kê hay bảo mật trước đối thủ.

Không có phép kiểm nào cần dựa vào một thứ tự pivot cụ thể để quyết định kết quả sort/select. Đây là thuộc tính quan trọng của thuật toán Las Vegas: sự đúng đắn không phụ thuộc seed.

## 13. Phân tích kỹ hơn độ phức tạp và độ an toàn

| Tác vụ | Thời gian trung bình/kỳ vọng | Trường hợp xấu | Bộ nhớ phụ |
|---|---|---|---|
| Fisher–Yates n phần tử | O(n) | O(n) | O(1) |
| Randomized 3-way QuickSort | O(n log n) kỳ vọng | O(n²) | O(log n) stack bản cài đệ quy phía nhỏ |
| Randomized 3-way Quickselect | O(n) kỳ vọng | O(n²) | O(1) ngoài mảng và phân hoạch ngắn |
| Partition3 một đoạn t phần tử | O(t) | O(t) | O(1) (hai ranh giới) |
| Tính hash một khóa | O(1) trên long cố định | O(1) | O(1) |
| Đếm n khóa vào m bucket | O(n+m) | O(n+m) | O(m) |
| Tính số cặp collision từ m count | O(m) | O(m) | O(1) |

Các con số expected QuickSort/Quickselect giả định lựa chọn ngẫu nhiên đủ công bằng theo phân tích. Chúng không phải một lời hứa thời gian thực với giới hạn cứng. Khi yêu cầu worst-case, dùng thuật toán có bảo đảm tương ứng hoặc ngưỡng chuyển phương pháp.

### 13.1. Phát hiện phân hoạch lỗi bằng oracle

Nếu partition3 tăng i sau khi đổi chỗ với phần tử ở gt, một phần tử mới chưa xét có thể bị bỏ qua. Sort đôi khi vẫn đúng ở ví dụ nhỏ nhưng sai ở bộ kiểm thử ngẫu nhiên. Vì thế nên kiểm cả **đa tập phần tử**, thứ tự sau sort, và thứ hạng của Quickselect với nhiều duplicate.

### 13.2. Phát hiện hàm băm lỗi bằng oracle

Ngay cả khi tổng bucket count đúng n, hàm hash vẫn có thể đặt sai bucket. So từng khóa với phép tính BigInteger sẽ bắt lỗi modulo/tràn ở biểu thức a*k+b. Nếu keys vượt miền F_P mà hàm tự co modulo P, hai khóa nguyên khác nhau có thể có cùng phần tử trường, phá giả thiết về tính độc lập cho các khóa nguyên ấy.

### 13.3. Năng lực chống đầu vào bất lợi

Với pivot random, nguy cơ xấu có thể giảm khi đầu vào được chọn trước và seed khó dự đoán, nhưng 3-way partition và giới hạn stack vẫn cần thiết. Với hash random, cần thiết kế capacity, collision resolution và một chính sách seed phù hợp mức đe dọa; java.util.Random không phải PRNG mật mã.

**Không hứa rằng hash ngẫu nhiên luôn nhanh**, cũng không diễn giải mức expected dưới giả thiết khóa cố định như bảo đảm cho đối thủ thấy seed rồi chọn khóa thích nghi.


## 14. Những lỗi thường gặp

| Sai lầm | Hậu quả | Cách làm đúng |
|---|---|---|
| Pivot luôn cố định ở đầu đoạn | Dễ lệch khi dữ liệu đã sort | Random pivot hoặc shuffle, kiểm worst-case |
| Chọn rng.nextInt() % n | Có thể âm/thiên lệch | rng.nextInt(n) với n>0 |
| Dùng Math.abs cho mọi số nguyên ngẫu nhiên | Integer.MIN_VALUE vẫn âm | Dùng bounded API |
| Tạo new Random(cùng seed) ở mỗi bước | Lựa chọn lặp có cấu trúc | Truyền một RNG xuống lời gọi |
| Nhầm chọn đều theo vị trí với chọn đều theo giá trị | Phân tích sai khi nhiều duplicates | Pivot rank lấy theo multiplicity |
| Partition 2-way không xử lý bằng | Kém khi nhiều khóa bằng nhau | 3-way partition |
| Khi swap với gt lại tăng i | Bỏ sót phần tử chưa phân loại | Giữ i để xét lại |
| Cho rằng randomized QuickSort có worst O(n log n) | Có thể O(n²) | Introsort/guard |
| Cho rằng randomized Quickselect luôn O(n) | Vẫn có O(n²) | Nêu expected, dùng BFPRT nếu cần bound |
| Đệ quy cả phía lớn trong mọi trường hợp | Stack có thể O(n) | Đệ quy phía nhỏ, lặp phía lớn |
| Shuffle bằng comparator ngẫu nhiên | Comparator mất bắc cầu | Fisher–Yates |
| Dùng key % m cho các khóa đều là bội số m | Toàn bộ vào một bucket | Randomized hash phù hợp và collision handling |
| Không phân biệt hash residue với bucket | Khẳng định nhầm phân bố đều | Chỉ ra bias do mod m |
| Chọn a khác 0 nhưng chứng minh pairwise independence của a,b đều | Giả thiết chứng minh không khớp họ | Dùng đúng family và giả thiết |
| Dùng một seed cố định như công cụ bảo mật | Đối thủ đoán được | Định nghĩa threat model và keyed hashing khi cần |
| Nhầm duplicate key với collision giữa khóa khác | Đếm nhầm số va chạm có thể tránh | Khóa trùng luôn chung bucket |
| Áp family F_P cho mọi int bằng k mod P âm thầm | Mất giả thiết phân biệt khóa | Kiểm miền hoặc hash 32-bit riêng |
| Nhân a*k bằng int | Tràn trước modulo | Dùng long và chứng minh bound |
| Chỉ đo average load mà bỏ max bucket | Che bucket quá tải | Xem histogram và collision pairs |
| Mượn test Random seed cố định làm chứng minh xác suất | Không chứng minh phân bố kỳ vọng | Chứng minh riêng, test chỉ kiểm implementation |

## 15. Bài tập có đáp án

**Bài 1.** Randomized QuickSort là Las Vegas hay Monte Carlo trong mô hình chuẩn? *Đáp án:* Las Vegas; kết quả sort đúng nếu partition đúng, randomness ảnh hưởng chi phí.

**Bài 2.** Khi chọn pivot trên [lo,hi), viết biểu thức Java nào? *Đáp án:* lo + rng.nextInt(hi-lo), với hi>lo.

**Bài 3.** Dãy [5,5,5,5,8] có xác suất pivot mang giá trị 5 là bao nhiêu? *Đáp án:* 4/5 khi lấy đều vị trí.

**Bài 4.** Tại sao nhiều duplicates cần 3-way partition? *Đáp án:* loại toàn bộ vùng bằng pivot khỏi nhánh xử lý tiếp.

**Bài 5.** Bất biến vùng [lt,i) là gì? *Đáp án:* mọi giá trị bằng pivot.

**Bài 6.** Khi a[i]>p, sau swap với --gt có tăng i không? *Đáp án:* không, vì a[i] mới chưa được xét.

**Bài 7.** Độ phức tạp kỳ vọng của randomized QuickSort với khóa phân biệt? *Đáp án:* O(n log n).

**Bài 8.** Worst-case QuickSort random có còn O(n²) không? *Đáp án:* có, nếu pivot cực lệch nhiều lần.

**Bài 9.** Vì sao xác suất so sánh hai khóa ở hạng i<j là 2/(j-i+1)? *Đáp án:* khóa đầu tiên được chọn làm pivot trong đoạn hạng [i,j] phải là một trong hai đầu.

**Bài 10.** Cách hạn chế độ sâu call stack cho QuickSort? *Đáp án:* đệ quy phía nhỏ, xử lý phía lớn bằng vòng lặp.

**Bài 11.** Quickselect trả giá trị nào khi k=3 trong [-3,0,2,2,2,7,7,8]? *Đáp án:* 2.

**Bài 12.** Kỳ vọng của randomized Quickselect? *Đáp án:* O(n), worst O(n²).

**Bài 13.** Nếu bắt buộc selection worst-case O(n) có thể chọn gì? *Đáp án:* median-of-medians/BFPRT.

**Bài 14.** Với Fisher–Yates, j ở lượt i được chọn trong khoảng nào? *Đáp án:* [0,i] bao gồm i.

**Bài 15.** Số hoán vị của n phần tử phân biệt và xác suất của mỗi hoán vị sau shuffle đều? *Đáp án:* n! và 1/n!.

**Bài 16.** Hash k mod 5 với khóa [0,5,10,15] ra bucket nào? *Đáp án:* tất cả bucket 0.

**Bài 17.** Với P=17,a=3,b=2,m=5, khóa 15 thuộc bucket nào? *Đáp án:* (45+2) mod17=13, 13 mod5=3.

**Bài 18.** Vì sao không khẳng định bucket modulo m đều hoàn toàn? *Đáp án:* P thường không chia hết cho m, bucket nhận số residue khác nhau.

**Bài 19.** Family a*k+b mod P chọn a,b độc lập đều có pairwise independence cho khóa nào? *Đáp án:* hai khóa khác nhau trong trường F_P.

**Bài 20.** Hai bản sao cùng khóa có thể vào hai bucket khác nhau cùng một hàm hash không? *Đáp án:* không, hash nhất quán phải cho cùng bucket.

**Bài 21.** Mảng c[j] bucket counts có bao nhiêu cặp chung bucket? *Đáp án:* tổng c[j]*(c[j]-1)/2.

**Bài 22.** Với 12 khóa và 7 bucket, số cặp chung bucket nhỏ nhất? *Đáp án:* 5, khi phân bố tối ưu 2,2,2,2,2,1,1.

**Bài 23.** Tại sao kiểm [0,P) cho key ở ví dụ Java? *Đáp án:* giữ injective domain trong trường, không co nhiều khóa int khác nhau về một residue.

**Bài 24.** Vì sao dùng BigInteger làm oracle hash? *Đáp án:* kiểm độc lập phép nhân và modulo, tránh cùng một lỗi tràn trên long.

**Bài 25.** new Random(seed) có bảo đảm chống đối thủ thấy seed không? *Đáp án:* không, là PRNG để kiểm thử và ứng dụng không yêu cầu bảo mật.

**Bài 26.** Ngẫu nhiên hóa có làm thuật toán tự đúng nếu partition/hash lookup sai không? *Đáp án:* không; chứng minh tính đúng và kiểm tra collision vẫn bắt buộc.

## 16. Checklist trước khi áp dụng

1. Pivot chọn đều trên chỉ số của **đoạn hiện tại** và RNG không reset liên tục?
2. Partition có bất biến rõ cho vùng nhỏ/bằng/lớn, i không bị bỏ sót?
3. Dữ liệu nhiều khóa trùng có dùng 3-way?
4. Đã phân biệt correctness với expected time, nói rõ worst-case?
5. Có giới hạn stack, time budget hoặc worst-case fallback khi bắt buộc?
6. Quickselect dùng k 0-based và xử lý k không hợp lệ?
7. Shuffle đúng Fisher–Yates, không dùng comparator ngẫu nhiên?
8. Nếu băm, đã chọn họ hash, miền khóa, m bucket và cách xử lý collision?
9. Có chứng minh bound kiểu số và tránh tràn trước modulo?
10. Có phân biệt phần tử trường, bucket, xác suất đều và modulo bias?
11. Đã nghĩ đến duplicate keys, structured keys và load factor?
12. Có quan sát max bucket và collision pairs, không chỉ giá trị trung bình?
13. Seed phục vụ tái hiện hay bảo mật? Threat model có cho phép đối thủ biết seed?
14. Có so sort/select với oracle và hash arithmetic với BigInteger trên ca biên?
15. Có kiểm chứng mô hình xác suất, không coi vài lần test là chứng minh thống kê?

## Kết luận

**Ngẫu nhiên hóa pivot** giúp QuickSort đạt thời gian kỳ vọng O(n log n) và Quickselect đạt O(n) trong mô hình chuẩn, nhưng worst-case O(n²) vẫn tồn tại. **Phân hoạch ba chiều** là phần thiết yếu khi có khóa lặp, vì một lần phân hoạch có thể gộp toàn bộ vùng bằng pivot.

**Ngẫu nhiên hóa phân bố khóa** bằng một họ hàm băm được phân tích giúp hạn chế phụ thuộc vào cấu trúc khóa, nhưng không bảo đảm mọi seed đều tốt, không xóa va chạm và không tự bảo vệ trước đối thủ chủ động. Hãy kiểm miền khóa, bound số nguyên, capacity, chiến lược xử lý collision và nguồn seed.

Nguyên tắc chung: **ngẫu nhiên làm thay đổi phân bố chi phí, không thay thế chứng minh tính đúng**; dùng seed cố định để kiểm thử tái hiện, và nêu giả thiết xác suất rõ ràng khi đưa ra kết luận kỳ vọng.
