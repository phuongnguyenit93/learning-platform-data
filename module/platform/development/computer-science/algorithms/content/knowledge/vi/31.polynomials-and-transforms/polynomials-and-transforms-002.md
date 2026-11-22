# Cộng, nhân đa thức và tích chập trực tiếp

## 1. Đa thức là gì và vì sao cần thao tác trên hệ số?

Một **đa thức một biến** trên các số nguyên có dạng:

~~~text
P(x) = a[0] + a[1]*x + a[2]*x^2 + ... + a[d]*x^d
~~~

Trong đó a[i] là **hệ số của x^i**, i là **bậc của hạng tử**, và d là **bậc của đa thức** nếu a[d] khác 0. Ví dụ:

~~~text
A(x) = 2 - x + 3*x^2
B(x) = 4 + 5*x^2
~~~

Ta lưu hai đa thức bằng dãy hệ số **theo bậc tăng dần**:

~~~text
A = [ 2, -1, 3 ]
B = [ 4,  0, 5 ]
      ^   ^  ^
     x^0 x^1 x^2
~~~

Số 0 trong B ở vị trí 1 rất quan trọng: nó biểu thị **hệ số x bằng 0**, chứ không phải một hạng tử được phép xóa khỏi giữa dãy. Nếu bỏ hệ số 0 giữa dãy mà không đổi cấu trúc dữ liệu, bậc của những hệ số phía sau sẽ sai.

Trong thực hành thuật toán, cộng và nhân đa thức xuất hiện khi:

- Kết hợp các biểu thức đại số, hàm sinh, truy hồi và quy hoạch động.
- Đếm số cách tạo một tổng hoặc phân bố số lượng theo hệ số.
- Tính **tích chập tuyến tính** của hai dãy số.
- Xử lý dãy tín hiệu hữu hạn, nơi convolution có ý nghĩa kết hợp đóng góp từ các vị trí.
- Làm bước nền trước những thuật toán nhân đa thức nhanh hơn như FFT/NTT.

Mục tiêu của bài là hiểu và tự cài được phép cộng **O(n+m)** và phép nhân/tích chập trực tiếp **O(nm)**, chứng minh tính đúng, xử lý các trường hợp biên và biết khi nào cần kỹ thuật khác.

### Phân biệt hệ số, bậc và độ dài

Nếu mảng có n phần tử và hệ số cuối khác 0, bậc đa thức là **n−1**. Nếu cuối mảng có các số 0, độ dài mảng có thể lớn hơn bậc thực sự.

~~~text
[5, 0, 2]       -> 5 + 2*x^2, bac 2
[5, 0, 2, 0, 0] -> cung da thuc, bac van la 2
[0, 0, 0]       -> da thuc khong
~~~

Theo quy ước của bài:

- Đa thức không được biểu diễn **chuẩn hóa** bằng `[0]`.
- Mảng rỗng `[]` khi đi vào phép cộng/nhân được hiểu là đa thức không; đầu ra toán học vẫn là `[0]`.
- Các số 0 **ở cuối** có thể được loại khi chuẩn hóa. Các số 0 **ở giữa** không được xóa.
- Bậc của đa thức không được quy ước là **−1** trong mã, để phân biệt với đa thức hằng khác 0 có bậc 0. Trong đại số, nhiều tài liệu dùng deg(0)=−∞; đây là một quy ước biểu diễn trong chương trình.
- Hệ số trong bản Java đầu là số nguyên `long`; các phép tính dùng kiểm tra tràn. Nếu cần kết quả nguyên chính xác vượt 64-bit, dùng `BigInteger`.

## 2. Cộng hai đa thức theo từng bậc

Với:

~~~text
A(x) = SUM a[i]*x^i
B(x) = SUM b[i]*x^i
~~~

phép cộng có dạng:

~~~text
C(x) = A(x) + B(x)
c[k] = a[k] + b[k]
~~~

Nếu k vượt quá độ dài một dãy, ta coi hệ số tương ứng của dãy ấy bằng 0. Không có sự tương tác giữa các bậc khác nhau: **chỉ cộng những hệ số của cùng lũy thừa x^k**.

Ví dụ:

~~~text
A(x) = 2 - x + 3*x^2
B(x) = 4     + 5*x^2

C(x) = 6 - x + 8*x^2

A = [2, -1, 3]
B = [4,  0, 5]
C = [6, -1, 8]
~~~

Nếu A dài n và B dài m, ta cần tối đa max(n,m) hệ số đầu ra.

### Giả mã cộng

~~~text
add(A,B):
    a = normalize(A)
    b = normalize(B)

    L = max(length(a), length(b))
    c = array of L zero coefficients

    for k = 0..L-1:
        av = (k < length(a)) ? a[k] : 0
        bv = (k < length(b)) ? b[k] : 0
        c[k] = av + bv

    return normalize(c)
~~~

Thời gian **O(max(n,m)) = O(n+m)** theo độ dài đầu vào đã chuẩn hóa. Bộ nhớ cho đầu ra **O(max(n,m))**; nếu tính bản sao chuẩn hóa hai đầu vào, tổng bộ nhớ cấp phát có thể O(n+m).

### Phép trừ

Tương tự:

~~~text
D(x) = A(x) - B(x)
d[k] = a[k] - b[k]
~~~

Với hai đa thức mẫu:

~~~text
A - B = [ -2, -1, -2 ]
~~~

Phép trừ không cần nhân chéo hệ số. Nếu dùng kiểu số nguyên cố định, **phép cộng và phép trừ đều có thể tràn**; kiểm tra bằng `Math.addExact` hoặc `Math.subtractExact` trong Java.

### Cẩn thận với bậc của tổng

Với A,B khác 0, bậc của A+B **không nhất thiết bằng** max(deg A,deg B), vì hệ số đầu có thể triệt tiêu.

~~~text
A(x) = 3*x^2 + x
B(x) = -3*x^2 + 4
A+B  = x + 4
~~~

Bậc của tổng giảm từ 2 xuống 1. Công thức đúng là:

~~~text
deg(A+B) <= max(deg A, deg B)
~~~

nếu cả hai vế được hiểu theo quy ước bậc của đa thức không phù hợp. Đó là một lý do để loại các hệ số 0 ở cuối sau khi tính.

## 3. Nhân đa thức: từ quy tắc phân phối đến thuật toán

Ta nhân từng hạng tử của A với từng hạng tử của B:

~~~text
A(x) = SUM_{i=0..n-1} a[i]*x^i
B(x) = SUM_{j=0..m-1} b[j]*x^j
~~~

Theo quy tắc phân phối:

~~~text
A(x)*B(x)
  = SUM_i SUM_j (a[i]*b[j]) * x^(i+j)
~~~

Bậc của tích hai hạng tử là **i+j**, nên phần đóng góp của cặp hệ số a[i],b[j] phải được cộng vào **c[i+j]**:

~~~text
c[i+j] += a[i]*b[j]
~~~

Nếu A có n hệ số, B có m hệ số, chỉ số tích lớn nhất là:

~~~text
(n-1) + (m-1) = n+m-2
~~~

Do đó cần **n+m−1 vị trí hệ số** (nếu n,m đều ít nhất 1). Đây là kích thước của **tích chập tuyến tính đầy đủ**.

### Giả mã nhân trực tiếp

~~~text
multiply(A,B):
    a = normalize(A)
    b = normalize(B)

    c = array of length a.length+b.length-1 filled with 0

    for i = 0..a.length-1:
        for j = 0..b.length-1:
            c[i+j] += a[i]*b[j]

    return normalize(c)
~~~

Mỗi cặp (i,j) được xử lý đúng một lần. Có n·m cặp, nên thời gian **O(nm)**. Mảng kết quả dài n+m−1, nên bộ nhớ cho kết quả **O(n+m)**. Bản nhân này được gọi là **naive multiplication**, **schoolbook multiplication** hoặc **direct convolution**.

### Lưu ý khi nhân với đa thức không

Nếu A hoặc B là đa thức không, tích cũng là đa thức không:

~~~text
A(x) * 0 = 0
0 * B(x) = 0
~~~

Trong cách biểu diễn chuẩn hóa của bài, kết quả là `[0]` chứ không phải mảng có độ dài n+m−1 toàn số 0. Nếu một API riêng yêu cầu đầu ra cố định chiều dài, nó có thể giữ các số 0; cần ghi rõ khác biệt giữa **dãy hệ số có padding** và **đa thức chuẩn hóa**.

## 4. Tích chập tuyến tính là gì?

Với hai dãy hữu hạn:

~~~text
a = [a[0], a[1], ..., a[n-1]]
b = [b[0], b[1], ..., b[m-1]]
~~~

**Tích chập tuyến tính rời rạc** c=a*b được định nghĩa:

~~~text
c[k] = SUM_{i} a[i] * b[k-i]
~~~

trong đó các chỉ số ngoài miền hợp lệ được coi như hệ số 0. Viết giới hạn rõ ràng:

~~~text
c[k] =
  SUM_{i=max(0,k-(m-1))..min(n-1,k)} a[i]*b[k-i]

0 <= k <= n+m-2
~~~

Đây **chính là công thức hệ số của tích đa thức**:

~~~text
P_a(x) * P_b(x) = P_c(x)
~~~

Vì thế:

- **Nhân đa thức theo hệ số** là một bài toán tích chập.
- **Tích chập tuyến tính của hai dãy** có thể hiểu qua việc nhân hai đa thức có hệ số là các phần tử dãy.
- Trong cả hai cách diễn giải, chỉ số c[k] thu nhận các cặp (i,j) với **i+j=k**.

Điểm quan trọng: convolution **không** phải phép nhân từng phần tử cùng vị trí.

~~~text
a = [1, 2]
b = [3, 4]

nhan tung phan tu: [1*3, 2*4] = [3, 8]

tich chap tuyen tinh:
c[0] = 1*3       = 3
c[1] = 1*4 + 2*3 = 10
c[2] = 2*4       = 8

c = [3, 10, 8]
~~~

Nhân từng phần tử và tích chập trả những đối tượng toán học khác nhau, kể cả độ dài kết quả cũng khác.

## 5. Ví dụ đầy đủ với hệ số âm và hệ số bằng 0

Chọn:

~~~text
A(x) = 2 - x + 3*x^2
B(x) = 4 + 0*x + 5*x^2

a = [2, -1, 3]
b = [4,  0, 5]
~~~

Tính các tích hạng tử:

~~~text
2 * 4       =  8*x^0
2 * 0*x     =  0*x^1
2 * 5*x^2   = 10*x^2

(-x) * 4     = -4*x^1
(-x) * 0*x   =  0*x^2
(-x) * 5*x^2 = -5*x^3

3*x^2 * 4     = 12*x^2
3*x^2 * 0*x   =  0*x^3
3*x^2 * 5*x^2 = 15*x^4
~~~

Đưa mỗi tích vào c[i+j]:

| Cặp i,j | a[i]·b[j] | Cộng vào |
| --- | ---: | --- |
| 0,0 | 8 | c[0] |
| 0,1 | 0 | c[1] |
| 0,2 | 10 | c[2] |
| 1,0 | −4 | c[1] |
| 1,1 | 0 | c[2] |
| 1,2 | −5 | c[3] |
| 2,0 | 12 | c[2] |
| 2,1 | 0 | c[3] |
| 2,2 | 15 | c[4] |

Kết quả:

~~~text
c[0] = 8
c[1] = -4
c[2] = 10 + 12 = 22
c[3] = -5
c[4] = 15

A(x)*B(x) = 8 - 4*x + 22*x^2 - 5*x^3 + 15*x^4
c = [8, -4, 22, -5, 15]
~~~

Có thể kiểm nhanh tại x=2:

~~~text
A(2) = 2 - 2 + 3*4 = 12
B(2) = 4 + 5*4     = 24
(A*B)(2)           = 12*24 = 288

C(2) = 8 - 8 + 22*4 - 5*8 + 15*16
     = 8 - 8 + 88 - 40 + 240
     = 288
~~~

Phép kiểm giá trị tại một điểm không phải chứng minh mọi hệ số đều đúng, nhưng rất hữu ích để phát hiện nhầm chỉ số hoặc dấu trong ví dụ.

## 6. Hai cách cài trực tiếp: rải và gom

Có hai cách viết cùng một phép tích chập tuyến tính.

### Cách 1: rải theo từng cặp đầu vào (scatter)

~~~text
c = zeros(n+m-1)

for i in [0,n):
    for j in [0,m):
        c[i+j] += a[i]*b[j]
~~~

Ưu điểm: trực tiếp từ quy tắc phân phối, dễ nhớ **i+j** là bậc cần cộng vào, hai vòng lặp đơn giản.

### Cách 2: gom theo từng hệ số đầu ra (gather)

~~~text
for k in [0,n+m-1):
    c[k] = 0
    firstI = max(0,k-(m-1))
    lastI  = min(n-1,k)

    for i in [firstI,lastI]:
        c[k] += a[i]*b[k-i]
~~~

Ưu điểm: nhìn rõ c[k] là tổng mọi tích của những cặp có **chỉ số cộng thành k**. Cách này phù hợp khi chỉ cần một hệ số hoặc chỉ cần k hệ số thấp nhất.

Hai cách đều O(nm) nếu tính toàn bộ kết quả. Trong bài Java, phép nhân sản xuất dùng **scatter**, còn bộ kiểm tra độc lập dùng **gather**. Đối chiếu hai thuật toán khác cấu trúc giúp phát hiện lỗi c[i+j] hoặc giới hạn vòng lặp.

### Chứng minh hai cách bằng nhau

Mỗi cặp đầu vào (i,j) có duy nhất k=i+j. Vòng scatter cộng tích a[i]b[j] đúng vào c[k]. Vòng gather cố định k và chỉ xét i sao cho 0≤i<n, 0≤k−i<m; tức chính những cặp (i,j) với i+j=k. Vì hai cách cộng đúng cùng một tập số hạng (trong số học chính xác), kết quả toán học bằng nhau.

Với số thực dấu phẩy động, thứ tự cộng khác nhau có thể làm kết quả xấp xỉ khác nhau do làm tròn; điều này không mâu thuẫn với đẳng thức đại số.

## 7. Độ dài kết quả, bậc và chuẩn hóa

Giả sử A và B có bậc lần lượt dA và dB, đều **khác đa thức không**, và hệ số thuộc số nguyên (không có ước của 0):

~~~text
deg(A*B) = deg(A) + deg(B)
~~~

Vì hệ số đầu của tích là a[dA]·b[dB], tích của hai số nguyên khác 0 nên khác 0. Do đó bậc của tích đúng bằng tổng bậc.

Nếu A,B được chuẩn hóa với độ dài n,m và đều khác 0:

~~~text
length(A*B) = n + m - 1
~~~

Đối với phép cộng:

~~~text
deg(A+B) <= max(deg A,deg B)
~~~

vì hệ số đầu có thể triệt tiêu.

### Đa thức không là ngoại lệ

Bất kỳ đa thức nào nhân với 0 đều cho 0, không thể dùng deg(A*B)=deg(A)+deg(B) theo quy ước chương trình deg(0)=−1. Phải xét trường hợp không riêng.

### Nếu hệ số được lấy modulo một số

Nhân hệ số modulo M vẫn dùng công thức c[i+j], nhưng **vành modulo M có thể có ước của 0 nếu M không nguyên tố**. Ví dụ modulo 6:

~~~text
A(x) = 2*x
B(x) = 3*x

A(x)*B(x) = 6*x^2 = 0 modulo 6
~~~

Vì vậy đẳng thức về bậc của hai đa thức khác 0 **không đúng trong mọi vành có ước của 0**. Với hệ số nguyên bình thường hoặc một trường như modulo số nguyên tố, tính chất này giữ đúng (trừ trường hợp một đa thức là 0).

### Chuẩn hóa hệ số

Sau mỗi phép toán, có thể xóa các số 0 **ở cuối mảng** cho tới khi còn ít nhất một hệ số. Nếu mọi hệ số đều 0, trả `[0]`.

~~~text
normalize([3, 0, 2, 0, 0]) = [3, 0, 2]
normalize([0, 0, 0])       = [0]
normalize([])              = [0]
~~~

Chuẩn hóa làm việc so sánh hai đa thức dễ hơn và tránh nhiều phép nhân vô ích do bậc giả.

## 8. Độ phức tạp và chi phí bộ nhớ

Gọi n,m là **độ dài hệ số sau chuẩn hóa**.

| Phép toán | Thời gian | Dung lượng đầu ra |
| --- | --- | --- |
| Chuẩn hóa mảng hệ số | O(n) trong mã sao chép | O(n) |
| Cộng/trừ | O(max(n,m)) | O(max(n,m)) |
| Nhân trực tiếp | O(nm) | O(n+m) |
| Tính giá trị P(x) bằng Horner | O(n) | O(1) phụ |
| Lấy k hệ số tích đầu (cách cắt sớm) | O(min(n,k)·min(m,k)) cận trên | O(k) |

Cận nhân trực tiếp đếm đúng số cặp **n·m**. Cận chung cho nhân hai đa thức cùng độ dài n là O(n²). Nếu một đa thức có hệ số rất ít, chẳng hạn chỉ một số hằng, nhân trực tiếp có thể là O(n).

### Cấp phát kết quả đúng kích thước

Nếu chỉ cần tích chập đầy đủ, độ dài thô của kết quả bằng n+m−1. Không được ghi vào mảng có n phần tử nếu m>1, vì chỉ số lớn nhất có thể là n+m−2.

Trong Java, tính kích thước bằng kiểu rộng hơn để tránh tràn phép cộng độ dài:

~~~java
long needed = (long) n + m - 1;
if (needed > Integer.MAX_VALUE) {
    throw new IllegalArgumentException("result too large");
}
long[] result = new long[(int) needed];
~~~

Kiểm kích thước không bảo đảm máy có đủ RAM; hệ thống có thể gặp `OutOfMemoryError` nếu cấp phát một mảng khổng lồ.

### Vì sao nhân O(nm) không phải luôn lựa chọn tốt nhất?

Với n=m=1000, số cặp là một triệu, thường đủ dễ xử lý bằng vòng lặp đơn giản. Với n=m=100000, số cặp là mười tỷ, rất tốn CPU. Với bài lớn, cần cân nhắc thuật toán nhanh hơn như Karatsuba, FFT hoặc NTT tùy miền hệ số, giới hạn và độ chính xác.

Tuy vậy khi n,m nhỏ, nhân trực tiếp thường có ưu điểm **dễ chứng minh, dễ triển khai, không có rắc rối với làm tròn FFT**, và có thể làm oracle để kiểm thuật toán nhanh.

## 9. Java 17: chương trình độc lập từ cộng đến tích chập

Đoạn dưới đây là **một chương trình Java 17 biên dịch và chạy được**, gồm:

- `normalize`: đưa đa thức về dạng chuẩn, cho mảng rỗng đại diện đầu vào bằng không.
- `degree`: trả −1 cho đa thức không.
- `add` và `subtract`: cộng/trừ từng hệ số.
- `multiply`: nhân trực tiếp theo cặp i,j; cộng vào c[i+j].
- `firstCoefficientsOfProduct`: tính đúng **k hệ số thấp nhất** với độ dài đầu ra cố định k, kể cả các số 0.
- `evaluate`: tính P(x) bằng Horner.
- `multiplyBig`: phiên bản tích chập dùng `BigInteger` để không tràn số nguyên 64-bit khi hệ số/result rất lớn.
- `gatherReference`: oracle tính c[k] theo cách **gom**, độc lập với cách rải của `multiply`.
- `verifySmallProducts`: so hai cách tính trên **14.400 cặp** đa thức có hệ số thuộc {−1,0,1}, mỗi độ dài từ 1 đến 4; kiểm thêm tính giao hoán.

Bản `long` dùng `Math.multiplyExact`, `Math.addExact`, `Math.subtractExact` để **ném lỗi khi phép toán vượt miền `long`**, không để số tràn lặng lẽ. Mã không sửa mảng đầu vào.

**Lưu toàn bộ vào tệp `PolynomialConvolutionDemo.java`:**

~~~java
import java.math.BigInteger;
import java.util.Arrays;

public class PolynomialConvolutionDemo {

    // Coefficient index i represents x^i.
    // Canonical zero polynomial: [0].
    public static long[] normalize(long[] source) {
        if (source == null) {
            throw new IllegalArgumentException(
                    "coefficients must not be null");
        }
        if (source.length == 0) {
            return new long[] {0};
        }

        int end = source.length;
        while (end > 1 && source[end - 1] == 0L) {
            end--;
        }
        return Arrays.copyOf(source, end);
    }

    public static int degree(long[] source) {
        long[] a = normalize(source);
        if (a.length == 1 && a[0] == 0L) {
            return -1;
        }
        return a.length - 1;
    }

    public static long[] add(long[] left, long[] right) {
        long[] a = normalize(left);
        long[] b = normalize(right);
        long[] c = new long[Math.max(a.length, b.length)];

        for (int k = 0; k < c.length; k++) {
            long av = k < a.length ? a[k] : 0L;
            long bv = k < b.length ? b[k] : 0L;
            c[k] = Math.addExact(av, bv);
        }
        return normalize(c);
    }

    public static long[] subtract(long[] left, long[] right) {
        long[] a = normalize(left);
        long[] b = normalize(right);
        long[] c = new long[Math.max(a.length, b.length)];

        for (int k = 0; k < c.length; k++) {
            long av = k < a.length ? a[k] : 0L;
            long bv = k < b.length ? b[k] : 0L;
            c[k] = Math.subtractExact(av, bv);
        }
        return normalize(c);
    }

    private static int productLength(int n, int m) {
        long needed = (long) n + m - 1L;
        if (needed > Integer.MAX_VALUE) {
            throw new IllegalArgumentException(
                    "result too large for a Java array");
        }
        return (int) needed;
    }

    // Direct linear convolution: scatter each a[i]*b[j].
    public static long[] multiply(long[] left, long[] right) {
        long[] a = normalize(left);
        long[] b = normalize(right);
        if (degree(a) == -1 || degree(b) == -1) {
            return new long[] {0};
        }

        long[] c = new long[productLength(a.length, b.length)];
        for (int i = 0; i < a.length; i++) {
            for (int j = 0; j < b.length; j++) {
                long term = Math.multiplyExact(a[i], b[j]);
                c[i + j] = Math.addExact(c[i + j], term);
            }
        }
        return normalize(c);
    }

    // Return coefficients c[0]..c[terms-1], zero-padded.
    // This is a fixed-size prefix, not a canonical polynomial.
    public static long[] firstCoefficientsOfProduct(
            long[] left, long[] right, int terms) {
        if (terms < 0) {
            throw new IllegalArgumentException(
                    "terms must be >= 0");
        }
        long[] a = normalize(left);
        long[] b = normalize(right);
        long[] c = new long[terms];

        for (int i = 0; i < a.length && i < terms; i++) {
            int maxJ = Math.min(b.length, terms - i);
            for (int j = 0; j < maxJ; j++) {
                long term = Math.multiplyExact(a[i], b[j]);
                c[i + j] = Math.addExact(c[i + j], term);
            }
        }
        return c;
    }

    // Horner evaluation, with checked long arithmetic.
    public static long evaluate(long[] source, long point) {
        long[] a = normalize(source);
        long value = 0L;
        for (int i = a.length - 1; i >= 0; i--) {
            value = Math.addExact(
                    Math.multiplyExact(value, point), a[i]);
        }
        return value;
    }

    // Exact result for long inputs: BigInteger accumulators.
    public static BigInteger[] multiplyBig(
            long[] left, long[] right) {
        long[] a = normalize(left);
        long[] b = normalize(right);
        if (degree(a) == -1 || degree(b) == -1) {
            return new BigInteger[] {BigInteger.ZERO};
        }

        BigInteger[] c =
                new BigInteger[productLength(a.length, b.length)];
        Arrays.fill(c, BigInteger.ZERO);

        for (int i = 0; i < a.length; i++) {
            BigInteger ai = BigInteger.valueOf(a[i]);
            for (int j = 0; j < b.length; j++) {
                c[i + j] = c[i + j].add(
                        ai.multiply(BigInteger.valueOf(b[j])));
            }
        }

        int end = c.length;
        while (end > 1 && c[end - 1].signum() == 0) {
            end--;
        }
        return Arrays.copyOf(c, end);
    }

    // Independent mathematical oracle: gather by output k.
    // Used only on small coefficients, so additions are safe.
    private static long[] gatherReference(
            long[] left, long[] right) {
        long[] a = normalize(left);
        long[] b = normalize(right);
        long[] c = new long[productLength(a.length, b.length)];

        for (int k = 0; k < c.length; k++) {
            long sum = 0L;
            int begin = Math.max(0, k - (b.length - 1));
            int end = Math.min(a.length - 1, k);
            for (int i = begin; i <= end; i++) {
                sum += a[i] * b[k - i];
            }
            c[k] = sum;
        }
        return normalize(c);
    }

    private static int power3(int n) {
        int value = 1;
        for (int i = 0; i < n; i++) {
            value *= 3;
        }
        return value;
    }

    private static long[] decode(int n, int code) {
        long[] a = new long[n];
        for (int i = 0; i < n; i++) {
            a[i] = code % 3 - 1;
            code /= 3;
        }
        return a;
    }

    private static int verifySmallProducts() {
        int tested = 0;

        for (int n = 1; n <= 4; n++) {
            for (int m = 1; m <= 4; m++) {
                for (int x = 0; x < power3(n); x++) {
                    for (int y = 0; y < power3(m); y++) {
                        long[] a = decode(n, x);
                        long[] b = decode(m, y);

                        long[] actual = multiply(a, b);
                        long[] expected = gatherReference(a, b);
                        if (!Arrays.equals(actual, expected)) {
                            throw new AssertionError(
                                    "Convolution mismatch");
                        }

                        if (!Arrays.equals(actual,
                                multiply(b, a))) {
                            throw new AssertionError(
                                    "Not commutative");
                        }
                        tested++;
                    }
                }
            }
        }
        return tested;
    }

    public static void main(String[] args) {
        long[] a = {2, -1, 3};
        long[] b = {4, 0, 5};

        System.out.println("A = " + Arrays.toString(normalize(a)));
        System.out.println("B = " + Arrays.toString(normalize(b)));
        System.out.println("A + B = " + Arrays.toString(add(a, b)));
        System.out.println("A - B = " + Arrays.toString(subtract(a, b)));

        long[] product = multiply(a, b);
        System.out.println("A * B = " + Arrays.toString(product));
        System.out.println("first 3 coefficients = "
                + Arrays.toString(
                        firstCoefficientsOfProduct(a, b, 3)));
        System.out.println("degree(A * B) = " + degree(product));
        System.out.println("A(2) = " + evaluate(a, 2));
        System.out.println("B(2) = " + evaluate(b, 2));
        System.out.println("(A*B)(2) = " + evaluate(product, 2));

        System.out.println("linear [1,2] * [3,4] = "
                + Arrays.toString(
                        multiply(new long[] {1, 2},
                                 new long[] {3, 4})));
        System.out.println("zero * A = "
                + Arrays.toString(multiply(new long[0], a)));
        System.out.println("normalized [0,0,0] = "
                + Arrays.toString(
                        normalize(new long[] {0, 0, 0})));
        System.out.println("degree(0) = "
                + degree(new long[] {0}));

        long[] hugeA = {Long.MAX_VALUE, 1};
        long[] hugeB = {2, 3};
        try {
            multiply(hugeA, hugeB);
        } catch (ArithmeticException e) {
            System.out.println(
                    "long overflow detected: " + e.getMessage());
        }
        System.out.println("exact big = "
                + Arrays.toString(multiplyBig(hugeA, hugeB)));

        System.out.println(
                "tested small products = " + verifySmallProducts());
    }
}
~~~

**Lệnh biên dịch và chạy:**

~~~bash
javac PolynomialConvolutionDemo.java
java PolynomialConvolutionDemo
~~~

**Stdout chính xác:**

~~~text
A = [2, -1, 3]
B = [4, 0, 5]
A + B = [6, -1, 8]
A - B = [-2, -1, -2]
A * B = [8, -4, 22, -5, 15]
first 3 coefficients = [8, -4, 22]
degree(A * B) = 4
A(2) = 12
B(2) = 24
(A*B)(2) = 288
linear [1,2] * [3,4] = [3, 10, 8]
zero * A = [0]
normalized [0,0,0] = [0]
degree(0) = -1
long overflow detected: long overflow
exact big = [18446744073709551614, 27670116110564327423, 3]
tested small products = 14400
~~~

### Diễn giải những con số trong stdout

Tổng A+B dùng phép cộng hệ số cùng bậc, cho `[6,-1,8]`. Tích tạo năm hệ số `[8,-4,22,-5,15]` vì hai mảng đầu vào đều có độ dài 3. Bậc tích bằng 4.

Tích tại x=2 cho 288, đúng với A(2)·B(2)=12·24. Ví dụ `[1,2]*[3,4]` trả `[3,10,8]`, cho thấy kết quả không phải tích từng phần tử.

Mảng `new long[0]` được chuẩn hóa thành `[0]`; nhân với A vẫn cho `[0]`. Hàm `degree` trả −1 cho đa thức không như đã quy ước.

Với `hugeA=[Long.MAX_VALUE,1]` và `hugeB=[2,3]`, bản `long` ném `ArithmeticException` khi phép nhân hệ số vượt giới hạn. Bản `BigInteger` cho kết quả chính xác, không bị modulo 2^64 ngầm:

~~~text
c[0] = 2*9223372036854775807
     = 18446744073709551614

c[1] = 3*9223372036854775807 + 2
     = 27670116110564327423

c[2] = 3
~~~

Số 14.400 bằng bình phương số lượng dãy hệ số độ dài 1..4 trên alphabet ba giá trị:

~~~text
countOfArrays = 3^1 + 3^2 + 3^3 + 3^4
              = 3 + 9 + 27 + 81
              = 120

countOfPairs = 120 * 120 = 14400
~~~

Mã so kết quả scatter/gather và cả A*B=B*A; nếu không khớp, nó ném AssertionError trước khi in dòng cuối.

### Điểm cần biết về xử lý tràn số

Bản `long` dùng Math.multiplyExact và Math.addExact, nên có thể ném lỗi nếu **một kết quả trung gian** không vừa long, ngay cả khi sau đó có triệt tiêu khiến hệ số cuối vừa miền. Đây là lựa chọn **phát hiện rủi ro và fail-fast**, không phải thuật toán dùng số nguyên tùy ý. Nếu cần xử lý những đa thức có hệ số lớn/triệt tiêu mạnh một cách chính xác, dùng BigInteger ngay từ đầu cho các phép nhân và tích lũy.

Nếu cần kết quả theo modulo M, thực hiện phép cộng/nhân modulo một cách kiểm soát; không dựa vào overflow của long để thay cho toán học modulo M, trừ khi chứng minh đầy đủ các giả định và cách biểu diễn số của thuật toán cụ thể.

## 10. Cắt sớm: chỉ tính những hệ số thấp nhất

Không phải bài nào cũng cần toàn bộ tích n+m−1 hệ số. Một số bài chỉ cần hệ số tới bậc K−1, ví dụ tính:

~~~text
(A(x)*B(x)) modulo x^K
~~~

Điều này có nghĩa là **giữ các hệ số của x^0,...,x^(K−1)** và bỏ các bậc cao hơn. Không phải phép lấy số dư của từng hệ số theo một số nguyên K.

Với tích mẫu:

~~~text
A*B = [8,-4,22,-5,15]

K=3 -> [8,-4,22]
K=2 -> [8,-4]
K=0 -> []  (khong co he so nao duoc yeu cau)
~~~

Trong `firstCoefficientsOfProduct`, chỉ cần cộng các cặp (i,j) thỏa **i+j<K**. Vì thế có thể bỏ phần vòng lặp j ở những bậc cao, tránh tính toàn bộ rồi cắt.

~~~text
firstCoefficients(A,B,K):
    c = zeros(K)

    for i while i < n and i < K:
        for j while j < m and i+j < K:
            c[i+j] += a[i]*b[j]

    return c
~~~

API này trả **dãy k hệ số đầu có độ dài cố định K**. Nó có thể kết thúc bằng các số 0, khác với `multiply` trả đa thức đã chuẩn hóa.

### Giới hạn độ phức tạp

Số cặp được xét không vượt min(n,K)·min(m,K), và còn ít hơn nếu nhiều cặp có i+j≥K. Trường hợp n,m≥K, số cặp đúng bằng K(K+1)/2, nên cận là O(K²). Bộ nhớ đầu ra là O(K).

Nếu K lớn hơn độ dài tích đầy đủ, các hệ số chưa tồn tại được coi bằng 0 để điền đủ chiều dài K. Đây là **zero padding**, không phải sinh thêm hạng tử toán học có đóng góp khác 0.

## 11. Tích chập tuyến tính và tích chập vòng không giống nhau

Phép nhân đa thức trực tiếp ở bài này tạo **linear convolution** với các chỉ số từ 0 tới n+m−2. Một bài khác có thể yêu cầu **circular convolution** với độ dài chu kỳ L; khi đó những hệ số vượt L−1 được **quấn vòng** về chỉ số modulo L.

Ví dụ:

~~~text
a = [1,2]
b = [3,4]

Linear convolution = [3,10,8]

Circular convolution length 2:
c[0] = linear[0] + linear[2] = 3+8 = 11
c[1] = linear[1]             = 10

Result = [11,10]
~~~

Tích chập vòng theo chu kỳ L tương ứng với giảm các số mũ theo quan hệ x^L=1, tức nhân đa thức **modulo x^L−1** trong ngữ cảnh hệ số thích hợp. Nó không giống **cắt các bậc từ L trở lên**:

~~~text
Linear prefix length 2 : [3,10]
Circular length 2      : [11,10]
~~~

Hai kết quả khác nhau vì circular convolution cộng đóng góp ở bậc 2 quay về bậc 0.

### Zero-padding và FFT

Khi tính linear convolution bằng FFT, thường zero-pad tới chiều dài biến đổi **ít nhất n+m−1** để tránh hiện tượng quấn vòng vào miền kết quả. Nếu dùng chiều dài biến đổi quá ngắn, kết quả có thể thành circular convolution hoặc bị aliasing, không còn bằng nhân đa thức tuyến tính mong muốn.

Bản nhân trực tiếp trong bài không cần zero-padding theo kích thước FFT; nó cấp phát thẳng c dài n+m−1.

### Cross-correlation là phép toán khác

**Cross-correlation** so độ giống nhau của hai dãy khi một dãy bị dịch chuyển; trong những quy ước thường gặp, một dãy được đảo chiều trước khi đưa về công thức convolution. Vì vậy đừng gọi tùy ý phép nhân từng phần tử, tích chập tuyến tính và tương quan chéo là một thao tác. Khi gặp đề xử lý tín hiệu, cần đọc rõ **công thức và chiều dịch** để tránh sai dấu/chỉ số.

## 12. Dense và sparse: chọn cách biểu diễn phù hợp

Các mảng `long[]` dùng ở trên là **dense representation**: có một vị trí cho mọi bậc từ 0 tới d, kể cả hệ số bằng 0 ở giữa.

Ví dụ:

~~~text
P(x) = 7 + 0*x + 0*x^2 + 0*x^3 + 5*x^4

Dense coefficients:
[7,0,0,0,5]

Sparse terms:
(0,7), (4,5)
~~~

### Dense

**Ưu điểm:** truy cập a[i] O(1), dễ cộng và nhân bằng vòng lặp, bộ nhớ liên tục, thường chạy nhanh khi đa thức tương đối dày đặc.

**Nhược điểm:** nếu bậc rất lớn nhưng chỉ vài hệ số khác 0, có thể tốn nhiều bộ nhớ và nhân vô ích với số 0.

### Sparse

Biểu diễn thành các cặp `(bậc, hệ số)` khác 0, có thể lưu trong map hoặc danh sách đã sắp thứ tự.

Khi nhân hai đa thức có tA và tB hạng tử khác 0:

~~~text
for (degreeA, coeffA) in nonzeroTerms(A):
    for (degreeB, coeffB) in nonzeroTerms(B):
        result[degreeA+degreeB] += coeffA*coeffB
~~~

Số cặp thực sự nhân là tA·tB; chi phí truy cập/cộng dồn map còn phụ thuộc cấu trúc dữ liệu (hash map kỳ vọng O(1), tree map O(log t) mỗi thao tác).

Phải loại các hệ số trở thành 0 do triệt tiêu sau khi gộp, để biểu diễn sparse thực sự chỉ lưu hạng tử khác 0.

### Chọn theo yêu cầu

- Đa thức bậc vừa, nhiều hệ số khác 0: dùng dense.
- Đa thức bậc rất cao nhưng thưa: sparse thường tiết kiệm hơn.
- Bài cho dãy hệ số trực tiếp: dense thường tự nhiên.
- Bài chỉ yêu cầu vài hệ số mục tiêu: xem xét gather hoặc cắt sớm.
- Bài cực lớn cần mọi hệ số: xem xét nhân nhanh, không tự dùng sparse nếu kết quả dày đặc.

## 13. Phép toán modulo, số thực và độ chính xác

### Hệ số số nguyên tùy ý

Với `BigInteger`, các phép cộng/nhân số nguyên có kết quả chính xác và không tràn theo giới hạn 64-bit. Tuy nhiên một phép nhân hai BigInteger rất lớn không phải O(1) như một phép nhân long: chi phí còn phụ thuộc số chữ số của các hệ số. Vì thế thời gian O(nm) chỉ đếm số **cặp hệ số**; nếu hệ số là số lớn, cần nhân chi phí số học nhiều chữ số.

### Hệ số theo modulo M

Nếu đề yêu cầu tất cả hệ số theo modulo M (M>0), phép toán trên hệ số là:

~~~text
c[k] = SUM_{i+j=k} a[i]*b[j] mod M
~~~

Để tránh overflow, dùng phép nhân modulo an toàn với miền M được chọn, hoặc BigInteger/thuật toán chuyên biệt. Không được chỉ viết `long term=a[i]*b[j] % M` mà không chứng minh tích `a[i]*b[j]` vừa `long`.

Chú ý số âm trong Java: toán tử `%` giữ dấu của toán hạng trái, nên để đưa về `[0,M−1]` cần chuẩn hóa số dư (ví dụ `Math.floorMod(value,M)` khi value đã nằm trong long hợp lệ). Vẫn phải kiểm chi phí và overflow của phép cộng modulo.

### Hệ số số thực

Dùng `double` cho hệ số thực có thể tích chập trực tiếp như trên, nhưng kết quả là xấp xỉ:

- Thứ tự cộng có thể làm sai số làm tròn khác nhau.
- Không nên dùng so sánh `==` cho mọi kết quả mong đợi là số thực.
- Dùng sai số tuyệt đối/tương đối tùy miền giá trị.
- Với độ dài lớn, FFT có thể nhanh hơn nhưng thêm sai số số học.
- Nếu muốn kết quả nguyên chính xác, đừng mặc định FFT double luôn khôi phục mọi hệ số mà không có phân tích ràng buộc.

## 14. Các tính chất đại số dùng để kiểm thử

Trên hệ số nguyên hoặc một vành giao hoán có đơn vị, cộng và nhân đa thức thỏa:

~~~text
A+B = B+A                (giao hoan phep cong)
A*B = B*A                (giao hoan phep nhan)
(A+B)+C = A+(B+C)        (ket hop phep cong)
(A*B)*C = A*(B*C)        (ket hop phep nhan)
A*(B+C) = A*B + A*C      (phan phoi)
A+0 = A
A*1 = A
A*0 = 0
~~~

Những tính chất này là **oracle định tính** rất hữu ích khi không có kết quả đã tính sẵn, dù không thay thế hoàn toàn so với một thuật toán độc lập.

### Đánh giá đa thức tại một điểm

Với x=t:

~~~text
(A+B)(t) = A(t) + B(t)
(A*B)(t) = A(t) * B(t)
~~~

Tính P(t) hiệu quả bằng **Horner**:

~~~text
value = 0
for i from highest degree down to 0:
    value = value*t + a[i]
~~~

Horner dùng O(n) phép toán và O(1) bộ nhớ phụ. Trên bài mẫu, A(2)=12, B(2)=24, (A*B)(2)=288. Đây là một phép đối chiếu quan trọng nhưng **không đủ một mình để chứng minh hai đa thức bằng nhau**: hai đa thức khác nhau vẫn có thể cùng giá trị tại một vài điểm.

### Không giả định distributivity của số học tràn

Khi dùng `Math.addExact` và `Math.multiplyExact`, một trong hai cách đặt ngoặc có thể ném overflow ở trung gian mặc dù giá trị toán học cuối cùng vừa long. Vì thế các kiểm thử đại số với `long` cần chọn hệ số/điểm nhỏ hoặc dùng BigInteger để không có sai khác do giới hạn biểu diễn.

## 15. Kiểm thử chương trình bằng oracle độc lập

### Một tập ca cố định

| A | B | A+B | A*B |
| --- | --- | --- | --- |
| [2,−1,3] | [4,0,5] | [6,−1,8] | [8,−4,22,−5,15] |
| [1,2] | [3,4] | [4,6] | [3,10,8] |
| [0] | [5,7] | [5,7] | [0] |
| [] | [3] | [3] | [0] |
| [1,−1] | [−1,1] | [0] | [−1,2,−1] |
| [5] | [7] | [12] | [35] |
| [0,0,3] | [0,2] | [0,2,3] | [0,0,0,6] |

Đây là các ca kiểm cả hệ số âm, đa thức 0, hệ số 0 ở giữa, bậc tăng và triệt tiêu hệ số cao.

### Oracle theo hệ số đầu ra

Một cách kiểm độc lập:

~~~text
for k=0..n+m-2:
    sum=0
    for i=max(0,k-(m-1))..min(n-1,k):
        sum += a[i]*b[k-i]
    expected[k]=sum
~~~

Nó sử dụng **gather**, trong khi thuật toán thực tế sử dụng **scatter**. Nếu hai cách độc lập khớp trên nhiều test, khả năng nhầm vị trí cộng dồn giảm đáng kể.

### Kiểm vét cạn trên đa thức rất nhỏ

Chọn các hệ số từ tập {−1,0,1}, độ dài từ 1 đến 4.

Số mảng có thể có:

~~~text
3^1+3^2+3^3+3^4 = 120
~~~

Mỗi mảng được ghép với mọi mảng còn lại, cho:

~~~text
120 * 120 = 14400 cap
~~~

Java demo tính tích bằng scatter và bằng gather cho từng cặp, so mảng chuẩn hóa và còn kiểm **A*B=B*A**. Vì hệ số nhỏ, các phép tính đều vừa long. Mã in `tested small products = 14400` nếu tất cả ca vượt qua.

### Property-based tests

1. `normalize` không thay đổi giá trị đa thức.
2. `normalize(normalize(A))` giống `normalize(A)` (tính idempotent).
3. `add(A,B)` và `multiply(A,B)` không sửa A hoặc B.
4. `A+B=B+A`, `A*B=B*A` với miền hệ số an toàn.
5. `A*(B+C)=A*B+A*C` khi không tràn.
6. `A*0=0`, `A*1=A`, `A+0=A`.
7. Bậc của tích hai đa thức nguyên khác 0 bằng tổng bậc.
8. Độ dài biểu diễn chuẩn hóa không có số 0 ở cuối trừ khi toàn bộ là `[0]`.
9. Hệ số c[k] khớp tổng trên tất cả cặp i+j=k.
10. Tính tại x=t: `evaluate(multiply(A,B),t)` bằng tích `evaluate(A,t)*evaluate(B,t)` khi không tràn.
11. `firstCoefficientsOfProduct(A,B,K)` khớp K giá trị đầu của tích đã zero-pad.
12. Tích `long` và `BigInteger` khớp nếu mọi trung gian long vừa miền.
13. Khi có hệ số lớn dẫn tới overflow, bản `long` phải ném lỗi chứ không âm thầm sai.
14. Với dữ liệu ít hơn hai hệ số, xử lý các cận K=0,K=1 và mảng rỗng.
15. Kết quả linear convolution có tối đa n+m−1 hệ số trước chuẩn hóa, không tự quấn vòng.

## 16. Những lỗi triển khai thường gặp

| Lỗi | Hậu quả | Cách sửa |
| --- | --- | --- |
| Nhầm a[i] với hệ số x^(n−1−i) | Đảo thứ tự bậc | Ghi rõ ascending powers |
| Xóa 0 ở giữa mảng | Các hệ số phía sau dịch bậc | Chỉ trim trailing zeros |
| Cộng chéo bậc khác nhau | Sai A+B | Cộng a[k]+b[k] |
| Nhân a[i]b[j] vào c[i] hoặc c[j] | Sai bậc tích | Dùng c[i+j] |
| Cấp kết quả chỉ n phần tử | Thiếu bậc lớn | Cấp n+m−1 |
| Khởi tạo c với giá trị rác | Tích bị cộng thêm dữ liệu cũ | Zero-fill |
| Dùng phép gán c[i+j]=term | Ghi đè những đóng góp trước | Phải dùng `+=` |
| Nhầm convolution với pointwise product | Sai độ dài và giá trị | Dùng tổng i+j=k |
| Nhầm linear với circular convolution | Hệ số cao quấn về đầu | Chỉ wrap khi đề yêu cầu |
| Lấy prefix nhưng vẫn ghi c[i+j] ngoài K | Tràn chỉ số | Chỉ duyệt i+j<K |
| Không xử lý đa thức không | Bậc và độ dài sai | Chuẩn hóa `[0]` |
| Quy ước mảng rỗng không nhất quán | Crash hoặc kết quả khác nhau | Công bố [] là đầu vào 0 |
| Tưởng deg(A+B)=max luôn | Sai khi triệt tiêu | Dùng ≤ |
| Tưởng deg(A*B) luôn cộng bậc | Sai với 0 hoặc vành có ước 0 | Nêu giả định |
| Dùng `int` để tích các hệ số lớn | Overflow | `long` checked hoặc BigInteger |
| Dùng `long` nhưng không kiểm tràn | Sai âm thầm | Math.multiplyExact/addExact |
| Nghĩ long checked luôn nhận mọi kết quả vừa long | Trung gian vẫn có thể tràn | BigInteger nếu cần tính chính xác |
| Cộng độ dài n+m bằng int khi rất lớn | Tràn khi cấp mảng | Tính kích thước bằng long |
| Chia modulo khi tích đã overflow | Số dư sai | Modular multiplication an toàn |
| Dùng `%` cho số âm rồi mặc định không âm | Hệ số âm không chuẩn hóa | floorMod/chuẩn hóa |
| So double bằng `==` tuyệt đối | Test sai vì rounding | Sai số tuyệt đối/tương đối |
| Xây BigInteger từ kết quả long đã tràn | Không khôi phục được giá trị đúng | Tính BigInteger từ đầu |
| Tái chạy nhân O(nm) cho nhiều query giống nhau | Tốn CPU | Cache kết quả khi phù hợp |
| Dùng FFT cho bài rất nhỏ | Tăng độ phức tạp code | Ưu tiên vòng lặp trực tiếp |
| Không kiểm tên tệp/class Java | Không biên dịch được | Tên `PolynomialConvolutionDemo.java` |

## 17. Khi nào dùng thuật toán nhân nhanh hơn?

Nhân trực tiếp dễ hiểu và đáng tin cậy, nhưng O(nm) có thể chậm khi cả hai đa thức dài.

Các lựa chọn chuyên sâu:

- **Karatsuba:** chia đa thức thành phần thấp/cao, giảm số phép nhân con; độ phức tạp tiệm cận khoảng O(n^log2(3)) cho kích thước cân bằng và những giả định thường gặp.
- **FFT:** biến nhân đa thức thành nhân điểm trên các giá trị biến đổi, thường O(N log N) cho hai dãy với N là độ dài biến đổi đủ lớn. Với số thực, phải xét sai số làm tròn.
- **NTT:** biến đổi số học trên modulo đặc biệt, cho phép nhiều bài nhân modulo thực hiện chính xác, nhưng cần modulus/root of unity và giới hạn chiều dài phù hợp.
- **Sparse convolution:** duyệt các cặp hệ số khác 0 nếu chúng hiếm; hiệu quả phụ thuộc số hạng và cấu trúc lưu.

Nếu một đa thức chỉ có vài hệ số khác 0 hoặc rất ngắn, nhân trực tiếp có thể vẫn tối ưu về thực tế. Chọn kỹ thuật dựa trên n,m, miền hệ số, yêu cầu chính xác, RAM và thời gian triển khai.

### Kỹ thuật không thay đổi định nghĩa

Dù dùng schoolbook, FFT hay NTT, phép nhân đa thức tuyến tính vẫn có:

~~~text
c[k] = SUM_{i+j=k} a[i]*b[j]
~~~

Các kỹ thuật khác nhau chỉ thay **cách tính nhanh và chính xác hệ số**, không thay kết quả toán học mà đề yêu cầu.

## 18. Bài tập thực hành

1. Viết dạng mảng hệ số của P(x)=7−3x+2x³ theo bậc tăng.
2. Giải thích vì sao hệ số x² bằng 0 vẫn phải giữ vị trí trong mảng dense.
3. Chuẩn hóa `[4,0,2,0,0]`, `[0,0,0]` và `[]`.
4. Tính A+B với A=[2,−1,3], B=[4,0,5].
5. Tính A−B với cùng dữ liệu.
6. Nhân bằng tay A*B và điền bảng i,j→c[i+j].
7. Dùng công thức gather tính c[2] của tích mẫu, kiểm c[2]=22.
8. Tính convolution tuyến tính của [1,2] và [3,4].
9. Phân biệt convolution tuyến tính với nhân từng phần tử.
10. Chứng minh kết quả nhân đầy đủ cần n+m−1 hệ số trước chuẩn hóa.
11. Chứng minh nhân trực tiếp dùng n·m cặp hệ số.
12. Viết phép cộng/trừ với quy ước đa thức không `[0]`.
13. Viết phép nhân xử lý mảng đầu vào rỗng như đa thức không.
14. Tính bậc của A+B khi hệ số đầu triệt tiêu.
15. Chứng minh deg(A*B)=deg A+deg B cho hai đa thức nguyên khác 0.
16. Tìm phản ví dụ của định lý bậc khi hệ số lấy modulo 6.
17. Cài hàm lấy K hệ số thấp nhất của tích và kiểm K=0,1,3.
18. So linear prefix length2 với circular convolution length2 trên [1,2] và [3,4].
19. Dùng Horner kiểm (A*B)(2)=A(2)B(2)=288.
20. Cài oracle gather độc lập và so với scatter cho 1000 cặp ngẫu nhiên nhỏ.
21. Sinh toàn bộ 14.400 cặp đa thức hệ số {−1,0,1} độ dài 1..4, so kết quả.
22. Thử hệ số Long.MAX_VALUE và quan sát Math.multiplyExact ném lỗi.
23. Thay bộ tích lũy long bằng BigInteger, kiểm hệ số lớn.
24. Giải thích vì sao có thể overflow ở trung gian dù tổng hệ số cuối vẫn vừa long.
25. Viết phiên bản nhân số học modulo M với phép nhân modular an toàn.
26. Cài sparse convolution bằng Map<Integer,BigInteger>.
27. Đo số phép nhân khi đa thức rất thưa so với dense.
28. Với n=m=50000, ước lượng số cặp nhân và lý do cần thuật toán nhanh.
29. Tìm một bài đếm cách có đa thức sinh với hệ số là số cách; diễn giải phép nhân.
30. Viết property test tính giao hoán/phân phối trên đa thức nhỏ.
31. Thực hiện multiplication rồi trim trailing zeros; giải thích khi nào số 0 ở cuối xuất hiện.
32. Mô tả điều kiện zero-padding của FFT để nhận linear convolution đúng.
33. Giải thích tại sao vòng `for (j) c[i+j]=term` (thiếu cộng dồn) là sai.
34. Thiết kế benchmark chọn giữa schoolbook và FFT/NTT mà không thay đổi độ chính xác yêu cầu.

## 19. Checklist áp dụng

- Dãy hệ số được lưu theo **bậc tăng hay giảm**?
- Hệ số 0 **ở giữa** có được giữ nguyên không?
- Đã xử lý `[0]`, mảng rỗng và trailing zeros nhất quán chưa?
- Với cộng/trừ, có căn theo **cùng bậc** không?
- Với nhân, có cộng mỗi a[i]b[j] vào **c[i+j]** không?
- Đã cấp đủ **n+m−1** hệ số cho tích đầy đủ chưa?
- Đã dùng `+=` chứ không ghi đè các đóng góp trước chưa?
- Đề cần **linear convolution**, circular convolution hay chỉ prefix K?
- Có kiểm tràn số và chọn `long`, `BigInteger` hoặc số học modulo phù hợp không?
- Nếu dùng `double`, tiêu chí sai số đã rõ chưa?
- Có tính đúng bậc sau khi hệ số đầu triệt tiêu không?
- Nếu dùng dense, số hệ số 0 và độ dài có làm nhân tốn thời gian vô ích không?
- Nếu kết quả rất lớn, đã xem xét FFT/NTT hoặc sparse chưa?
- Có thử ví dụ hệ số âm, hệ số 0 giữa, đa thức hằng, đa thức không và ranh giới K=0 chưa?
- Có đối chiếu với một oracle gather hoặc kiểm Horner tại vài điểm không?

## 20. Tổng kết

**Cộng đa thức** thực hiện theo từng bậc: c[k]=a[k]+b[k] và mất O(n+m) thời gian. **Nhân đa thức trực tiếp** dùng quy tắc phân phối: mỗi cặp hệ số a[i] và b[j] đóng góp a[i]b[j] vào c[i+j]. Gom lại theo bậc k ta được:

~~~text
c[k] = SUM_{i+j=k} a[i]*b[j]
~~~

Đó là **tích chập tuyến tính rời rạc**, không phải nhân từng phần tử và không phải tích chập vòng. Với hai dãy độ dài n,m, phép nhân schoolbook xét n·m cặp, có **O(nm) thời gian** và **O(n+m) bộ nhớ đầu ra**. Ví dụ A=[2,−1,3], B=[4,0,5] cho tích `[8,−4,22,−5,15]` và (A*B)(2)=288.

Khi viết Java, hãy chốt quy ước **ascending coefficients**, chuẩn hóa đa thức không, giữ các số 0 ở giữa, cấp phát đúng n+m−1 và xử lý overflow. Nếu chỉ cần K hệ số thấp, giới hạn các cặp i+j<K. Nếu dữ liệu thưa, rất lớn hoặc cần xử lý modulo, lựa chọn sparse, BigInteger, FFT/NTT sẽ phụ thuộc yêu cầu cụ thể. Dù dùng cách tính nào, công thức tích chập theo **i+j=k** vẫn là nền tảng để hiểu, chứng minh và kiểm thử phép nhân đa thức.
