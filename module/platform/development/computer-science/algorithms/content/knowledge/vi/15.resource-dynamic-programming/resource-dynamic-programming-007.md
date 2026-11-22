# Phân hoạch tập theo tổng hoặc độ chênh lệch

## 1. Bài toán phân hoạch tập là gì?

Cho n phần tử **được phân biệt theo chỉ số** và mỗi phần tử i có giá trị nguyên không âm a[i]. Ta muốn chia các phần tử thành **hai nhóm A, B không giao nhau, hợp đúng bằng toàn bộ tập chỉ số ban đầu**: mỗi phần tử xuất hiện trong đúng một nhóm, kể cả khi giá trị của nhiều phần tử bằng nhau.

Đặt:

~~~text
S    = a[0] + a[1] + ... + a[n-1]
sumA = tong gia tri cac phan tu trong nhom A
sumB = tong gia tri cac phan tu trong nhom B

sumA + sumB = S
difference  = |sumA - sumB|
~~~

Những dạng câu hỏi thường gặp trong **quy hoạch động tài nguyên** gồm:

1. **Chia đều (equal partition):** có thể phân thành hai nhóm có tổng bằng nhau không?
2. **Phân hoạch tối ưu:** chia thế nào để độ chênh lệch |sumA-sumB| là nhỏ nhất?
3. **Độ chênh lệch cho trước:** có bao nhiêu cách phân hoạch đạt độ chênh lệch chính xác D?
4. **Khôi phục nghiệm:** cần đưa ra **các chỉ số phần tử thuộc hai nhóm**, không chỉ giá trị tối ưu.
5. **Đếm nghiệm:** phân biệt hai nhóm có nhãn A/B với hai nhóm **không có nhãn**, hoặc đếm theo bộ chỉ số thay vì theo những tổng trùng nhau.

Ví dụ a=[1,6,11,5], S=23:

- Nhóm A={11} có tổng 11, B={1,6,5} có tổng 12.
- Độ chênh lệch = |11-12|=1, là nhỏ nhất có thể vì tổng S lẻ.
- Cũng có thể chọn A={6,5} và B={1,11}; hai cách chọn nhóm nhẹ hơn là **hai bộ chỉ số khác nhau** nhưng cùng tổng 11.

Nếu chỉ hỏi “tập con có tổng bằng t tồn tại không?”, đó là **subset sum (tổng tập con)**. Bài toán phân hoạch có quan hệ trực tiếp với subset sum vì chọn một nhóm tự xác định nhóm còn lại bằng **phần bù**.

**Giới hạn của bài học:** các công thức DP theo mảng 0..S trước hết giả định mọi a[i] ≥ 0. Với phần tử âm, tổng tập con có thể âm và cần biểu diễn trạng thái khác (xem phần cuối). Trọng số/tổng cũng phải được lưu bằng kiểu số đủ rộng.

## 2. Biến đổi đại số: từ hai nhóm sang một tổng đích

Nếu nhóm A có tổng s, nhóm B là phần bù nên sumB=S-s. Do vậy:

~~~text
difference = |s - (S-s)| = |S - 2s|
~~~

Bài toán hai nhóm trở thành việc chọn **một tập con** với tổng s sao cho |S-2s| đạt yêu cầu. Đây là phép biến đổi quan trọng nhất.

### Chia đều tổng

Nếu sumA=sumB thì cả hai phải bằng S/2:

~~~text
sumA = sumB
    <=> S la so chan va ton tai tap con co tong S/2
~~~

Vì vậy:

- Nếu S **lẻ**, trả false ngay; không cần chạy DP.
- Nếu S **chẵn**, dùng subset sum target=S/2 để kiểm tra tồn tại.
- Nếu tìm được một tập con tổng S/2, phần bù tự động cũng tổng S/2.

Ví dụ a=[1,5,11,5] có S=22. Tập con {11} có tổng 11, phần bù {1,5,5} cũng 11, nên **chia đều được**. Với [1,2,3,5], S=11 lẻ, **không thể** chia đều.

**Chẵn là điều kiện cần, chưa đủ.** Dãy [2,2,2] có tổng 6 chẵn nhưng không có tập con tổng 3, nên không chia đều. Không nên thấy S chẵn rồi khẳng định luôn có lời giải.

### Độ chênh lệch nhỏ nhất

Trong hai nhóm, có thể gọi nhóm nhẹ hơn là A, do đó s=sumA≤S/2. Khi ấy:

~~~text
difference = S - 2s        (voi s <= floor(S/2))
~~~

Muốn giảm difference, ta cần tìm **tổng s lớn nhất có thể đạt** mà s≤floor(S/2). Như vậy:

1. Đặt capacity=floor(S/2).
2. Tìm tất cả tổng s khả thi từ 0 đến capacity.
3. Lấy best=max{s khả thi | s≤capacity}.
4. Đáp án minDifference=S-2×best.

Với S lẻ, difference nhỏ nhất về mặt số học ít nhất bằng 1; với S chẵn, độ chênh lệch có thể bằng 0 nếu và chỉ nếu target S/2 khả thi. Tuy nhiên, ràng buộc giá trị phần tử có thể khiến đáp án lớn hơn mức sàn do tính chẵn lẻ.

### Độ chênh lệch chính xác D

Nếu yêu cầu |sumA-sumB|=D với D≥0 và sumA+sumB=S, tổng nhóm nhẹ hơn là:

~~~text
smallerSum = (S-D) / 2
largerSum  = (S+D) / 2
~~~

Điều kiện cần:

- 0≤D≤S (khi mọi giá trị a[i]≥0).
- S-D là số chẵn, tức S và D có cùng tính chẵn lẻ.
- Tồn tại tập con có tổng (S-D)/2.

Nếu vi phạm điều kiện đầu hoặc chẵn lẻ, số cách bằng 0. Nếu điều kiện số học đúng, ta vẫn cần DP để biết có thể tạo tổng ấy từ các phần tử cụ thể hay không.

## 3. DP kiểm tra tổng tập con: khả thi hay không?

Định nghĩa:

~~~text
can[i][s] = true neu co the chon mot so phan tu
            trong i phan tu dau de co tong dung bang s
~~~

Các a[i] không âm nên s chỉ cần nằm từ 0 tới target (hoặc capacity). Với target là số nguyên nhỏ vừa đủ để cấp phát, đây là bảng Boolean kích thước (n+1)×(target+1).

**Trường hợp cơ sở:**

~~~text
can[0][0] = true
can[0][s>0] = false
can[i][0] = true  (vi duoc phep khong lay phan tu nao)
~~~

Đối với phần tử mới x=a[i-1], một tập con đạt tổng s hoặc **bỏ x**, hoặc **lấy x**:

~~~text
can[i][s] =
    can[i-1][s]
    OR (s>=x AND can[i-1][s-x])
~~~

Hai nhánh đều đọc từ hàng i-1: mỗi phần tử chỉ được quyết định **một lần**, phù hợp với phân hoạch **0/1**. Không được dùng can[i][s-x] cho nhánh lấy nếu làm như vậy cho phép dùng phần tử x nhiều lần.

Ví dụ a=[1,5,11,5], target=11:

- Sau 1, có các tổng 0 và 1.
- Sau 5 thứ nhất, có 0,1,5,6.
- Sau 11, tổng 11 xuất hiện, nên can[3][11]=true.
- Phần tử 5 còn lại không làm mất các tổng đã đạt; can[4][11]=true và bài chia đều có đáp án true.

**Độ phức tạp:** O(n×target) trạng thái/cập nhật, bộ nhớ O(n×target) nếu lưu đủ bảng. Nếu chỉ cần một đáp án Boolean và không truy vết, có thể nén xuống một chiều O(target).

### Vì sao không cần xét các tổng lớn hơn S/2?

Trong bài phân hoạch, nếu một tập con có tổng s>S/2 thì **phần bù** có tổng S-s<S/2, và hai nhóm có cùng độ chênh lệch. Do đó để tìm độ chênh lệch nhỏ nhất chỉ cần xét một phía của tổng, tức s≤floor(S/2).

Đối với mục tiêu **đếm phân hoạch** theo D, một tổng nhỏ hơn (S-D)/2 hoặc lớn hơn (S+D)/2 không thể cho đúng chênh lệch; chỉ cần đếm các tập con đạt tổng đích tương ứng, không cần lập bảng toàn dải nếu truy vấn đã biết D.

## 4. Nén DP 2D còn 1D và hướng vòng lặp

Vì can[i][s] chỉ phụ thuộc can[i-1][s] và can[i-1][s-x], có thể dùng một mảng Boolean reachable[s]:

~~~text
reachable[0] = true
reachable[1..target] = false

for each x in a:
    for s from target down to x:
        reachable[s] = reachable[s] OR reachable[s-x]
~~~

Vòng **s giảm dần** là phần quyết định tính đúng. Khi đang xử lý x, reachable[s-x] phải phản ánh kết quả **trước khi lấy x**, tránh dùng chính x nhiều lần trong một bước.

### Phản ví dụ nếu duyệt tăng dần

Giả sử chỉ có một phần tử x=3 và target=6. Ban đầu reachable[0]=true, các ô khác false.

- Duyệt **tăng** s=3: reachable[3] trở thành true nhờ reachable[0].
- Sau đó s=6: reachable[6] lại thấy reachable[3] vừa được cập nhật bởi **chính x=3**, nên thành true.
- Chương trình sai tuyên bố dùng một phần tử 3 để tạo tổng 6.

Duyệt **giảm** thì khi xét s=6, reachable[3] còn false của lớp cũ; kết quả đúng là không thể tạo tổng 6.

**Quy tắc ghi nhớ:** bài **0/1** dùng vòng sức chứa đi **giảm** khi cập nhật in-place; một phiên bản **unbounded** cho phép dùng phần tử nhiều lần có thể dùng chiều tăng, nhưng đó là bài toán khác.

Với phần tử x=0, nhánh lấy không tạo ra tổng mới: reachable[s] OR reachable[s] vẫn là chính reachable[s]. Vì vậy các số 0 **không ảnh hưởng tính khả thi**, nhưng **có ảnh hưởng lớn đến số cách** (xem phần đếm). Nếu chỉ dùng Boolean, không cần xử lý đặc biệt ngoài việc đảm bảo vòng lặp không bị lỗi.

### Bất biến của 1D

Sau khi xử lý đúng i phần tử đầu tiên, reachable[s] đúng khi và chỉ khi tồn tại một tập con của các phần tử đó có tổng s. Ban đầu chỉ tổng 0 khả thi. Khi thêm x, nhánh bỏ giữ lại mọi tổng cũ; nhánh lấy tạo s từ tổng s-x cũ. Vòng giảm giữ nguyên nguồn dữ liệu logic của bước trước, nên bất biến được bảo toàn.

Nếu chỉ hỏi **có thể chia đều không**, kiểm tra S chẵn trước, rồi chạy reachable tới target=S/2 và trả reachable[target].

## 5. Tìm độ chênh lệch nhỏ nhất và khôi phục hai nhóm

Đối với tối ưu hóa, Boolean DP cho ta biết các tổng **có thể đạt**. Sau khi tính reachable[0..floor(S/2)], duyệt s từ floor(S/2) xuống 0, tìm ô true đầu tiên. Khi đó s là tổng nhỏ nhất-chênh-lệch lớn nhất gần nửa tổng.

Ví dụ:

~~~text
a = [1, 6, 11, 5]
S = 23
capacity = floor(23/2) = 11

Tong 11 dat duoc:
    {11} hoac {6,5}

best = 11
minimum difference = 23 - 2*11 = 1
~~~

Để xuất **chính các phần tử đã chọn**, có thể lưu toàn bộ bảng can[i][s] rồi truy vết từ (i=n,s=best):

1. Nếu can[i-1][s] vẫn true, **bỏ** phần tử i-1 và về (i-1,s). Quy tắc này chọn bỏ khi nhiều cách cùng đạt s.
2. Nếu can[i-1][s] false thì phần tử i-1 **phải được lấy** trong đường đi đã chọn. Kiểm tra x≤s và can[i-1][s-x] true, ghi chỉ số i-1, về (i-1,s-x).
3. Lặp đến i=0. Khi đó s phải bằng 0; đảo danh sách chỉ số nếu truy vết đã ghi từ cuối về đầu.
4. Các chỉ số không được chọn thuộc nhóm còn lại. Tính lại tổng mỗi nhóm và đối chiếu difference.

Với dữ liệu [1,6,11,5] và chính sách **ưu tiên bỏ phần tử chỉ số cao khi có thể**, truy vết sẽ chọn **chỉ số [2]** (giá trị 11) vào nhóm nhẹ hơn, còn **[0,1,3]** (giá trị 1,6,5) vào nhóm kia. Hai tổng là 11 và 12.

**Tại sao không truy vết chỉ từ một mảng Boolean 1D cuối cùng?** Sau khi nén, ta đã mất lịch sử can[i][s] ứng với từng tập tiền tố. Một con trỏ cha không gắn với phiên bản có thể bị ghi đè bởi các lượt sau, dẫn tới dùng một phần tử nhiều lần hoặc chọn đường đi không còn khớp tổng. Muốn khôi phục, giữ bảng 2D, lưu quyết định/parent theo từng lớp, dùng checkpoint tính lại, hoặc chọn kỹ thuật khôi phục đặc thù đã được chứng minh.

Trong một số bài chỉ yêu cầu độ chênh lệch, bản 1D đủ. Khi đề yêu cầu **hai nhóm cụ thể**, nên dự tính chiến lược truy vết trước khi tối ưu bộ nhớ.

## 6. Đếm số phân hoạch có độ chênh lệch D

Khi đếm, Boolean reachable chỉ cho biết **có hay không**; nó không cho biết có bao nhiêu tập con tạo được tổng t. Ta cần DP theo số cách:

~~~text
ways[s] = so bo chi so chon tu cac phan tu da xu ly
          sao cho tong gia tri dung bang s

ways[0] = 1
ways[s>0] = 0
~~~

Khi thêm một phần tử x≥0:

~~~text
for s from target down to x:
    ways[s] = ways[s] + ways[s-x]
~~~

Lại phải duyệt s **giảm dần**: mỗi phần tử chỉ dùng tối đa một lần. Hai nhóm cách **bỏ x** và **lấy x** không trùng nhau vì chúng khác nhau ở việc có chứa **chỉ số của x** hay không.

Với tổng S và chênh lệch D≥0:

~~~text
if D > S or (S-D) is odd:
    answer = 0
else:
    target = (S-D)/2
    countSubsetWays(target)
~~~

Nhưng còn một bước quan trọng: **hai nhóm được coi là có nhãn hay không?**

### Đếm phân hoạch không gắn nhãn hai nhóm

Ở cách hiểu phổ biến “chia tập thành hai nhóm” **không phân biệt tên** A/B, cặp nhóm {X,Y} bằng {Y,X}. Với D>0, một nhóm có tổng nhỏ hơn nhóm kia, nên **mỗi phân hoạch có đúng một nhóm nhẹ hơn**. Vì thế số tập con có tổng target=(S-D)/2 bằng chính số phân hoạch **không gắn nhãn** có chênh lệch D.

Với D=0, mỗi tập con tổng S/2 có một tập con phần bù **cũng tổng S/2**. Nếu n>0, hai tập chỉ số ấy khác nhau và cùng biểu diễn **một phân hoạch không gắn nhãn**. Vì vậy:

~~~text
D > 0:
    unorderedPartitions = ways[(S-D)/2]

D = 0, n > 0:
    unorderedPartitions = ways[S/2] / 2

D = 0, n = 0:
    unorderedPartitions = 1
~~~

Ở trường hợp n=0, tập rỗng có phần bù là chính nó, nên chỉ có một phân hoạch (rỗng, rỗng); **không chia đôi 1**. Số ways[S/2] là số chẵn khi n>0 và D=0, vì phép lấy phần bù ghép các tập con thành các cặp khác nhau.

Nếu đề bài định nghĩa **nhóm A và nhóm B có nhãn** (đổi chỗ được tính là cách mới), số cách cần tính theo tiêu chí đó. Với D=0 và n>0, không chia hai; với D>0, mỗi phân hoạch không nhãn thường tương ứng **hai** cách gắn nhãn. Đừng áp dụng công thức chia đôi nếu đề hỏi các cách **gán phần tử vào nhóm A/B** có nhãn.

### Các phần tử cùng giá trị vẫn là đối tượng khác nhau

Ví dụ a=[1,1,2,2], tổng S=6. Để có độ chênh lệch D=0, một nhóm phải có tổng 3, tức chọn **một trong hai chỉ số mang giá trị 1** và **một trong hai chỉ số mang giá trị 2**: có 2×2=4 tập con được chọn theo chỉ số.

- Số tập con tổng 3 = **4**.
- Số phân hoạch hai nhóm **không gắn nhãn** bằng 4/2=**2**.

Với D=2, nhóm nhẹ hơn phải có tổng (6-2)/2=2. Có ba cách chọn theo chỉ số: lấy một trong hai phần tử giá trị 2 (hai cách), hoặc lấy cả hai phần tử giá trị 1 (một cách). Vậy có **3 phân hoạch không nhãn** với chênh lệch 2.

### Phần tử giá trị 0 và số cách

Khi xét một phần tử x=0, công thức là:

~~~text
ways[s] = ways[s] + ways[s] = 2 * ways[s]
~~~

Điều này **không phải lỗi đếm trùng** nếu phần tử được phân biệt theo chỉ số: ta có thể cho phần tử 0 vào nhóm A hoặc nhóm B mà không đổi tổng, nhưng được một phân hoạch chỉ số khác.

Ví dụ a=[0,0], S=0, D=0:

- Có 2²=4 tập con tổng 0, vì hai phần tử 0 được chọn hay bỏ độc lập.
- Nếu hai nhóm **không gắn nhãn** và n>0, số phân hoạch là 4/2=**2**.
- Nếu n=0 và D=0, chỉ có **1** cách, không áp dụng chia đôi.

Đối với đề bài coi các phần tử trùng giá trị là **không phân biệt**, kết quả đếm hoàn toàn có thể khác. Phải xác định “một cách” theo **bộ chỉ số** hay theo **đa tập giá trị** trước khi dùng DP đếm.

## 7. Số cách có thể rất lớn: BigInteger và modulo

DP Boolean chỉ lưu true/false, nhưng DP đếm có thể đạt tới 2^n cách chọn tập con. Với n phần tử 0 và target=0, số cách là 2^n. Chỉ khoảng n=63 đã có thể vượt phạm vi long có dấu (2^63 > Long.MAX_VALUE).

Nếu bài yêu cầu **số cách chính xác**, hãy dùng BigInteger hoặc kiểu số lớn tương đương:

~~~text
ways[0] = 1
ways[s>0] = 0

for each x:
    for s from target down to x:
        ways[s] = ways[s] + ways[s-x]
~~~

Trong Java, các ô là đối tượng **BigInteger**; cần khởi tạo bằng BigInteger.ZERO, không thể mặc định tất cả ô là số 0 như mảng primitive. Công thức cộng và dịch bit cho số cách chẵn có thể dùng BigInteger.add và shiftRight(1).

Nếu đề yêu cầu lấy modulo M>0, ta có thể cập nhật:

~~~text
ways[s] = (ways[s] + ways[s-x]) mod M
~~~

**Cảnh báo khi đếm phân hoạch không nhãn có D=0:** nếu chỉ giữ số cách **mod M**, không được **tùy tiện chia phần dư cho 2**. Khi M chẵn, phép chia modulo 2 có thể không có nghịch đảo; ngay cả khi M lẻ, phải dùng nghịch đảo nhân đúng chứ không dùng phép chia nguyên trên phần dư. Cách rõ nhất trong bài học này là **tính số cách chính xác bằng BigInteger, chia nguyên cho 2 rồi mới lấy mod nếu cần**. Với giới hạn lớn, có thể dùng phương pháp đếm quy ước riêng hoặc kỹ thuật modulo đã chứng minh để tránh số lớn.

### Chi phí tính toán với số lớn

Phát biểu O(n×target) thời gian thường coi phép cộng là O(1). Với BigInteger, thời gian một phép cộng phụ thuộc số bit của hai toán hạng; bộ nhớ cũng phụ thuộc độ dài số, không chỉ số ô DP. Tuy nhiên, dùng BigInteger giúp trả đáp án **chính xác** mà không tràn âm như int hoặc long.

Khi bài yêu cầu chỉ tồn tại, hãy dùng boolean[] thay vì BigInteger[]: kiểu dữ liệu của trạng thái phải phù hợp với mục tiêu.

## 8. Java 17 – Một chương trình đầy đủ cho ba dạng bài

Chương trình minh họa:

1. **canPartitionEqual:** kiểm tra chia đều với DP Boolean 1D theo sức chứa, duyệt giảm.
2. **minimumDifferencePartition:** tìm chênh lệch tối thiểu và **truy vết hai nhóm** từ bảng 2D.
3. **countUnorderedPartitionsByDifference:** đếm chính xác các phân hoạch **không gắn nhãn**, phân biệt từng phần tử theo chỉ số, bằng BigInteger.

Để ví dụ an toàn khi chạy trên máy học tập, mã giới hạn target≤200.000 cho các mảng DP, và giới hạn tổng số ô của bảng truy vết 2D≤2.000.000. Đây là **giới hạn cấp phát của demo**, không phải giới hạn toán học của bài toán. Với đầu vào vượt ngưỡng, hàm báo lỗi thay vì cố cấp phát một mảng khổng lồ.

Lưu vào tệp **PartitionBySumDemo.java**:

~~~java
import java.math.BigInteger;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;
import java.util.Objects;

public class PartitionBySumDemo {
    private static final int MAX_TARGET = 200_000;
    private static final long MAX_2D_STATES = 2_000_000L;

    record Partition(long difference,
                     long smallerSum,
                     long largerSum,
                     List<Integer> smallerIndices,
                     List<Integer> largerIndices) {}

    private static long validatedTotal(int[] a) {
        Objects.requireNonNull(a, "a");
        long total = 0L;
        for (int x : a) {
            if (x < 0) {
                throw new IllegalArgumentException(
                        "all values must be nonnegative");
            }
            total += x;
        }
        return total;
    }

    private static int checkedTarget(long target) {
        if (target < 0 || target > MAX_TARGET) {
            throw new IllegalArgumentException(
                    "target too large for demo DP");
        }
        return (int) target;
    }

    // Chi can ket qua true/false: bo nho O(S/2).
    static boolean canPartitionEqual(int[] a) {
        long total = validatedTotal(a);
        if ((total & 1L) != 0L) {
            return false;
        }

        int target = checkedTarget(total / 2L);
        boolean[] reachable = new boolean[target + 1];
        reachable[0] = true;

        for (int x : a) {
            for (int s = target; s >= x; s--) {
                reachable[s] |= reachable[s - x];
            }
        }
        return reachable[target];
    }

    // Tra hai tap chi so va chenh lech nho nhat.
    static Partition minimumDifferencePartition(int[] a) {
        long total = validatedTotal(a);
        int capacity = checkedTarget(total / 2L);
        int n = a.length;

        long states = ((long) n + 1L) * (capacity + 1L);
        if (states > MAX_2D_STATES) {
            throw new IllegalArgumentException(
                    "2D DP too large for demo");
        }

        boolean[][] can = new boolean[n + 1][capacity + 1];
        can[0][0] = true;

        for (int i = 1; i <= n; i++) {
            int x = a[i - 1];
            for (int s = 0; s <= capacity; s++) {
                boolean skip = can[i - 1][s];
                boolean take = x <= s && can[i - 1][s - x];
                can[i][s] = skip || take;
            }
        }

        int best = capacity;
        while (!can[n][best]) {
            best--;
        }

        // Khi hoa, uu tien bo phan tu chi so cao.
        List<Integer> selected = new ArrayList<>();
        int remaining = best;

        for (int i = n; i >= 1; i--) {
            if (can[i - 1][remaining]) {
                continue;
            }

            int x = a[i - 1];
            if (x > remaining || !can[i - 1][remaining - x]) {
                throw new IllegalStateException("broken traceback");
            }

            selected.add(i - 1);
            remaining -= x;
        }
        if (remaining != 0) {
            throw new IllegalStateException("trace did not reach zero");
        }
        Collections.reverse(selected);

        boolean[] chosen = new boolean[n];
        for (int idx : selected) {
            chosen[idx] = true;
        }
        List<Integer> other = new ArrayList<>();
        for (int i = 0; i < n; i++) {
            if (!chosen[i]) {
                other.add(i);
            }
        }

        return new Partition(
                total - 2L * best,
                best,
                total - best,
                List.copyOf(selected),
                List.copyOf(other));
    }

    // Hai nhom KHONG GAN NHAN; moi phan tu phan biet bang index.
    static BigInteger countUnorderedPartitionsByDifference(
            int[] a, long difference) {
        long total = validatedTotal(a);
        if (difference < 0) {
            throw new IllegalArgumentException(
                    "difference must be nonnegative");
        }
        if (difference > total || ((total - difference) & 1L) != 0L) {
            return BigInteger.ZERO;
        }

        int target = checkedTarget((total - difference) / 2L);
        BigInteger[] ways = new BigInteger[target + 1];
        Arrays.fill(ways, BigInteger.ZERO);
        ways[0] = BigInteger.ONE;

        for (int x : a) {
            for (int s = target; s >= x; s--) {
                ways[s] = ways[s].add(ways[s - x]);
            }
        }

        BigInteger count = ways[target];
        if (difference == 0 && a.length > 0) {
            // Hai tap con bu tru nhau la mot phan hoach khong nhan.
            if (count.testBit(0)) {
                throw new IllegalStateException("odd complement count");
            }
            return count.shiftRight(1);
        }
        return count;
    }

    public static void main(String[] args) {
        int[] values = {1, 6, 11, 5};
        Partition p = minimumDifferencePartition(values);
        System.out.println("minimum difference = " + p.difference());
        System.out.println("smaller indices = " + p.smallerIndices());
        System.out.println("larger indices = " + p.largerIndices());
        System.out.println("sums = " + p.smallerSum() +
                " and " + p.largerSum());

        System.out.println("equal [1,5,11,5] = " +
                canPartitionEqual(new int[]{1, 5, 11, 5}));
        System.out.println("equal [1,2,3,5] = " +
                canPartitionEqual(new int[]{1, 2, 3, 5}));
        System.out.println("equal [] = " +
                canPartitionEqual(new int[0]));

        int[] duplicates = {1, 1, 2, 2};
        System.out.println("count D=0 = " +
                countUnorderedPartitionsByDifference(duplicates, 0));
        System.out.println("count D=2 = " +
                countUnorderedPartitionsByDifference(duplicates, 2));
        System.out.println("count zeros D=0 = " +
                countUnorderedPartitionsByDifference(
                        new int[]{0, 0}, 0));
        System.out.println("count empty D=0 = " +
                countUnorderedPartitionsByDifference(new int[0], 0));

        try {
            canPartitionEqual(new int[]{-1, 1});
        } catch (IllegalArgumentException ex) {
            System.out.println("negative rejected: " + ex.getMessage());
        }
    }
}
~~~

Biên dịch và chạy bằng **JDK 17 trở lên**:

~~~bash
javac PartitionBySumDemo.java
java PartitionBySumDemo
~~~

**Stdout chính xác:**

~~~text
minimum difference = 1
smaller indices = [2]
larger indices = [0, 1, 3]
sums = 11 and 12
equal [1,5,11,5] = true
equal [1,2,3,5] = false
equal [] = true
count D=0 = 2
count D=2 = 3
count zeros D=0 = 2
count empty D=0 = 1
negative rejected: all values must be nonnegative
~~~

### Diễn giải các hàm

**validatedTotal** yêu cầu mảng không null, mọi giá trị nguyên không âm; dùng long để tích lũy tổng. Vì mỗi a[i] là int không âm và số phần tử của mảng Java không vượt miền chỉ số int, tổng các a[i] không vượt giới hạn long. Tuy nhiên, tổng hoàn toàn có thể vượt Integer.MAX_VALUE, nên không dùng int để cộng tổng trước khi chuyển sang long.

**canPartitionEqual** kiểm tra chẵn lẻ trước, sau đó dùng boolean[] để tìm target=S/2. Hướng cập nhật giảm bảo đảm mỗi phần tử dùng tối đa một lần. Với a=[] hoặc toàn số 0, tổng bằng 0 và tập con rỗng tạo tổng 0, nên true.

**minimumDifferencePartition** chỉ tìm tổng đến floor(S/2), xây bảng 2D để giữ lịch sử theo từng phần tử, tìm tổng best khả thi lớn nhất, rồi truy vết từ hàng n về 0. Khi có cả nhánh lấy và bỏ, chương trình ưu tiên bỏ, nên với ví dụ [1,6,11,5] kết quả ổn định là chỉ số [2] vào nhóm nhẹ hơn. Hàm trả cả hai danh sách chỉ số và hai tổng, đủ để tự kiểm chứng.

**countUnorderedPartitionsByDifference** chuyển D thành target=(S-D)/2 nếu hợp lệ. BigInteger[] lưu số **tập con chỉ số** đạt mỗi tổng. Với D=0 và n>0, mỗi phân hoạch không nhãn có hai lựa chọn nhóm A/B bổ sung cho nhau, nên chia đúng cho 2; với a=[] giữ một phân hoạch rỗng. Không chia hai khi D>0 vì nhóm nhẹ hơn được xác định duy nhất bằng tổng.

### Độ phức tạp các phương thức

| Hàm | Thời gian DP theo số trạng thái | Bộ nhớ phụ | Đầu ra |
| --- | --- | --- | --- |
| canPartitionEqual | O(n×S/2) | O(S/2) ô Boolean | true/false |
| minimumDifferencePartition | O(n×S/2) | O(n×S/2) ô Boolean + O(n) danh sách | Độ chênh lệch và hai nhóm |
| countUnorderedPartitionsByDifference | O(n×(S-D)/2) | O((S-D)/2) ô BigInteger | Số phân hoạch không nhãn chính xác |

Các biểu thức dùng target thực tế và bỏ qua chi phí BigInteger theo bit. Trong mã có giới hạn MAX_TARGET=200_000 và MAX_2D_STATES=2_000_000 để tránh cấp phát quá sức; nếu vượt, chương trình **ném IllegalArgumentException**, chứ không cố cho ra một kết quả gần đúng.

Lưu ý: nếu tổng S=0 và n nhiều phần tử 0, DP đếm có target=0 nhưng số cách vẫn là 2^n; **chi phí số học BigInteger và bộ nhớ theo bit vẫn tăng**.

## 9. Chứng minh tính đúng: khả thi, tối ưu và đếm cách

### 9.1 Công thức khả thi đúng

Chứng minh bằng quy nạp theo số phần tử đã xử lý. Khi i=0, chỉ có tập con rỗng đạt tổng 0 nên can[0][0]=true, các tổng dương false. Giả sử mọi giá trị của hàng i-1 đúng. Một tập con của i phần tử đạt tổng s hoặc không chứa phần tử cuối, hoặc có chứa nó. Trường hợp bỏ tương đương can[i-1][s]; trường hợp lấy tương đương can[i-1][s-x] khi s≥x. Hai trường hợp bao phủ mọi tập con và không tạo trạng thái sai. Vậy công thức OR đúng.

Bản 1D duyệt s giảm, nên mọi giá trị can[s-x] đọc được vẫn thuộc lớp i-1; vì thế tương đương với cập nhật 2D và đúng cho đến hết n phần tử.

### 9.2 Tìm best tối ưu cho độ chênh lệch

Với bất kỳ phân hoạch, có thể hoán đổi tên nhóm để chọn nhóm có tổng s≤S/2. Độ chênh lệch là S-2s, giảm khi s tăng. DP đã xét đầy đủ mọi tổng khả thi trong [0,floor(S/2)], nên tổng khả thi lớn nhất best cho chênh lệch nhỏ nhất. Phần bù của tập con best luôn tạo nhóm còn lại và không dùng trùng phần tử.

Truy vết 2D đúng vì tại (i,s) đang khả thi, hoặc trạng thái bỏ (i-1,s) khả thi hoặc trạng thái lấy (i-1,s-x) khả thi. Chọn một nhánh đúng giữ tổng mục tiêu có thể đạt và giảm i mỗi bước, nên cuối cùng đến (0,0) và tạo bộ chỉ số hợp lệ đạt best. Độ chênh lệch của hai nhóm đúng S-2best.

### 9.3 Đếm chính xác và phép chia đôi

Tương tự trường hợp khả thi, mỗi tập con đạt tổng s được phân loại **rời nhau** theo việc có chứa phần tử cuối hay không; công thức cộng số cách không bỏ sót và không đếm hai lần cùng một tập chỉ số. DP đếm vì thế cho chính xác số tập con tạo target.

Nếu D>0, ở mỗi phân hoạch không nhãn nhóm có tổng (S-D)/2 là nhóm **duy nhất nhẹ hơn**, nên số tập con target bằng số phân hoạch. Nếu D=0 và n>0, phép lấy phần bù là một phép song ánh không có điểm cố định trên các tập con chỉ số: không tập con nào bằng chính phần bù của nó khi có ít nhất một phần tử. Do đó các tập con target chia thành các **cặp bổ sung**, mỗi cặp tương ứng một phân hoạch không nhãn, và số cách phải chia 2. Trường hợp n=0 là ngoại lệ duy nhất vì tập rỗng bằng phần bù của chính nó.

## 10. Độ phức tạp giả đa thức và chọn thuật toán

Bài toán subset sum/partition 0/1 tổng quát không có lời giải thời gian đa thức theo **số bit đầu vào** đã biết; phiên bản quyết định PARTITION là một bài toán NP-complete **yếu** (weakly NP-complete). Nhưng khi tổng S không quá lớn, DP theo tổng chạy O(nS), thường rất hiệu quả.

**Giả đa thức (pseudo-polynomial):** thời gian O(nS) được xem là đa thức theo **giá trị số S**, không nhất thiết theo độ dài bit để ghi S. Ví dụ W=10^9 chỉ cần khoảng 30 bit để lưu nhưng mảng DP cần tới một tỉ ô nếu dùng chỉ số trực tiếp. Vì vậy “DP O(nS)” không đồng nghĩa có thể giải mọi đầu vào lớn.

Cách lựa chọn thực tế:

| Tình huống | Phương án đáng cân nhắc | Giới hạn |
| --- | --- | --- |
| n vừa, tổng S nhỏ | Boolean DP 1D | O(S) bộ nhớ, O(nS) thời gian |
| Cần xuất hai nhóm | DP 2D hoặc parent theo lớp | O(nS) bộ nhớ có thể quá lớn |
| Chỉ kiểm tra tổng đạt được, cần bit operations | Bitset/bit-parallel subset sum | Vẫn phụ thuộc dải tổng và số bit được lưu |
| n nhỏ–vừa, S rất lớn | Meet-in-the-middle | Khoảng O(n×2^(n/2)) thời gian liệt kê/sắp và O(2^(n/2)) bộ nhớ tùy triển khai |
| Giá trị lớn nhưng số tổng khả thi thực tế ít | Tập HashSet các tổng đạt được | Có thể vẫn bùng nổ số trạng thái |
| Chỉ cần chênh lệch **gần tối ưu** | Heuristic hoặc thuật toán xấp xỉ phù hợp | Không tự khẳng định tối ưu nếu chưa chứng minh |
| Nhiều truy vấn target trên cùng tập phần tử | Tiền xử lý các tổng khả thi một lần | Phải xử lý lại khi dữ liệu thay đổi |

### Bitset thay cho boolean[]

Với giá trị không âm và bitset đủ độ dài, có thể biểu diễn bit s=1 nếu tổng s khả thi. Bắt đầu bit0=1; mỗi phần tử x cập nhật:

~~~text
reachableBits = reachableBits OR (reachableBits << x)
~~~

Bên phải dùng **trạng thái cũ** của bitset (theo ngữ nghĩa một phép dịch và OR), nên một phần tử không được dùng nhiều lần. Trên phần cứng, phép toán bit theo từ máy có thể xử lý nhiều tổng trong một lượt và nhanh hơn vòng Boolean; tuy nhiên bộ nhớ vẫn tăng theo miền tổng và cần cắt/giới hạn các bit trên target nếu không cần.

Một số ngôn ngữ hoặc thư viện có thao tác bitset thuận tiện; trong Java có thể khai thác BigInteger làm tập bit hoặc tự triển khai mảng từ máy, nhưng cần chú ý shiftLeft số bit lớn sẽ cấp phát nhiều bộ nhớ. **BigInteger bitset** để biểu diễn tính khả thi khác hoàn toàn với **BigInteger số cách** trong DP đếm.

### Greedy cân bằng hai nhóm có thể thất bại

Một heuristic phổ biến: sắp phần tử giảm dần rồi lần lượt đưa món tiếp theo vào nhóm đang có tổng nhỏ hơn. Nó nhanh và thường cho kết quả khá tốt, nhưng không bảo đảm tối ưu.

Với a=[8,7,6,5,4], tổng S=30:

- Đưa 8 vào nhóm A, 7 vào nhóm B.
- Đưa 6 vào nhóm nhẹ hơn B ⇒ A=8, B=13.
- Đưa 5 vào A ⇒ A=13, B=13.
- Đưa 4 vào một trong hai nhóm ⇒ tổng thành 17 và 13, chênh lệch **4**.

Trong khi đó, phân hoạch A={8,7}, B={6,5,4} có tổng mỗi bên **15**, chênh lệch tối ưu bằng **0**. Phản ví dụ này cho thấy chọn cục bộ nhóm nhẹ hơn có thể bỏ lỡ kết quả tốt hơn của tổ hợp.

## 11. Số âm, số thực và ràng buộc biến thể

### Nếu phần tử có thể âm

Các công thức đại số sumA+sumB=S và difference=|S-2s| **vẫn đúng** với số âm. Tuy nhiên, nhiều bước suy luận và giới hạn trạng thái phải thay đổi:

- S có thể âm, nên không thể coi mọi tổng tập con nằm trong [0,S].
- “Nhóm nhẹ hơn có tổng trong [0,S/2]” không còn đúng; nhóm nhẹ hơn có thể có tổng âm.
- Miền tổng khả thi có thể từ **L=tổng tất cả số âm** đến **U=tổng tất cả số dương**.
- Có thể dùng DP với **offset -L** trên dải L..U khi dải đủ nhỏ, hoặc HashSet<Long> cho tính khả thi và Map<Long,BigInteger> cho số cách nếu các tổng thưa.
- Khi cập nhật tập tổng trong Map/Set, phải đọc từ **snapshot của lớp trước**; sửa trực tiếp rồi dùng trạng thái mới trong cùng lượt có thể tái sử dụng phần tử.

Ví dụ a=[-3,1,2], S=0 và có một nhóm {-3,1,2} tổng 0 cùng nhóm rỗng tổng 0, cũng như các phân hoạch khác tùy cách chọn. Không thể cấp phát boolean[S+1] rồi mong bao quát những tổng âm trung gian.

Với số âm, công thức đếm theo D còn cho hai giá trị (S±D)/2, nhưng không được giữ điều kiện **D≤S** hoặc giới hạn target không âm như ở mô hình chuẩn. Cách đếm và xác định nhóm nhẹ hơn phải làm việc trên cả miền tổng có dấu.

### Nếu phần tử là số thực

Với số thực, tổng đích có thể không nguyên, nên một mảng boolean đánh chỉ số trực tiếp bằng tổng không áp dụng. Nếu các giá trị là số thập phân có hữu hạn chữ số theo một đơn vị rõ ràng, có thể **quy đổi về số nguyên** (ví dụ tiền thành đồng/xu nguyên) khi quy đổi chính xác và dải tổng phù hợp. Nếu dùng double, lỗi làm tròn có thể khiến hai tổng “bằng nhau” về toán học lại khác nhau ở biểu diễn máy.

Đừng làm tròn tùy tiện rồi tuyên bố lời giải đúng tuyệt đối: việc làm tròn có thể thay đổi bài toán. Nếu yêu cầu tối ưu theo sai số cho phép, phải đặc tả ngưỡng và phương pháp xấp xỉ.

### Nếu phải phân thành nhiều hơn hai nhóm

Với **k nhóm**, một tập con không còn tự xác định duy nhất k-1 nhóm còn lại. Bài toán k-partition / multiway partition có trạng thái và ràng buộc khác. Phương pháp “chọn tổng gần S/2 rồi lấy phần bù” chỉ giải trực tiếp trường hợp **hai nhóm**.

Tương tự, ràng buộc “mỗi nhóm phải có đúng p phần tử”, “một số cặp bắt buộc cùng nhóm”, “mỗi nhóm có giới hạn số món” cần **thêm chiều trạng thái hoặc cách giải khác**, không được xem là tự động xử lý bởi DP tổng một chiều.

## 12. Những lỗi phổ biến và cách phòng tránh

| Lỗi | Hậu quả | Biện pháp |
| --- | --- | --- |
| Xem S chẵn là đủ để chia đều | Trả true cho [2,2,2] dù target 3 không đạt | Luôn kiểm tra subset sum S/2 |
| Dùng int để cộng S rất lớn | Tràn dấu, target sai | Cộng bằng long ngay từ đầu |
| Khởi tạo can[0]=false | Không có trạng thái xuất phát | Đặt true cho tổng 0 |
| Quên xét tập con rỗng | Trả sai khi S=0 hoặc n=0 | Cho phép chọn 0 phần tử |
| Duyệt s tăng cho ba lô 0/1 | Dùng cùng phần tử nhiều lần | Duyệt s giảm |
| Lấy tổng lớn nhất bất kỳ thay vì gần S/2 | Không tối thiểu chênh lệch | Tìm best≤floor(S/2) |
| Trả S-best thay vì S-2best | Chênh lệch sai | Dùng difference=|S-2s| |
| Truy vết từ dp 1D cuối mà không lưu lịch sử | Có thể sinh hai nhóm không hợp lệ | Dùng bảng 2D hoặc parent theo lớp |
| Đếm giá trị trùng như một phần tử | Thiếu số cách phân biệt theo chỉ số | Định nghĩa rõ “một cách” |
| Quên x=0 trong DP đếm | Đếm thiếu theo nhãn vị trí | x=0 làm số cách của mỗi tổng tăng đôi |
| Chia đôi mọi số cách đếm | Sai với D>0 hoặc n=0 | Chỉ chia khi D=0,n>0 và hai nhóm không nhãn |
| Chia 2 trên phần dư modulo tùy tiện | Sai số cách không nhãn | Chia giá trị nguyên chính xác hoặc xử lý modular đúng |
| Dùng long cho số cách quá lớn | Overflow, có thể âm | BigInteger hoặc modulo nếu đề yêu cầu |
| Cấp phát theo tổng S quá lớn | Hết bộ nhớ dù n nhỏ | Kiểm tra hạn mức, dùng phương án khác |
| Giữ DP 0..S cho số âm | Bỏ sót trạng thái tổng âm | Dùng offset/Map và cập nhật theo lớp |
| Không phân biệt hai nhóm gắn nhãn/không nhãn | Hệ số 2 sai | Quy định rõ cách đếm |
| Lấy greedy như lời giải tối ưu | Có phản ví dụ cân bằng sai | Dùng DP/exact method khi cần chứng minh tối ưu |

**Mẹo kiểm tra nhanh:** với a=[], phân hoạch có chênh lệch tối thiểu 0; chia đều khả thi với hai nhóm rỗng; đếm phân hoạch không nhãn ở D=0 bằng 1. Với a=[0,0], các tổng vẫn đều bằng 0 nhưng số phân hoạch không nhãn theo **chỉ số** bằng 2. Nếu chương trình trả cùng số đếm 1 cho cả hai ca, có thể đã bỏ qua ý nghĩa của từng phần tử 0.

## 13. Kiểm thử theo thuộc tính và bộ ca biên

### Bất biến cần kiểm

**Khả thi/Boolean:**

- reachable[0] luôn true.
- Sau i phần tử, reachable[s] chỉ true nếu thực sự có tập con của i phần tử đạt tổng s.
- Kết quả true của equal partition chỉ có thể xảy ra khi S chẵn.
- Tăng thêm phần tử không làm mất những tổng trước đó có thể đạt.

**Tối ưu và truy vết:**

- Hai danh sách chỉ số không giao nhau, hợp đúng {0,...,n-1}.
- Không có chỉ số ngoài [0,n); mỗi chỉ số xuất hiện đúng một lần.
- smallerSum cộng từ các chỉ số nhóm nhẹ, largerSum cộng từ phần bù.
- smallerSum+largerSum=S.
- difference=largerSum-smallerSum=|S-2smallerSum|.
- Không tồn tại phân hoạch khác có chênh lệch nhỏ hơn; với n nhỏ có thể đối chứng bằng brute force.
- Truy vết phải kết thúc ở tổng 0 và i=0.

**Đếm số phân hoạch:**

- Với D<0, API từ chối; với D>S hoặc S-D lẻ, kết quả 0 trong miền a[i]≥0.
- Nếu n=0,D=0 thì kết quả 1.
- Với D=0 và n>0, số tập con tổng S/2 luôn chẵn; số phân hoạch không nhãn bằng một nửa.
- Với D>0, đếm tập con có tổng (S-D)/2 không cần chia đôi.
- Với k phần tử 0, số cách tập con theo chỉ số được nhân 2^k; với D=0,n>0, số phân hoạch không nhãn tương ứng được chia 2.
- Đáp án chính xác dùng BigInteger không âm.

### Bảng kiểm thử gợi ý

| Mảng a | Câu hỏi | Kỳ vọng |
| --- | --- | --- |
| [] | Equal partition | true |
| [] | Min difference | 0, hai nhóm rỗng |
| [] | Count D=0, không nhãn | 1 |
| [0] | Count D=0, không nhãn | 1 |
| [0,0] | Count D=0, không nhãn | 2 |
| [1,5,11,5] | Equal partition | true |
| [2,2,2] | Equal partition | false dù tổng chẵn |
| [1,2,3,5] | Equal partition | false vì tổng lẻ |
| [1,6,11,5] | Min difference | 1, có thể lấy [2] hoặc [1,3] |
| [8,7,6,5,4] | Min difference | 0, đối chứng greedy |
| [1,1,2,2] | Count D=0, không nhãn | 2 |
| [1,1,2,2] | Count D=2, không nhãn | 3 |
| [1,1,2,2] | Count D=1, không nhãn | 0 vì sai chẵn lẻ |
| [0,0,3] | Count D=3, không nhãn | 4, mỗi số 0 chọn độc lập |
| [-1,1] | Hàm ví dụ nhận số âm? | Từ chối theo hợp đồng |
| Tổng rất lớn, target>200.000 | Hàm ví dụ có cấp phát DP? | Từ chối có chủ đích |

### Đối chứng brute force cho n nhỏ

Với n≤20, có thể duyệt tất cả 2^n bitmask. Mỗi bitmask biểu diễn nhóm A (nhóm B là phần bù). Tính s của A, chênh lệch |S-2s|, giữ giá trị nhỏ nhất để đối chứng DP tối ưu.

Để đếm phân hoạch **không nhãn**, khi n>0 có thể chuẩn hóa bằng quy tắc **phần tử chỉ số 0 luôn thuộc nhóm A**. Mỗi cặp tập con bù nhau sẽ có đúng một đại diện thỏa quy tắc ấy; với n=0 giữ một đại diện rỗng. Duyệt các mask đại diện, tính độ chênh lệch và đếm theo D. Cách chuẩn hóa này hoạt động cho cả D=0 và D>0, giúp có một **oracle độc lập** để kiểm tra công thức chia đôi. Nó không phải tối ưu cho n lớn vì 2^n tăng theo cấp số mũ.

Nếu chỉ dùng các tập con tổng target làm oracle cho D>0, chúng là nhóm **nhẹ hơn**, còn nếu D=0 thì phải tránh đếm hai lần cặp phần bù; n=0 vẫn là trường hợp riêng.

## 14. Bài tập tự luyện

1. Với a=[1,5,11,5], tính S, target=S/2, lập bảng can[i][s] tới s=11 và truy vết một phân hoạch có hai tổng bằng nhau. Sau đó thử a=[2,2,2] để thấy tổng chẵn chưa đủ.
2. Với a=[1,6,11,5], liệt kê mọi tổng subset≤11 có thể đạt; chứng minh best=11 cho chênh lệch 1. Viết hai cách tạo nhóm nhẹ hơn có tổng 11 và các nhóm bù tương ứng.
3. Cho a=[8,7,6,5,4], mô phỏng heuristic luôn đưa phần tử kế tiếp vào nhóm có tổng nhỏ hơn. So sánh độ chênh lệch greedy với nghiệm tối ưu DP.
4. Đếm số phân hoạch không nhãn có D=0 và D=2 cho a=[1,1,2,2]. Phân biệt **chỉ số** của hai số 1 và hai số 2; giải thích vì sao chia hai chỉ khi D=0.
5. Cho a=[0,0,3], đếm số phân hoạch không nhãn có D=3. Nếu bỏ một số 0, số cách đổi ra sao? Nếu bỏ cả hai số 0 thì sao?
6. Viết lại minimumDifferencePartition chỉ trả chênh lệch bằng boolean[] 1D. So sánh thời gian và bộ nhớ với bản 2D cần truy vết.
7. Viết DP đếm theo modulo M, rồi giải thích vì sao không thể lấy phần dư và chia 2 bằng phép chia nguyên khi D=0. Đề xuất cách giữ đáp án chính xác trước khi modulo hoặc một quy tắc đếm không nhãn trực tiếp.
8. Nếu mảng có số âm, đặt L=tổng các số âm và U=tổng các số dương. Mô tả ánh xạ offset để biểu diễn tổng s∈[L,U]; xây một ví dụ chứng tỏ boolean[0..S] không đủ.
9. Với n=40 nhưng các giá trị cực lớn, so sánh DP theo S với meet-in-the-middle. Hãy ước lượng số tập con mỗi nửa và lượng bộ nhớ cần để lưu danh sách tổng.
10. Tạo kiểm thử brute force cho n≤16: đối chiếu min difference, equal partition, số cách cho mọi D khả thi với kết quả DP, bao gồm dãy rỗng, dãy toàn 0 và dãy nhiều phần tử trùng.

**Ghi nhớ:** phân hoạch hai nhóm được giải bằng việc chọn một tập con có tổng s. Chia đều cần S chẵn và s=S/2 khả thi; chênh lệch nhỏ nhất cần **tổng khả thi lớn nhất không vượt S/2**; đếm chênh lệch D cần target=(S-D)/2, xác định rõ **hai nhóm có gắn nhãn không** và xử lý phần tử 0. DP 0/1 nén một chiều phải duyệt sức chứa **giảm dần**. Trước khi dùng bảng theo tổng, kiểm tra giá trị âm, sức chứa bộ nhớ, tràn số và yêu cầu truy vết.
