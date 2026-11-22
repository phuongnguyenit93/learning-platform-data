# Theo dõi cực trị, tần suất và các thống kê đơn giản khi xử lý dãy

## 1. Mục tiêu và cách nghĩ khi duyệt dãy

Cho dãy a gồm n phần tử, ta thường cần xác định: giá trị nhỏ nhất/lớn nhất, vị trí xuất hiện của chúng, tổng, trung bình, số lần xuất hiện của từng giá trị, số giá trị phân biệt hoặc giá trị xuất hiện nhiều nhất. Các yêu cầu này liên quan chặt chẽ đến **trạng thái tích lũy**: mỗi khi đọc thêm một phần tử, cập nhật kết quả tạm thời bằng thông tin vừa biết.

Với ví dụ a = [4, -2, 4, 7, -2, 4] và chỉ số bắt đầu từ 0, ta có:

- Min = -2, vị trí xuất hiện đầu tiên 1; max = 7, vị trí xuất hiện đầu tiên 3.
- Sum = 15; mean = 15/6 = 2,5.
- Tần suất: -2 xuất hiện 2 lần, 4 xuất hiện 3 lần, 7 xuất hiện 1 lần; có 3 giá trị phân biệt.
- Mốt (mode) = 4 do có tần suất cao nhất.
- Phương sai tổng thể bằng 11,25; trung vị bằng 4.

Mỗi thống kê có trạng thái, công thức cập nhật, chi phí và điều kiện hợp lệ riêng. Nếu chỉ cần kết quả sau khi đọc hết dãy, ta thường có thể tính nhiều thống kê trong cùng **một lượt duyệt O(n)**. Nếu cần xử lý truy vấn đoạn, cập nhật phần tử hoặc cửa sổ trượt, có thể cần cấu trúc dữ liệu bổ sung.

## 2. Theo dõi giá trị nhỏ nhất, lớn nhất và vị trí

### Cực trị trong một lượt duyệt

Với dãy không rỗng, khởi tạo bằng phần tử đầu tiên:

~~~text
min = max = a[0]
for i = 1..n-1:
    if a[i] < min: min = a[i]
    if a[i] > max: max = a[i]
~~~

**Bất biến vòng lặp:** sau khi đã xét a[0..i], min là giá trị nhỏ nhất và max là giá trị lớn nhất của tiền tố đó. Bước cập nhật đúng vì cực trị mới chỉ có thể là cực trị trước đó hoặc phần tử mới đọc. Vì mỗi phần tử được xét một lần, thời gian O(n), bộ nhớ phụ O(1).

Khởi tạo max = 0 là sai trên dãy toàn số âm; khởi tạo min = 0 là sai trên dãy toàn số dương. Đọc a[0] cũng đòi dãy không rỗng, nên phải có tiền điều kiện hoặc cơ chế xử lý trường hợp rỗng.

### Theo dõi chỉ số và quy tắc hòa

Muốn trả chỉ số xuất hiện **đầu tiên**, khởi tạo minIndex = maxIndex = 0, chỉ đổi chỉ số khi giá trị **nhỏ hơn hẳn** hoặc **lớn hơn hẳn**:

~~~text
if a[i] < min: min = a[i]; minIndex = i
if a[i] > max: max = a[i]; maxIndex = i
~~~

Nếu dùng <= và >= thì chỉ số cuối cùng của giá trị cực trị sẽ thắng. Muốn thu thập **mọi vị trí cực trị**, phải lưu thêm danh sách chỉ số hoặc quét lần hai; kết quả có thể dài O(n). Quy tắc hòa là một phần của đặc tả, không thể bỏ qua khi có phần tử trùng.

### Mô phỏng trên ví dụ

| Phần tử vừa đọc | Min của tiền tố | Max của tiền tố | Tổng tiền tố |
| ---: | ---: | ---: | ---: |
| 4 | 4 | 4 | 4 |
| -2 | -2 | 4 | 2 |
| 4 | -2 | 4 | 6 |
| 7 | -2 | 7 | 13 |
| -2 | -2 | 7 | 11 |
| 4 | -2 | 7 | 15 |

Nếu cần xuất cực trị **sau mỗi tiền tố**, có thể cập nhật và in ngay, dùng O(1) bộ nhớ phụ; nếu phải lưu toàn bộ n kết quả thì mảng đầu ra chiếm O(n).

**Giới hạn quan trọng:** trạng thái chỉ có min/max giúp thêm phần tử nhanh nhưng không đủ để xóa phần tử bất kỳ. Khi giá trị min vừa bị xóa, ta không biết min kế tiếp nếu không giữ thêm thông tin hoặc quét lại dãy.

## 3. Đếm tần suất, phần tử phân biệt và mốt

Tần suất của giá trị x là số chỉ số i thỏa a[i] = x. Cách biểu diễn bảng đếm phụ thuộc miền giá trị.

### Dùng mảng đếm nếu miền giá trị nhỏ

Nếu mọi a[i] thuộc [0,100], dùng int[] count = new int[101]; khi gặp x thì count[x]++. Truy cập theo chỉ số có thời gian O(1), dựng bảng tần suất tốn O(n + R) với R = 101 tính cả khởi tạo, bộ nhớ O(R).

Nếu miền giá trị là [L,U] có thể dùng count[x-L], nhưng phải kiểm tra 0 ≤ x-L < R và tránh tràn số khi tính khoảng U-L+1. Không cấp phát một mảng cực lớn chỉ vì có vài giá trị xa nhau, ví dụ -1.000.000.000 và 1.000.000.000.

### Dùng HashMap khi miền giá trị lớn hoặc thưa

Trong Java, HashMap<Integer,Integer> cho phép dùng giá trị làm khóa:

~~~java
Map<Integer, Integer> count = new HashMap<>();
for (int x : values) {
    count.merge(x, 1, Integer::sum);
}
~~~

Với hàm băm phân bố phù hợp, mỗi lần cập nhật có thời gian kỳ vọng O(1), toàn bộ dãy O(n) kỳ vọng, bộ nhớ O(u) với u là số giá trị phân biệt. Không hiểu O(1) này thành bảo đảm tuyệt đối về thời gian xấu nhất.

Sau khi tạo bảng đếm:

- count.getOrDefault(x, 0) cho tần suất của x.
- count.size() cho số giá trị phân biệt, **không phải** độ dài dãy.
- Tổng tất cả tần suất bằng n: đây là bất biến hữu ích để kiểm thử.
- Một giá trị có tần suất lớn hơn 1 là giá trị xuất hiện trùng.
- **Mốt (mode)** là giá trị có tần suất lớn nhất.

**Mốt có thể không duy nhất.** Ví dụ [2,2,1,1] có hai mốt 1 và 2. Nếu đề yêu cầu một mốt duy nhất, hãy công bố quy tắc: lấy giá trị nhỏ nhất khi hòa, lấy giá trị gặp đầu tiên, hoặc chính sách khác. HashMap không bảo đảm thứ tự duyệt nên không được dựa vào thứ tự các khóa để chọn ngẫu nhiên một kết quả.

Ta có thể vừa tăng bảng đếm, vừa giữ biến mode/modeCount: khi tần suất của x vượt modeCount thì cập nhật; nếu bằng modeCount thì so theo quy tắc hòa. Với cách hòa “lấy giá trị nhỏ nhất”, cập nhật khi count[x] > modeCount **hoặc** bằng modeCount và x < mode.

Nếu chỉ cần kiểm tra “đã xuất hiện chưa?”, HashSet thường đủ; nếu muốn truy vấn khóa có thứ tự và tần suất, TreeMap phù hợp nhưng thao tác tra/thêm là O(log u).

## 4. Tổng, trung bình và các thống kê số học

### Tổng và trung bình

Công thức là sum = Σ a[i] và mean = sum/n với n > 0. Dùng long cho biến cộng dồn int trong Java để tránh tràn int, đồng thời tránh chia nguyên:

~~~java
long sum = 0;
for (int x : values) {
    sum += x;
}
double mean = (double) sum / values.length;
~~~

Trong một int[] Java, độ dài mảng và miền giá trị int được giới hạn, nên tổng toán học tối đa của toàn mảng nằm trong miền long. Với dữ liệu đến từ luồng không giới hạn, hoặc khi cộng các long, phải xét tràn số riêng. Ép kiểu **sau** khi tổng int đã tràn không cứu được kết quả. Với dãy rỗng, mean không được xác định.

Mean rất nhạy với ngoại lệ: [1,2,3,100] có mean 26,5, không gần với phần lớn giá trị. Khi muốn đo “trung tâm”, đôi khi cần cả trung vị và thông tin về độ phân tán.

### Phương sai và độ lệch chuẩn

Với mean μ, phương sai tổng thể:

~~~text
variance_population = (Σ (a[i] - μ)^2) / n       (n > 0)
variance_sample     = (Σ (a[i] - μ)^2) / (n - 1) (n > 1)
standard_deviation  = sqrt(variance)
~~~

Phương sai mẫu dùng mẫu số n-1 theo định nghĩa ước lượng phương sai tổng thể phổ biến; phương sai tổng thể dùng n. Phải đặt tên rõ ràng, không trộn hai khái niệm. Với [4,-2,4,7,-2,4], mean = 2,5; tổng bình phương độ lệch = 67,5; phương sai tổng thể = 67,5/6 = **11,25**, phương sai mẫu = 67,5/5 = **13,5**.

Một cách tính dễ hiểu gồm hai lượt: lượt một lấy mean, lượt hai cộng bình phương độ lệch. Khi dữ liệu là luồng hoặc muốn giảm sai số do trừ hai số lớn gần bằng nhau trong công thức E[x²]-E[x]², có thể dùng **thuật toán Welford**:

~~~text
count = 0, mean = 0, M2 = 0
với mỗi x:
    count += 1
    delta = x - mean
    mean += delta / count
    delta2 = x - mean
    M2 += delta * delta2

variance_population = M2 / count         (count > 0)
variance_sample     = M2 / (count - 1)   (count > 1)
~~~

M2 là tổng bình phương độ lệch được tích lũy có hiệu chỉnh khi mean thay đổi. Chỉ cần count, mean, M2: O(n) thời gian, O(1) bộ nhớ phụ. double vẫn có sai số làm tròn; nếu thống kê cần độ chính xác decimal hoặc phục vụ nghiệp vụ tài chính, phải quy định kiểu dữ liệu và cách làm tròn thích hợp.

### Trung vị và số phân biệt

Trung vị (median) của dãy đã sắp xếp là giá trị giữa nếu n lẻ; nếu n chẵn thì lấy trung bình hai giá trị giữa. Ví dụ sắp [4,-2,4,7,-2,4] thành [-2,-2,4,4,4,7], nên trung vị bằng 4.

Nếu chỉ cần trung vị một lần, sao chép rồi sắp xếp trong O(n log n) là cách đơn giản và không làm thay đổi dãy gốc. Khi lấy trung bình hai int lớn, đừng cộng bằng int trước khi chia vì dễ tràn; hãy dùng long hoặc double trung gian. Không thể suy ra trung vị chính xác chỉ từ min, max, sum và mean. Với luồng cần trung vị liên tục, hai heap là một phương án thường gặp nhưng có trạng thái và quy tắc cân bằng phức tạp hơn.

## 5. Bảng so sánh theo yêu cầu

| Yêu cầu | Trạng thái cần lưu | Thời gian với n phần tử | Bộ nhớ phụ |
| --- | --- | --- | --- |
| Min, max, vị trí đầu tiên | Giá trị và chỉ số | O(n) | O(1) |
| Tổng, mean | Tổng và đếm | O(n) | O(1) |
| Mean, phương sai streaming | count, mean, M2 | O(n) | O(1) |
| Tần suất mọi giá trị | Mảng đếm hoặc HashMap | O(n+R) hoặc O(n) kỳ vọng | O(R) hoặc O(u) |
| Mốt | Tần suất + mode/modeCount | O(n) kỳ vọng với HashMap | O(u) |
| Cực đại của từng tiền tố | Cực đại hiện tại và mảng kết quả | O(n) | O(n) nếu giữ các kết quả |
| Trung vị một lần | Dãy sao chép đã sắp xếp | O(n log n) | O(n) với bản sao |
| Tổng của q đoạn trên dãy tĩnh | Mảng prefix sums | Dựng O(n), hỏi O(1)/đoạn | O(n) |

R là kích thước miền đếm, u là số giá trị phân biệt. Chi phí bộ nhớ của kết quả đầu ra được nêu riêng khi cần lưu nhiều kết quả.

## 6. Ví dụ Java 17+: kết hợp nhiều thống kê trong một lượt

Chương trình tự chạy sau tính min/max và vị trí **đầu tiên**, sum, mean, phương sai tổng thể theo Welford, tần suất, số phần tử phân biệt, mốt có quy tắc hòa “chọn giá trị nhỏ nhất” và mảng cực đại của từng tiền tố. Đầu vào null/rỗng của hàm summarize bị từ chối rõ ràng.

Lưu thành **SequenceStatsDemo.java**:

~~~java
import java.util.Arrays;
import java.util.HashMap;
import java.util.Locale;
import java.util.Map;

public class SequenceStatsDemo {
    record Summary(
            int min, int firstMinIndex,
            int max, int firstMaxIndex,
            long sum, double mean, double populationVariance,
            int mode, int modeCount,
            int distinctCount, Map<Integer, Integer> frequencies) {
    }

    static Summary summarize(int[] values) {
        if (values == null) {
            throw new IllegalArgumentException("values must not be null");
        }
        if (values.length == 0) {
            throw new IllegalArgumentException("values must not be empty");
        }

        int min = values[0], max = values[0];
        int minIndex = 0, maxIndex = 0;
        int mode = values[0], modeCount = 0;
        long sum = 0;
        double mean = 0.0, m2 = 0.0;
        Map<Integer, Integer> counts = new HashMap<>();

        for (int i = 0; i < values.length; i++) {
            int x = values[i];

            if (x < min) {
                min = x;
                minIndex = i;
            }
            if (x > max) {
                max = x;
                maxIndex = i;
            }

            sum += x;

            int newCount = counts.merge(x, 1, Integer::sum);
            if (newCount > modeCount ||
                    (newCount == modeCount && x < mode)) {
                mode = x;
                modeCount = newCount;
            }

            int processed = i + 1;
            double delta = x - mean;
            mean += delta / processed;
            double deltaAfter = x - mean;
            m2 += delta * deltaAfter;
        }

        return new Summary(
                min, minIndex, max, maxIndex,
                sum, mean, m2 / values.length,
                mode, modeCount, counts.size(), Map.copyOf(counts)
        );
    }

    static int[] prefixMax(int[] values) {
        if (values == null) {
            throw new IllegalArgumentException("values must not be null");
        }
        int[] result = new int[values.length];
        for (int i = 0; i < values.length; i++) {
            result[i] = (i == 0) ?
                    values[i] : Math.max(result[i - 1], values[i]);
        }
        return result;
    }

    public static void main(String[] args) {
        int[] values = {4, -2, 4, 7, -2, 4};
        Summary s = summarize(values);

        System.out.printf("min=%d at %d; max=%d at %d%n",
                s.min(), s.firstMinIndex(),
                s.max(), s.firstMaxIndex());
        System.out.printf(Locale.ROOT, "sum=%d; mean=%.2f%n",
                s.sum(), s.mean());
        System.out.printf("mode=%d (%d times); distinct=%d%n",
                s.mode(), s.modeCount(), s.distinctCount());
        System.out.printf(Locale.ROOT, "population variance=%.2f%n",
                s.populationVariance());
        System.out.println("frequency(-2)=" +
                s.frequencies().getOrDefault(-2, 0));
        System.out.println("prefix max=" +
                Arrays.toString(prefixMax(values)));

        try {
            summarize(new int[0]);
        } catch (IllegalArgumentException e) {
            System.out.println("empty: " + e.getMessage());
        }
    }
}
~~~

Biên dịch và chạy trong thư mục chứa tệp, với JDK 17 trở lên:

~~~bash
javac SequenceStatsDemo.java
java SequenceStatsDemo
~~~

Đầu ra:

~~~text
min=-2 at 1; max=7 at 3
sum=15; mean=2.50
mode=4 (3 times); distinct=3
population variance=11.25
frequency(-2)=2
prefix max=[4, 4, 4, 7, 7, 7]
empty: values must not be empty
~~~

**Giải thích và chi phí:**

- Với mỗi x, hai phép so sánh cập nhật cực trị, còn sum cộng dồn bằng long. Dấu so sánh nghiêm ngặt giữ vị trí đầu tiên dù có cực trị lặp.
- counts.merge tăng tần suất. Cập nhật mode khi số lần xuất hiện tăng kỷ lục hoặc hòa nhưng giá trị nhỏ hơn mode hiện tại. Vì vậy kết quả không dựa vào thứ tự duyệt HashMap.
- Biến mean và m2 được cập nhật bởi Welford. Hàm trả phương sai tổng thể m2/n, là 11,25 với ví dụ trên. Với n=1, phương sai tổng thể là 0.
- Map.copyOf trả bản sao bảng tần suất không cho người gọi sửa trực tiếp. Mảng values ban đầu không bị thay đổi.
- summarize có thời gian O(n) **kỳ vọng** và bộ nhớ O(u) với u khóa phân biệt. Nếu bỏ thống kê tần suất/mốt, các thống kê cực trị, sum và Welford chỉ cần O(1) bộ nhớ phụ.
- prefixMax sinh một mảng độ dài n; mỗi vị trí i lưu max(a[0],...,a[i]), tổng thời gian O(n), bộ nhớ đầu ra O(n). Với dãy rỗng, hàm này trả mảng rỗng; còn summarize từ chối dãy rỗng vì min/mean không xác định theo hợp đồng đó.

Đây là ví dụ xử lý mảng int[] một luồng. Dữ liệu decimal, đa luồng hoặc nguồn đọc vô hạn có thể cần chính sách về kiểu số, đồng bộ và dung lượng khác.

## 7. Dãy tĩnh, truy vấn đoạn và cửa sổ trượt

### Tổng đoạn khi dãy không thay đổi

Nếu có q truy vấn “tổng từ l đến r”, dựng prefix sums:

~~~text
prefix[0] = 0
prefix[i+1] = prefix[i] + a[i]
sum(l,r) = prefix[r+1] - prefix[l]    (0 <= l <= r < n)
~~~

Dùng long[] nếu a[i] là int. Dựng trong O(n), trả một tổng đoạn O(1), bộ nhớ O(n). Trung bình đoạn có độ dài r-l+1 bằng sum(l,r)/(double)(r-l+1). Nếu dãy được cập nhật nhiều lần, prefix sums thường không thuận lợi vì một thay đổi ảnh hưởng nhiều tổng phía sau; có thể cân nhắc Fenwick tree hoặc segment tree nếu yêu cầu lớn hơn phạm vi thống kê cơ bản.

### Cửa sổ độ dài k

Cửa sổ trượt gồm đúng k phần tử liên tiếp. Sau khi dịch sang phải một vị trí, một phần tử rời đi và một phần tử mới vào:

- **Tổng cửa sổ:** cộng phần tử vào và trừ phần tử ra, O(1) mỗi bước.
- **Mean cửa sổ:** tổng cửa sổ chia k, O(1) mỗi bước sau khi cập nhật tổng.
- **Tần suất cửa sổ:** tăng đếm của phần tử vào, giảm đếm phần tử ra, xóa khóa nếu tần suất về 0; O(1) kỳ vọng mỗi bước với HashMap.
- **Min/max cửa sổ:** biến min/max đơn lẻ không đủ khi cực trị rời cửa sổ. Có thể dùng **monotonic deque** lưu chỉ số ứng viên, cho tổng O(n) thời gian qua mọi cửa sổ.
- **Median cửa sổ:** phức tạp hơn, do cả chèn và xóa phần tử; cần cấu trúc duy trì thứ tự hoặc hai heap với xóa trễ phù hợp.

Ví dụ a=[2,1,4,3,5], k=3: tổng từng cửa sổ là [7,8,12]; cực đại từng cửa sổ là [4,4,5]. Cần quy định k hợp lệ, chẳng hạn 1 ≤ k ≤ n; k=0 hoặc k>n là trường hợp phải xác định hành vi trước khi cài đặt.

### Trả lời nhiều truy vấn tần suất

Một truy vấn đơn lẻ có thể quét O(n). Nếu có q truy vấn tần suất trên cùng dãy và q rất lớn, dựng HashMap với chi phí O(n) kỳ vọng, sau đó mỗi truy vấn trung bình O(1). Nếu dãy đã sắp và không cập nhật, có thể dùng hai lần tìm kiếm nhị phân (lower bound và upper bound) để tìm số phần tử bằng x trong O(log n) mỗi truy vấn mà không cần bảng đếm.

## 8. Những trường hợp biên cần nêu rõ

| Tình huống | Hành vi và chú ý |
| --- | --- |
| Dãy rỗng | Min/max/mean/mode/median thường không được định nghĩa; phải từ chối hoặc dùng kiểu biểu diễn vắng mặt |
| Một phần tử | Min=max=mode=giá trị đó, variance population=0; variance sample chưa được định nghĩa |
| Toàn số âm | Max vẫn âm; tuyệt đối không mặc định max=0 |
| Nhiều cực trị bằng nhau | Quy định lấy vị trí đầu, cuối hay tất cả |
| Nhiều mode cùng tần suất | Quy định cách chọn, tránh phụ thuộc thứ tự Map |
| Phần tử int rất lớn | Sum dùng long; tính trung vị hai số giữa nên tránh cộng int gây tràn |
| Miền khóa lớn, thưa hoặc có số âm | Dùng HashMap hoặc nén miền; không truy cập trực tiếp mảng đếm bằng chỉ số âm |
| Dữ liệu double có NaN/Infinity | Phải đặt chính sách trước; so sánh số thường với NaN không hành xử như với số hữu hạn |
| Dữ liệu bị xóa/cập nhật | Min/max hoặc mode hiện tại đơn lẻ không đủ để suy ra trạng thái mới |
| Nhiều luồng cập nhật chung | HashMap và biến thống kê thông thường không tự an toàn khi ghi đồng thời |

Với double, sai số làm tròn là bình thường; trong kiểm thử, so sánh với một dung sai thích hợp thay vì đòi bằng tuyệt đối ở mọi trường hợp. Với tổng số nguyên có miền phù hợp, nên so sánh chính xác.

Nếu chỉ cần min, max, mean và phương sai từ một luồng dữ liệu, có thể dùng O(1) trạng thái bằng các biến tích lũy; tần suất **chính xác cho mọi khóa** nói chung cần bộ nhớ theo số khóa phân biệt. Trung vị chính xác của luồng cũng không thể suy ra từ vài biến tổng hợp đơn giản.

## 9. Chứng minh tính đúng và sinh kiểm thử

Viết hậu điều kiện trước khi chọn mã:

- Min là một phần tử của dãy và không lớn hơn phần tử nào; max cũng là phần tử của dãy và không nhỏ hơn phần tử nào.
- Nếu trả firstMinIndex thì a[firstMinIndex] = min và mọi chỉ số nhỏ hơn không chứa min.
- Sum đúng bằng tổng toán học của các phần tử; mean = sum/n khi n>0.
- Với mọi giá trị x, frequency(x) đúng bằng số vị trí có a[i]=x; tổng các tần suất bằng n.
- Mode có tần suất lớn nhất và thỏa quy tắc hòa.
- PrefixMax[i] = max(a[0],...,a[i]) và không giảm khi i tăng.
- Nếu trả phương sai phải ghi rõ đó là phương sai tổng thể hay mẫu.

Bảng kiểm thử trọng yếu:

| Đầu vào | Đáp án hoặc tính chất |
| --- | --- |
| [5] | Min=max=mode=5; sum=5; mean=5; phương sai tổng thể=0 |
| [-9,-4,-7] | Max=-4, không phải 0 |
| [2,2,1,1] | Mode=1 nếu quy tắc hòa lấy số nhỏ nhất |
| [0,0,0] | Distinct=1; mode=0; phương sai=0 |
| [Integer.MAX_VALUE,Integer.MAX_VALUE] | Sum=4294967294 (long) |
| [4,-2,4,7,-2,4] | Min=-2 ở 1; max=7 ở 3; sum=15; mode=4; mean=2,5 |
| [] và null | Thất bại theo hợp đồng, không trả một “min=0” giả |

Có thể kiểm thử tính chất ngẫu nhiên: sau mỗi lần tăng tần suất, tổng các giá trị trong bảng đếm bằng số phần tử đã đọc; sau mỗi bước, min ≤ mọi phần tử đã xét ≤ max; prefixMax không giảm; và thống kê không sửa dãy nguồn. Với dữ liệu hữu hạn, mean lý tưởng nằm giữa min và max (chấp nhận sai số số thực phù hợp).

## 10. Sai lầm phổ biến

1. **Khởi tạo cực trị sai:** max=0 hoặc min=0 làm sai dãy toàn âm/toàn dương.
2. **Không xác định chính sách khi bằng nhau:** vị trí cực trị đầu tiên hay cuối cùng khác nhau do dấu < so với <=.
3. **Nhầm số khóa với số phần tử:** HashMap.size() trả u, không trả n.
4. **Dùng thứ tự duyệt HashMap để quyết định mode:** không có bảo đảm thứ tự và kết quả có thể không tái lập đúng chính sách hòa.
5. **Dùng sum/n bằng số nguyên:** mất phần thập phân; ép kiểu trước khi chia.
6. **Cộng bằng int rồi ép sang long:** phép cộng đã tràn trước khi ép; nên dùng biến sum kiểu long ngay từ đầu.
7. **Quên dãy rỗng:** không thể đọc a[0] hoặc chia cho n=0 một cách đúng đắn.
8. **Trộn phương sai mẫu và tổng thể:** mẫu số n-1 chỉ hợp lệ khi n>1 và có ý nghĩa thống kê riêng.
9. **Dùng biến min/max đơn lẻ cho thao tác xóa:** không biết ứng viên kế tiếp khi giá trị cực trị biến mất.
10. **Quá tối ưu hóa:** một bài chỉ cần min/max cuối cùng không cần heap, balanced tree hay bảng đếm.

## 11. Tự luyện

1. Viết hàm trả **vị trí đầu và cuối của giá trị lớn nhất**; tự xác định hành vi dãy rỗng, một phần tử, nhiều giá trị cực đại trùng nhau.
2. Với [-3,2,-3,5,2,5], lập bảng tần suất và tìm mọi mode; sau đó áp dụng quy tắc hòa “chọn số nhỏ nhất”.
3. Viết bộ thống kê streaming chỉ giữ min, max, long sum, count, mean và M2. Giải thích vì sao không cần lưu mọi phần tử.
4. Cho [2,1,4,3,5] và k=3, tự tính sum, mean và max của từng cửa sổ; giải thích vì sao cập nhật tổng đơn giản hơn cập nhật max khi có phần tử rời cửa sổ.
5. Có 100.000 giá trị và 100.000 truy vấn “x xuất hiện bao nhiêu lần?”. So sánh quét trực tiếp, HashMap và mảng đếm khi miền mọi giá trị đều thuộc [0,100].

**Ghi nhớ:** min/max, tổng, mean và phương sai có thể tính bằng trạng thái nhỏ khi duyệt tuần tự; tần suất và mode cần bộ đếm theo giá trị; trung vị hay thống kê cửa sổ động có thể cần sắp xếp hoặc cấu trúc hỗ trợ khác. Điều quyết định là **thao tác cần thực hiện, dữ liệu hợp lệ và bảo đảm đầu ra**.
