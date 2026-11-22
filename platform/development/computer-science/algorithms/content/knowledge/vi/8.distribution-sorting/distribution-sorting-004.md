# Radix sort từ chữ số thấp đến cao (LSD Radix Sort)

## 1. Bản chất của sắp xếp phân phối theo chữ số

**Radix sort** thuộc nhóm thuật toán **sắp xếp phân phối**: thay vì chỉ so sánh từng cặp khóa, thuật toán khai thác cấu trúc của khóa (chữ số, byte hoặc ký tự) để phân phối các phần tử vào nhóm. Với **LSD radix sort (Least Significant Digit first)**, ta xử lý các vị trí từ **chữ số thấp nhất** tới **chữ số cao nhất**: hàng đơn vị, hàng chục, hàng trăm... nếu chọn cơ số 10.

Mỗi lượt sắp xếp các phần tử theo **một chữ số**. Điều kiện quyết định sự đúng đắn là: **mỗi lượt phân phối phải ổn định (stable)**, nghĩa là các phần tử có cùng chữ số của lượt đó giữ nguyên thứ tự tương đối từ lượt trước. Nhờ vậy, khi lên chữ số cao hơn, thứ tự đã thiết lập ở các chữ số thấp không mất đi.

Đây là khác biệt quan trọng giữa LSD và việc “sắp xếp theo hàng trăm trước, rồi sắp theo hàng đơn vị”: xử lý chữ số cao trước theo một lượt sắp toàn dãy có thể phá hủy những kết quả trước. LSD thực hiện theo thứ tự thấp → cao và **bảo toàn các lượt trước** bằng stable sort.

Radix sort không làm mất phần tử, không tự loại trùng và không cần mọi phần tử có cùng số chữ số. Các chữ số còn thiếu ở phía trái được hiểu bằng **0 dẫn đầu**: số 7 có thể xem là 007 khi số lớn nhất có ba chữ số.

## 2. Cơ số và chữ số của khóa

Giả sử dãy có n số nguyên **không âm**. Chọn cơ số b=10; khóa nguyên x có dạng:

\[
x=\sum_{k=0}^{d-1}x_k b^k,\qquad 0\le x_k<b.
\]

Chữ số \(x_0\) là chữ số thấp nhất. Với b=10, chữ số ở vị trí k (đếm từ 0) được tính:

\[
digit_k(x)=\left\lfloor\frac{x}{10^k}\right\rfloor\bmod10.
\]

Trong Java, với x không âm, có thể lấy exp=1,10,100,... và viết phép chia nguyên **(x / exp) % 10**. Mỗi chữ số nằm trong khoảng 0..9.

Số lượt d là số chữ số cần để biểu diễn **khóa lớn nhất** theo cơ số đã chọn. Khi khóa lớn nhất chỉ là 0, có thể bỏ qua mọi lượt vì dãy toàn các số 0 đã được sắp đúng.

**Không sử dụng công thức tách chữ số này một cách ngây thơ cho int âm:** phép chia và lấy phần dư số âm trong Java không tạo ra một chữ số 0..9 theo cùng cách. Nếu cần sắp cả số âm, phải có một ánh xạ khóa bảo toàn thứ tự hoặc xử lý phần dấu một cách có chứng minh.

## 3. Ví dụ qua từng lượt

Đầu vào:

~~~text
[170, 45, 75, 90, 802, 24, 2, 66, 45, 0]
~~~

Số lớn nhất 802 có ba chữ số, nên ta chạy ba lượt:

| Lượt | Chữ số | Thứ tự sau khi phân phối ổn định |
|---|---|---|
| Ban đầu | Chưa xử lý | [170, 45, 75, 90, 802, 24, 2, 66, 45, 0] |
| 1 | Hàng đơn vị, exp=1 | [170, 90, 0, 802, 2, 24, 45, 75, 45, 66] |
| 2 | Hàng chục, exp=10 | [0, 802, 2, 24, 45, 45, 66, 170, 75, 90] |
| 3 | Hàng trăm, exp=100 | [0, 2, 24, 45, 45, 66, 75, 90, 170, 802] |

Phân tích một vài nhóm:
- Sau lượt 1, 170, 90 và 0 cùng có chữ số đơn vị 0, nên xuất hiện theo đúng thứ tự cũ 170 → 90 → 0.
- Ở lượt 2, các số 0, 802 và 2 có chữ số hàng chục bằng 0 và giữ thứ tự của lượt 1. Hai số 170, 75 cùng có hàng chục bằng 7; chúng giữ thứ tự 170 → 75 đã tạo theo chữ số đơn vị.
- Ở lượt 3, những số nhỏ hơn 100 có hàng trăm bằng 0, 170 có hàng trăm 1, 802 có hàng trăm 8. Những chữ số thấp đã được giải quyết ở lượt trước nên dãy cuối tăng dần.

Hai bản sao số 45 vẫn tồn tại; radix sort không phải thuật toán loại trùng. Nếu đây là các **bản ghi** có cùng khóa số nhưng thông tin khác nhau, tính ổn định còn yêu cầu bảo toàn thứ tự tương đối của chính các bản ghi ấy.

## 4. Một lượt ổn định bằng Counting Sort

Với cơ số b=10, một lượt LSD có thể dùng **counting sort ổn định trên chữ số hiện tại**, không phải counting sort theo toàn bộ giá trị x.

Các bước của một lượt:
1. Tạo count[0..9] ban đầu toàn 0. Với mỗi phần tử x, tính chữ số d=(x/exp)%10 và tăng count[d].
2. Tính tổng tích lũy từ trái sang phải: count[d] += count[d−1] với d=1..9. Sau bước này count[d] là **số phần tử có chữ số ≤ d**.
3. Duyệt **từ phải sang trái** của dãy hiện tại. Với phần tử x thuộc nhóm chữ số d, ghi vào output[--count[d]], rồi chuyển sang phần tử trước.
4. Chép output về dãy nguồn để làm đầu vào cho lượt chữ số tiếp theo.

### Tại sao phải duyệt từ phải sang trái?

Giả sử trong dãy trước lượt có hai bản ghi A rồi B có cùng chữ số d. Vì count[d] ban đầu chỉ vị trí **ngay sau cuối nhóm**, khi duyệt ngược, B chiếm vị trí cuối trước, rồi A được đặt ở vị trí trước B. Do đó **A vẫn đứng trước B** ở kết quả.

Nếu duyệt xuôi nhưng vẫn dùng biểu thức output[--count[d]], A sẽ chiếm vị trí cuối nhóm trước, B đứng trước A, phá tính ổn định. Có thể viết counting sort ổn định duyệt xuôi bằng **vị trí bắt đầu nhóm và tăng dần**, nhưng không được trộn lẫn hai công thức.

Bất biến của một lượt: output tăng theo chữ số được xét, và giữa các phần tử có chữ số bằng nhau, output giữ nguyên thứ tự của đầu vào lượt đó.

Chi phí một lượt: đếm n phần tử O(n), tính tổng tích lũy O(b), phân phối n phần tử O(n), sao chép n phần tử O(n). Tổng **\(\Theta(n+b)\)** thời gian, bộ nhớ phụ trợ **\(\Theta(n+b)\)** gồm output và count.

## 5. Chứng minh LSD Radix Sort bằng quy nạp

Gọi \(D_k(x)=x\bmod b^k\) là phần khóa gồm k chữ số thấp nhất. Ta chứng minh:

> Sau khi xử lý k chữ số thấp nhất bằng k lượt **ổn định**, dãy tăng theo \(D_k(x)\).

**Cơ sở k=1:** counting sort theo hàng đơn vị tạo thứ tự tăng theo \(x_0=D_1(x)\).

**Bước quy nạp:** giả sử sau k lượt, dãy tăng theo \(D_k(x)\). Ở lượt k+1 ta phân phối ổn định theo chữ số \(x_k\):
- Nếu hai phần tử có \(x_k\) khác nhau, chữ số này quyết định thứ tự theo k+1 chữ số thấp.
- Nếu chúng có cùng \(x_k\), tính ổn định giữ thứ tự theo k chữ số thấp đã thiết lập ở những lượt trước.

Vì vậy sau lượt k+1, dãy tăng theo \(D_{k+1}(x)\). Sau d lượt, mọi khóa đều được biểu diễn bằng d chữ số (có thể có 0 dẫn đầu), nên \(D_d(x)=x\), và dãy tăng theo **toàn bộ khóa**.

Lập luận nêu đúng lý do stable sort là bắt buộc. Một thuật toán phân phối không ổn định ở lượt chữ số cao có thể đảo các phần tử cùng chữ số cao, xóa đi thứ tự chữ số thấp đã đúng.

### Phân biệt LSD và MSD

- **LSD:** sắp toàn dãy theo chữ số thấp, rồi cao dần; tính ổn định của mỗi lượt là cơ sở chứng minh.
- **MSD (Most Significant Digit first):** xét chữ số cao trước, thường chia dữ liệu thành các nhóm rồi tiếp tục xử lý những chữ số thấp **bên trong mỗi nhóm**. Chiến lược phân nhóm/đệ quy không giống LSD.

## 6. Cài đặt Java 17+ hoàn chỉnh

Chương trình dưới đây dùng counting sort ổn định cơ số 10. Có hai giao diện:
- **sortNonNegative** nhận số nguyên không âm, báo lỗi nếu có số âm.
- **sortSigned** nhận mọi int, kể cả Integer.MIN_VALUE. Để xử lý dấu chính xác, ánh xạ x sang khóa không âm \(key(x)=(long)x-(long)Integer.MIN_VALUE\). Khóa ở miền [0,4294967295] và **bảo toàn thứ tự**: x<y khi và chỉ khi key(x)<key(y).

Hàm lõi tính chữ số từ khóa kiểu long, nhưng **sao chép giá trị int gốc** qua các lượt. Biến exp cũng dùng long để tránh tràn số trong phạm vi dữ liệu int.

Lưu thành tệp **LsdRadixSortDemo.java**:

~~~java
import java.util.Arrays;

public final class LsdRadixSortDemo {
    private static final int BASE = 10;

    private LsdRadixSortDemo() {
    }

    public static void sortNonNegative(int[] values, boolean trace) {
        if (values == null) {
            throw new IllegalArgumentException("Array must not be null");
        }
        for (int x : values) {
            if (x < 0) {
                throw new IllegalArgumentException(
                        "Only nonnegative integers are supported");
            }
        }
        sortByShiftedKey(values, 0L, trace);
    }

    public static void sortSigned(int[] values, boolean trace) {
        if (values == null) {
            throw new IllegalArgumentException("Array must not be null");
        }
        sortByShiftedKey(values, (long) Integer.MIN_VALUE, trace);
    }

    private static void sortByShiftedKey(
            int[] values, long offset, boolean trace) {
        long maxKey = 0;
        for (int x : values) {
            long key = (long) x - offset;
            if (key > maxKey) {
                maxKey = key;
            }
        }

        int[] output = new int[values.length];

        // maxKey == 0: mọi khóa bằng 0, không cần thực hiện lượt.
        for (long exp = 1; maxKey / exp > 0; exp *= BASE) {
            int[] count = new int[BASE];

            // Đếm tần suất chữ số.
            for (int x : values) {
                long key = (long) x - offset;
                int digit = (int) ((key / exp) % BASE);
                count[digit]++;
            }

            // Vị trí kết thúc (1-based) của mỗi nhóm.
            for (int d = 1; d < BASE; d++) {
                count[d] += count[d - 1];
            }

            // Duyệt ngược để giữ thứ tự phần tử đồng chữ số.
            for (int i = values.length - 1; i >= 0; i--) {
                int x = values[i];
                long key = (long) x - offset;
                int digit = (int) ((key / exp) % BASE);
                output[--count[digit]] = x;
            }

            System.arraycopy(output, 0, values, 0, values.length);

            if (trace) {
                System.out.println(
                        "Buoc " + exp + ": " + Arrays.toString(values));
            }
        }
    }

    public static void main(String[] args) {
        int[] data = {170, 45, 75, 90, 802, 24, 2, 66, 45, 0};
        sortNonNegative(data, true);
        System.out.println("Ket qua: " + Arrays.toString(data));

        int[] signed = {
            3, -1, Integer.MIN_VALUE, 0, Integer.MAX_VALUE, -9
        };
        sortSigned(signed, false);
        System.out.println("Co dau: " + Arrays.toString(signed));

        int[] zeros = {0, 0, 0};
        sortNonNegative(zeros, false);
        System.out.println("Toan 0: " + Arrays.toString(zeros));

        try {
            sortNonNegative(new int[] {2, -1}, false);
        } catch (IllegalArgumentException ex) {
            System.out.println("Loi: " + ex.getMessage());
        }
    }
}
~~~

Lệnh biên dịch và chạy bằng JDK 17 trở lên:

~~~bash
javac LsdRadixSortDemo.java
java LsdRadixSortDemo
~~~

Stdout chính xác:

~~~text
Buoc 1: [170, 90, 0, 802, 2, 24, 45, 75, 45, 66]
Buoc 10: [0, 802, 2, 24, 45, 45, 66, 170, 75, 90]
Buoc 100: [0, 2, 24, 45, 45, 66, 75, 90, 170, 802]
Ket qua: [0, 2, 24, 45, 45, 66, 75, 90, 170, 802]
Co dau: [-2147483648, -9, -1, 0, 3, 2147483647]
Toan 0: [0, 0, 0]
Loi: Only nonnegative integers are supported
~~~

**Đọc kết quả:**
- Đối với dãy không âm, khóa lớn nhất 802 nên chương trình chạy exp=1,10,100 và dừng khi 802/1000=0.
- Dãy có dấu được chuyển sang khóa long không âm. Giá trị Integer.MIN_VALUE trở thành khóa 0, còn Integer.MAX_VALUE trở thành 4294967295; quy tắc này đặt mọi số âm trước 0 rồi số dương theo đúng thứ tự int.
- Dãy toàn 0 và dãy rỗng không cần lượt nào: maxKey ban đầu bằng 0 và thứ tự đã đúng.
- Phép kiểm tra số âm của sortNonNegative thực hiện **trước** khi sửa dãy. Nếu có số âm, hàm ném IllegalArgumentException với thông báo rõ.
- output được dùng lại qua các lượt; count được tạo lại ở mỗi lượt. Mỗi lượt ghi đúng n phần tử vào output rồi mới sao chép, không để lại phần tử cũ trong kết quả.

Đối với mảng **int**, hai số 45 trùng nhau không có thông tin để phân biệt danh tính. Nếu chuyển sang sắp xếp bản ghi có khóa số, phải chuyển **cả bản ghi** trong output và tính chữ số từ khóa của bản ghi; nhờ duyệt ngược, các bản ghi có cùng khóa giữ được thứ tự đầu vào.

## 7. Cẩn thận với số âm và các giá trị biên

Cách thông thường tách chữ số của số nguyên không âm sẽ sai với khóa âm. Không nên áp dụng Math.abs tùy tiện: Math.abs(Integer.MIN_VALUE) vẫn trả về một số âm do tràn kiểu int. Cũng không nên đảo ngược mọi bản ghi âm sau khi sắp độ lớn tuyệt đối mà không xét tác động lên tính ổn định.

Cách dịch miền trong chương trình có ba ưu điểm:
1. **Bảo toàn thứ tự:** trừ cùng hằng số trên kiểu long, nên x<y tương đương key(x)<key(y).
2. **Không tràn khi tạo khóa:** miền số nguyên int được biến thành khóa long trong [0,4294967295].
3. **Không cần quy tắc riêng ở mỗi lượt:** stable counting sort trên chữ số 0..9 hoạt động nhất quán cho cả hai loại dấu.

Một lựa chọn khác với cơ số 256 là làm việc trên bốn byte của int 32 bit, có xử lý byte dấu đúng (hoặc biến đổi khóa theo kiểu XOR với bit dấu rồi so theo quy tắc unsigned). **Không được** sắp bốn byte như khóa không dấu thông thường rồi giả định kết quả tự đúng cho số nguyên có dấu.

Nếu đối tượng cần sắp theo khóa String, khóa nhiều phần, số nguyên độ dài tùy ý hoặc số thực, phải định nghĩa ánh xạ chữ số hoặc ký tự và quy tắc thứ tự cụ thể. Radix sort không tự hiểu mọi kiểu dữ liệu.

## 8. Độ phức tạp

Gọi n là số phần tử, b là cơ số và d là số chữ số của khóa lớn nhất ở cơ số b. Một lượt stable counting sort tốn:
- O(n) để đếm.
- O(b) để tính cộng dồn.
- O(n) để phân phối và chép lại.

Với d lượt, cộng thêm O(n) tìm khóa lớn nhất:

\[
T(n,b,d)=O(n+d(n+b)).
\]

Với n≥1 và d≥1, có thể ghi **\(\Theta(d(n+b))\)** cho cài đặt sử dụng đúng d lượt counting sort, vì mỗi lượt thực hiện các phép quét n và b. Bộ nhớ phụ trợ **\(\Theta(n+b)\)**: output có n ô, count có b ô.

Khi b=10 cố định, thời gian **O(dn)** và bộ nhớ phụ trợ O(n). Với các khóa **int 32 bit** và phép dịch miền ở trên, d≤10, nên trong mô hình thao tác số nguyên máy độ rộng cố định, có thể coi thời gian **O(n)**. Điều đó không mở rộng tự động sang khóa có d chữ số tăng không bị chặn, chẳng hạn chuỗi hoặc số nguyên tùy ý.

Chặn dưới Ω(n log n) của sắp xếp **dựa hoàn toàn vào phép so sánh** không áp dụng trực tiếp cho radix sort: radix sort khai thác chữ số và phân phối vào các nhóm, sử dụng thông tin mạnh hơn phép so sánh hai khóa. Tuy nhiên nó cần thêm bộ nhớ và nhiều lượt đọc/ghi, nên không nhất thiết nhanh hơn một thuật toán so sánh trong mọi trường hợp thực tế.

Nếu chọn \(b=2^r\) cho khóa w bit, số lượt xấp xỉ \(\lceil w/r\rceil\). Tăng b có thể giảm lượt nhưng làm mảng count lớn hơn; cần cân nhắc bộ nhớ, cache và chi phí trích chữ số.

## 9. Khi nào nên dùng LSD radix sort?

Phù hợp khi:
- Có nhiều khóa số hoặc khóa gồm các vị trí chữ số/bản ghi cố định dễ trích xuất.
- Biết trước miền hoặc độ rộng khóa, có thể chọn cơ số hợp lý.
- Cần sắp ổn định các bản ghi mang khóa và chấp nhận bộ nhớ phụ O(n+b).
- Có đủ dữ liệu để chi phí nhiều lượt phân phối có ý nghĩa.

Cần cân nhắc thuật toán khác khi:
- Bộ nhớ bổ sung rất hạn chế.
- Khóa cần một Comparator phức tạp mà không có ánh xạ chữ số bảo toàn đúng thứ tự.
- n nhỏ và chi phí khởi tạo count/output qua nhiều lượt lớn hơn lợi ích.
- Khóa biến độ dài, chính sách sắp chữ/sắp dấu/ngôn ngữ chưa được xác định.

**LSD so với counting sort trực tiếp:** counting sort trực tiếp trên toàn giá trị cần một mảng đếm kích thước bằng **miền giá trị**, có thể quá lớn nếu khóa tới hàng tỷ. LSD chỉ đếm b chữ số mỗi lượt, đổi lại cần d lượt. Đây là đánh đổi giữa số nhóm và số lần phân phối.

## 10. Lỗi thường gặp

1. **Phân phối không ổn định:** lượt chữ số cao có thể đảo thứ tự đã đúng theo chữ số thấp, phá chứng minh LSD.
2. **Duyệt xuôi mà vẫn dùng output[--count[digit]]:** cấp vị trí từ cuối nhóm khiến các phần tử đồng chữ số bị đảo.
3. **Quên cộng dồn count:** tần suất thuần không phải vị trí cuối nhóm; các phần tử có thể ghi sai chỗ.
4. **Không sao chép output về dãy giữa các lượt:** lượt sau không nhìn thấy kết quả sắp của lượt trước.
5. **Không thêm các số 0 ở đầu khóa:** số 7 phải được hiểu có hàng chục/hàng trăm bằng 0 nếu dãy có số ba chữ số.
6. **Đếm thiếu số 0 hoặc số trùng:** kết quả phải giữ nguyên n phần tử, kể cả các bản sao số 0/45.
7. **Quên quy tắc cho số âm:** không thể coi dấu âm là chữ số thập phân thông thường. Dùng ánh xạ có chứng minh hoặc thuật toán xử lý dấu riêng.
8. **Dùng int cho exp khi có nguy cơ tràn:** cần long hoặc một điều kiện dừng tránh phép nhân vượt giới hạn.
9. **Chỉ tính không gian O(b):** còn output n phần tử, nên bộ nhớ phụ trợ O(n+b).
10. **Nhầm ổn định với loại trùng:** stable giữ thứ tự bản ghi đồng khóa, không xóa các bản ghi đó.
11. **Tuyên bố O(n) với mọi độ dài khóa:** số lượt d vẫn là tham số và có thể tăng theo dữ liệu.
12. **Lẫn LSD với MSD:** xử lý chữ số cao trước mà sắp toàn dãy ở các lượt sau là một thuật toán khác và không có cùng bất biến.

## 11. Kiểm thử

Nên thử:
- **Rỗng, một phần tử, toàn số 0:** không truy cập vị trí sai.
- **Dãy đã tăng, đã giảm, nhiều phần tử bằng nhau:** kết quả đúng và giữ đủ số lượng phần tử.
- **Độ dài chữ số khác nhau:** [2,24,802,0,170], kiểm tra chữ số 0 dẫn đầu.
- **Số nguyên có dấu:** Integer.MIN_VALUE, -9, -1, 0, 3, Integer.MAX_VALUE.
- **Sai phạm vi:** số âm đi vào sortNonNegative phải bị từ chối.
- **Ngẫu nhiên:** đối chiếu với Arrays.sort trên bản sao của mảng đầu vào để phát hiện lỗi góc.

Với đối tượng có **khóa** nhưng các trường thông tin khác nhau, gắn thứ tự gốc vào từng bản ghi; sau sort, mọi nhóm đồng khóa phải giữ thứ tự gốc nếu yêu cầu stable. Quan sát mảng số nguyên có giá trị trùng thôi chưa kiểm chứng được tính ổn định vì chúng không có danh tính phân biệt.

Có thể kiểm thử bất biến từng lượt: sau lượt k, các phần tử tăng theo **key(x) mod b^k**. Nếu bất biến sai từ một lượt, kiểm tra lại count, chiều duyệt và việc sao chép output.

## 12. Tự kiểm tra

**Câu 1.** Tại sao lượt sắp theo chữ số cao phải giữ thứ tự cũ giữa các phần tử có chữ số hiện tại bằng nhau?  
**Đáp án:** Vì thứ tự cũ đã phản ánh đúng các chữ số thấp. Đảo thứ tự giữa những phần tử đồng chữ số cao sẽ làm mất kết quả của các lượt trước.

**Câu 2.** Với [21,13,11,2], sau lượt hàng đơn vị thu được gì?  
**Đáp án:** [21,11,2,13]. Nhóm có chữ số đơn vị 1 giữ 21 trước 11; sau lượt hàng chục kết quả [2,11,13,21].

**Câu 3.** Nếu n số nguyên có khóa dài d chữ số ở cơ số b, thời gian LSD bằng counting sort ổn định là bao nhiêu?  
**Đáp án:** O(n+d(n+b)), thường viết Θ(d(n+b)) với d≥1 cho cài đặt quét đủ d lượt. Bộ nhớ phụ trợ Θ(n+b).

**Câu 4.** Vì sao không thể dùng số lượng chữ số của phần tử đầu tiên làm d?  
**Đáp án:** Các phần tử sau có thể có nhiều chữ số hơn; phải xét khóa lớn nhất hoặc có quy tắc chiều dài khóa phù hợp để mọi chữ số quan trọng đều được xử lý.

**Câu 5.** Vì sao ánh xạ \(key(x)=(long)x-(long)Integer.MIN_VALUE\) cho phép LSD sắp đúng cả số âm?  
**Đáp án:** Phép trừ cùng hằng số bằng long bảo toàn thứ tự của int, biến mọi khóa về miền không âm; stable radix sort theo khóa đó trả thứ tự số nguyên gốc.

**Ghi nhớ:** LSD radix sort xử lý **thấp đến cao**, và **ổn định ở mỗi lượt** là điều kiện làm các kết quả chữ số thấp được giữ lại. Chọn đúng miền khóa, cơ số, kiểu số và số lượt trước khi tối ưu.
