# Phân biệt cận lý thuyết với số đo trên một bộ dữ liệu

## 1. Hai câu hỏi khác nhau về chi phí thuật toán

Khi đánh giá một thuật toán, cần phân biệt:

1. **Cận lý thuyết:** Khi kích thước đầu vào n thay đổi, số phép toán hoặc lượng bộ nhớ mà thuật toán cần có thể tăng theo quy luật nào, dưới những giả định nào? Đây là phát biểu về một **họ đầu vào** và một mô hình tính toán.
2. **Số đo thực nghiệm:** Một bản cài đặt cụ thể mất bao nhiêu thời gian, bộ nhớ hoặc tài nguyên khi chạy trên **bộ dữ liệu cụ thể**, thiết bị, JVM và cấu hình cụ thể? Đây là quan sát có điều kiện, chịu ảnh hưởng của môi trường đo.

Ví dụ, tìm kiếm nhị phân trên mảng đã sắp xếp có cận thời gian tệ nhất O(log n), còn tìm kiếm tuyến tính có cận O(n). Điều đó **không có nghĩa** lần chạy tìm kiếm nhị phân nào cũng có số nano giây nhỏ hơn lần chạy tuyến tính. Với mảng rất ngắn, phần tử ở ngay đầu hoặc bộ nhớ đệm thuận lợi, tìm kiếm tuyến tính có thể nhanh hơn trong một phép đo. Hai kết quả này không mâu thuẫn: một bên mô tả xu hướng tăng trưởng khi n đủ lớn trong mô hình xác định; bên kia mô tả thời gian thực tế trên một trường hợp.

| Tiêu chí | Cận lý thuyết | Số đo trên bộ dữ liệu |
| --- | --- | --- |
| Đối tượng | Thuật toán và họ đầu vào hợp lệ | Cài đặt, bộ dữ liệu, máy và phiên chạy |
| Đại lượng | Số phép toán, lần truy cập, bộ nhớ phụ... | ns, ms, thông lượng, bộ nhớ cấp phát... |
| Phụ thuộc n | Phân tích hàm theo kích thước n | Quan sát tại một hoặc vài kích thước cụ thể |
| Kết quả | O, Ω, Θ hoặc công thức chặt hơn | Số đo cùng đơn vị, độ phân tán, điều kiện đo |
| Cơ sở | Lập luận, đếm phép toán, chứng minh | Thí nghiệm và đo đạc |
| Giới hạn | Phụ thuộc mô hình và giả định | Phụ thuộc dữ liệu, cấu hình, độ nhiễu |
| Điều không thể kết luận | Không cho thời gian tuyệt đối | Không tự chứng minh cận cho mọi đầu vào |

Cả hai đều hữu ích: phân tích lý thuyết cho biết khả năng mở rộng về nguyên tắc; đo đạc giúp lựa chọn và tối ưu một cài đặt trong bối cảnh sử dụng thực tế.

## 2. Phải xác định n, miền đầu vào và mô hình chi phí

Trước khi viết O(n) hoặc O(log n), hãy trả lời ba câu hỏi:

- **n là gì?** Số phần tử mảng, số đỉnh V và cạnh E, độ dài chuỗi, số chữ số, số truy vấn hay tổng kích thước dữ liệu? Với đồ thị thường cần T(V, E), không ép mọi thứ vào một n mơ hồ.
- **Đầu vào hợp lệ có những tính chất gì?** Đã sắp xếp, trọng số không âm, không có chu trình, cấu trúc cân bằng... Những giả định này quyết định cận nào áp dụng.
- **Đếm chi phí nào?** So sánh khóa, phép cộng, thao tác trên mảng, lần truy cập bộ nhớ, số bộ nhớ phụ hoặc thời gian theo mô hình RAM. Một thao tác “hằng số” trong mô hình đơn giản chưa chắc có độ trễ cố định trên phần cứng thực.

Có thể mô tả chi phí của một đầu vào cụ thể x bằng C(x). Khi kích thước được xác định, chi phí tệ nhất có dạng:

~~~text
T_worst(n) = max { C(x) : x là đầu vào hợp lệ có kích thước n }
~~~

Đây là giá trị lớn nhất **trên toàn bộ họ đầu vào hợp lệ cùng kích thước n**. Một lần đo C(x₀) chỉ cho biết chi phí của x₀; nó không xác định giá trị lớn nhất trên tất cả x.

Nếu xử lý n phần tử trên mảng và mỗi phần tử được xét đúng một lần với chi phí hằng số, số lần xét tăng tuyến tính theo n. Nhưng nếu việc “xét một phần tử” bao gồm thao tác xử lý chuỗi có độ dài biến thiên, phải tính cả chi phí đó. Chỉ chọn mô hình chi phí sau khi hiểu hành vi thực tế.

## 3. Hiểu đúng O, Ω và Θ

Với hàm chi phí T(n) không âm khi n đủ lớn, và hàm f(n) dương:

- **O(f(n)) — cận trên tiệm cận:** tồn tại các hằng số c > 0 và n₀ sao cho T(n) ≤ c·f(n) với mọi n ≥ n₀.
- **Ω(f(n)) — cận dưới tiệm cận:** tồn tại c > 0 và n₀ sao cho T(n) ≥ c·f(n) với mọi n ≥ n₀.
- **Θ(f(n)) — cận chặt tiệm cận:** vừa thuộc O(f(n)) vừa thuộc Ω(f(n)), tức tăng trưởng bị kẹp trên và dưới bởi các bội số hằng của f(n) khi n đủ lớn.

Các ký hiệu này **không mặc nhiên chỉ trường hợp tệ nhất**. Ta có thể nói T_best(n) = Θ(1), T_worst(n) = Θ(n) và T_average(n) = Θ(n) cho tìm kiếm tuyến tính theo các giả định thích hợp. Phải ghi rõ biến thể nào đang được phân tích.

Một thuật toán có T(n) = 3n + 7 là O(n), Ω(n) và Θ(n). Vì vậy, câu “độ phức tạp của thuật toán là O(n²)” chỉ khẳng định một cận trên; với T(n) = 3n + 7, phát biểu O(n²) cũng đúng nhưng lỏng hơn O(n). Nếu muốn khẳng định mức tăng trưởng chặt, dùng Θ và đưa ra lập luận tương ứng. Từ “cận dưới Ω(n)” cũng không đồng nghĩa “mọi thuật toán giải bài toán đều cần Ω(n)”: muốn kết luận **cận dưới của bài toán** phải chứng minh điều đó cho mọi thuật toán trong mô hình đang xét, không chỉ một thuật toán cụ thể.

Ký hiệu tiệm cận bỏ qua các hệ số nhân cố định, các số hạng bậc thấp và một tiền tố kích thước hữu hạn. Do đó:

~~~text
T_A(n) = 100n
T_B(n) = n log₂ n
~~~

Cả hai đều có biểu thức tăng trưởng khác nhau, nhưng với n nhỏ, hệ số 100 có thể khiến A tốn nhiều phép toán hơn B. Khi n rất lớn, n log n có tốc độ tăng nhanh hơn n. Không thể lấy một giá trị n duy nhất để xác định quan hệ tiệm cận.

## 4. Best case, worst case, average case và amortized

**Trường hợp tốt nhất (best case)** là đầu vào hợp lệ kích thước n có chi phí nhỏ nhất. **Trường hợp tệ nhất (worst case)** có chi phí lớn nhất. **Chi phí trung bình lý thuyết (average case)** cần một **phân phối xác suất được khai báo rõ** trên các đầu vào; không có phân phối thì nói “trung bình” có thể thiếu ý nghĩa.

Ví dụ với tìm kiếm tuyến tính trong mảng n phần tử:

- Khi target nằm ngay vị trí đầu, số phần tử được kiểm tra là 1: best case Θ(1).
- Khi target vắng mặt, phải kiểm tra n phần tử: worst case Θ(n).
- Nếu target chắc chắn có mặt, mỗi vị trí xuất hiện đều có xác suất 1/n, các phần tử phân biệt, thì số phép kiểm tra trung bình là (n + 1)/2: average case Θ(n).
- Nếu xác suất target vắng mặt cao, giá trị trung bình phụ thuộc thêm vào xác suất ấy; không thể tự dùng (n + 1)/2.

**Amortized analysis** là một khái niệm riêng: đánh giá chi phí trung bình trên **một chuỗi thao tác được quy định** và chứng minh tổng chi phí bị chặn, dù một số thao tác đơn lẻ tốn kém. Ví dụ một mảng động tăng dung lượng theo hệ số cố định có thao tác thêm phần tử đôi khi phải sao chép nhiều phần tử, nhưng chi phí thêm phần tử *khấu hao* là O(1) trong mô hình thích hợp. Điều này không có nghĩa mọi lần thêm đều O(1) ở trường hợp tệ nhất, và cũng không phải là “thời gian trung bình thu được từ 10 lần chạy”.

Một thống kê từ bộ dữ liệu thực nghiệm — ví dụ “trung bình 12 μs trên 100 truy vấn đã chọn” — là trung bình **mẫu đo**. Nó chỉ có thể đại diện cho hoạt động tương lai khi cách chọn dữ liệu và điều kiện đo thực sự đại diện.

## 5. Ví dụ đối chiếu: tìm kiếm tuyến tính và tìm kiếm nhị phân

Giả sử dữ liệu là mảng int tăng dần, phần tử phân biệt và truy cập ngẫu nhiên. Hai thuật toán đều trả về chỉ số của target hoặc −1 nếu vắng mặt.

| Điều kiện / thuộc tính | Tìm kiếm tuyến tính | Tìm kiếm nhị phân |
| --- | --- | --- |
| Cần dữ liệu đã sắp xếp? | Không | Có |
| Phép kiểm tra | Duyệt từ trái sang phải | So sánh phần tử giữa khoảng còn lại |
| Best case | Θ(1) | Θ(1) |
| Worst case | Θ(n) | Θ(log n) khi n đủ lớn |
| Bộ nhớ phụ cho bản lặp | Θ(1) | Θ(1) |
| Thực nghiệm có thể ảnh hưởng bởi | Tính liên tục bộ nhớ, vị trí target | Nhánh điều kiện, mẫu truy cập bộ nhớ, cache |

Với n là lũy thừa của 2 và target là **phần tử cuối cùng**, thuật toán tuyến tính phải kiểm tra n vị trí. Phiên bản tìm kiếm nhị phân dùng khoảng chỉ số đóng và chia đôi sẽ kiểm tra log₂(n) + 1 vị trí cho các n sau:

| n | Số vị trí tuyến tính kiểm tra | Số vị trí nhị phân kiểm tra |
| ---: | ---: | ---: |
| 128 | 128 | 8 |
| 4.096 | 4.096 | 13 |
| 65.536 | 65.536 | 17 |

Đây là **số bước từ thuật toán trên một đầu vào được chọn**, không phải số nano giây. Mỗi bước nhị phân có thể gồm nhiều phép so sánh nhánh và truy cập ở vị trí xa nhau; mỗi bước tuyến tính có thể tận dụng dữ liệu liên tục trong cache. Không được chuyển tỷ lệ 65.536/17 thành lời hứa “nhanh hơn 3.855 lần” trên máy thật.

Cần lưu ý tổng quy trình: nếu mảng **chưa sắp xếp**, muốn dùng tìm kiếm nhị phân có thể phải trả chi phí sắp xếp trước, thường O(n log n) bằng một thuật toán sắp xếp so sánh phù hợp, rồi O(log n) cho mỗi truy vấn. Với q truy vấn trên cùng dữ liệu được tái sử dụng, tổng cận có thể là O(n log n + q log n). Nếu chỉ có một truy vấn, quét tuyến tính O(n) có thể hợp lý hơn. Đây là phép so sánh hai **bài toán vận hành khác nhau** nếu quên tính bước chuẩn bị dữ liệu.

## 6. Đo thời gian thực nghiệm phải đặt trong ngữ cảnh

Một kết quả đo có thể hình dung như:

~~~text
observedTime = measure(implementation, dataset, environment, procedure)
~~~

Nó phụ thuộc ít nhất vào:

1. **Dataset:** kích thước n, phân phối giá trị, tỷ lệ truy vấn tìm thấy/không thấy, độ trùng lặp, vị trí target, thứ tự, dữ liệu có nằm trong cache không.
2. **Implementation:** ngôn ngữ, cấu trúc dữ liệu, kiểm tra lỗi, lựa chọn hàm thư viện, mức tối ưu, cấp phát bộ nhớ.
3. **Environment:** CPU, RAM, tải nền, giới hạn năng lượng, trạng thái cache, hệ điều hành, phiên bản JVM, bộ thu gom rác.
4. **Procedure:** thời gian khởi động, warm-up, số lượt lặp, thứ tự chạy các ứng viên, cách gộp kết quả, có tính thời gian tạo input/đọc file vào phép đo không.

Một chương trình Java vừa khởi động có thể chưa được JIT tối ưu giống chương trình chạy lâu. Những đợt garbage collection hoặc tác vụ nền có thể làm vài lượt đo chậm đột biến. Với thao tác quá ngắn, chi phí vòng lặp, đồng hồ và gọi hàm có thể chiếm tỷ lệ lớn. Vì vậy, phép đo chỉ một lần thường không đáng tin để so sánh sát sao.

**System.nanoTime()** phù hợp để đo khoảng thời gian trôi qua giữa hai mốc trong cùng tiến trình; giá trị tuyệt đối của nó không có ý nghĩa như giờ đồng hồ. **System.currentTimeMillis()** là đồng hồ lịch, độ phân giải và khả năng điều chỉnh thời gian khiến nó không phải lựa chọn tốt cho microbenchmark. Tuy nhiên, dùng nanoTime() không tự biến một vòng lặp thủ công thành phép đo chuẩn: JVM vẫn có thể tối ưu mã, làm nóng khác nhau và tạo nhiễu.

Khi quan sát bộ nhớ, phải làm rõ đang nói **bộ nhớ phụ theo cận lý thuyết**, **heap đã cấp phát**, **heap đang được sử dụng**, **RSS của tiến trình** hay **đỉnh sử dụng bộ nhớ**. Các đại lượng khác nhau không thể thay thế cho nhau.

## 7. Thực hành Java 17: cùng một bộ truy vấn, hai cách giải

Chương trình độc lập dưới đây tạo mảng số nguyên tăng dần và cùng một danh sách 3.000 truy vấn cho mỗi kích thước. Một phần năm truy vấn cố ý không tìm thấy (target = −1), còn lại truy vấn phần tử có mặt. Cả hai thuật toán xử lý **chính xác cùng tập truy vấn**. Chương trình kiểm tra hai kết quả khớp nhau, làm nóng mỗi cách, đo 5 lượt và lấy trung vị của **thời gian mỗi lượt / số truy vấn**.

Lưu tệp **TheoryVsMeasurement.java**:

~~~java
import java.util.Arrays;
import java.util.Locale;

public final class TheoryVsMeasurement {
    private static volatile long sink;

    private TheoryVsMeasurement() {}

    static int linearSearch(int[] a, int target) {
        for (int i = 0; i < a.length; i++) {
            if (a[i] == target) {
                return i;
            }
        }
        return -1;
    }

    static int binarySearch(int[] a, int target) {
        int left = 0;
        int right = a.length - 1;
        while (left <= right) {
            int mid = left + (right - left) / 2;
            int value = a[mid];
            if (value < target) {
                left = mid + 1;
            } else if (value > target) {
                right = mid - 1;
            } else {
                return mid;
            }
        }
        return -1;
    }

    // Number of array positions probed for this specific target.
    static int binaryProbes(int[] a, int target) {
        int left = 0;
        int right = a.length - 1;
        int probes = 0;
        while (left <= right) {
            int mid = left + (right - left) / 2;
            probes++;
            int value = a[mid];
            if (value < target) {
                left = mid + 1;
            } else if (value > target) {
                right = mid - 1;
            } else {
                return probes;
            }
        }
        return probes;
    }

    static long timeBatch(int[] a, int[] targets, boolean useBinary) {
        long checksum = 0;
        long start = System.nanoTime();
        for (int target : targets) {
            checksum += useBinary
                    ? binarySearch(a, target)
                    : linearSearch(a, target);
        }
        long elapsed = System.nanoTime() - start;
        sink = checksum; // Make the computed answers observable.
        return elapsed;
    }

    public static void main(String[] args) {
        int[] sizes = {128, 4096, 65536};
        final int queryCount = 3000;

        for (int n : sizes) {
            int[] data = new int[n];
            for (int i = 0; i < n; i++) {
                data[i] = i * 2;
            }

            int[] targets = new int[queryCount];
            for (int i = 0; i < queryCount; i++) {
                // These sizes are powers of two. Make repeatable queries.
                int index = (int) (((long) i * 1103515245L + 12345L)
                        & (n - 1L));
                targets[i] = i % 5 == 0 ? -1 : data[index];
            }

            for (int target : targets) {
                int linear = linearSearch(data, target);
                int binary = binarySearch(data, target);
                if (linear != binary) {
                    throw new AssertionError("Search result mismatch");
                }
            }

            for (int warmup = 0; warmup < 3; warmup++) {
                timeBatch(data, targets, false);
                timeBatch(data, targets, true);
            }

            long[] linearSamples = new long[5];
            long[] binarySamples = new long[5];
            for (int rep = 0; rep < 5; rep++) {
                linearSamples[rep] = timeBatch(data, targets, false);
                binarySamples[rep] = timeBatch(data, targets, true);
            }
            Arrays.sort(linearSamples);
            Arrays.sort(binarySamples);

            double linearNs = linearSamples[2] / (double) queryCount;
            double binaryNs = binarySamples[2] / (double) queryCount;

            System.out.printf(Locale.ROOT,
                    "n=%d | last probes: linear=%d, binary=%d"
                    + " | median: linear=%.1f ns/query, binary=%.1f ns/query%n",
                    n, n, binaryProbes(data, data[n - 1]),
                    linearNs, binaryNs);
        }
    }
}
~~~

Biên dịch và chạy với JDK 17 trở lên:

~~~bash
javac TheoryVsMeasurement.java
java TheoryVsMeasurement
~~~

Chương trình in **ba dòng**, mỗi dòng gồm số vị trí được kiểm tra ở trường hợp target cuối cùng và số đo thời gian. Phần đếm vị trí là xác định:

~~~text
n=128   -> last probes: linear=128, binary=8
n=4096  -> last probes: linear=4096, binary=13
n=65536 -> last probes: linear=65536, binary=17
~~~

Các mũi tên ở trên chỉ **trích riêng phần thông tin đếm bước**, không phải nguyên văn stdout: dòng thực tế còn có các trường thời gian, ví dụ “median: linear=... ns/query, binary=... ns/query”. **Giá trị ns/query không có đáp án số cố định** và phải lấy từ máy đang chạy; không được chép số đo bịa đặt vào bài báo cáo. Cặp giá trị đếm bước cũng thuộc truy vấn “target là phần tử cuối”, trong khi phép đo dùng hỗn hợp nhiều truy vấn; không so trực tiếp tỷ số đếm bước của trường hợp cuối với tỷ số thời gian của hỗn hợp.

Vì chương trình chỉ là minh họa cách đặt phép đo, không nên coi kết quả là benchmark đủ chặt để công bố. Để đo vi mô trên JVM nghiêm túc, nên dùng **JMH (Java Microbenchmark Harness)** với cấu hình warm-up, measurement, fork, state và blackhole phù hợp; JMH là thư viện/công cụ bổ sung, **không** có sẵn chỉ nhờ cài JDK 17. Ngay cả với JMH, vẫn cần thiết kế input và môi trường đo đúng mục tiêu.

## 8. Quy trình thực nghiệm đáng tin hơn

1. **Nêu rõ câu hỏi cần đo.** Chẳng hạn “với các mảng tăng dần có 80% truy vấn tìm thấy và 20% không thấy, thời gian trung vị/truy vấn thay đổi thế nào khi n tăng?” Câu hỏi phải gắn với tải công việc thực tế.
2. **Xác nhận tính đúng.** So sánh với oracle đơn giản hoặc kiểm thử thuộc tính trên đầu vào hợp lệ trước khi đo. Một thuật toán trả sai nhưng nhanh không phải lời giải có thể so sánh.
3. **Đặt các kích thước n có ý nghĩa.** Chọn nhiều cấp độ lớn nhỏ, tốt nhất cách nhau theo bội số để quan sát xu hướng. Không suy ra đồ thị tăng trưởng từ một điểm dữ liệu.
4. **Kiểm soát đặc trưng đầu vào.** Cùng kích thước không đồng nghĩa cùng độ khó: tìm giá trị ở đầu, cuối, vắng mặt hay trên phân phối lệch có thể khác nhau rất nhiều.
5. **Xác định ranh giới đo.** Nếu chi phí tạo mảng hay sắp xếp có phát sinh trong hệ thống thật, báo cáo riêng hoặc tính trong end-to-end; nếu chỉ đo truy vấn sau khi tiền xử lý, nói rõ.
6. **Lặp và ghi phân tán.** Warm-up phù hợp, đo nhiều lượt/fork, công bố trung vị cùng khoảng biến thiên hoặc phân vị; ghi cả số lượt đo. Tránh dùng một giá trị đẹp nhất.
7. **Giảm nhiễu và tối ưu hóa sai.** Hạn chế tải nền, theo dõi GC/JIT, bảo đảm kết quả phép tính được sử dụng, tránh phép đo quá ngắn; thay đổi thứ tự chạy để phát hiện ảnh hưởng cache hoặc thứ tự.
8. **Báo cáo khả năng tái lập.** Phiên bản Java, hệ điều hành, CPU, tùy chọn JVM, đặc tả input, seed sinh dữ liệu, đơn vị, số vòng lặp và cách tổng hợp đều có giá trị.
9. **Đối chiếu lý thuyết với thực nghiệm.** Một xu hướng quan sát được có thể *phù hợp* với cận dự đoán, nhưng không phải chứng minh tiệm cận. Nếu không phù hợp, xem lại miền dữ liệu, đơn vị chi phí, code, JIT và tiền xử lý.

Một báo cáo thí nghiệm hữu ích phân tách **giả thuyết**, **điều kiện**, **đơn vị đo**, **số liệu thực thu**, **độ bất định** và **kết luận có giới hạn**. Ví dụ: “Trong môi trường X, với bộ truy vấn Y và kích thước n thuộc tập Z, cài đặt A có trung vị nhỏ hơn B” là phát biểu có thể kiểm tra lại. Câu “A luôn nhanh hơn B vì O(log n) nhỏ hơn O(n)” là suy diễn quá mức.

## 9. Diễn giải số liệu và tránh kết luận sai

### Một điểm đo không xác định hàm tăng trưởng

Giả sử hai thuật toán đều mất 2 ms với n = 1.000 trong một bài thử. Điều này không chứng minh chúng có cùng Θ(n), cùng cận tệ nhất hoặc cùng chi phí ở n = 1.000.000. Hai hàm có thể trùng nhau tại một điểm nhưng khác nhau hoàn toàn về tăng trưởng. Nếu muốn suy đoán xu hướng, đo thêm nhiều kích thước và kiểm soát phân phối; để khẳng định cận, phải phân tích thuật toán.

### Tỷ lệ tốc độ chỉ có nghĩa trong bối cảnh đã đo

Nếu cùng bộ dữ liệu và thủ tục, A mất t_A và B mất t_B (đều dương), tỷ lệ t_A / t_B mô tả tốc độ **của chính phép thử ấy**. Tỷ lệ đó không phải tỷ lệ số phép toán tiệm cận và không tự áp dụng cho đầu vào hoặc máy khác. Với số đo nhỏ, cần xem độ phân tán trước khi diễn giải một chênh lệch vài phần trăm.

### Mô hình lý thuyết không phải số chu kỳ CPU

Cận O(log n) có thể dựa trên số phần tử kiểm tra, trong khi một lần đọc bộ nhớ khác vùng cache có độ trễ cao hơn rất nhiều lần đọc liên tục. Hiệu năng phần cứng còn phụ thuộc dự đoán nhánh, vector hóa, bộ nhớ cấp phát và tương tác GC. Ngược lại, một thuật toán có cận xấu hơn vẫn có thể hoạt động tốt cho kích thước dữ liệu thường gặp. Cần cân nhắc cả tính đúng, dữ liệu thực tế, thời gian phát triển và tính đơn giản của cài đặt.

### Phân biệt chi phí một truy vấn và chi phí cả chuỗi

Nếu cần 10.000 truy vấn trên một tập dữ liệu giữ nguyên, việc đầu tư sắp xếp hoặc xây dựng chỉ mục có thể được khấu trừ qua nhiều lượt truy vấn. Nếu chỉ cần 1 truy vấn, chi phí tiền xử lý có thể áp đảo. Khi báo cáo, nêu rõ n, số truy vấn q, tần suất cập nhật dữ liệu và chi phí xây dựng/duy trì cấu trúc.

## 10. Những lỗi thường gặp

- **Đọc O(n) như “mất n milli giây”.** Big-O không có đơn vị thời gian; nó mô tả tốc độ tăng trưởng của đại lượng đã chọn.
- **Nhìn một biểu đồ rồi “chứng minh” Θ(n).** Một số hữu hạn điểm đo không chứng minh mệnh đề với mọi n đủ lớn.
- **Không nói đến best/worst/average.** Một lần tìm thấy ngay đầu không đại diện cho trường hợp tệ nhất của tìm kiếm tuyến tính.
- **Nhầm O và Θ.** O(n²) có thể là cận trên đúng nhưng lỏng cho thuật toán thực tế Θ(n); không kết luận tốc độ tăng chính xác chỉ từ cận trên.
- **Dùng dữ liệu không đúng tiền điều kiện.** Kết quả tìm kiếm nhị phân trên mảng không sắp xếp không có giá trị để xác nhận thuật toán.
- **Đo hai cách trên hai bộ dữ liệu khác nhau.** Phải so sánh cùng phân phối, kích thước và điều kiện hoặc giải thích sự khác biệt.
- **Đo cả tạo dữ liệu ở một bên, bỏ ở bên kia.** Cần cùng ranh giới hoặc báo cáo từng công đoạn.
- **Không warm-up JVM, chỉ chạy một lần, hoặc không chống việc phép tính bị tối ưu bỏ.** Dễ thu được giá trị bị nhiễu hoặc không đo đúng phép tính định đo.
- **Đổi đơn vị mà không ghi.** Phải phân biệt ns/query, ms/batch, queries/s; tốc độ thông lượng và độ trễ là hai đại lượng khác nhau.
- **Cho rằng thời gian đo nhỏ hơn nghĩa là thuật toán tốt hơn về mọi mặt.** Cần xét bộ nhớ, độ ổn định, trường hợp biên, chi phí chuẩn bị và tính đúng.

## 11. Checklist khi đọc một kết quả phân tích/benchmark

Trước khi tin một tuyên bố “thuật toán A tốt hơn B”, tự hỏi:

- Kích thước n là gì và dữ liệu có đáp ứng tiền điều kiện của hai thuật toán?
- Phát biểu O/Ω/Θ nói về best, worst, average hay amortized? Mô hình chi phí là gì?
- Chi phí tiền xử lý, cấp phát và số lần truy vấn có được tính nhất quán?
- Số đo được lấy ở máy/JVM nào, trên input nào, trong bao nhiêu lượt?
- Đơn vị, trung vị, độ phân tán và sai số đo có được nêu?
- Hai phiên bản có trả **kết quả đúng tương đương** trên cùng dữ liệu?
- Kết luận có chỉ giới hạn trong điều kiện đo hay đã suy rộng quá mức?

**Nguyên tắc cốt lõi:** Cận lý thuyết giúp hiểu mức tăng trưởng và các giới hạn có thể chứng minh; số đo giúp hiểu hiệu suất quan sát được trên dữ liệu và máy cụ thể. Dùng cận để lý giải khả năng mở rộng, dùng thí nghiệm để chọn cách cài đặt trong bối cảnh thật, và luôn ghi rõ giả định của từng kết luận.