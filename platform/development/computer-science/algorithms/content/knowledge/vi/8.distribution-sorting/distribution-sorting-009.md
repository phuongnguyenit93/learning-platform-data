# Chi phí bộ nhớ và dữ liệu có miền giá trị rất lớn

Sắp xếp phân phối (distribution sorting) tận dụng cấu trúc của **khóa**: miền giá trị, chữ số, hoặc các nhóm giá trị, thay vì chỉ so sánh từng cặp phần tử. Counting sort, radix sort và bucket sort là các đại diện quan trọng. Chúng có thể đạt thời gian tuyến tính dưới những điều kiện phù hợp, nhưng hiệu quả phụ thuộc mạnh vào cách tổ chức bộ nhớ. Khi dữ liệu chỉ gồm vài trăm phần tử mà khóa trải rộng từ Integer.MIN_VALUE tới Integer.MAX_VALUE, một mảng đếm trực tiếp theo giá trị là một lựa chọn tồi hoặc không thể cấp phát được.

Bài này tập trung vào **chi phí bộ nhớ và dữ liệu có miền giá trị rất lớn**, trong chủ đề **Sắp xếp phân phối**. Mục tiêu là biết phân biệt **số phần tử**, **độ rộng miền giá trị**, **số khóa phân biệt**, **số chữ số** và **ngân sách bộ nhớ**; từ đó chọn cấu trúc phù hợp thay vì áp dụng counting sort trực tiếp ở mọi tình huống.

## 1. Những đại lượng phải đo đúng

Cho mảng số nguyên a có n phần tử. Đặt:

- **n:** số phần tử đầu vào, bao gồm cả các phần tử trùng.
- **min, max:** giá trị nhỏ nhất và lớn nhất thực tế trong mảng không rỗng.
- **R = max − min + 1:** số giá trị nguyên có thể có trong khoảng kín [min, max], dù trong mảng chỉ xuất hiện một số ít giá trị.
- **k:** số khóa **phân biệt thật sự xuất hiện**, luôn có 0 ≤ k ≤ n và khi n > 0 thì k ≤ R.
- **B:** số nhóm/bucket hoặc số chữ số có thể có trong một lượt radix sort, ví dụ B = 256 cho một byte.
- **d:** số lượt theo chữ số, ví dụ d = 4 cho kiểu int 32 bit khi xử lý từng byte.

Không được đánh đồng R với n hoặc k. Ví dụ a = [Integer.MIN_VALUE, 5, Integer.MAX_VALUE, 5] có n = 4, k = 3 nhưng R = 4.294.967.296. R có thể lớn hơn rất nhiều lần n, thậm chí lớn hơn giới hạn chiều dài mảng cho phép của Java.

**Đơn vị quan trọng:** một phần tử của int[] dùng 4 byte dữ liệu số nguyên (chưa tính header, căn chỉnh đối tượng và phần bộ nhớ khác). Một mảng đếm với R phần tử đòi hỏi xấp xỉ **4 × R byte** chỉ cho các bộ đếm. Bộ nhớ còn phụ thuộc runtime và cấu trúc dữ liệu; phép nhân 4 × R là ước lượng phần dữ liệu thô, **không phải dự báo chính xác toàn bộ heap Java**.

## 2. Counting sort trực tiếp: khi nào nhanh, khi nào phá ngân sách?

Với khóa nguyên có miền giá trị đủ hẹp, counting sort lưu frequency[v − min] = số phần tử có giá trị v. Sau khi đếm, duyệt các ô từ chỉ số 0 tới R−1 và ghi mỗi giá trị ra số lần tương ứng. Với a = [3, −1, 2, −1, 0, 3], min = −1, max = 3:

| Chỉ số bucket | 0 | 1 | 2 | 3 | 4 |
| --- | ---: | ---: | ---: | ---: | ---: |
| Giá trị ứng với bucket | −1 | 0 | 1 | 2 | 3 |
| Số lần xuất hiện | 2 | 1 | 0 | 1 | 2 |

Kết quả: **[−1, −1, 0, 2, 3, 3]**. Chỉ cần R = 5 bộ đếm cho n = 6 phần tử. Mảng đếm được khởi tạo về 0; việc tạo và duyệt mảng cũng có chi phí.

**Độ phức tạp của cách đếm rồi ghi đè:** O(n + R) thời gian và O(R) bộ nhớ phụ. Nó thay đổi mảng int tại chỗ theo nghĩa kết quả nằm lại trong mảng đầu vào, nhưng **không có nghĩa O(1) bộ nhớ**, vì vẫn tạo mảng frequency.

**Lưu ý tính ổn định:** cách “đếm rồi ghi lại giá trị” chỉ xử lý số nguyên, không bảo toàn thứ tự tương đối của những **bản ghi có khóa bằng nhau**. Stable counting sort dùng thêm mảng đầu ra, tổng tiền tố để xác định vị trí và phân phối bản ghi một cách ổn định, thường cần O(n + R) bộ nhớ phụ. Không nên gọi tất cả phiên bản counting sort là stable nếu chưa kiểm tra cách xuất dữ liệu.

## 3. Miền cực rộng: n nhỏ vẫn không cứu được mảng đếm

Xét hai số nguyên:
- a[0] = Integer.MIN_VALUE = −2.147.483.648.
- a[1] = Integer.MAX_VALUE = 2.147.483.647.

Miền khóa nguyên liên tục của hai giá trị biên này có:

~~~text
R = max - min + 1
  = 2,147,483,647 - (-2,147,483,648) + 1
  = 4,294,967,296 = 2^32 vị trí.

Dung lượng thô của int[R] = 4 × 4,294,967,296
                          = 17,179,869,184 byte
                          = 16 GiB, chưa tính overhead.
~~~

Đó là lượng bộ đếm khổng lồ chỉ để sắp xếp **hai số**! Hơn nữa, Java không thể biểu diễn chiều dài mảng bằng một int có giá trị lớn như R này. Cấp phát kiểu int[] với số bin quá lớn không chỉ chậm; nó còn có thể dẫn tới lỗi kích thước mảng, thiếu bộ nhớ hoặc làm JVM bị áp lực GC.

Đây là điểm then chốt: counting sort có thể tuyến tính theo **n + R** nhưng **không tuyến tính theo n** nếu R tăng độc lập với n. Với n = 2, R vẫn có thể là hàng tỷ. Độ phức tạp phải nêu rõ tham số R, không được rút thành O(n) khi chưa ràng buộc miền giá trị.

Ngay cả khi R vừa đủ biểu diễn bởi int, lựa chọn dense cũng có thể không hợp lý nếu R lớn và n rất nhỏ. Ví dụ 100 phần tử trải đều trong khoảng một triệu giá trị vẫn phải tạo, khởi tạo và duyệt một triệu bộ đếm.

## 4. Quy tắc tính miền an toàn và giới hạn trước khi cấp phát

Với số nguyên có dấu 32 bit trong Java, biểu thức **max − min + 1 tính bằng int có thể tràn số**. Nếu max = Integer.MAX_VALUE và min = Integer.MIN_VALUE, kết quả toán học là 2^32 nhưng phép trừ int không biểu diễn được.

**Cách đúng:** nâng hai toán hạng sang long trước phép trừ.

~~~java
long range = (long) max - (long) min + 1L;
if (range > MAX_DENSE_BINS) {
    throw new IllegalArgumentException("value range is too wide");
}
int[] frequency = new int[(int) range];
~~~

Khi tính chỉ số bucket, cũng nên làm phép trừ bằng long trước rồi mới ép về int, sau khi đã xác nhận range đủ nhỏ. Trong ví dụ hoàn chỉnh, giới hạn MAX_DENSE_BINS = 1_000_000 là **ngưỡng minh họa chính sách bộ nhớ**, không phải một hằng số tối ưu cho mọi ứng dụng. Thực tế cần lựa chọn theo heap, độ đồng thời, số lượng mảng trung gian, mức giới hạn độ trễ và kích thước dữ liệu.

Một cách ước lượng trước khi chọn dense:

1. Với n = 0 hoặc 1, không cần mảng đếm để sắp xếp; có thể trả kết quả ngay.
2. Tìm min và max với một lượt O(n), nếu dữ liệu không rỗng.
3. Tính R bằng long; kiểm tra R có thể biểu diễn và nhỏ hơn ngân sách bin đã chọn hay không.
4. Ước lượng bộ nhớ của tần suất (4 × R byte) **cộng** bộ nhớ mảng đầu ra nếu cần stable.
5. Chỉ sau những bước đó mới cấp phát frequency; nếu không phù hợp, chuyển sang cấu trúc khác.

Không cố tạo một mảng khổng lồ rồi dùng try/catch OutOfMemoryError như cơ chế ra quyết định bình thường. Kiểm tra ngân sách trước sẽ an toàn và dễ dự đoán hơn.

## 5. Dữ liệu thưa: đếm đúng những giá trị thực sự xuất hiện

Nếu k rất nhỏ so với R, cấu trúc đếm **sparse** chỉ lưu các giá trị xuất hiện. Một TreeMap<Integer, Integer> trong Java có thể làm việc này:

- Duyệt n phần tử, tăng tần suất cho mỗi khóa.
- Các khóa trong TreeMap được giữ theo thứ tự tăng dần.
- Duyệt từ khóa nhỏ nhất đến lớn nhất, ghi mỗi khóa ra số lần đã đếm.

Ví dụ [Integer.MAX_VALUE, −2, Integer.MIN_VALUE, 5, −2] chỉ có **4 khóa khác nhau** mặc dù R phủ toàn bộ miền int. TreeMap chứa 4 entry, không phải 4.294.967.296 bucket.

Độ phức tạp dự kiến với k khóa phân biệt là **O(n log(k + 1) + n + k)** thời gian (chi phí thêm/tra cứu trong cây cân bằng và ghi ra n phần tử) cùng **O(k)** cấu trúc phụ. Dấu +1 chỉ để biểu thức có nghĩa với k nhỏ. Đổi lại, mỗi entry TreeMap mang overhead của đối tượng/nút, tham chiếu, cấu trúc cây và có thể cả boxing; nó không gọn như một int[] khi R nhỏ.

**HashMap không tự sắp xếp:** nếu dùng HashMap để đếm, không được duyệt entry rồi giả định khóa ra theo thứ tự. Phải lấy k khóa ra và sắp xếp, khi đó chi phí gồm O(n) trung bình cho đếm và O(k log k) cho sắp xếp khóa, cộng thời gian ghi n phần tử.

Các phương án sparse phù hợp khi dữ liệu có nhiều giá trị lặp và trải trên miền rộng. Nếu k xấp xỉ n, TreeMap có thể cần nhiều bộ nhớ và chi phí so sánh hơn sắp xếp trực tiếp mảng bằng thuật toán so sánh.

## 6. Nén tọa độ: tạo miền nhỏ từ tập khóa đang có

**Coordinate compression** biến các giá trị thưa, rất lớn thành chỉ số liên tiếp từ 0 đến k−1 trong khi giữ nguyên thứ tự giữa các giá trị khác nhau.

Ví dụ:

~~~text
Giá trị gốc:        [-2_000_000_000, 5, 900_000_000, 5]
Các khóa đã sắp:    [-2_000_000_000, 5, 900_000_000]
Chỉ số nén:         [0, 1, 2]
Mảng khóa đã nén:   [0, 1, 2, 1]
Số lần theo chỉ số: [1, 2, 1]
~~~

Khi cần dựng dữ liệu đã sắp, duyệt các chỉ số nén theo thứ tự tăng rồi ánh xạ ngược về giá trị gốc. Nếu dữ liệu là bản ghi và cần stable, cần lưu ánh xạ chỉ số và thực hiện phân phối ổn định theo tần suất trên **miền nén k**, không chỉ dựng lại các khóa.

Cách làm thường gặp:

1. Tạo một danh sách chứa các khóa của n phần tử.
2. Sắp xếp danh sách và loại trùng để lấy k khóa tăng dần.
3. Ánh xạ mỗi khóa ban đầu tới thứ hạng của nó (qua binary search hoặc map).
4. Dùng chỉ số nén trong những bước đếm, prefix sum hoặc cấu trúc hỗ trợ khác.

Nén tọa độ giúp giảm **bộ đếm** từ O(R) xuống O(k), nhưng **không miễn phí**: bước lấy thứ tự các khóa thường cần so sánh/sắp xếp, ví dụ O(n log n) thời gian nếu sắp xếp toàn bộ n khóa. Đừng nói “nén tọa độ + counting sort luôn O(n)”; chi phí tiền xử lý có thể chi phối.

Nén đặc biệt có ích khi nhiều thao tác tiếp theo cần làm trên các **thứ hạng** (Fenwick tree, segment tree, frequency prefix queries) chứ không chỉ sắp xếp đúng một lần.

## 7. Radix sort: chi phí theo chữ số, không theo độ rộng liên tục R

Với số nguyên có độ dài bit cố định, **radix sort** có thể phân nhóm theo từng chữ số/cụm bit mà không cần mảng kích thước R. Ví dụ với int 32 bit:

- Chọn cơ số B = 256, tức một byte gồm 8 bit.
- Có d = 4 lượt, từ byte thấp lên byte cao (LSD radix).
- Mỗi lượt tạo mảng đếm 256 nhóm và phân phối **ổn định** các phần tử sang một buffer.
- Sau 4 lượt, toàn bộ khóa được sắp xếp theo thứ tự byte nếu thứ tự byte được thiết kế đúng.

Với một lượt có n phần tử và B nhóm, chi phí là **O(n + B)**; với d lượt là **O(d(n + B))**. Đối với int 32 bit, d = 4 và B = 256 cố định, nên có thể xem là O(n) theo số phần tử trong mô hình khóa cố định. Bộ nhớ phụ cần **O(n + B)**: một buffer chứa n số nguyên và vài mảng nhóm kích thước 256.

Điều này khác dense counting sort ở chỗ **không cấp phát R bucket**. Dù có hai khóa ở hai đầu miền int, ta vẫn chỉ dùng 256 nhóm trên mỗi lượt.

**Đổi lại**, radix cần đi qua dữ liệu nhiều lượt, và buffer O(n) có thể quá lớn trong hệ thống bộ nhớ chật. Với khóa có độ dài biến đổi như chuỗi hoặc số nguyên tùy ý, phải tính chi phí theo số chữ số/byte thật, không mặc định bốn lượt.

## 8. Số âm và tính ổn định trong radix sort

Nếu chỉ coi các bit của int Java là số nguyên **không dấu**, các giá trị âm sẽ đứng phía sau giá trị không âm khi sắp theo thứ tự bit không dấu. Điều này **không đúng** với thứ tự tăng dần có dấu thông thường của Java.

Trong chương trình bên dưới, ta dùng khóa biến đổi:

~~~text
transformed = value XOR Integer.MIN_VALUE
bucket = (transformed >>> (pass * 8)) & 255
~~~

XOR với Integer.MIN_VALUE đảo **bit dấu**: nhóm giá trị âm nằm trước nhóm không âm theo thứ tự không dấu của khóa biến đổi, trong khi trật tự nội bộ của từng nửa vẫn được giữ. Sau khi sắp 4 byte theo transformed, thứ tự thu được tương ứng với int tăng dần có dấu. Dữ liệu gốc vẫn được ghi ra, **không** bị biến thành khóa XOR.

Từng lượt counting theo byte phải **ổn định**: các phần tử có cùng byte hiện tại giữ nguyên thứ tự tương đối do các lượt byte thấp tạo ra. Trong chương trình, starts[bucket] được xây từ tổng tiền tố, sau đó đi qua source từ trái qua phải và ghi vào target theo vị trí đang tăng. Đây là cách duy trì tính ổn định của từng lượt.

Nếu chỉ nhóm theo byte nhưng làm mất trật tự trong các nhóm có byte bằng nhau, phép xử lý LSD từ thấp lên cao có thể tạo kết quả sai. Đây là khác biệt giữa “đếm để tái tạo giá trị” và “đếm để phân phối bản ghi một cách ổn định”.

## 9. Bucket sort và các chi phí dễ bị bỏ quên

**Bucket sort** ánh xạ giá trị vào các nhóm theo một quy tắc phân bố, sắp xếp bên trong mỗi nhóm rồi nối nhóm theo thứ tự. Cần cân nhắc ba loại bộ nhớ:

1. Bộ nhớ để quản lý các bucket (một mảng có B đầu nhóm hoặc các đối tượng danh sách).
2. Bộ nhớ để chứa phần tử bên trong các bucket (thường tổng O(n), cộng dung lượng dự phòng của các collection).
3. Bộ nhớ và stack mà thuật toán sắp xếp **từng bucket** sử dụng.

Độ phức tạp không tự động là O(n): nếu mọi phần tử dồn vào một bucket, công việc bên trong có thể giống sắp xếp n phần tử bằng một thuật toán so sánh. Phân bố đều và cách chọn B có vai trò quan trọng. Trong trường hợp phân bố rất lệch hoặc không rõ, một phương án có bảo đảm O(n log n) có thể đáng tin hơn.

**Bucket theo giá trị thưa** không đồng nghĩa phải tạo mọi bucket từ min tới max. Có thể cấp bucket theo nhóm thực sự được sử dụng, nhưng sau đó phải xác định thứ tự các nhóm, tương tự bài toán duy trì thứ tự khóa trong map.

## 10. So sánh các chiến lược theo thời gian và bộ nhớ

| Chiến lược | Thời gian thường dùng để phân tích | Bộ nhớ phụ | Phù hợp nhất khi |
| --- | --- | --- | --- |
| Counting trực tiếp, ghi đè int | O(n + R) | O(R) | R nhỏ so với ngân sách bộ nhớ |
| Stable counting cho bản ghi | O(n + R) | O(n + R) | R nhỏ và cần giữ thứ tự bản ghi bằng khóa |
| TreeMap đếm các khóa đang có | O(n log(k + 1) + n + k) | O(k) entry cùng overhead | R rất lớn, k khá nhỏ |
| HashMap đếm + sort k khóa | O(n) trung bình cho đếm, O(k log k) cho sort, cộng O(n) xuất | O(k) và bộ nhớ phụ của sort | Khóa thưa, muốn lựa chọn cách sắp xếp khóa |
| Nén tọa độ rồi đếm | Thường O(n log n) tiền xử lý + O(n + k) phân phối | O(n + k) tùy hiện thực | Cần tái sử dụng thứ hạng cho nhiều thao tác |
| Radix LSD, 4 byte/int | O(4(n + 256)) | O(n + 256) | Khóa int 32 bit, đủ RAM cho buffer |
| Bucket sort | Phụ thuộc phân bố và cách sort từng bucket | O(n + B) thường gặp, cộng overhead | Có giả thiết phân bố hoặc quy tắc chia nhóm tốt |
| Sắp xếp so sánh trên mảng | O(n log n) với thuật toán có bảo đảm tương ứng | Phụ thuộc thuật toán/cài đặt | Không muốn cấp phát theo miền R hoặc khó khai thác cấu trúc khóa |

Trong bảng, O(k) của TreeMap là **số entry**, không phải cam kết mỗi entry chiếm vài byte. Các phương thức nén, map, bucket và radix có thể sử dụng cấu trúc trung gian với overhead khác nhau. Với Java, hãy đo peak heap và throughput trên dữ liệu thật nếu bài toán ở gần giới hạn bộ nhớ.

## 11. Chương trình Java 17+ đối chiếu ba phương án

Chương trình minh họa:

- **sortDenseCounting:** chỉ cấp phát mảng đếm nếu R nằm trong ngưỡng MAX_DENSE_BINS; xử lý số âm bằng độ lệch so với min, ghi đè giá trị trong mảng.
- **sortSparseTreeMap:** giữ bộ đếm cho k khóa thực xuất hiện, có thứ tự ngay trong cấu trúc cây.
- **sortSignedRadix:** chia khóa thành bốn byte, dùng 256 nhóm mỗi lượt và xử lý dấu bằng XOR với Integer.MIN_VALUE; đầu ra nằm trong mảng truyền vào.

Tệp đầy đủ có tên **DistributionSortMemory.java**:

~~~java
import java.util.Arrays;
import java.util.Map;
import java.util.TreeMap;

public final class DistributionSortMemory {
    private static final int MAX_DENSE_BINS = 1_000_000;

    private DistributionSortMemory() {
    }

    private static void requireArray(int[] a) {
        if (a == null) {
            throw new IllegalArgumentException("array must not be null");
        }
    }

    public static void sortDenseCounting(int[] a) {
        requireArray(a);
        if (a.length < 2) {
            return;
        }

        int min = a[0];
        int max = a[0];
        for (int value : a) {
            if (value < min) {
                min = value;
            }
            if (value > max) {
                max = value;
            }
        }

        long bins = (long) max - (long) min + 1L;
        if (bins > MAX_DENSE_BINS) {
            throw new IllegalArgumentException("value range is too wide");
        }

        int[] frequency = new int[(int) bins];
        for (int value : a) {
            frequency[(int) ((long) value - min)]++;
        }

        int index = 0;
        for (int bucket = 0; bucket < frequency.length; bucket++) {
            int value = (int) ((long) min + bucket);
            for (int remaining = frequency[bucket]; remaining > 0; remaining--) {
                a[index++] = value;
            }
        }
    }

    public static void sortSparseTreeMap(int[] a) {
        requireArray(a);
        TreeMap<Integer, Integer> frequency = new TreeMap<>();
        for (int value : a) {
            frequency.merge(value, 1, Integer::sum);
        }

        int index = 0;
        for (Map.Entry<Integer, Integer> entry : frequency.entrySet()) {
            for (int i = 0; i < entry.getValue(); i++) {
                a[index++] = entry.getKey();
            }
        }
    }

    public static void sortSignedRadix(int[] a) {
        requireArray(a);
        int[] buffer = new int[a.length];
        int[] source = a;
        int[] target = buffer;
        int[] counts = new int[256];
        int[] starts = new int[256];

        for (int pass = 0; pass < 4; pass++) {
            Arrays.fill(counts, 0);
            int shift = pass * 8;

            for (int value : source) {
                int bucket = ((value ^ Integer.MIN_VALUE) >>> shift) & 0xFF;
                counts[bucket]++;
            }

            starts[0] = 0;
            for (int b = 1; b < 256; b++) {
                starts[b] = starts[b - 1] + counts[b - 1];
            }

            for (int value : source) {
                int bucket = ((value ^ Integer.MIN_VALUE) >>> shift) & 0xFF;
                target[starts[bucket]++] = value;
            }

            int[] temporary = source;
            source = target;
            target = temporary;
        }

        if (source != a) {
            System.arraycopy(source, 0, a, 0, a.length);
        }
    }

    private static void checkOne(int[] input) {
        int[] expected = input.clone();
        Arrays.sort(expected);

        int[] dense = input.clone();
        int[] sparse = input.clone();
        int[] radix = input.clone();
        sortDenseCounting(dense);
        sortSparseTreeMap(sparse);
        sortSignedRadix(radix);

        if (!Arrays.equals(expected, dense)
                || !Arrays.equals(expected, sparse)
                || !Arrays.equals(expected, radix)) {
            throw new AssertionError("Mismatch on " + Arrays.toString(input));
        }
    }

    private static void verifySmallCases() {
        int[] alphabet = {-2, 0, 2};
        int checked = 0;
        for (int length = 0; length <= 5; length++) {
            int combinations = 1;
            for (int i = 0; i < length; i++) {
                combinations *= alphabet.length;
            }

            for (int encoded = 0; encoded < combinations; encoded++) {
                int[] input = new int[length];
                int remaining = encoded;
                for (int i = 0; i < length; i++) {
                    input[i] = alphabet[remaining % alphabet.length];
                    remaining /= alphabet.length;
                }
                checkOne(input);
                checked++;
            }
        }

        int[] extremes = {
            Integer.MAX_VALUE, -2, Integer.MIN_VALUE, 5, -2
        };
        int[] reference = extremes.clone();
        Arrays.sort(reference);
        int[] sparse = extremes.clone();
        int[] radix = extremes.clone();
        sortSparseTreeMap(sparse);
        sortSignedRadix(radix);

        if (!Arrays.equals(reference, sparse)
                || !Arrays.equals(reference, radix)) {
            throw new AssertionError("Extreme values test failed");
        }

        System.out.println("Verified " + checked + " generated arrays: PASS");
        System.out.println("Extreme values test: PASS");
    }

    public static void main(String[] args) {
        int[] smallDomain = {3, -1, 2, -1, 0, 3};
        sortDenseCounting(smallDomain);
        System.out.println("Dense: " + Arrays.toString(smallDomain));

        int[] sparseDomain = {
            Integer.MAX_VALUE, -2, Integer.MIN_VALUE, 5, -2
        };
        int[] radixInput = sparseDomain.clone();
        sortSparseTreeMap(sparseDomain);
        sortSignedRadix(radixInput);
        System.out.println("Sparse: " + Arrays.toString(sparseDomain));
        System.out.println("Radix: " + Arrays.toString(radixInput));

        long fullRange = (long) Integer.MAX_VALUE
                - (long) Integer.MIN_VALUE + 1L;
        System.out.println("Full int domain bins: " + fullRange);

        try {
            sortDenseCounting(radixInput);
            System.out.println("Dense range guard: FAILED");
        } catch (IllegalArgumentException expected) {
            System.out.println("Dense range guard: PASS");
        }
        verifySmallCases();
    }

~~~

Biên dịch và chạy tại thư mục có tệp:

~~~bash
javac DistributionSortMemory.java
java DistributionSortMemory
~~~

Kết quả chính xác:

~~~text
Dense: [-1, -1, 0, 2, 3, 3]
Sparse: [-2147483648, -2, -2, 5, 2147483647]
Radix: [-2147483648, -2, -2, 5, 2147483647]
Full int domain bins: 4294967296
Dense range guard: PASS
Verified 364 generated arrays: PASS
Extreme values test: PASS
~~~

Phần tự kiểm tra lấy bảng ký tự thử {-2, 0, 2}, sinh tất cả các mảng độ dài 0 đến 5: 1 + 3 + 9 + 27 + 81 + 243 = **364 mảng**. Cả ba phương án được chạy trên bản sao độc lập và kết quả được so sánh với Arrays.sort. Các mảng thử này đều có R nhỏ nên dense được phép cấp phát. Tiếp theo, bài thử biên chứa Integer.MIN_VALUE và Integer.MAX_VALUE chỉ kiểm tra sparse và radix, vì dense phải từ chối miền quá rộng.

**Giới hạn bài mẫu:** phương thức dense ghi đè mảng int nên không thể được dùng làm chứng cứ cho tính ổn định đối với bản ghi có trường phụ. Ba phương thức được minh họa theo hợp đồng “sắp xếp số nguyên tăng dần”, không phải API tự động chọn phương án tối ưu cho mọi tập dữ liệu.

## 12. Phân tích bộ nhớ thực tế của ví dụ

Trong trường hợp dense, ngoài mảng đầu vào đã có sẵn, cấp thêm một int[] có độ dài R; khi R = 1.000.000, phần tử int chiếm khoảng 4.000.000 byte, tức xấp xỉ 3,81 MiB, chưa tính overhead. Trong trường hợp R nhỏ hơn, phần bộ nhớ này giảm theo R.

Trong sparse TreeMap, số entry bằng k; mỗi entry là một phần của cây cân bằng và dữ liệu được đóng gói dưới dạng đối tượng tham chiếu/giá trị. Cùng k, nó có thể tốn nhiều byte hơn một int[] dài k. Nhưng nếu k chỉ là 10 trong khi R là một tỷ, sự chênh lệch số lượng bucket thường quan trọng hơn overhead mỗi entry.

Trong radix, buffer int[] chứa n giá trị, tương ứng gần 4n byte dữ liệu, cộng hai mảng đếm/vị trí 256 phần tử (khoảng 2 KiB dữ liệu số nguyên) và một số biến cục bộ. Với n rất lớn, buffer O(n) là khoản mục chính; với n nhỏ, phần 256 nhóm gần như cố định. Trong triển khai minh họa, sau bốn lượt, dữ liệu trả về mảng đầu vào; không tạo bốn buffer khác nhau.

**Không nên cộng nhầm dữ liệu đã có với bộ nhớ phụ:** khi phân tích extra space, mảng input ban đầu không được tính là vùng nhớ cấp thêm; khi lập kế hoạch heap thực tế, **cả input lẫn bộ nhớ phụ** đều chiếm RAM. Hai cách đo phục vụ hai câu hỏi khác nhau.

## 13. Ra quyết định theo n, R, k và loại khóa

Một quy trình chọn chiến lược có thể áp dụng được:

1. **Xác định hợp đồng dữ liệu.** Khóa là int/long, chuỗi hay số thực? Sắp xếp khóa hay bản ghi? Có cần ổn định không? Có được thay đổi mảng gốc không?
2. **Kiểm tra đầu vào đặc biệt.** Với n ≤ 1, không cần một cấu trúc phân phối đầy đủ; với mảng rỗng, không có min/max.
3. **Đo R một cách an toàn.** Với int, dùng long cho max − min + 1; so với ngân sách, không chỉ với n.
4. **Ước lượng k hoặc mức độ thưa.** Nếu số khóa khác nhau ít, cân nhắc map tần suất hoặc nén tọa độ. Không bắt buộc phải đếm k bằng một cấu trúc đắt đỏ nếu có thể chọn tốt từ đặc trưng đầu vào.
5. **Xem xét kiểu khóa cố định.** Với int 32 bit và đủ bộ nhớ cho buffer, radix là lựa chọn không phụ thuộc R; với khóa dài biến thiên, chi phí theo byte và thứ tự từ điển phải được tính lại.
6. **Đánh giá giới hạn hệ thống.** Nhiều request chạy đồng thời, kích thước heap, áp lực GC, cache locality và độ trễ có thể làm phương án lý thuyết nhanh hơn lại chậm hơn.
7. **Kiểm chứng trước khi tối ưu.** So với một thuật toán sắp xếp chuẩn trên các trường hợp nhỏ, mảng có số âm, phần tử trùng, mảng toàn bằng nhau, giá trị int cực trị và đầu vào tăng/giảm.

Hai ví dụ ra quyết định:

- **n = 1.000.000, R = 20:** counting sort có thể rất hấp dẫn vì mảng tần suất nhỏ; cần kiểm tra điều kiện stable nếu sắp xếp bản ghi.
- **n = 100, R = 2^32, k = 4:** tuyệt đối không dùng mảng đếm phủ toàn miền; TreeMap tần suất hoặc một thuật toán so sánh đơn giản có thể phù hợp hơn, còn radix có thể hoạt động nhưng chi phí bốn lượt khó có lợi khi n rất nhỏ.

Không có một ngưỡng R/n duy nhất phù hợp cho mọi môi trường. Hãy dựa trên giới hạn bộ nhớ thực tế và benchmark.

## 14. Lỗi phổ biến và trường hợp biên

| Tình huống | Cần làm đúng | Lỗi thường gặp |
| --- | --- | --- |
| Mảng rỗng | Trả về rỗng trước khi tính min/max | Truy cập a[0] |
| Một phần tử | Không cần phân phối | Cấp phát mảng đếm khổng lồ |
| Nhiều phần tử trùng | Đếm đúng tần suất và bảo toàn số lần xuất hiện | Làm mất bản sao khi dùng set |
| Có số âm | Dùng v − min an toàn hoặc ánh xạ bit phù hợp | Dùng v trực tiếp làm chỉ số âm |
| Đầu miền int cực trị | Tính R bằng long trước khi cấp phát | Overflow int làm R sai |
| R lớn, n nhỏ | Chọn phương án sparse, radix hoặc so sánh | Tạo int[R] rồi gặp OOM |
| HashMap tần suất | Sắp xếp khóa trước khi xuất | Tin rằng HashMap duyệt theo thứ tự |
| Stable LSD radix | Giữ thứ tự trong từng nhóm qua mỗi pass | Phân phối không stable |
| Sắp xếp int có dấu | Xử lý bit dấu nhất quán | Sắp xếp như int không dấu |
| Sorting bản ghi | Giữ payload và tính ổn định nếu cần | Chỉ viết lại khóa và đánh mất bản ghi |
| Bộ nhớ gấp | Tính cả input, buffer, map và concurrent tasks | Chỉ tính mảng frequency |

**Lỗi tính toán bộ nhớ:** 1 GiB = 1.073.741.824 byte, khác với 1 GB = 1.000.000.000 byte. Khi tính gần ngưỡng RAM, cần phân biệt đơn vị và tính thêm overhead.

**Tràn số khi nhân kích thước:** nếu ước lượng bytes = 4 × R bằng int, kết quả có thể tràn. Dùng long hoặc số nguyên lớn hơn khi ước lượng, đồng thời kiểm tra giới hạn riêng của JVM và hệ điều hành.

## 15. Bài tập vận dụng

**Bài 1 — Chọn cấu trúc:** Với n = 10.000 bản ghi và các khóa phân bố trong [−1.000.000.000, 1.000.000.000] nhưng chỉ có k = 20 khóa khác nhau, đề xuất ít nhất hai giải pháp. So sánh cấu trúc đếm, chi phí khởi tạo, yêu cầu ổn định và chi phí dựng đầu ra.

**Bài 2 — Stable counting sau nén:** Viết giả mã nén các khóa thành 0..k−1 rồi dùng prefix sum để phân phối các bản ghi theo thứ tự khóa, giữ nguyên thứ tự những bản ghi bằng khóa. Hãy nêu rõ chi phí lấy danh sách k khóa có thứ tự, chi phí ánh xạ khóa và mảng output n phần tử.

**Bài 3 — Radix với số âm:** Giải thích bằng thứ tự bit tại sao Integer.MIN_VALUE phải đứng trước 0 trong sắp xếp tăng dần có dấu. Thử với các giá trị −1, 0, Integer.MIN_VALUE và Integer.MAX_VALUE và kiểm tra biến đổi XOR bit dấu.

**Bài 4 — Giới hạn bộ nhớ:** Cho phép dùng tối đa 64 MiB bộ nhớ phụ, n = 5.000.000 và R = 10.000.000. Ước lượng dung lượng frequency, output và phần còn lại. Hỏi việc cấp phát đồng thời có vừa ngân sách hay không; nêu giả thiết về kích thước phần tử, overhead và bộ nhớ runtime.

**Câu hỏi tổng kết:** Vì sao R rất lớn không nhất thiết có nghĩa k lớn? Tại sao stable counting sort cần phân phối bản ghi thay vì chỉ ghi lại giá trị? Vì sao radix int có thể dùng 256 bucket ngay cả khi dữ liệu trải dài toàn miền 32 bit? Khi nào không nên dùng bất kỳ thuật toán phân phối nào?

**Kết luận:** Khi phân tích sắp xếp phân phối, đừng chỉ hỏi “có thể chạy O(n) không?”. Hãy hỏi **O(n) theo giả thiết nào và phải trả bao nhiêu bộ nhớ theo R, k, B và n?** Với miền nhỏ, đếm trực tiếp đơn giản và hiệu quả. Với miền cực rộng nhưng dữ liệu thưa, dùng lưu trữ sparse hoặc nén tọa độ. Với khóa có độ dài bit cố định, radix tránh phụ thuộc vào R nhưng cần buffer theo n. Chọn đúng cấu trúc là một bài toán thiết kế về cả **thời gian, bộ nhớ và đặc tả đầu ra**.
