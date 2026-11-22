# Ký hiệu O, Ω, Θ trong mô tả một thuật toán

## 1. Đang mô tả điều gì khi nói thuật toán “nhanh” hay “chậm”?

Khi đánh giá chi phí của thuật toán, ta quan tâm lượng tài nguyên cần dùng **khi kích thước đầu vào tăng**, thường là thời gian tính toán hoặc bộ nhớ. Với kích thước đầu vào \(n\), gọi \(T(n)\) là số bước xử lý theo một mô hình chi phí đã chọn và \(S(n)\) là lượng bộ nhớ cần thiết. Những đại lượng này là **hàm theo kích thước đầu vào**; cách đếm chi tiết có thể khác giữa các máy, nhưng tốc độ tăng trưởng thường quan trọng hơn một con số đo tại một kích thước duy nhất.

Ví dụ, duyệt một mảng có n phần tử bằng một vòng lặp với công việc hằng số mỗi lần thường có số bước dạng \(T(n)=an+b\), với \(a,b\) là hằng số không phụ thuộc n. Ta nói tốc độ tăng trưởng **bậc tuyến tính**, ký hiệu \(\Theta(n)\). Một thuật toán có số bước \(3n^2+5n+7\) tăng theo bậc bình phương, ký hiệu \(\Theta(n^2)\).

Ba ký hiệu tiệm cận thường dùng là **Big O** \(O\) — chặn trên, **Big Omega** \(\Omega\) — chặn dưới và **Big Theta** \(\Theta\) — chặn chặt cả hai phía. Chúng mô tả quan hệ giữa các hàm khi n đủ lớn, không phải số giây chạy chính xác, cũng không tự động khẳng định thuật toán đúng về mặt chức năng.

**Kích thước đầu vào phải được định nghĩa:** với mảng là số phần tử n; với đồ thị có thể là số đỉnh V và số cạnh E; với số nguyên rất lớn có thể là số bit biểu diễn. Nếu dữ liệu có hai kích thước độc lập n và m, biểu thức \(O(nm)\) có thể chính xác hơn việc ép tất cả vào một biến n.

## 2. Định nghĩa toán học của O, Ω, Θ

Giả sử \(f(n)\) và \(g(n)\) không âm từ một ngưỡng nào đó trở đi, \(g(n)>0\) khi n đủ lớn. Ta xét các số nguyên n không âm.

### Big O: chặn trên tiệm cận

Ta viết \(f(n)\in O(g(n))\) nếu tồn tại hai hằng số \(c>0\) và \(n_0\) sao cho:

\[
0\le f(n)\le c\,g(n)\quad\text{với mọi }n\ge n_0.
\]

Nói cách khác, kể từ một kích thước đủ lớn, f **không tăng nhanh hơn g quá một hệ số hằng số**. Big O diễn đạt một **chặn trên**, không nhất thiết là chặn chính xác nhất.

### Big Omega: chặn dưới tiệm cận

Ta viết \(f(n)\in\Omega(g(n))\) nếu tồn tại \(c>0\) và \(n_0\) sao cho:

\[
0\le c\,g(n)\le f(n)\quad\text{với mọi }n\ge n_0.
\]

Nghĩa là từ một ngưỡng đủ lớn, f **ít nhất tăng nhanh bằng g theo một hệ số hằng số**.

### Big Theta: chặn chặt tiệm cận

Ta viết \(f(n)\in\Theta(g(n))\) nếu tồn tại \(c_1,c_2>0\) và \(n_0\) sao cho:

\[
0\le c_1g(n)\le f(n)\le c_2g(n)
\quad\text{với mọi }n\ge n_0.
\]

Do đó, \(\Theta(g)=O(g)\cap\Omega(g)\): f vừa có chặn trên vừa có chặn dưới cùng bậc g. **Theta là cách phát biểu bậc tăng trưởng chặt**, trong khi O hay Ω riêng lẻ có thể lỏng.

Trong tài liệu thuật toán, cách ghi \(T(n)=O(n^2)\) rất phổ biến và được hiểu là “T thuộc lớp O(n²)”; ký hiệu tập hợp \(T(n)\in O(n^2)\) diễn đạt quan hệ một cách tường minh hơn.

| Ký hiệu | Câu hỏi trả lời | Ví dụ với \(f(n)=n^2+3n+2\) | Có là chặn chặt không? |
|---|---|---|---|
| \(O(g)\) | f tăng **không nhanh hơn** bậc nào? | \(f\in O(n^2)\), cũng thuộc \(O(n^3)\) | Không bắt buộc |
| \(\Omega(g)\) | f tăng **không chậm hơn** bậc nào? | \(f\in\Omega(n^2)\), cũng thuộc \(\Omega(n)\) | Không bắt buộc |
| \(\Theta(g)\) | Bậc tăng trưởng **hai chiều** là gì? | \(f\in\Theta(n^2)\) | Có |

**Điểm cần nhớ:** \(O(n^3)\) có thể đúng cho một thuật toán thật sự chạy \(\Theta(n^2)\), nhưng là chặn trên lỏng. Cũng vậy, \(\Omega(n)\) là chặn dưới đúng của hàm \(\Theta(n^2)\), dù chưa mô tả hết tốc độ tăng trưởng.

## 3. Chứng minh bằng các hằng số: đừng chỉ “bỏ số nhỏ”

Xét:

\[
f(n)=n^2+3n+2,\qquad n\ge1.
\]

Vì \(3n\le3n^2\) và \(2\le2n^2\) khi \(n\ge1\):

\[
n^2\le n^2+3n+2\le6n^2.
\]

Chọn \(c_1=1\), \(c_2=6\), \(n_0=1\). Theo định nghĩa, \(f(n)\in\Theta(n^2)\); suy ra đồng thời \(f\in O(n^2)\) và \(f\in\Omega(n^2)\).

Để thấy \(f\notin O(n)\), xét \(f(n)/n=n+3+2/n\), tăng không bị chặn khi n tăng. Không tồn tại một hằng số c cố định để \(f(n)\le cn\) với **mọi n đủ lớn**.

Phương pháp thực hành thường là tìm số hạng chi phối khi n lớn; song muốn **chứng minh** một chặn, cần chỉ rõ vì sao bất đẳng thức phù hợp với mọi n từ một ngưỡng \(n_0\). Các hằng số được phép phụ thuộc thuật toán, nhưng **không được phụ thuộc n**.

Một số ví dụ chuẩn, với n đủ lớn:

| Hàm chi phí | Bậc chặt |
|---|---|
| \(7n+30\) | \(\Theta(n)\) |
| \(4n^2+2n+9\) | \(\Theta(n^2)\) |
| \(n\log_2 n+5n\) | \(\Theta(n\log n)\) |
| \(3\log_2 n+8\) | \(\Theta(\log n)\) |
| \(2^n+n^4\) | \(\Theta(2^n)\) |

Với cơ số cố định \(a,b>1\), công thức đổi cơ số \(\log_a n=\log_b n/\log_b a\) cho thấy \(\Theta(\log_a n)=\Theta(\log_b n)\). Cơ số logarit không làm đổi bậc tiệm cận khi chỉ khác nhau bởi một hằng số.

## 4. O, Ω, Θ **không đồng nghĩa** worst case, best case, average case

Phải tách **hai lựa chọn khác nhau**:

1. **Trường hợp đầu vào nào được đo?** Thời gian tốt nhất, xấu nhất, trung bình theo một phân phối đầu vào cụ thể, kỳ vọng do ngẫu nhiên trong thuật toán, hoặc chi phí khấu hao của một chuỗi thao tác.
2. **Dùng quan hệ tiệm cận nào?** Chặn trên O, chặn dưới Ω, hay chặn chặt Θ cho **hàm chi phí đã chọn**.

Ký hiệu \(T_{\mathrm{best}}(n)\) là số bước nhỏ nhất trên mọi đầu vào hợp lệ cỡ n; \(T_{\mathrm{worst}}(n)\) là lớn nhất; \(T_{\mathrm{avg}}(n)\) cần một mô hình phân phối xác suất đầu vào.

Ví dụ **tìm tuyến tính** trong mảng n phần tử, trả về chỉ số phần tử mục tiêu hoặc −1:
- Nếu phần tử ở vị trí đầu tiên: chỉ cần một phép so sánh, nên \(T_{\mathrm{best}}(n)\in\Theta(1)\) với n≥1.
- Nếu phần tử ở cuối hoặc không xuất hiện: cần n phép so sánh, nên \(T_{\mathrm{worst}}(n)\in\Theta(n)\).
- Nếu mục tiêu chắc chắn có mặt và mỗi vị trí xuất hiện có xác suất bằng nhau, số phép so sánh kỳ vọng là \((1+2+\cdots+n)/n=(n+1)/2\), nên \(T_{\mathrm{avg}}(n)\in\Theta(n)\) **theo giả định phân phối ấy**. Nếu thay giả định, phải tính lại.

Câu “Big O là worst case, Big Omega là best case” là **sai**. Ta có thể nêu \(T_{\mathrm{best}}\in O(1)\), \(T_{\mathrm{best}}\in\Omega(1)\), \(T_{\mathrm{best}}\in\Theta(1)\); hoặc cả ba quan hệ cho \(T_{\mathrm{worst}}\). Tương tự, một thuật toán có thể được mô tả bằng chặn dưới cho thời gian **xấu nhất**. Chữ O/Ω/Θ trả lời về **quan hệ giữa các hàm**, còn best/worst/average trả lời về **cách chọn tập đầu vào và phép tổng hợp chi phí**.

Cũng cần phân biệt **chặn dưới cho một thuật toán** và **chặn dưới cho cả bài toán**. Chứng minh một thuật toán cụ thể mất \(\Omega(n^2)\) bước trong trường hợp xấu nhất không có nghĩa mọi thuật toán giải bài toán ấy đều phải mất \(\Omega(n^2)\).

## 5. Cách suy ra bậc thời gian từ mã

### Mẫu A — một vòng lặp tuyến tính

Nếu chương trình xét n phần tử và thực hiện lượng công việc hằng số ở mỗi bước, tổng số bước có dạng \(an+b\), vì thế thời gian \(\Theta(n)\). Nếu mỗi bước có thể kết thúc tìm kiếm sớm, phải xét riêng trường hợp tốt nhất, xấu nhất.

### Mẫu B — hai vòng lặp tam giác

Xét các cặp chỉ số \(0\le i<j<n\):

~~~text
for i = 0, 1, ..., n-1:
    for j = i+1, i+2, ..., n-1:
        xử lý cặp (i, j) trong thời gian hằng số
~~~

Với i cố định, vòng trong lặp \(n-i-1\) lần. Tổng số lần là:

\[
(n-1)+(n-2)+\cdots+1+0
=\frac{n(n-1)}2.
\]

Khi \(n\ge2\), ta có \(n^2/4\le n(n-1)/2\le n^2/2\). Vì vậy số lần thực hiện thân vòng lặp thuộc **\(\Theta(n^2)\)**. Hai vòng lặp này không chạy chính xác n² lần: **đếm miền lặp** mới cho lập luận đúng.

Không thể khẳng định “cứ có hai vòng lặp lồng nhau là \(\Theta(n^2)\)”: nếu vòng trong chỉ chạy đến \(\log n\), hoặc giới hạn phụ thuộc đầu vào khác đi, phải tính lại số lần thực hiện.

### Mẫu C — kích thước giảm một nửa

~~~text
m = n
while m > 1:
    m = floor(m / 2)
~~~

Với n≥1, số vòng lặp bằng \(\lfloor\log_2 n\rfloor\). Mỗi vòng làm công việc hằng số, nên thời gian **\(\Theta(\log n)\)** cho n≥2. Đây là kiểu tăng trưởng thường xuất hiện khi liên tục chia đôi không gian tìm kiếm.

**Lưu ý khi lập luận:** với một chuỗi công đoạn chạy liên tiếp, cộng chi phí các công đoạn; với vòng lặp, cộng theo số lần và chi phí mỗi lần; với nhánh điều kiện, xác định đúng trường hợp đầu vào đang phân tích; với đệ quy, lập quan hệ truy hồi cho số lần gọi và công việc mỗi lần. Đừng nhân hoặc cộng các biểu thức chỉ vì nhìn thấy nhiều dòng mã.

## 6. Java 17+: đo số thao tác minh họa, rồi suy ra O/Ω/Θ

Chương trình sau **đếm lần chạy thân vòng lặp**, không đo milliseconds. Cách này giúp nhìn thấy cấu trúc tăng trưởng của thuật toán mà không nhầm với ảnh hưởng của JVM, JIT, CPU hay tác vụ hệ điều hành.

Lưu tệp **AsymptoticNotationDemo.java**:

~~~java
public final class AsymptoticNotationDemo {
    private AsymptoticNotationDemo() {
    }

    // Xét mọi cặp chỉ số i < j.
    public static long pairIterations(int n) {
        if (n < 0) {
            throw new IllegalArgumentException("n must be >= 0");
        }

        long count = 0;
        for (int i = 0; i < n; i++) {
            for (int j = i + 1; j < n; j++) {
                count++;
            }
        }
        return count;
    }

    // Đếm số lần chia đôi đến khi còn 1.
    public static int halvingIterations(int n) {
        if (n <= 0) {
            throw new IllegalArgumentException("n must be > 0");
        }

        int count = 0;
        while (n > 1) {
            n /= 2;
            count++;
        }
        return count;
    }

    // Trả vị trí đầu tiên có target, hoặc -1 nếu không tìm thấy.
    public static int linearSearch(int[] values, int target) {
        if (values == null) {
            throw new IllegalArgumentException("values must not be null");
        }

        for (int i = 0; i < values.length; i++) {
            if (values[i] == target) {
                return i;
            }
        }
        return -1;
    }

    public static void main(String[] args) {
        int[] values = {7, 4, 9, 2};

        System.out.println("pairIterations(5) = " + pairIterations(5));
        System.out.println("halvingIterations(8) = " + halvingIterations(8));
        System.out.println("linearSearch(7) = " + linearSearch(values, 7));
        System.out.println("linearSearch(2) = " + linearSearch(values, 2));
        System.out.println("linearSearch(5) = " + linearSearch(values, 5));
    }
}
~~~

Biên dịch và chạy với JDK 17 trở lên:

~~~bash
javac AsymptoticNotationDemo.java
java AsymptoticNotationDemo
~~~

Stdout chính xác:

~~~text
pairIterations(5) = 10
halvingIterations(8) = 3
linearSearch(7) = 0
linearSearch(2) = 3
linearSearch(5) = -1
~~~

**Phân tích kết quả và độ phức tạp:**

- **pairIterations(n)** duyệt \(n(n-1)/2\) cặp, nên thân vòng lặp chạy \(\Theta(n^2)\) lần; thời gian tổng thể \(\Theta(n^2)\) theo mô hình mỗi thao tác số học, so sánh và tăng biến có chi phí hằng số. Đồng thời có chặn trên \(O(n^2)\) và chặn dưới \(\Omega(n^2)\). Không gian phụ trợ \(\Theta(1)\), vì chỉ giữ các biến đếm.
- **halvingIterations(n)** chạy \(\lfloor\log_2 n\rfloor\) vòng, nên \(\Theta(\log n)\) thời gian với n≥2 và \(\Theta(1)\) bộ nhớ phụ trợ.
- **linearSearch(values, target)** có trường hợp tốt nhất \(\Theta(1)\), trường hợp xấu nhất \(\Theta(n)\), bộ nhớ phụ trợ \(\Theta(1)\). Kết quả 0, 3, −1 minh họa tìm thấy sớm, tìm thấy muộn và không tìm thấy. Với dữ liệu cố định của hàm main, lần tìm 7 kiểm tra một phần tử; tìm 2 hoặc 5 kiểm tra bốn phần tử.

Chú ý rằng **pairIterations** được viết để **thực sự duyệt các cặp**. Nếu yêu cầu chỉ là tính **số lượng cặp**, có thể dùng công thức số học \(n(n-1)/2\) thay vòng lặp và đạt số thao tác hằng số trong mô hình số nguyên máy, sau khi xử lý đúng giới hạn kiểu dữ liệu. Độ phức tạp là thuộc **thuật toán được triển khai**, không phải chỉ thuộc biểu thức giá trị kết quả.

## 7. Phân biệt chặn tiệm cận với chi phí thực tế

Các ký hiệu O/Ω/Θ bỏ qua hệ số hằng số và các số hạng bậc thấp **trong phân tích tăng trưởng**. Chúng không bảo đảm thuật toán có bậc thấp hơn luôn chạy nhanh hơn cho mọi đầu vào thực tế.

Ví dụ:
- \(1000n\) và \(2n\) đều là \(\Theta(n)\), nhưng thời gian thực tế có thể chênh rất lớn.
- \(100n\) và \(n^2\): với n nhỏ, \(n^2\) có thể ít hơn \(100n\), dù khi n tăng đủ lớn, hàm bậc hai tăng nhanh hơn bậc tuyến tính.
- Thời gian chạy còn phụ thuộc thao tác cụ thể, bộ nhớ đệm, cấp phát đối tượng, tối ưu hóa trình biên dịch/JIT, cơ chế I/O, biểu diễn dữ liệu và phần cứng.

Bởi vậy, **chứng minh độ phức tạp** và **benchmark thực nghiệm** phục vụ hai mục đích bổ trợ: lý thuyết dự đoán cách chi phí tăng khi quy mô lớn; thực nghiệm kiểm tra hiệu năng trong môi trường và dữ liệu cụ thể.

### Thời gian và không gian là hai câu hỏi riêng

Một thuật toán có thể cần \(\Theta(n)\) thời gian nhưng chỉ \(\Theta(1)\) bộ nhớ phụ trợ, như duyệt mảng tại chỗ. Nếu tạo một bản sao n phần tử, bộ nhớ phụ trợ có thể tăng lên \(\Theta(n)\). Phải nói rõ **bộ nhớ tính cả đầu vào, đầu ra hay chỉ phần phụ trợ**. Chẳng hạn, khi thuật toán phải in ra k nghiệm, riêng việc xuất k mục đã tạo chặn dưới \(\Omega(k)\) thao tác xuất theo mô hình mỗi mục có chi phí hằng số.

## 8. Các bậc tăng trưởng thường gặp

Với n lớn và cùng mô hình tính toán, thứ tự điển hình từ chậm tăng đến nhanh tăng là:

\[
1,\ \log n,\ n,\ n\log n,\ n^2,\ n^3,\ 2^n,\ n!.
\]

| Bậc | Mô hình thường gặp | Ý nghĩa khi n tăng |
|---|---|---|
| \(\Theta(1)\) | Truy cập một phần tử mảng qua chỉ số | Không phụ thuộc n theo mô hình đã chọn |
| \(\Theta(\log n)\) | Lặp lại thao tác chia đôi kích thước | Tăng rất chậm |
| \(\Theta(n)\) | Duyệt tất cả n phần tử đúng một lần | Tăng tỷ lệ với n |
| \(\Theta(n\log n)\) | Một số thuật toán chia để trị/sắp xếp | Nhanh hơn bậc tuyến tính, chậm hơn bình phương |
| \(\Theta(n^2)\) | Duyệt tất cả cặp phần tử | Tăng mạnh khi n lớn |
| \(\Theta(2^n)\) | Duyệt mọi tập con của n phần tử | Số trường hợp tăng theo hàm mũ |
| \(\Theta(n!)\) | Duyệt tất cả hoán vị | Số trường hợp tăng rất nhanh |

Bảng mô tả **mẫu hình thường gặp**, không khẳng định mọi thuật toán thuộc nhóm ví dụ luôn có bậc đó trong mọi trường hợp. Ví dụ, tìm kiếm nhị phân trên mảng **đã sắp xếp** có thời gian xấu nhất \(\Theta(\log n)\) với truy cập chỉ số hằng số; nếu phải sắp xếp mảng trước, chi phí chuẩn bị phải cộng vào tổng chi phí của toàn quy trình.

Với đồ thị biểu diễn bằng danh sách kề, một phép duyệt BFS đầy đủ thường có chặn thời gian \(O(V+E)\). Viết hai biến V, E tránh che mất ảnh hưởng của độ dày cạnh và không tùy tiện thay bằng \(O(n)\) khi n chưa được định nghĩa.

## 9. Những lỗi diễn đạt và suy luận cần tránh

1. **“O(n²) nghĩa là chạy chính xác n² lần.”** Sai: đó là một chặn trên theo hệ số hằng số khi n đủ lớn. Nếu muốn khẳng định bậc chính xác, chứng minh thêm chặn dưới để đạt \(\Theta(n^2)\).
2. **“O là trường hợp xấu nhất, Ω là trường hợp tốt nhất.”** Sai: trường hợp và loại chặn là hai chiều phân tích độc lập.
3. **“Vì có O(n²), chắc chắn không có O(n).”** Không suy ra. Một hàm \(\Theta(n)\) cũng thuộc \(O(n^2)\); cần xét chặn chặt hoặc chứng minh không thuộc lớp nhỏ hơn.
4. **“Bỏ toàn bộ hệ số và số hạng thấp trong mọi tình huống.”** Chỉ phù hợp khi mô tả bậc tiệm cận; hệ số, bộ nhớ và hằng số có thể quyết định hiệu năng trong thực tế.
5. **“Hai vòng lặp lồng nhau luôn là O(n²).”** Không nhất thiết: phải đếm số lần chạy thực tế, kể cả việc giới hạn vòng trong có phụ thuộc vòng ngoài hoặc đầu vào.
6. **“Average case hiển nhiên là Θ(n).”** Không có phân phối đầu vào thì không thể suy ra một giá trị kỳ vọng duy nhất.
7. **“Chứng minh thuật toán A cần Ω(n²) là chứng minh bài toán không giải nhanh hơn.”** Không đúng: chặn dưới cho một cách triển khai khác với chặn dưới cho mọi thuật toán hợp lệ.
8. **“Thuật toán tối ưu tiệm cận đương nhiên đúng và phù hợp mọi đầu vào.”** Độ phức tạp không thay thế chứng minh tính đúng; chi phí cũng có thể phụ thuộc cấu trúc dữ liệu, miền giá trị và giả định tính toán.
9. **“Một hàm thuộc Θ(g) nhưng không cần chứng minh hai phía.”** Để dùng Theta nghiêm ngặt, cần chặn trên lẫn chặn dưới cùng bậc.
10. **“Dùng biến n chung cho mọi loại đầu vào.”** Với đồ thị, ma trận, chuỗi nhiều biến hoặc số nguyên mã hóa theo bit, phải xác định kích thước thật và chi phí đọc/ghi dữ liệu.

## 10. Cách trình bày kết quả phân tích trong tài liệu thuật toán

Một mô tả có thể kiểm chứng thường gồm:

1. **Đầu vào và kích thước:** n là gì; nếu có m, V, E, k thì chúng biểu thị gì.
2. **Đại lượng chi phí:** số bước thời gian \(T(n)\), bộ nhớ phụ trợ \(S(n)\), hay chi phí đầu ra.
3. **Trường hợp và giả định:** tốt nhất, xấu nhất, trung bình theo phân phối nào; có phụ thuộc dữ liệu đã sắp xếp hay không.
4. **Lập luận:** mỗi vòng lặp chạy bao nhiêu lần; công việc mỗi lần; phép cộng/tổng hay truy hồi nào xuất hiện.
5. **Chặn được chứng minh:** nêu rõ \(O\), \(\Omega\) hoặc \(\Theta\), tránh dùng Theta khi mới chứng minh một phía.
6. **Giới hạn:** hằng số lớn, giới hạn bộ nhớ, đầu vào đặc biệt, I/O và kích thước kết quả nếu chúng thay đổi cách hiểu chi phí.

Ví dụ mô tả đầy đủ: “Với mảng n phần tử, tìm tuyến tính dùng \(\Theta(1)\) bộ nhớ phụ trợ. Nếu phần tử ở vị trí đầu, thời gian \(\Theta(1)\); trường hợp xấu nhất, khi phần tử vắng mặt hoặc ở cuối, thời gian \(\Theta(n)\). Kết luận này dựa trên phép so sánh từng phần tử có chi phí hằng số.”

## 11. Tự kiểm tra nhanh

**Câu 1.** Cho \(T(n)=5n^2+100n+2\). Hãy tìm một chặn trên, một chặn dưới và chặn chặt.

**Đáp án:** \(T\in O(n^2)\), \(T\in\Omega(n^2)\) và \(T\in\Theta(n^2)\). Các chặn lỏng như \(O(n^3)\) hoặc \(\Omega(n)\) cũng đúng nhưng kém thông tin hơn.

**Câu 2.** Một vòng lặp giảm m từ n xuống \(\lfloor m/2\rfloor\) cho đến khi m≤1, mỗi vòng làm một thao tác hằng số. Bậc thời gian là gì?

**Đáp án:** \(\Theta(\log n)\) khi n≥2, vì sau k vòng kích thước giảm xấp xỉ \(n/2^k\), và cần \(k\) tỷ lệ với \(\log_2 n\) để xuống 1.

**Câu 3.** Một thuật toán có thời gian xấu nhất \(\Theta(n)\). Viết “thời gian xấu nhất là O(n²)” có sai không?

**Đáp án:** Về mặt chặn trên thì **đúng**, nhưng là thông tin lỏng. Viết \(\Theta(n)\) thể hiện đúng bậc tăng trưởng đã chứng minh; hoặc ít nhất viết \(O(n)\) nếu chỉ muốn phát biểu chặn trên.

**Câu 4.** Nếu tìm tuyến tính thấy phần tử ngay đầu mảng, có thể tuyên bố thuật toán có thời gian xấu nhất O(1) không?

**Đáp án:** **Không.** Quan sát đó chỉ minh họa một đầu vào thuộc trường hợp tốt nhất. Muốn chứng minh xấu nhất, phải xét cả đầu vào đòi hỏi n lần so sánh.

**Câu 5.** Vì sao từ \(T(n)\in O(n^2)\) và \(T(n)\in\Omega(n)\) chưa suy ra \(T(n)\in\Theta(n^2)\)?

**Đáp án:** Chặn trên \(n^2\) và chặn dưới n không cùng bậc. Chẳng hạn \(T(n)=n\) thỏa cả hai nhưng thuộc \(\Theta(n)\), không thuộc \(\Theta(n^2)\).

**Ghi nhớ:** Trước tiên xác định **hàm chi phí và trường hợp đang xét**; sau đó mới dùng **O để nói chặn trên, Ω để nói chặn dưới, Θ để nói bậc chặt**. Một kết luận tốt luôn có lập luận về số phép toán hoặc bất đẳng thức đi kèm.
