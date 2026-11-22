# Xáo trộn đồng đều bằng Fisher–Yates

## 1. Bài toán: hoán vị ngẫu nhiên có phân phối đồng đều

Cho một mảng có n phần tử, cần **xáo trộn (shuffle)** các phần tử để tạo ra một hoán vị ngẫu nhiên. Đặc tính quan trọng nhất không phải chỉ là “trông có vẻ lộn xộn” mà là **mọi hoán vị của n vị trí phân biệt phải có cùng xác suất**.

Ví dụ ban đầu:

~~~text
a = [0, 1, 2]

Cac hoan vi co the:
[0, 1, 2]
[0, 2, 1]
[1, 0, 2]
[1, 2, 0]
[2, 0, 1]
[2, 1, 0]
~~~

Có 3!=6 hoán vị. Một bộ xáo trộn **đồng đều (uniform shuffle)** lý tưởng phải cho mỗi hoán vị xác suất 1/6. Với n phần tử phân biệt, tổng số hoán vị là:

~~~text
n! = n * (n-1) * ... * 2 * 1
P(moi hoan vi cu the) = 1 / n!
~~~

**Fisher–Yates** (còn gọi là Knuth shuffle ở một số tài liệu) thực hiện đúng mô hình này bằng **n−1 lượt chọn chỉ số ngẫu nhiên có giới hạn và đổi chỗ**, không phải tạo n! khả năng rồi bốc ngẫu nhiên.

Đề bài thường yêu cầu một trong các dạng:

- Xáo trộn trực tiếp mảng có sẵn.
- Trả một bản sao đã xáo trộn mà không sửa mảng gốc.
- Xáo trộn danh sách các chỉ số, thẻ, câu hỏi hoặc item trong giao diện.
- Tạo một hoán vị ngẫu nhiên 0..n−1.
- Chọn k phần tử khác nhau bằng cách lấy k vị trí đầu sau một phép shuffle, khi k gần n.

Trong bài này, `a[i]` chỉ phần tử tại vị trí i, **không yêu cầu giá trị của mảng là những số khác nhau**. Quy trình chọn ngẫu nhiên tác động lên *các vị trí*; phần tử trùng giá trị được phân tích riêng.

### Những điều kiện phải xác định

- Xáo trộn **đồng đều theo các hoán vị vị trí**, không chỉ bảo toàn số lượng phần tử.
- Đơn vị ngẫu nhiên là **một chỉ số hợp lệ và đồng đều** trong miền được chỉ định.
- Cần biết API sửa mảng gốc hay trả mảng mới.
- Cần biết tính tái lập bằng seed hay tính không thể dự đoán trong tình huống an toàn thông tin.
- Mảng rỗng và mảng một phần tử đều là những input hợp lệ, không cần lấy số ngẫu nhiên.
- Nếu đầu vào có giá trị trùng nhau, nhiều hoán vị vị trí có thể hiển thị thành cùng một dãy giá trị.

## 2. Vì sao “đổi ngẫu nhiên nhiều lần” chưa chắc đồng đều?

Một cách viết rất phổ biến nhưng sai về mặt phân phối là:

~~~text
for i = 0..n-1:
    j = randomInteger(0,n-1)
    swap(a[i],a[j])
~~~

Ở mỗi lượt, j được lấy từ **toàn bộ mảng**, kể cả những vị trí đã tham gia chọn trước. Mã vẫn giữ nguyên multiset phần tử, nhưng **không đồng đều trên mọi hoán vị**.

### Phản ví dụ chính xác với n=3

Với n=3, thuật toán sai có **3 lựa chọn j mỗi lượt và 3 lượt**, tổng 3³=27 chuỗi lựa chọn có xác suất như nhau nếu các lần chọn độc lập, đồng đều. Ta liệt kê toàn bộ 27 chuỗi chỉ số và đếm hoán vị đầu ra:

| Hoán vị đầu ra | Số chuỗi lựa chọn | Xác suất |
| --- | ---: | ---: |
| [0,1,2] | 4 | 4/27 |
| [0,2,1] | 5 | 5/27 |
| [1,0,2] | 5 | 5/27 |
| [1,2,0] | 5 | 5/27 |
| [2,0,1] | 4 | 4/27 |
| [2,1,0] | 4 | 4/27 |

Trong khi xác suất lý tưởng của mỗi hoán vị là 1/6, tức 4,5/27. Vì 27 không chia hết cho 6, một ánh xạ từ **27 nhánh đồng xác suất** sang 6 kết quả **không thể** có mỗi kết quả đúng cùng số nhánh.

Sự khác biệt 4/27 so với 5/27 có thể khó phát hiện qua vài ví dụ ngẫu nhiên, nhưng đã đủ chứng minh thuật toán **không đồng đều**.

### Vấn đề không nằm ở hàm swap

Đổi chỗ là thao tác hoàn toàn hợp lệ. Lỗi nằm ở **phạm vi bốc j** và việc không “cố định” những vị trí đã hoàn thành. Fisher–Yates giới hạn j trong phần chưa được xáo trộn, bảo đảm mỗi lựa chọn có một ý nghĩa duy nhất trong quá trình tạo hoán vị.

### Một cách sai khác: sắp xếp bằng comparator ngẫu nhiên

Không nên viết một hàm so sánh trả ngẫu nhiên −1,0,+1 rồi giao cho `sort` để “shuffle”. Comparator của sort cần đáp ứng hợp đồng **nhất quán, phản xạ, bắc cầu** phù hợp; comparator ngẫu nhiên có thể vi phạm và gây kết quả không đáng tin.

Gán cho mỗi phần tử một khóa ngẫu nhiên rồi sort cũng cần xử lý **đụng khóa (ties)**, tính độc lập của các khóa và độ phân giải nguồn ngẫu nhiên, đồng thời thường tốn O(n log n). Fisher–Yates trực tiếp O(n) đơn giản hơn cho yêu cầu uniform permutation.

## 3. Thuật toán Fisher–Yates từ cuối về đầu

Ý tưởng: khi đang xử lý vị trí i, chọn **một phần tử ngẫu nhiên trong các vị trí 0..i** để đặt vào i. Sau đó coi vị trí i đã cố định và tiếp tục với 0..i−1.

Giả mã chuẩn:

~~~text
fisherYates(a):
    n = length(a)

    for i = n-1 downTo 1:
        j = uniformRandomInteger(0, i) // inclusive
        swap(a[i], a[j])

    return a
~~~

**Điểm bắt buộc:** j được chọn đồng đều trong đoạn **[0,i] gồm cả i**. Điều này có nghĩa là có i+1 lựa chọn, trong đó j=i là trường hợp **không thay đổi phần tử ở i**.

Trong Java:

~~~java
int j = rng.nextInt(i + 1);
~~~

Theo hợp đồng `nextInt(bound)` của Java, giá trị nhận được từ **0 bao gồm** đến **bound không bao gồm**. Vì `bound=i+1`, nên j chạy từ 0 đến i, đúng yêu cầu.

### Vùng đã hoàn thành và chưa hoàn thành

Ở mỗi lượt i:

~~~text
[ 0 ............ i | i+1 ..... n-1 ]
  phan chua co dinh     phan da co dinh
~~~

Sau khi đổi a[i] với a[j] (j≤i), vị trí i trở thành vị trí được chọn từ tất cả phần tử chưa cố định. Những vị trí >i không bị đụng lại vì j không thể vượt i.

### Vì sao vòng kết thúc tại i=1?

Sau khi đã cố định các vị trí n−1,n−2,…,1, chỉ còn duy nhất một phần tử ở vị trí 0. Không còn lựa chọn thực sự cần thực hiện: j bắt buộc bằng 0 nếu vẫn chạy lượt i=0.

Vì vậy vòng từ n−1 xuống 1 có **n−1 lần bốc chỉ số và n−1 phép swap**, đối với n≥1. Với n=0 hoặc n=1, vòng không chạy.

### Tại sao cần cho phép j=i?

Nếu cấm j=i, phần tử đang ở vị trí i bắt buộc phải rời vị trí đó tại lượt này. Khi ấy nhiều hoán vị, chẳng hạn hoán vị giữ nguyên, không thể đạt được. Đây là một biến thể khác (có liên hệ với thuật toán Sattolo), **không phải Fisher–Yates đồng đều trên tất cả n! hoán vị**.

## 4. Mô phỏng từng lượt trên mảng năm phần tử

Mảng ban đầu:

~~~text
a = [0,1,2,3,4]
n = 5
~~~

Để kiểm thử có thể **chỉ định trước** các lựa chọn hợp lệ (không phải nguồn RNG thật):

~~~text
Khi i=4, chon j=1
Khi i=3, chon j=0
Khi i=2, chon j=2
Khi i=1, chon j=0
~~~

Bảng trạng thái:

| Lượt | i | j | Trước swap | Sau swap | Vị trí đã cố định |
| ---: | ---: | ---: | --- | --- | --- |
| 1 | 4 | 1 | [0,1,2,3,4] | [0,4,2,3,1] | 4 |
| 2 | 3 | 0 | [0,4,2,3,1] | [3,4,2,0,1] | 3,4 |
| 3 | 2 | 2 | [3,4,2,0,1] | [3,4,2,0,1] | 2,3,4 |
| 4 | 1 | 0 | [3,4,2,0,1] | [4,3,2,0,1] | 1,2,3,4 |

Kết quả cuối:

~~~text
[4,3,2,0,1]
~~~

Phần tử ở vị trí 0 tự động là phần tử còn lại. Việc j=i ở lượt thứ ba **không phải lỗi hay “không đủ ngẫu nhiên”**; đó là một nhánh cần có để các hoán vị đạt xác suất đúng.

### Chọn sẵn các j để làm gì?

Trong test và tài liệu, cách này giúp truy vết và có stdout chính xác. Nhưng **một dãy j cố định không tạo ra một hoán vị ngẫu nhiên**; nó chỉ kiểm cơ chế swap, giới hạn và vòng lặp. Trong chương trình thật, mỗi j phải được sinh bằng nguồn ngẫu nhiên có phân phối đúng trong [0,i].

## 5. Chứng minh xáo trộn đồng đều

Xét n **phần tử được gắn nhãn phân biệt**. Ở lượt đầu i=n−1, thuật toán chọn đều một trong n phần tử để đặt vào vị trí cuối, mỗi phần tử xác suất 1/n.

Sau khi đã chọn vị trí cuối, chỉ còn n−1 phần tử chưa cố định. Ở lượt tiếp theo, j đều trên [0,n−2], nên mỗi phần tử còn lại có xác suất 1/(n−1) được đặt vào vị trí n−2, **có điều kiện trên mọi lựa chọn trước đó**.

Tiếp tục cho tới vị trí 1. Với một hoán vị cụ thể:

~~~text
P(hoan vi cu the)
  = 1/n * 1/(n-1) * ... * 1/2
  = 1/n!
~~~

Đây là chứng minh trực tiếp bằng **quy tắc xác suất có điều kiện**. Nó đòi mỗi lần chọn j thực sự đồng đều trên phạm vi đang xét và phù hợp với phân phối có điều kiện (thông thường là các lần bốc độc lập từ RNG chất lượng phù hợp).

### Mỗi chuỗi lựa chọn sinh đúng một hoán vị

Tại lượt i có i+1 lựa chọn; tổng số dãy chỉ số hợp lệ là:

~~~text
n * (n-1) * ... * 2 = n!
~~~

Mỗi dãy j tạo một hoán vị. Ngược lại, cho một hoán vị đích và dãy phần tử phân biệt ban đầu, vị trí cuối bắt buộc chọn đúng phần tử đích ở lượt đầu; sau đó vị trí n−2 cũng có lựa chọn bắt buộc, v.v. Vì vậy có **đúng một chuỗi lựa chọn** dẫn tới một hoán vị cụ thể.

Khi các nhánh ở lượt i đều có xác suất 1/(i+1), mọi chuỗi lựa chọn xác suất 1/n!, nên mọi hoán vị đồng đều.

### Bất biến của vòng lặp

Ngay trước lượt xử lý i:

1. Hậu tố a[i+1..n−1] đã được cố định và không bị sửa nữa.
2. Tiền tố a[0..i] chứa đúng các phần tử chưa được đặt vào hậu tố.
3. Với điều kiện trên hậu tố đã được chọn, mọi phần tử còn lại có cơ hội bằng nhau để xuất hiện tại vị trí i.

Lượt chọn j đồng đều trong [0,i] đặt một phần tử bất kỳ còn lại vào i, đồng thời bảo toàn hai tính chất đầu. Đây là cơ sở cho phép chứng minh bằng quy nạp rằng thuật toán trả về hoán vị đồng đều.

### Không nhầm xác suất mỗi nhánh với xác suất toàn đường đi

Các lượt có kích thước miền j khác nhau: n, n−1, ..., 2. Không phải mỗi lượt đều có xác suất 1/n. Phải nhân xác suất **có điều kiện theo từng lượt**, chứ không lấy 1/n cho tất cả.

## 6. Vì sao kết quả luôn là một hoán vị hợp lệ?

Mỗi bước chỉ **đổi chỗ hai phần tử hiện có**. Phép swap không sinh phần tử mới, không xóa phần tử và không làm thay đổi số lần xuất hiện của mỗi giá trị.

Do đó, dù RNG có hoàn toàn thiên lệch, thuật toán vẫn luôn trả về một **hoán vị hợp lệ** về mặt multiset. Tuy nhiên điều này **không chứng minh tính đồng đều**.

Cần tách hai thuộc tính:

- **Permutation correctness:** đầu ra chứa chính xác các phần tử đầu vào, cùng số lần xuất hiện.
- **Distribution correctness:** mọi hoán vị vị trí phân biệt có xác suất 1/n!.

Một bộ kiểm thử chỉ so hai mảng sau khi sort để kiểm multiset sẽ bắt lỗi làm mất phần tử, nhưng **không bắt được** bộ shuffle có phân phối lệch. Vì vậy các test phải gồm cả kiểm ranh giới lựa chọn và kiểm cách ánh xạ từ dãy j sang hoán vị.

## 7. Độ phức tạp thời gian và bộ nhớ

Với mảng có n phần tử và truy cập chỉ số/đổi chỗ O(1):

- Vòng lặp chạy **max(0,n−1)** lượt.
- Mỗi lượt lấy đúng một chỉ số ngẫu nhiên có giới hạn rồi swap hai giá trị.
- Tổng thời gian **O(n)**.
- Bộ nhớ phụ của phiên bản in-place chỉ gồm vài biến i,j,temp: **O(1)**.
- Không cần tạo một mảng phụ O(n) hay sort.

Nếu API yêu cầu **giữ nguyên đầu vào**, phải sao chép mảng trước khi xáo, cần **O(n) bộ nhớ đầu ra** và O(n) thời gian sao chép. Vòng shuffle trên bản sao vẫn O(n)/O(1) phụ ngoài mảng sao chép.

### Số lần bốc random và swap

Với n≥1:

~~~text
Random bounded draws: n-1
Swap calls:           n-1
~~~

Nếu j=i, một phép swap với chính mình không đổi mảng; vẫn có thể gọi swap cho đơn giản. Tránh swap khi j=i là một tối ưu vi mô không làm thay đổi phân phối nếu không làm thay đổi việc bốc j.

Với n=0 hoặc n=1, số lượt là 0. Không gọi `nextInt(0)` vì Java sẽ ném ngoại lệ khi bound không dương.

### Chi phí API truy cập dữ liệu

O(n) giả định mảng hoặc cấu trúc truy cập ngẫu nhiên O(1). Với một `LinkedList`, việc `get(i)`/`set(i)` lặp lại có thể tốn O(n) mỗi thao tác, dẫn tới O(n²). Khi shuffle List, nên ưu tiên `ArrayList`/mảng hoặc dùng API thư viện phù hợp với loại dữ liệu, thay vì áp dụng máy móc phép truy cập theo chỉ số vào linked list.

## 8. Chọn chỉ số đồng đều và tránh modulo bias

Điều kiện quan trọng của Fisher–Yates là:

~~~text
j uniform in {0,1,...,i}
~~~

Không phải mọi cách biến số ngẫu nhiên thành chỉ số đều cho phân phối đều. Ví dụ:

~~~text
j = randomBits() % (i+1)
~~~

**có thể bị lệch (modulo bias)** nếu số trạng thái nguồn đồng đều không chia hết cho i+1.

### Ví dụ nguồn có 8 giá trị, cần 6 lựa chọn

Giả sử nguồn ngẫu nhiên cho số nguyên đều trên {0,1,2,3,4,5,6,7}. Lấy `%6` cho:

~~~text
Nguon:      0 1 2 3 4 5 6 7
Sau modulo: 0 1 2 3 4 5 0 1
~~~

Hai giá trị 0 và 1 có xác suất **2/8** mỗi giá trị; bốn giá trị 2,3,4,5 chỉ có **1/8** mỗi giá trị. Không thể gọi kết quả là uniform [0,5].

### Dùng API bounded của Java

Với `java.util.random.RandomGenerator` (Java 17):

~~~java
int j = rng.nextInt(i + 1);
~~~

Lệnh này yêu cầu một giá trị từ 0 đến i theo hợp đồng phân phối của API, thay vì tự `%` một số nguyên bất kỳ. Việc hiện thực bounded sampling có thể dùng các kỹ thuật tránh lệch như **rejection sampling**.

### Rejection sampling ở mức khái niệm

Nếu nguồn có R kết quả đồng xác suất và cần b lựa chọn, có thể chỉ chấp nhận một số lượng kết quả là **bội số lớn nhất của b không vượt R**, loại các kết quả dư rồi lấy modulo b. Mỗi số dư khi ấy có cùng số lượng tiền ảnh, nên phân phối đều.

Đây là giải thích lý thuyết; khi dùng JDK, nên tận dụng `nextInt(bound)` thay vì tự cài thuật toán có thể gặp lỗi overflow hoặc giới hạn ngẫu nhiên.

### Một biến thể off-by-one phổ biến

~~~java
int j = rng.nextInt(i);     // SAI cho Fisher-Yates
~~~

Giá trị này chỉ từ 0 đến i−1 và **không thể bằng i**, nên loại nhánh tự giữ phần tử hiện tại. Đặc biệt `nextInt(0)` còn không hợp lệ. Viết đúng `nextInt(i+1)` khi i chạy từ n−1 xuống 1.

## 9. RNG, seed và yêu cầu bảo mật

Một thuật toán shuffle tốt chỉ bảo đảm tính đồng đều nếu **nguồn chọn chỉ số** thỏa giả định. Cần phân biệt thuật toán hoán vị và chất lượng hoặc tính dự đoán được của RNG.

### `Random` cho mô phỏng và test tái lập

~~~java
import java.util.Random;

Random rng = new Random(2026L);
~~~

Với cùng seed và cùng chuỗi lệnh gọi trong cùng hợp đồng thuật toán của `Random`, kết quả được lặp lại. Điều này hữu ích cho test, demo và tái hiện lỗi.

Nhưng `java.util.Random` không được thiết kế để chống dự đoán trong những tình huống an toàn thông tin. Một shuffle có thể gần đồng đều về phân phối nhưng vẫn **dự đoán được** nếu seed bị lộ.

### `SplittableRandom` cho công việc không nhạy cảm bảo mật

`java.util.SplittableRandom` cung cấp nguồn giả ngẫu nhiên hiệu quả và phù hợp nhiều tác vụ mô phỏng, sinh dữ liệu test. Nó không phải bộ sinh ngẫu nhiên mật mã. Các thuật toán và bảo đảm reproducibility phải được đọc theo hợp đồng của lớp/JDK đang dùng nếu cần kết quả giống tuyệt đối trên nhiều hệ thống.

### `SecureRandom` cho trường hợp nhạy cảm

~~~java
import java.security.SecureRandom;

SecureRandom secure = new SecureRandom();
~~~

Khi xáo trộn có yêu cầu chống dự đoán, ví dụ một số cơ chế phát thẻ/bốc lựa chọn có tác động an toàn, nên cân nhắc nguồn ngẫu nhiên mật mã như `SecureRandom`.

**Fisher–Yates không tạo thêm entropy**: nếu RNG yếu hoặc seed dễ đoán, thuật toán shuffle không tự sửa được điều đó. Với hệ thống có yêu cầu công bằng/audit/bảo mật thực tế, còn cần thiết kế quy trình ghi nhận, kiểm chứng nguồn randomness và quản lý seed phù hợp.

### Không tái tạo RNG mỗi lượt

Tránh tạo `new Random(seed)` hoặc một RNG mới trong **mỗi vòng i**; việc lặp seed có thể tạo cùng giá trị đầu của chuỗi và phá giả định độc lập. Thường tạo một RNG một lần rồi dùng xuyên suốt toàn bộ lượt shuffle.

## 10. Java 17: chương trình độc lập có kiểm thử đầy đủ

Chương trình dùng `java.util.random.RandomGenerator` để giao diện shuffle chấp nhận nhiều nguồn RNG. Các hàm:

- `shuffle(int[], RandomGenerator)`: xáo trộn mảng **tại chỗ**, chọn `j=rng.nextInt(i+1)`.
- `shuffledCopy`: tạo bản sao để không sửa mảng gốc.
- `scriptedShuffle`: nhận danh sách j hợp lệ **chỉ dành cho trace/test**, không giả vờ là RNG.
- `sameMultiset`: kiểm đầu ra giữ đủ giá trị kể cả phần tử trùng.
- `enumerateAllChoices`: thử mọi dãy j hợp lệ với n=6, xác nhận **720 nhánh cho 720 hoán vị khác nhau**.
- `enumerateWrongAllIndex`: xác minh phản ví dụ thuật toán sai trên n=3 với 27 nhánh.
- Ví dụ `Random` có seed, `SecureRandom`, mảng rỗng, một phần tử, phần tử trùng và lựa chọn j không hợp lệ.

Không sử dụng thư viện ngoài JDK 17. Chương trình không in nội dung shuffle ngẫu nhiên thực tế để stdout **không phụ thuộc seed, nền tảng hoặc hệ điều hành**; thay vào đó in thuộc tính tái lập và bảo toàn mảng.

**Lưu toàn bộ vào tệp `FisherYatesDemo.java`:**

~~~java
import java.security.SecureRandom;
import java.util.Arrays;
import java.util.HashSet;
import java.util.Map;
import java.util.Objects;
import java.util.Random;
import java.util.Set;
import java.util.TreeMap;
import java.util.random.RandomGenerator;

public class FisherYatesDemo {

    // Production algorithm: all j in [0,i] are allowed.
    public static void shuffle(
            int[] values, RandomGenerator rng) {
        Objects.requireNonNull(values, "values");
        Objects.requireNonNull(rng, "rng");

        for (int i = values.length - 1; i > 0; i--) {
            int j = rng.nextInt(i + 1);
            swap(values, i, j);
        }
    }

    public static int[] shuffledCopy(
            int[] values, RandomGenerator rng) {
        Objects.requireNonNull(values, "values");
        int[] copy = values.clone();
        shuffle(copy, rng);
        return copy;
    }

    private static void swap(int[] values, int i, int j) {
        int temp = values[i];
        values[i] = values[j];
        values[j] = temp;
    }

    // Deterministic trace helper; NOT a random sampler.
    // choices[0] is j for i=n-1, then i=n-2, ..., i=1.
    public static void scriptedShuffle(
            int[] values, int[] choices) {
        Objects.requireNonNull(values, "values");
        Objects.requireNonNull(choices, "choices");

        if (choices.length != Math.max(0, values.length - 1)) {
            throw new IllegalArgumentException(
                    "invalid choice count");
        }

        // Validate the entire script before changing input.
        for (int i = values.length - 1, t = 0;
                i > 0; i--, t++) {
            if (choices[t] < 0 || choices[t] > i) {
                throw new IllegalArgumentException(
                        "choice out of range");
            }
        }

        for (int i = values.length - 1, t = 0;
                i > 0; i--, t++) {
            swap(values, i, choices[t]);
        }
    }

    public static boolean sameMultiset(int[] left, int[] right) {
        if (left.length != right.length) {
            return false;
        }
        int[] a = left.clone();
        int[] b = right.clone();
        Arrays.sort(a);
        Arrays.sort(b);
        return Arrays.equals(a, b);
    }

    private static class Counts {
        int paths;
        int collisions;
    }

    // Exhaustive enumeration of every valid Fisher-Yates choice.
    private static void enumerateAllChoices(
            int[] current, int i,
            Set<String> outputs, Counts counts) {
        if (i <= 0) {
            counts.paths++;
            if (!outputs.add(Arrays.toString(current))) {
                counts.collisions++;
            }
            return;
        }

        for (int j = 0; j <= i; j++) {
            int[] next = current.clone();
            swap(next, i, j);
            enumerateAllChoices(next, i - 1, outputs, counts);
        }
    }

    // Deliberately wrong shuffle for a counterexample.
    // Each i swaps with any j in the whole array.
    private static void enumerateWrongAllIndex(
            int[] current, int i,
            Map<String, Integer> frequency) {
        if (i == current.length) {
            StringBuilder key = new StringBuilder();
            for (int value : current) {
                key.append(value);
            }
            frequency.merge(key.toString(), 1, Integer::sum);
            return;
        }

        for (int j = 0; j < current.length; j++) {
            int[] next = current.clone();
            swap(next, i, j);
            enumerateWrongAllIndex(next, i + 1, frequency);
        }
    }

    public static void main(String[] args) {
        int[] original = {0, 1, 2, 3, 4};
        int[] scripted = original.clone();

        scriptedShuffle(scripted, new int[] {1, 0, 2, 0});
        System.out.println("original = "
                + Arrays.toString(original));
        System.out.println("scripted = "
                + Arrays.toString(scripted));
        System.out.println("scripted is permutation = "
                + sameMultiset(original, scripted));

        int[] seededFirst = shuffledCopy(
                original, new Random(2026L));
        int[] seededSecond = shuffledCopy(
                original, new Random(2026L));
        System.out.println("same seed repeatable = "
                + Arrays.equals(seededFirst, seededSecond));
        System.out.println("original unchanged = "
                + Arrays.equals(
                        original, new int[] {0, 1, 2, 3, 4}));

        int[] empty = {};
        int[] single = {9};
        shuffle(empty, new Random(1L));
        shuffle(single, new Random(1L));
        System.out.println("empty = "
                + Arrays.toString(empty));
        System.out.println("single = "
                + Arrays.toString(single));

        int[] duplicates = {7, 7, 9};
        scriptedShuffle(duplicates, new int[] {1, 0});
        System.out.println("duplicates scripted = "
                + Arrays.toString(duplicates));

        int[] secure = {4, 5, 6, 7, 8};
        int[] secureOriginal = secure.clone();
        shuffle(secure, new SecureRandom());
        System.out.println("secure keeps multiset = "
                + sameMultiset(secureOriginal, secure));

        try {
            scriptedShuffle(
                    new int[] {1, 2, 3},
                    new int[] {3, 0});
        } catch (IllegalArgumentException exception) {
            System.out.println("invalid choice: "
                    + exception.getMessage());
        }

        int[] six = {0, 1, 2, 3, 4, 5};
        Set<String> allOutputs = new HashSet<>();
        Counts counts = new Counts();

        enumerateAllChoices(
                six, six.length - 1, allOutputs, counts);

        if (counts.paths != 720
                || allOutputs.size() != 720
                || counts.collisions != 0) {
            throw new AssertionError(
                    "Fisher-Yates enumeration failed");
        }

        System.out.println(
                "all 6! paths = " + counts.paths);
        System.out.println(
                "all 6! distinct permutations = "
                + allOutputs.size());
        System.out.println(
                "one-to-one paths = "
                + (counts.collisions == 0));

        Map<String, Integer> wrong = new TreeMap<>();
        enumerateWrongAllIndex(
                new int[] {0, 1, 2}, 0, wrong);
        System.out.println("wrong n=3 counts = " + wrong);
    }
}
~~~

**Biên dịch và chạy** trên JDK 17:

~~~bash
javac FisherYatesDemo.java
java FisherYatesDemo
~~~

**Stdout được xác định chính xác:**

~~~text
original = [0, 1, 2, 3, 4]
scripted = [4, 3, 2, 0, 1]
scripted is permutation = true
same seed repeatable = true
original unchanged = true
empty = []
single = [9]
duplicates scripted = [9, 7, 7]
secure keeps multiset = true
invalid choice: choice out of range
all 6! paths = 720
all 6! distinct permutations = 720
one-to-one paths = true
wrong n=3 counts = {012=4, 021=5, 102=5, 120=5, 201=4, 210=4}
~~~

### Các ý nghĩa cần đọc đúng

- `scripted` chỉ là **một đường đi cố định để kiểm test**, không phải kết quả lấy ngẫu nhiên.
- `same seed repeatable` kiểm hai `java.util.Random` có cùng seed và được dùng theo cùng chuỗi lời gọi.
- `secure keeps multiset` không khẳng định mẫu bảo mật luôn khác input; nó chỉ kiểm bảo toàn các phần tử, còn nguồn random là `SecureRandom`.
- `all 6! paths` và `all 6! distinct permutations` cùng bằng 720, tức mỗi chuỗi lựa chọn j hợp lệ tạo một hoán vị riêng khi phần tử ban đầu phân biệt.
- Bảng `wrong n=3 counts` cho thấy cách hoán đổi với j ở toàn bộ mảng có phân phối **không đồng đều**, dù luôn trả một hoán vị hợp lệ.

### Vì sao Java này chạy trên cả mảng rỗng?

Vòng ngoài có điều kiện `i>0`, nên với n=0 hoặc n=1 không có lần gọi RNG. Điều này tránh `nextInt(0)` và lỗi chỉ số âm. Hàm `scriptedShuffle` yêu cầu số lượng lựa chọn `max(0,n−1)` và kiểm từng j trước khi swap.

### Tại sao kiểm `RandomGenerator` nhưng demo vẫn dùng `Random` và `SecureRandom`?

`RandomGenerator` là interface chuẩn Java 17 cho các nguồn sinh ngẫu nhiên. `Random` cung cấp kết quả lặp với seed, còn `SecureRandom` phục vụ tình huống cần nguồn khó dự đoán. Giao diện shuffle chỉ cần khả năng sinh chỉ số bounded trong [0,i], không phụ thuộc lớp cụ thể.

## 11. Phần tử trùng giá trị và tính đồng đều

Nếu đầu vào là `[A,A,B]`, có **3!=6 hoán vị của ba vị trí được gắn nhãn**:

~~~text
A1, A2, B
A1, B,  A2
A2, A1, B
A2, B,  A1
B,  A1, A2
B,  A2, A1
~~~

Khi bỏ nhãn và chỉ giữ giá trị hiển thị, có ba dãy khác nhau:

~~~text
[A,A,B]
[A,B,A]
[B,A,A]
~~~

Mỗi dãy có đúng **2** hoán vị vị trí tạo ra, nên mỗi dãy giá trị có xác suất:

~~~text
2/6 = 1/3
~~~

Nói chung, nếu một multiset có n phần tử với các nhóm giá trị trùng có kích thước c₁,c₂,…,cₖ, thì số dãy giá trị phân biệt là:

~~~text
n! / (c1! * c2! * ... * ck!)
~~~

Mỗi dãy giá trị phân biệt tương ứng với **c1!·c2!·...·ck!** hoán vị các nhãn, bằng nhau cho mọi dãy. Vì Fisher–Yates đồng đều trên các nhãn, nó cũng đồng đều trên các dãy giá trị phân biệt khi những phần tử trùng được coi là không phân biệt.

### Điều cần tránh

Không kết luận rằng thuật toán sai vì một mảng chứa toàn giá trị giống nhau thường trả lại đúng mảng ban đầu. Với `[7,7,7]`, có 3!=6 hoán vị **vị trí**, nhưng tất cả hiển thị như một dãy giá trị duy nhất.

Nếu bài thực tế cần đối xử khác nhau với những bản ghi có cùng giá trị hiển thị nhưng ID khác nhau, hãy hiểu chúng là các đối tượng phân biệt theo ID, dù trường nội dung trùng.

## 12. Phiên bản Fisher–Yates duyệt từ đầu

Một cách cài đúng tương đương về phân phối:

~~~text
for i = 0..n-2:
    j = uniformRandomInteger(i, n-1)
    swap(a[i], a[j])
~~~

Ở mỗi lượt i, ta chọn ngẫu nhiên phần tử thuộc **hậu tố chưa cố định [i,n−1]** để đặt vào a[i], rồi tiến sang i+1.

Điểm chung với phiên bản duyệt ngược là: **j chỉ chọn trong vùng chưa cố định và phải bao gồm vị trí hiện tại i**.

### Cài bounded từ Java

Để lấy j đều trong [i,n−1], với n>i:

~~~java
int j = i + rng.nextInt(n - i);
~~~

`nextInt(n-i)` trả số trong [0,n-i−1]; cộng i cho ra [i,n−1]. Công thức này không áp dụng khi `n-i=0`, nên điều kiện vòng hợp lý là i<n−1.

### Không lẫn hai phiên bản

- **Duyệt ngược:** i từ n−1 xuống 1, j trong [0,i].
- **Duyệt xuôi:** i từ 0 lên n−2, j trong [i,n−1].

Nếu giữ vòng duyệt ngược nhưng dùng miền j của phiên bản xuôi, hoặc ngược lại, lập luận xác suất đã thay đổi và dễ tạo bias.

## 13. Phân biệt với thuật toán Sattolo

Một biến thể trông rất giống Fisher–Yates:

~~~text
for i = n-1 downTo 1:
    j = uniformRandomInteger(0,i-1)
    swap(a[i],a[j])
~~~

Khác biệt duy nhất: **không cho phép j=i**. Với n>1 và các phần tử phân biệt, biến thể **Sattolo** này tạo một **chu trình dài n** trong biểu diễn hoán vị và chỉ có **(n−1)!** đầu ra có thể nhận, thay vì tất cả n!.

Ví dụ n=3, Fisher–Yates cho 6 hoán vị; Sattolo chỉ cho 2 hoán vị chu trình 3. Nó có thể hữu ích khi chủ đích muốn một hoán vị chu trình đơn, nhưng **không phải shuffle đồng đều trên toàn bộ n! hoán vị**.

### “Không có phần tử ở vị trí cũ” khác với shuffle thường

Một **derangement** là hoán vị không có điểm cố định. Sattolo tạo chu trình duy nhất, nên với n>1 nó không có điểm cố định, nhưng **không đồng đều trên toàn bộ các derangement** khi n đủ lớn. Đừng dùng Sattolo nếu đề yêu cầu “mỗi derangement có cùng xác suất” mà không chứng minh phân phối phù hợp.

### Khi nào một kết quả giữ nguyên là hợp lệ?

Hoán vị đồng nhất (input giữ nguyên) là một trong n! hoán vị và phải có xác suất 1/n!, không phải một sự cố cần loại bỏ hoặc chạy lại shuffle. Nếu một yêu cầu sản phẩm không muốn trả nguyên thứ tự, đó là một **bài toán phân phối có điều kiện khác**; cần thiết kế lấy mẫu riêng, không tự bỏ nhánh j=i trong Fisher–Yates.

## 14. Kiểm thử exhaustive và kiểm thử thống kê

### Exhaustive cho n nhỏ

Với n=6, số đường đi hợp lệ của Fisher–Yates là:

~~~text
6 * 5 * 4 * 3 * 2 = 720
~~~

Ta có thể duyệt mọi lựa chọn j tại từng bước thay vì dùng RNG:

~~~text
enumerate(a,i):
    if i <= 0:
        record(copyOf(a))
        return

    for j=0..i:
        next=copyOf(a)
        swap(next[i],next[j])
        enumerate(next,i-1)
~~~

Nếu input gồm sáu nhãn khác nhau, có **720 kết quả phân biệt** và không có trùng lặp. Đây là một kiểm tra mạnh cho **cơ chế hoán vị và phạm vi j**, bổ sung cho chứng minh xác suất.

Lưu ý: exhaustively enumerate **không tự kiểm chất lượng RNG**. Nó chứng minh mọi đường đi hợp lệ xuất hiện đúng một lần về mặt cấu trúc, nhưng nếu RNG thiên lệch, xác suất các đường đi vẫn có thể khác nhau.

### Kiểm phân phối bằng thực nghiệm

Có thể shuffle n=3 hoặc n=4 nhiều lần, đếm số lần xuất hiện của từng hoán vị. Kỳ vọng gần T/n! sau T lần thử khi RNG đủ tốt và các lần thử đủ độc lập. Dùng kiểm định thống kê như chi-squared khi cần, và chọn ngưỡng hợp lý.

**Không** kiểm `count == T/n!` một cách tuyệt đối: ngay cả nguồn ngẫu nhiên hoàn hảo cũng có dao động tần suất. Một kết quả thống kê không đạt ngưỡng chưa xác định ngay nguyên nhân, và kết quả đạt ngưỡng **không phải chứng minh toán học** về tính đồng đều.

### Test có thể tái lập

Dùng seed cố định để kiểm bất biến/điều kiện biên. Lưu seed hoặc sequence j khi báo lỗi để có thể chạy lại cùng đường đi. Nếu cần test lỗi hiếm, ưu tiên **scripted RNG** tạo chính xác các lựa chọn cần kiểm thay vì phụ thuộc một seed “may mắn”.

## 15. Các bất biến và thuộc tính kiểm thử

Một bộ kiểm thử tốt gồm ít nhất:

1. **Độ dài bảo toàn:** output.length == input.length.
2. **Multiset bảo toàn:** sau sort hoặc đếm tần suất, các phần tử giống trước shuffle.
3. **Không thêm/xóa phần tử**: tổng số lượng không đổi.
4. **Đường đi hợp lệ:** tại lượt i, 0≤j≤i.
5. **Các vị trí đã cố định không đổi** trong những lượt sau.
6. **Cả j=0 và j=i** đều là lựa chọn hợp lệ.
7. **n=0, n=1** không gọi bounded random với bound 0.
8. **n=2** có đúng hai hoán vị với xác suất 1/2 mỗi hoán vị.
9. **n=3** có đúng sáu hoán vị với chuỗi j hợp lệ.
10. **n=6** exhaustive cho 720 đường đi, 720 đầu ra phân biệt.
11. **In-place** thay đổi chính mảng đầu vào, không cấp bản sao O(n).
12. **Copy API** giữ nguyên input và trả về mảng khác.
13. **Cùng seed** và cùng luồng gọi cho `Random` cho cùng kết quả.
14. **Khác seed không bảo đảm kết quả khác nhau**: trùng hoán vị vẫn có xác suất.
15. **Mảng có duplicate** giữ đúng tần suất từng giá trị.
16. **Không bao giờ gọi `%` trực tiếp** trên nguồn có thể gây modulo bias mà không xử lý điều kiện.
17. **Không loại j=i** trừ khi cố tình muốn một thuật toán khác.
18. **Không yêu cầu output khác input** trong shuffle đồng đều chuẩn.
19. **RNG mạnh** cần được chọn riêng nếu kết quả phải khó dự đoán.
20. **Truy cập O(1)** phải có nếu tuyên bố tổng thời gian O(n) với cấu trúc tổng quát.

### Phép kiểm độc lập về multiset

Nếu mảng có n phần tử, so hai bản sao sau sort cần O(n log n) cho việc kiểm. Điều đó **không làm thay đổi độ phức tạp thuật toán shuffle**, vì đây là chi phí của test bên ngoài.

Nếu miền giá trị hẹp, có thể đếm tần suất trong một cấu trúc map; nhưng vẫn phải đối chiếu đúng số lần xuất hiện, không chỉ so tổng hay xor. Hai mảng khác nhau có thể có cùng tổng và xor.

## 16. In-place, immutable API và kiểu dữ liệu

### Xáo trực tiếp `int[]`

Phù hợp khi người gọi cho phép sửa input. Một hàm có thể trả `void` và thao tác ngay trên mảng. Chi phí phụ O(1).

### Xáo trên bản sao

~~~java
int[] copy = source.clone();
shuffle(copy, rng);
return copy;
~~~

Phù hợp khi danh sách ban đầu cần dùng lại hoặc một hàm được thiết kế theo hướng tránh side effect. Tổng bộ nhớ phải tính cả bản sao O(n).

### Với đối tượng hoặc phần tử generic

Đổi chỗ giữa hai phần tử không cần sao chép toàn bộ đối tượng; chỉ đổi **tham chiếu**. Có thể cài Fisher–Yates cho `T[]` bằng cùng vòng lặp hoặc dùng thư viện:

~~~java
Collections.shuffle(list, random);
~~~

Khi dùng danh sách có nhiều phần tử, cần để ý cấu trúc có truy cập ngẫu nhiên tốt như `ArrayList`. Đối với API `List<T>`, nếu chọn cách dùng `get(i)`/`set(i)`, đặc biệt tránh giả định LinkedList cho truy cập O(1).

`Collections.shuffle` là API tiện lợi trong Java và thường được mô tả là tạo hoán vị với khả năng xuất hiện gần đồng đều dựa trên nguồn giả ngẫu nhiên. Tuy nhiên khi bài yêu cầu **chứng minh thuật toán**, cài đặt vòng Fisher–Yates trực tiếp giúp làm rõ miền lấy j.

### Input rỗng hoặc tham chiếu null

- Rỗng: trả rỗng, không gọi RNG.
- Một phần tử: giữ nguyên.
- `null`: chương trình demo ném `NullPointerException` bằng `Objects.requireNonNull`.
- RNG `null`: cũng ném `NullPointerException`, kể cả input rỗng, để hợp đồng API nhất quán.

Không cần đặc biệt loại các giá trị âm, 0 hoặc phần tử trùng; thuật toán chỉ đổi vị trí, không tính toán trên giá trị.

## 17. Fisher–Yates một phần và chọn k phần tử

Nếu cần **k phần tử khác nhau** từ n vị trí với k≤n, ta có thể chỉ chạy **k lượt** của Fisher–Yates mà không xáo phần còn lại.

### Cách chọn k phần tử đặt về cuối mảng

~~~text
for i=n-1 downTo n-k:
    j=uniformRandomInteger(0,i)
    swap(a[i],a[j])

selected = a[n-k..n-1]
~~~

Khi chọn k lượt, các phần tử được đặt vào k vị trí cuối tạo một **mẫu có thứ tự không lặp**. Nếu không quan tâm thứ tự, tập k phần tử được chọn là đồng đều trên các tổ hợp kích thước k, dưới giả định RNG tương tự Fisher–Yates.

Thời gian O(k) cho phần swap, bộ nhớ phụ O(1) nếu dùng trực tiếp mảng và không tính đầu ra. Nếu cần trả k phần tử trong mảng riêng, đầu ra O(k).

### Cẩn thận khi k=0 hoặc k=n

- k=0: không swap, tập chọn rỗng.
- k=n: thực hiện n lượt nếu theo công thức trên, trong đó lượt i=0 có j=0 duy nhất. Có thể bỏ lượt cuối để dùng n−1 lượt như shuffle chuẩn.
- k>n hoặc k<0: phải từ chối đầu vào hoặc có quy ước riêng; không dùng chỉ số âm.

### So với reservoir sampling

**Reservoir sampling** giải bài toán chọn k phần tử từ một **dòng dữ liệu (stream)** khi n chưa biết trước hoặc không lưu toàn bộ dữ liệu. Fisher–Yates thường tự nhiên khi đã có mảng n phần tử trong RAM. Cả hai có thể tạo mẫu ngẫu nhiên đồng đều, nhưng điều kiện truy cập dữ liệu và không gian lưu trữ khác nhau.

### Chọn k đầu tiên trong bản shuffle hoàn chỉnh

Một cách đơn giản khác là shuffle toàn bộ O(n), rồi lấy k phần tử đầu tiên. Nó đúng về phân phối nhưng làm nhiều việc hơn cần thiết nếu k rất nhỏ và n rất lớn.

## 18. Các lỗi triển khai thường gặp

| Lỗi | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Lấy j ngẫu nhiên từ [0,n−1] ở mọi lượt | Phân phối hoán vị lệch | Chọn [0,i] ở vòng ngược |
| Viết `nextInt(i)` | Loại j=i, không uniform all permutations | `nextInt(i+1)` |
| Viết `nextInt(0)` khi i=0 | Java ném ngoại lệ | Dừng ở i>0 |
| Chọn j từ [0,i−1] cố ý nhưng gọi Fisher–Yates | Sinh biến thể Sattolo | Gọi đúng thuật toán |
| Bỏ qua nhánh j=i | Thiếu hoán vị giữ nguyên | Cho phép tự swap |
| Tự `randomInt % bound` | Modulo bias | Dùng bounded RNG |
| Sort với comparator ngẫu nhiên | Vi phạm comparator contract | Dùng Fisher–Yates |
| Không cố định vùng đã chọn | Có thể đổi lại vị trí cũ | Giới hạn j vào vùng chưa cố định |
| Dùng vòng xuôi với miền j của vòng ngược | Sai lập luận đồng đều | Giữ cặp vòng/miền chuẩn |
| Tạo RNG mới mỗi lượt cùng seed | Dãy lựa chọn phụ thuộc bất thường | Tạo RNG một lần |
| Nghĩ cùng seed là bảo mật | Shuffle dễ dự đoán | SecureRandom cho yêu cầu bảo mật |
| Nghĩ mỗi lần phải cho output khác input | Loại một hoán vị hợp lệ | Chấp nhận identity |
| Trùng giá trị bị coi là thiếu uniform | Nhầm vị trí với giá trị | Gắn nhãn phần tử khi chứng minh |
| Chỉ test multiset rồi nói đã chứng minh uniform | Bỏ qua bias | Chứng minh/xét phân phối |
| Chỉ test một seed | Không bao phủ mọi nhánh | Scripted choices và exhaustive |
| Assert tần suất phải đúng tuyệt đối | Test random dễ thất bại giả | Chấp nhận dao động thống kê |
| Dùng LinkedList với get/set theo index | Có thể thành O(n²) | ArrayList/mảng hoặc API phù hợp |
| Hàm copy nhưng sửa mảng gốc | Side effect | Clone trước khi shuffle |
| Cho j vượt i | Động vào hậu tố đã cố định | Validate j∈[0,i] |
| Không kiểm k khi partial shuffle | Out of range | Yêu cầu 0≤k≤n |
| Coi `Random` có tính mật mã | Không chống dự đoán | SecureRandom/thiết kế an toàn |
| Coi shuffle bảo đảm công bằng ứng dụng | Bỏ qua nguồn ngẫu nhiên và vận hành | Kiểm RNG, quy trình, audit |

## 19. Bài tập thực hành

1. Liệt kê mọi hoán vị của [0,1,2].
2. Tính xác suất của mỗi hoán vị khi n=3 và shuffle đồng đều.
3. Mô phỏng Fisher–Yates ngược trên [0,1,2,3,4] với j=[1,0,2,0].
4. Giải thích vì sao kết quả trace là [4,3,2,0,1].
5. Chứng minh vị trí n−1 được chọn đều từ n phần tử.
6. Chứng minh xác suất mỗi hoán vị là 1/n! bằng xác suất có điều kiện.
7. Nêu invariant của hậu tố đã cố định.
8. Giải thích vì sao j=i phải hợp lệ.
9. So sánh `rng.nextInt(i+1)` với `rng.nextInt(i)`.
10. Chứng minh `nextInt(0)` không được gọi ở n=0,1.
11. Tạo phản ví dụ cho thuật toán “mỗi lượt chọn j trong toàn mảng”.
12. Liệt kê 27 đường đi của thuật toán sai với n=3 và đếm mỗi kết quả.
13. Giải thích vì sao chia 8 trạng thái đều cho 6 giá trị bằng modulo bị lệch.
14. Trình bày rejection sampling để loại modulo bias.
15. Viết `shuffle(int[],RandomGenerator)` với O(1) bộ nhớ phụ.
16. Viết `shuffledCopy` không sửa input.
17. Viết scripted picker nhận dãy j và từ chối chỉ số sai.
18. Thử mảng rỗng, một phần tử và mảng hai phần tử.
19. Kiểm multiset sau shuffle của mảng chứa số âm và số trùng.
20. Enumerate toàn bộ đường đi n=5; xác nhận 120 hoán vị.
21. Enumerate toàn bộ đường đi n=6; xác nhận 720 hoán vị.
22. Viết kiểm thử để bảo đảm hậu tố đã chọn không bị đụng lại.
23. Tạo hai RNG `new Random(2026L)` và kiểm kết quả lặp.
24. Giải thích vì sao kết quả cùng seed không chứng minh RNG an toàn.
25. Thay `Random` bằng `SecureRandom`, giải thích mục tiêu thay đổi.
26. Với [A,A,B], tính xác suất của mỗi dãy giá trị phân biệt.
27. Mở rộng chứng minh khi có c₁,c₂,… nhóm phần tử trùng nhau.
28. Cài biến thể Fisher–Yates duyệt xuôi j∈[i,n−1].
29. Cài Sattolo và so tập kết quả với Fisher–Yates khi n=4.
30. Phân biệt Sattolo với lấy mẫu đồng đều trên mọi derangement.
31. Dùng seed cố định để tạo test tái lập và lưu chuỗi j khi test lỗi.
32. Chạy test thống kê n=3 với số lượng mẫu lớn; không assert tần suất bằng nhau tuyệt đối.
33. So thời gian O(n) của Fisher–Yates với sort theo khóa ngẫu nhiên O(n log n).
34. Phân tích tại sao LinkedList truy cập theo index có thể làm cài đặt shuffle thành O(n²).
35. Cài shuffle trên mảng đối tượng `T[]` và giữ tham chiếu gốc.
36. Thực hiện partial shuffle chọn k=3 trong n=10, kiểm không có phần tử lặp theo vị trí.
37. Chứng minh chọn k vị trí cuối bằng Fisher–Yates một phần cho tổ hợp k phần tử đều.
38. So partial shuffle với reservoir sampling khi dữ liệu là stream.
39. Nêu lý do hai lần shuffle độc lập có thể cho cùng hoán vị.
40. Phân biệt kiểm permutation correctness với distribution correctness.

## 20. Checklist và tổng kết

Trước khi dùng Fisher–Yates, hãy kiểm:

- Bài cần **hoán vị đồng đều** hay có ràng buộc đặc biệt (không giữ nguyên, không điểm cố định...)?
- Các phần tử phân biệt theo **vị trí/ID** hay chỉ theo giá trị hiển thị?
- Vòng ngược chạy i từ n−1 xuống 1?
- Ở lượt i, j có nằm đều trong **[0,i] bao gồm i**?
- API bounded dùng `nextInt(i+1)` chứ không phải `nextInt(i)`?
- Có tránh modulo bias và việc tạo RNG mới sai cách?
- Phần hậu tố đã hoàn thành có được giữ nguyên sau lượt i?
- Với n=0,1 có tránh gọi bounded random với bound 0?
- Có biết hàm sửa tại chỗ hay trả bản sao?
- RNG phù hợp yêu cầu: seeded reproducibility, mô phỏng hay bảo mật?
- Có kiểm mảng trùng giá trị, bảo toàn multiset và kiểm mọi đường đi nhỏ?
- Có phân biệt chứng minh đồng đều với test thống kê hữu hạn?
- Nếu dùng danh sách, truy cập chỉ số có O(1) không?
- Nếu cần chọn k thay vì xáo toàn n, partial shuffle/reservoir có phù hợp hơn không?
- Có tránh nhầm Fisher–Yates với Sattolo hay random comparator sort?

**Kết luận:** Fisher–Yates đặt từng phần tử ngẫu nhiên vào vị trí cuối của phần chưa cố định bằng một lần chọn **j đồng đều trong [0,i]** và một phép swap. Vùng đã cố định không bị sửa nữa. Các lượt có lần lượt n,n−1,…,2 lựa chọn, nên một hoán vị cụ thể có xác suất:

~~~text
1/n * 1/(n-1) * ... * 1/2 = 1/n!
~~~

Với mảng truy cập O(1), thuật toán chạy **O(n) thời gian** và **O(1) bộ nhớ phụ** khi sửa tại chỗ. Tính đồng đều phụ thuộc vào **cách chọn chỉ số** và **nguồn RNG**, không chỉ vào việc kết quả nhìn ngẫu nhiên. Trong Java 17, `rng.nextInt(i+1)` thể hiện đúng miền chọn; `Random` với seed hỗ trợ test tái lập, `SecureRandom` phù hợp hơn khi yêu cầu chống dự đoán. Tách biệt **tính đúng của hoán vị**, **tính đồng đều về xác suất** và **tính bảo mật của nguồn ngẫu nhiên** là chìa khóa áp dụng Fisher–Yates chính xác.
