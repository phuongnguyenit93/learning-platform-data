# Phân biệt thuật toán, cấu trúc dữ liệu và phân tích thuật toán

Trong bản đồ kiến thức về thuật toán, ba khái niệm **thuật toán (algorithm)**, **cấu trúc dữ liệu (data structure)** và **phân tích thuật toán (algorithm analysis)** luôn liên quan với nhau nhưng trả lời ba câu hỏi khác nhau:

- **Thuật toán:** Giải bài toán **bằng những bước nào** để nhận được kết quả đúng?
- **Cấu trúc dữ liệu:** **Tổ chức và truy cập dữ liệu ra sao** để các bước đó thực hiện được?
- **Phân tích thuật toán:** Giải pháp **đúng đến đâu, tốn bao nhiêu thời gian và bộ nhớ** khi quy mô đầu vào thay đổi?

Ví dụ, với yêu cầu “mảng số nguyên có phần tử trùng nhau hay không?”, ta có thể kiểm tra từng cặp phần tử hoặc dùng một tập hợp để ghi nhớ các giá trị đã thấy. Đây là **hai thuật toán/chiến lược xử lý**; mảng và tập hợp là **cấu trúc dữ liệu**; so sánh thời gian O(n²) với thời gian kỳ vọng O(n) và bộ nhớ phụ O(1) với O(n) là **phân tích thuật toán**.

## 1. Định nghĩa và ranh giới

| Khái niệm | Bản chất | Câu hỏi cần trả lời | Ví dụ |
| --- | --- | --- | --- |
| Thuật toán | Quy trình có các bước được xác định rõ, biến đầu vào thành đầu ra thỏa yêu cầu | Làm gì, theo thứ tự nào, điều kiện dừng là gì? | Tìm kiếm tuyến tính, tìm kiếm nhị phân, duyệt đồ thị BFS, sắp xếp trộn |
| Cấu trúc dữ liệu | Cách biểu diễn, lưu trữ, liên kết và cung cấp thao tác trên dữ liệu | Dữ liệu nằm ở đâu, truy cập/thêm/xóa/tra cứu như thế nào? | Mảng, danh sách liên kết, ngăn xếp, hàng đợi, bảng băm, cây, đồ thị |
| Phân tích thuật toán | Hoạt động lập luận, đo đạc và đánh giá tính đúng đắn cùng tài nguyên của giải pháp | Khi n tăng, thời gian/bộ nhớ tăng thế nào; giả định nào cần có? | Chứng minh tính đúng đắn, tính O(n log n), đo benchmark, xét ca xấu nhất |

**Thuật toán không đồng nghĩa với đoạn mã.** Một thuật toán là ý tưởng quy trình độc lập ngôn ngữ; Java, Python hoặc pseudocode chỉ là cách biểu diễn và hiện thực quy trình đó. Một chương trình có thể kết hợp nhiều thuật toán và nhiều cấu trúc dữ liệu.

**Cấu trúc dữ liệu không đồng nghĩa với tập dữ liệu cụ thể.** Dãy `[4, 7, 4]` là dữ liệu, còn kiểu mảng `int[]` là cách tổ chức dữ liệu. Trong Java, `Set<Integer>` biểu diễn hợp đồng “không chứa phần tử trùng nhau”; `HashSet<Integer>` là một cách hiện thực hợp đồng đó dựa trên bảng băm. Chọn cấu trúc dữ liệu là chọn các thao tác, chi phí và ràng buộc phù hợp với bài toán.

**Phân tích thuật toán không phải là một cách giải thay thế.** Nó đánh giá một thuật toán **trong bối cảnh cấu trúc dữ liệu và các giả định cụ thể**. Thuật toán phải được lập luận là đúng trước khi kết luận chạy nhanh; một chương trình trả kết quả sai trong O(1) vẫn không giải được bài toán.

## 2. Cùng bài toán, hai lựa chọn thuật toán và cấu trúc dữ liệu

**Đề bài:** Cho mảng `numbers` gồm n số nguyên; trả về `true` nếu tồn tại hai vị trí khác nhau có cùng giá trị. Không yêu cầu trả về vị trí hoặc danh sách giá trị trùng.

### Cách A: So sánh từng cặp

Duyệt từng vị trí `i`; với mỗi `i`, duyệt `j > i` và so sánh `numbers[i] == numbers[j]`. Nếu có cặp bằng nhau, trả về `true`; nếu duyệt hết, trả về `false`.

- **Thuật toán:** Duyệt và so sánh mọi cặp chưa xét, dừng sớm khi tìm thấy một cặp trùng.
- **Cấu trúc dữ liệu:** Chỉ mảng đầu vào; không cần tập hợp phụ.
- **Phân tích:** Trường hợp không có phần tử trùng, số lần so sánh là `(n − 1) + (n − 2) + ... + 1 = n(n − 1)/2`, nên thời gian xấu nhất **O(n²)**; bộ nhớ phụ **O(1)**. Nếu hai phần tử đầu tiên trùng nhau, có thể dừng sau một lần so sánh.

### Cách B: Dùng tập hợp các giá trị đã gặp

Quét mảng từ trái sang phải. Với mỗi phần tử, thử thêm vào `HashSet`; nếu thao tác `add` trả về `false` thì giá trị đã có và ta trả về `true`. Hết vòng lặp mà chưa gặp trùng thì trả về `false`.

- **Thuật toán:** Quét một lượt và kiểm tra phần tử đã xuất hiện hay chưa.
- **Cấu trúc dữ liệu:** Mảng đầu vào **và** `HashSet<Integer>` dùng để ghi nhớ các phần tử đã gặp.
- **Phân tích:** Trung bình/kỳ vọng, thao tác tra cứu và thêm phần tử trong bảng băm gần O(1) mỗi lần, nên tổng thời gian kỳ vọng **O(n)**; bộ nhớ phụ **O(n)** trong trường hợp các giá trị đều khác nhau. Tính chất O(1) là giả định về hàm băm, phân bố khóa và hiện thực, không phải bảo đảm tuyệt đối cho mọi tình huống.

Hai cách giải đều đúng, nhưng **đổi cấu trúc dữ liệu hỗ trợ đã đổi chi phí thời gian–bộ nhớ**. Với n nhỏ hoặc giới hạn bộ nhớ chặt, so sánh cặp có thể phù hợp; với n lớn và có đủ bộ nhớ, cách dùng tập hợp thường tốt hơn.

## 3. Cùng cấu trúc dữ liệu, hai thuật toán khác nhau

Giữ nguyên cấu trúc dữ liệu là **mảng `int[]`** và đổi bài toán thành “tìm chỉ số của giá trị `target`”.

- **Tìm kiếm tuyến tính (linear search):** Xem lần lượt từ đầu đến cuối. Hoạt động trên cả mảng chưa sắp xếp; thời gian xấu nhất O(n), bộ nhớ phụ O(1).
- **Tìm kiếm nhị phân (binary search):** So sánh với phần tử giữa, loại bỏ một nửa khoảng tìm kiếm sau mỗi bước. Đòi hỏi mảng **đã được sắp xếp theo đúng thứ tự so sánh**; thời gian xấu nhất O(log n), bộ nhớ phụ O(1) với bản lặp.

Điểm khác nhau nằm ở **thuật toán**, dù cả hai cùng thao tác trên mảng. Điều kiện “đã sắp xếp” là **tiền điều kiện**, không tự xuất hiện chỉ vì chọn tìm kiếm nhị phân. Nếu mảng ban đầu chưa sắp xếp và chỉ cần tìm một lần, việc sắp xếp trước còn phát sinh chi phí; tuyến tính có thể hợp lý hơn.

Cũng cần xác định chính xác đầu ra: hàm tuyến tính dưới đây trả về **vị trí xuất hiện đầu tiên**, trong khi tìm kiếm nhị phân thông thường chỉ bảo đảm trả về **một vị trí hợp lệ** nếu có nhiều giá trị bằng nhau. Khi đặc tả yêu cầu “vị trí đầu tiên”, thuật toán nhị phân phải được điều chỉnh.

## 4. Ví dụ Java 17+ chạy được

Lưu toàn bộ đoạn mã sau vào tệp `AlgorithmVsDataStructure.java`, sau đó chạy lệnh `javac AlgorithmVsDataStructure.java` và `java AlgorithmVsDataStructure`.

```java
import java.util.HashSet;
import java.util.Set;

public class AlgorithmVsDataStructure {
    static boolean hasDuplicateWithLoops(int[] numbers) {
        for (int i = 0; i < numbers.length; i++) {
            for (int j = i + 1; j < numbers.length; j++) {
                if (numbers[i] == numbers[j]) {
                    return true;
                }
            }
        }
        return false;
    }

    static boolean hasDuplicateWithSet(int[] numbers) {
        Set<Integer> seen = new HashSet<>();
        for (int number : numbers) {
            if (!seen.add(number)) {
                return true;
            }
        }
        return false;
    }

    static int linearSearch(int[] data, int target) {
        for (int i = 0; i < data.length; i++) {
            if (data[i] == target) {
                return i;
            }
        }
        return -1;
    }

    static int binarySearch(int[] sorted, int target) {
        int left = 0;
        int right = sorted.length - 1;
        while (left <= right) {
            int mid = left + (right - left) / 2;
            if (sorted[mid] == target) {
                return mid;
            }
            if (sorted[mid] < target) {
                left = mid + 1;
            } else {
                right = mid - 1;
            }
        }
        return -1;
    }

    public static void main(String[] args) {
        int[] numbers = {8, 3, 5, 3, 1};
        int[] unique = {8, 3, 5, 2, 1};
        int[] sorted = {1, 3, 5, 7, 9, 11, 13};

        System.out.println("Nested loops: " + hasDuplicateWithLoops(numbers));
        System.out.println("HashSet: " + hasDuplicateWithSet(numbers));
        System.out.println("Unique: " + hasDuplicateWithSet(unique));
        System.out.println("Linear search (7): " + linearSearch(sorted, 7));
        System.out.println("Binary search (7): " + binarySearch(sorted, 7));
        System.out.println("Binary search (8): " + binarySearch(sorted, 8));
    }
}
```

Kết quả chuẩn:

```text
Nested loops: true
HashSet: true
Unique: false
Linear search (7): 3
Binary search (7): 3
Binary search (8): -1
```

**Giải thích:** Mảng `numbers` có hai số 3, nên cả hai cách phát hiện trùng trả về `true`. Mảng `unique` có các giá trị khác nhau nên trả về `false`. Trong `sorted`, giá trị 7 nằm ở chỉ số 3 (chỉ số bắt đầu từ 0); giá trị 8 không có nên nhận `-1`.

Một số chi tiết đáng chú ý:

1. `HashSet.add(x)` trả về `false` khi tập hợp đã chứa `x`; ví dụ không cần thực hiện riêng `contains(x)` rồi `add(x)`.
2. Mảng `int[]` là dữ liệu đầu vào ở cả hai cách phát hiện trùng; chỉ cách B tạo thêm `HashSet<Integer>`. Việc dùng `Integer` có boxing và chi phí bộ nhớ thực tế.
3. Công thức `left + (right - left) / 2` tránh cộng trực tiếp `left + right` có thể tràn số nguyên với chỉ số rất lớn.
4. Hàm tìm kiếm nhị phân chỉ đúng khi `sorted` tăng dần. Thay nó bằng mảng chưa sắp xếp có thể cho kết quả sai dù mã biên dịch và chạy bình thường.
5. Các hàm đều không thay đổi mảng đầu vào. Nếu một giải pháp chọn sắp xếp tại chỗ, yêu cầu “được phép thay đổi đầu vào hay không” phải được xem xét riêng.

## 5. Phân tích thuật toán như thế nào?

Trước khi gắn ký hiệu Big O, cần xác định **mô hình đầu vào**, **thao tác chính**, **đường đi thực thi** và **tài nguyên cần tính**.

| Giải pháp | Điều kiện áp dụng | Thời gian xấu nhất / kỳ vọng | Bộ nhớ phụ |
| --- | --- | --- | --- |
| Kiểm tra trùng bằng hai vòng lặp | Mọi mảng số nguyên | O(n²) xấu nhất | O(1) |
| Kiểm tra trùng với `HashSet` | Có thể cấp phát bộ nhớ cho tập đã gặp | O(n) kỳ vọng với thao tác băm trung bình O(1); không khẳng định bảo đảm xấu nhất O(n) | O(n) |
| Tìm kiếm tuyến tính | Mảng bất kỳ | O(n) xấu nhất | O(1) |
| Tìm kiếm nhị phân lặp | Mảng đã sắp xếp | O(log n) xấu nhất | O(1) |

Ở đây **n là số phần tử trong mảng** và “bộ nhớ phụ” là bộ nhớ dùng thêm ngoài đầu vào, không tính không gian đã tồn tại của chính mảng.

- **Thời gian:** Với hai vòng lặp, cộng số cặp phải xét trong ca xấu nhất. Với HashSet, có tối đa n lần thêm/kiểm tra và mỗi lần có chi phí tra cứu băm. Với tìm kiếm nhị phân, kích thước khoảng ứng viên từ n giảm còn khoảng n/2, n/4, ... cho đến 0 hoặc tìm thấy.
- **Trường hợp tốt nhất, xấu nhất, trung bình/kỳ vọng:** Đó là các góc nhìn khác nhau; không được tự thay “kỳ vọng O(n)” bằng “chắc chắn O(n)”. Dữ liệu, va chạm băm và cách cài đặt có thể ảnh hưởng đến hiệu năng.
- **Bộ nhớ:** Hai vòng lặp và tìm kiếm nhị phân lặp chỉ dùng vài biến đếm/chỉ số. HashSet phải giữ các giá trị đã thấy, nên chi phí phụ tăng theo n; ngoài độ phức tạp tiệm cận còn có overhead của đối tượng, ô băm và bộ nhớ máy.
- **Tiền xử lý và số lượng truy vấn:** Nếu dữ liệu chưa sắp xếp, chi phí sắp xếp phải tính vào tổng giải pháp trước khi dùng nhị phân. Với một lần tìm kiếm, quét tuyến tính O(n) có thể rẻ hơn việc sắp xếp rồi tìm. Với rất nhiều truy vấn trên dữ liệu ít thay đổi, đầu tư tiền xử lý có thể đáng giá.
- **Đo lường:** Big O mô tả xu hướng theo quy mô và các giả định, không phải thời gian chạy bằng mili giây. Benchmark còn phụ thuộc JVM warm-up/JIT, phân bố đầu vào, kích thước dữ liệu, GC và phần cứng. Khi đo, phải dùng cùng dữ liệu/điều kiện để so sánh công bằng.

### Tính đúng đắn là một câu hỏi riêng

Có thể lập luận ngắn gọn bằng **bất biến vòng lặp**:

- Hai vòng lặp: trước mỗi lượt so sánh, những cặp đã duyệt đều khác nhau; nếu gặp một cặp bằng nhau thì trả về `true` là đúng. Duyệt hết mọi cặp mà không thấy bằng nhau chứng tỏ không có phần tử trùng.
- HashSet: ngay trước khi xử lý một phần tử, `seen` chứa đúng các giá trị đã duyệt trước đó. `add` thất bại khi và chỉ khi giá trị hiện tại đã xuất hiện; vì vậy kết luận trùng là đúng. Nếu xử lý hết mà không thất bại, các giá trị đều phân biệt.
- Tìm kiếm nhị phân: trong mảng tăng dần, nếu mục tiêu còn tồn tại thì một vị trí phù hợp luôn nằm trong khoảng `[left, right]`. Sau khi so sánh với phần tử giữa, nửa bị loại không thể chứa mục tiêu. Khoảng rỗng nghĩa là không có mục tiêu.

Lập luận trên giải thích **vì sao giải pháp đúng**; phân tích số lượt thực hiện và bộ nhớ giải thích **nó tốn bao nhiêu tài nguyên**. Hai loại lập luận bổ sung cho nhau.

## 6. Chọn cấu trúc dữ liệu và thuật toán trong thực tế

Một trình tự giải quyết bài toán có thể dùng cho hầu hết các chủ đề sau này:

1. **Phát biểu chính xác đầu vào, đầu ra và ràng buộc:** Có cho phép thay đổi dữ liệu không? Cần một phần tử, mọi phần tử hay vị trí đầu tiên? Có phần tử trùng không? Dữ liệu đã được sắp xếp chưa?
2. **Xác định thao tác chủ đạo:** Chủ yếu tra cứu thành viên, thêm/xóa ở đầu/cuối, truy cập bằng chỉ số, lấy phần tử nhỏ nhất hay duyệt theo thứ tự?
3. **Chọn cấu trúc dữ liệu theo thao tác:** Mảng thuận tiện cho truy cập theo chỉ số; HashSet hợp với kiểm tra đã xuất hiện; hàng đợi hỗ trợ xử lý theo FIFO; heap hỗ trợ lấy phần tử ưu tiên. Mỗi cấu trúc có chi phí và ngữ nghĩa riêng.
4. **Thiết kế thuật toán trên cấu trúc đã chọn:** Nêu ý tưởng, điều kiện dừng, bất biến và kết quả mong đợi trước khi tối ưu mã.
5. **Phân tích toàn bộ chi phí:** Tính cả khởi tạo cấu trúc, chuyển đổi, tiền xử lý, số lần truy vấn, thời gian xấu nhất/kỳ vọng và bộ nhớ phụ. Xét thêm tính dễ hiểu, khả năng bảo trì, đặc điểm dữ liệu thực tế.
6. **Kiểm thử và đo khi cần:** Thử mảng rỗng, một phần tử, tất cả phần tử giống nhau, không có phần tử trùng, và dữ liệu rất lớn. Đo thực nghiệm nếu chênh lệch hiệu năng ảnh hưởng quyết định.

Chẳng hạn, cấu trúc `Set` tự loại trùng, nhưng **không phù hợp** nếu yêu cầu giữ lại mọi bản sao và tần suất xuất hiện; lúc đó `Map<Integer, Integer>` để đếm hoặc một thuật toán quét kết hợp bộ đếm có thể phù hợp hơn. Câu hỏi về **đầu ra** quyết định lựa chọn, chứ không có cấu trúc dữ liệu “nhanh nhất” cho mọi bài toán.

## 7. Các nhầm lẫn phổ biến

- **“Thuật toán là `HashSet`.”** Chưa chính xác: HashSet là cấu trúc dữ liệu; “duyệt từng phần tử, thử thêm vào tập và dừng khi thêm thất bại” là thuật toán sử dụng HashSet.
- **“Đổi từ `int[]` sang `ArrayList<Integer>` là tự động nhanh hơn.”** Không đúng: cần xét thao tác nào là nút thắt. Cả hai đều cho phép truy cập phần tử theo chỉ số với thời gian O(1), nhưng cách lưu trữ, chi phí boxing và hành vi thêm/xóa khác nhau.
- **“Có Big O nhỏ hơn thì luôn chạy nhanh hơn.”** Không chắc với dữ liệu nhỏ, hằng số lớn, chi phí cấp phát và đặc điểm phần cứng. Big O bỏ qua nhiều hằng số và không thay thế benchmark.
- **“Tìm kiếm nhị phân áp dụng cho mọi mảng.”** Sai nếu thiếu tiền điều kiện đã sắp xếp. Độ phức tạp O(log n) không có ý nghĩa nếu kết quả sai.
- **“HashSet luôn O(1) cho mỗi thao tác.”** Đây là mô tả hiệu năng trung bình/kỳ vọng thông dụng, phụ thuộc giả định về băm và hiện thực; không nên coi là bảo đảm tuyệt đối.
- **“Phân tích chỉ là Big O của một vòng lặp.”** Cần tính toàn bộ đường đi, vòng lặp lồng nhau, lời gọi hàm, cấu trúc dữ liệu phụ, tiền xử lý, bất biến và trường hợp biên.
- **“Kết quả boolean giống nhau nghĩa là hai thuật toán tương đương trong mọi yêu cầu.”** Nếu đổi yêu cầu sang trả về chỉ số đầu tiên, thứ tự xuất hiện, số lần lặp hoặc giữ nguyên đầu vào, hai cách có thể cần sửa đổi khác nhau.

## 8. Tự kiểm tra

**Câu 1.** Một thuật toán dùng mảng và hai vòng lặp để tìm phần tử trùng. Hãy phân loại: “hai vòng lặp so sánh cặp” là gì; `int[]` là gì; “O(n²) và O(1) bộ nhớ phụ” là gì?

**Đáp án:** Lần lượt là **thuật toán**, **cấu trúc dữ liệu** và **kết quả phân tích tài nguyên của thuật toán**.

**Câu 2.** Vì sao thay tìm kiếm tuyến tính bằng tìm kiếm nhị phân không chỉ là thao tác “tối ưu Big O”?

**Đáp án:** Tìm kiếm nhị phân đòi hỏi dữ liệu đã sắp xếp và có thể không trả về vị trí đầu tiên nếu có nhiều phần tử bằng nhau. Phải bảo đảm tiền điều kiện và đặc tả kết quả, đồng thời tính chi phí sắp xếp nếu cần.

**Câu 3.** Với mảng rất lớn, muốn phát hiện trùng và có đủ bộ nhớ, chọn chiến lược nào? Nếu bộ nhớ phụ gần như bằng không?

**Đáp án:** Có thể ưu tiên quét với HashSet vì thời gian kỳ vọng O(n), đổi lại O(n) bộ nhớ phụ. Khi bộ nhớ phụ bị giới hạn nghiêm ngặt, so sánh từng cặp dùng O(1) bộ nhớ phụ nhưng thời gian xấu nhất O(n²). Nếu được phép sửa đổi hoặc tạo bản sao của dữ liệu, có thể xét hướng sắp xếp rồi so sánh phần tử kề nhau, nhưng phải phân tích chi phí và tác động lên dữ liệu.

**Ghi nhớ:** Thuật toán mô tả **cách giải**; cấu trúc dữ liệu quyết định **cách lưu và thao tác với dữ liệu**; phân tích thuật toán giải thích **tính đúng đắn, thời gian và bộ nhớ**. Quyết định kỹ thuật tốt luôn xem xét cả ba cùng với yêu cầu cụ thể.
