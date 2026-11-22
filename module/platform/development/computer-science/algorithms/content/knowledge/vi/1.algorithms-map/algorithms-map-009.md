# Lộ trình từ lời giải trực tiếp đến lựa chọn giải pháp phù hợp

Một bài toán thuật toán thường có nhiều cách giải đúng. Mục tiêu không phải luôn tìm ngay cách có độ phức tạp Big-O nhỏ nhất, mà là đi từ một lời giải dễ kiểm chứng đến giải pháp **đúng với đặc tả, đủ nhanh trong giới hạn, dùng bộ nhớ chấp nhận được và có thể bảo trì**. Đây là một lộ trình ra quyết định, áp dụng cho tìm kiếm, xử lý mảng, chuỗi, đồ thị, quy hoạch động và nhiều nhóm bài khác.

## 1. Đọc bài toán trước khi chọn thuật toán

Hãy diễn đạt lại đề bài thành bốn phần:

1. **Input:** Kiểu dữ liệu, kích thước `n`, miền giá trị, dữ liệu có thể rỗng/trùng/âm hay không, đã sắp xếp chưa.
2. **Output:** Cần trả về tồn tại hay không, một nghiệm hay tất cả nghiệm, giá trị hay chỉ số, kết quả chính xác hay xấp xỉ.
3. **Ràng buộc:** Giới hạn thời gian, bộ nhớ, có được thay đổi input không, có bao nhiêu truy vấn `q`, dữ liệu tĩnh hay liên tục cập nhật.
4. **Điều kiện đúng:** Mệnh đề phải thỏa với **mọi** input hợp lệ, kể cả biên; đừng suy ra điều kiện không được nêu (ví dụ mảng “thường đã tăng dần”).

Ví dụ: “Cho mảng số nguyên và `target`, xác định có **hai phần tử ở hai vị trí khác nhau** có tổng bằng `target` hay không”. Chữ “hai vị trí khác nhau” quyết định rằng một phần tử `3` đơn lẻ không tạo thành cặp tổng `6`; hai phần tử `3, 3` thì có. Nếu bài yêu cầu trả về **chỉ số gốc**, việc sắp xếp tại chỗ có thể làm mất thông tin cần trả.

Đầu ra và tiền điều kiện thay đổi thì thuật toán phù hợp cũng có thể thay đổi. Chỉ chọn kỹ thuật sau khi làm rõ điều này.

## 2. Bắt đầu bằng lời giải trực tiếp (baseline)

Lời giải trực tiếp thường mô phỏng định nghĩa của đề: thử các đối tượng/khả năng hợp lệ, kiểm tra điều kiện, rồi trả kết quả. Với bài cặp tổng, thử mọi cặp chỉ số `i < j`.

Lợi ích của baseline:

- **Dễ lập luận đúng:** Nếu tồn tại cặp hợp lệ, vòng lặp sẽ duyệt đến nó; nếu trả `true`, cặp được kiểm tra thực sự có hai chỉ số khác nhau.
- **Mốc chi phí rõ:** Hai vòng lặp lồng nhau duyệt tối đa `n(n−1)/2` cặp: thời gian `O(n²)`, bộ nhớ phụ `O(1)`.
- **Bộ đối chiếu:** Với input nhỏ, kết quả baseline có thể dùng để kiểm tra cách tối ưu bằng test tự động.

Baseline không có nghĩa là “sai” hay “chỉ để bỏ đi”. Nếu `n` nhỏ, dữ liệu rất ít truy vấn, hoặc bộ nhớ bị giới hạn, `O(n²)` đôi khi là lựa chọn hợp lý nhất. Ngược lại, với `n = 100.000`, việc duyệt gần năm tỷ cặp trong tình huống xấu nhất là tín hiệu phải xem xét cách khác.

Đừng tối ưu trước khi biết **điểm nghẽn**. Hãy hỏi: chương trình lặp lại phép tìm nào, tính lại đại lượng nào, duyệt trạng thái nào nhiều lần, và tính chất nào của dữ liệu đang bị bỏ phí?

## 3. Từ điểm nghẽn đến “họ” kỹ thuật

| Dấu hiệu trong đề bài | Ứng viên thường hữu ích | Điều kiện và bẫy cần kiểm tra |
| --- | --- | --- |
| Tra cứu một giá trị trong tập đã sắp xếp, hoặc tìm ngưỡng của một điều kiện đơn điệu | Tìm kiếm nhị phân | Dữ liệu/điều kiện phải có tính thứ tự hoặc đơn điệu; không áp dụng tùy tiện cho mảng chưa sắp xếp |
| Nhiều phép kiểm tra “đã gặp giá trị này chưa?” | `HashSet` / `HashMap` | Đổi bộ nhớ lấy thời gian; thời gian trung bình phụ thuộc chất lượng băm và phân phối khóa |
| Hai đầu của dãy đã sắp xếp có thể tiến về nhau | Hai con trỏ | Phải có lập luận rằng khi di chuyển con trỏ không bỏ mất nghiệm |
| Xét một đoạn liên tiếp mà biên có thể tiến một chiều | Sliding window | Điều kiện cho phép co/giãn cửa sổ một cách an toàn; với tổng dãy chứa số âm, quy tắc dựa vào tổng tăng/giảm thường không còn đúng |
| Hỏi tổng đoạn hay tổng số phần tử có tiền tố cho trước | Prefix sum, đôi khi kết hợp bảng băm | Phân biệt tổng đoạn cố định với đếm số đoạn; tránh tràn số khi cộng dồn |
| Các bài toán con lặp lại và có cấu trúc kết hợp nghiệm | Quy hoạch động / ghi nhớ | Xác định đúng trạng thái, chuyển trạng thái, trường hợp cơ sở và thứ tự tính |
| Thăm các đỉnh/cạnh, khám phá kết nối | DFS/BFS | BFS tìm đường ít cạnh nhất trong đồ thị không trọng số; DFS không tự bảo đảm đường ngắn nhất |
| Đường đi ngắn nhất có trọng số | Dijkstra nếu trọng số không âm; Bellman–Ford trong trường hợp thích hợp có cạnh âm | Không áp dụng Dijkstra khi có cạnh âm nếu chưa có bảo đảm bổ sung; chú ý chu trình âm |
| Cần chọn phương án cục bộ để tối ưu toàn cục | Greedy | Phải chứng minh lựa chọn tham lam an toàn; ví dụ tiền xu mệnh giá `1, 3, 4`, đổi `6`: chọn `4+1+1` dùng ba đồng, trong khi `3+3` chỉ hai |
| Không gian lựa chọn lớn nhưng có thể loại nhánh sớm | Backtracking, branch-and-bound | Độ phức tạp xấu nhất vẫn có thể tăng theo hàm mũ; đánh giá giới hạn `n` và khả năng cắt nhánh |

Đây là **bản đồ gợi ý**, không phải phép ghép từ khóa với thuật toán. Chẳng hạn thấy “đoạn liên tiếp” chưa đủ để quyết định sliding window: với dãy `[4, -1]` và mục tiêu tổng `3`, cách “tổng lớn hơn mục tiêu thì bỏ phần tử bên trái” (phù hợp trong một số bài chỉ có số không âm) có thể bỏ `4` trước khi thấy `-1` và bỏ lỡ đoạn hợp lệ. Khi có số âm, prefix sum kết hợp bảng băm thường là hướng đáng xét cho bài tổng đoạn.

## 4. Ví dụ xuyên suốt: tìm hai phần tử có tổng bằng target

**Đặc tả cố định:** Input là `int[] values` (có thể rỗng, âm, trùng), `int target`; output là `boolean`. Hai phần tử phải ở hai chỉ số khác nhau. Không được thay đổi mảng đầu vào.

### Cách A — duyệt mọi cặp

Duyệt `i` từ đầu đến cuối, với mỗi `i` duyệt `j = i + 1` trở đi. Đây là chuẩn đúng đơn giản, không cần cấu trúc dữ liệu bổ sung.

### Cách B — sắp xếp bản sao rồi dùng hai con trỏ

Sao chép mảng, sắp xếp tăng dần, đặt `left` ở đầu và `right` ở cuối. Nếu tổng quá nhỏ, tăng `left`; nếu quá lớn, giảm `right`.

Lập luận loại trừ: khi `a[left] + a[right] < target`, phần tử ở `left` ghép với mọi vị trí từ `left+1` đến `right` đều không đạt mục tiêu (vì `right` đang lớn nhất), nên bỏ `left` là an toàn. Trường hợp tổng lớn hơn mục tiêu đối xứng. Điều kiện `left < right` ngăn dùng cùng một vị trí hai lần.

Chi phí gồm bước sắp xếp (thường `O(n log n)`), quét `O(n)`, và bộ nhớ `O(n)` để giữ bản sao. Nếu **input đã được bảo đảm sắp xếp** và không cần copy, riêng bước hai con trỏ là `O(n)` thời gian, `O(1)` bộ nhớ phụ.

### Cách C — tra cứu phần bù bằng HashSet

Duyệt mỗi `value`, tìm xem `target - value` có trong tập các phần tử **đã đi qua** chưa; sau khi kiểm tra mới thêm `value`. Như vậy phần bù, nếu có, luôn thuộc vị trí trước đó, không thể tái sử dụng đúng phần tử hiện tại. Một cặp `3,3` vẫn được nhận khi gặp số `3` thứ hai.

Thời gian trung bình `O(n)`, bộ nhớ `O(n)`. Thời gian của cấu trúc băm là kỳ vọng/trung bình, không phải cam kết mọi thao tác luôn `O(1)`. Đây là lựa chọn tốt cho mảng chưa sắp xếp khi có đủ bộ nhớ.

### Chương trình Java 17+ chạy độc lập

Lưu tệp **AlgorithmChoiceDemo.java**:

```java
import java.util.Arrays;
import java.util.HashSet;
import java.util.Set;

public class AlgorithmChoiceDemo {
    static boolean direct(int[] values, int target) {
        for (int i = 0; i < values.length; i++) {
            for (int j = i + 1; j < values.length; j++) {
                if ((long) values[i] + values[j] == target) {
                    return true;
                }
            }
        }
        return false;
    }

    static boolean sortedTwoPointers(int[] values, int target) {
        int[] sorted = values.clone(); // Giữ nguyên input.
        Arrays.sort(sorted);
        int left = 0;
        int right = sorted.length - 1;

        while (left < right) {
            long sum = (long) sorted[left] + sorted[right];
            if (sum == target) {
                return true;
            }
            if (sum < target) {
                left++;
            } else {
                right--;
            }
        }
        return false;
    }

    static boolean seenSet(int[] values, int target) {
        Set<Long> seen = new HashSet<>();
        for (int value : values) {
            long complement = (long) target - value;
            if (seen.contains(complement)) {
                return true;
            }
            seen.add((long) value);
        }
        return false;
    }

    public static void main(String[] args) {
        int[] sample = {7, 2, 11, 3, 8};
        int target = 10;

        System.out.println("Direct: " + direct(sample, target));
        System.out.println("Sort + two pointers: " + sortedTwoPointers(sample, target));
        System.out.println("HashSet: " + seenSet(sample, target));
        System.out.println("Original: " + Arrays.toString(sample));
        System.out.println("Duplicates: " + seenSet(new int[]{3, 3}, 6));
        System.out.println("Single element: " + seenSet(new int[]{3}, 6));
        System.out.println("No solution: " + seenSet(new int[]{1, 2, 3}, 100));
        System.out.println("Overflow guard: "
                + direct(new int[]{Integer.MAX_VALUE, Integer.MAX_VALUE}, -2));
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 AlgorithmChoiceDemo.java
java AlgorithmChoiceDemo
```

Stdout:

```text
Direct: true
Sort + two pointers: true
HashSet: true
Original: [7, 2, 11, 3, 8]
Duplicates: true
Single element: false
No solution: false
Overflow guard: false
```

**Vì sao ép sang `long`?** Hai số `int` lớn cộng với kiểu `int` có thể tràn số và tình cờ bằng một `target` sai. Biểu thức `(long) values[i] + values[j]` dùng phép cộng 64 bit. Trong HashSet, `(long) target - value` và `Set<Long>` giữ phép tìm phần bù nhất quán về kiểu số. Dòng “Overflow guard” trả `false` đúng vì tổng toán học của hai `Integer.MAX_VALUE` không phải `-2`.

### So sánh cùng một đặc tả

| Giải pháp | Thời gian | Bộ nhớ phụ | Điểm mạnh | Điều kiện/chi phí |
| --- | --- | --- | --- | --- |
| Duyệt mọi cặp | `O(n²)` | `O(1)` | Đơn giản, làm oracle khi test | Chậm khi `n` lớn |
| Copy + sort + hai con trỏ | Thường `O(n log n)` | `O(n)` cho bản sao | Không cần bảng băm; tận dụng thứ tự | Có bước sắp xếp; nếu cần chỉ số gốc phải lưu kèm chỉ số |
| HashSet phần bù | Trung bình `O(n)` | `O(n)` | Một lượt quét, input không cần sắp xếp | Cần bộ nhớ cho tập, phụ thuộc đặc tính băm |
| Hai con trỏ trên input **đã sắp xếp** | `O(n)` | `O(1)` | Ít bộ nhớ và nhanh | Chỉ áp dụng khi tiền điều kiện thứ tự được bảo đảm |

Với bài toán **trả về chỉ số**, có thể dùng `HashMap` ánh xạ giá trị → chỉ số đã gặp. Không được mặc nhiên trả chỉ số của mảng đã sắp xếp thay cho chỉ số gốc. Nếu cần **tất cả** cặp (nhất là có nhiều phần tử trùng nhau), độ phức tạp còn chịu ảnh hưởng của số kết quả cần xuất; cần định nghĩa rõ “cặp giá trị” hay “cặp chỉ số”.

## 5. Cách chọn giải pháp theo điều kiện thực tế

Hãy đánh giá ứng viên theo thứ tự:

1. **Tính đúng và tiền điều kiện:** Có chứng minh/invariant không? Trường hợp âm, trùng, rỗng, overflow, dữ liệu chưa sắp xếp có phá giả định không?
2. **Độ phức tạp theo quy mô:** So sánh số thao tác tương đối tại kích thước cực đại, không chỉ trên một input đẹp. Với `n = 100.000`, `n²` vượt xa `n log n`; với `n` rất nhỏ, chi phí dựng cấu trúc dữ liệu có thể không đáng.
3. **Bộ nhớ và tính biến đổi dữ liệu:** HashSet cần thêm bộ nhớ, sort tại chỗ làm thay đổi thứ tự, sort trên bản sao giữ input nhưng tốn RAM.
4. **Số truy vấn và cập nhật:** Một lần tìm kiếm khác với hàng nghìn lần tra cứu trên cùng tập tĩnh. Tạo cấu trúc tra cứu một lần có thể tiết kiệm tổng thời gian. Nếu dữ liệu thay đổi liên tục, phải tính cả chi phí cập nhật.
5. **Khả năng bảo trì và độ tin cậy:** Trong các giải pháp đều đạt giới hạn, chọn cách có lập luận đúng, test và mã dễ hiểu. Độ phức tạp tiệm cận nhỏ hơn không tự bảo đảm chạy nhanh hơn trên mọi dữ liệu nhỏ.

Ví dụ quyết định cho bài cặp tổng: `n` nhỏ và chỉ cần một lần kiểm tra → duyệt cặp có thể đủ; mảng đã sắp xếp → hai con trỏ; mảng chưa sắp xếp, `n` lớn và RAM đủ → HashSet; không được thay input và chọn sort → phải dùng bản sao. Đây là **lựa chọn theo ràng buộc**, không phải bảng xếp hạng thuật toán cố định.

## 6. Cách kiểm tra quá trình tối ưu

Một quy trình thực hành có thể lặp lại:

1. **Đặt baseline đúng.** Viết hoặc mô tả thuật toán trực tiếp, liệt kê bất biến và tính `O(...)`.
2. **Chỉ ra phần việc lặp lại.** Ví dụ: mỗi phần tử lại dò toàn bộ phần còn lại để tìm phần bù.
3. **Đề xuất thay đổi cụ thể.** HashSet lưu các giá trị đã gặp để thay quét lặp; hoặc sort để dùng thứ tự và loại bớt miền tìm.
4. **Chứng minh tính tương đương.** HashSet chỉ thấy các phần tử trước đó; hai con trỏ loại những cặp chắc chắn không đạt mục tiêu.
5. **So với baseline bằng trường hợp nhỏ.** Thử mảng rỗng, một phần tử, hai phần tử bằng nhau, số âm, số lớn, không có nghiệm, có nhiều nghiệm; nếu có thể, sinh ngẫu nhiên input nhỏ và đối chiếu đầu ra của hai phương pháp.
6. **Đánh giá dữ liệu sát thực tế.** Đo thời gian và bộ nhớ trên kích thước, phân phối dữ liệu, số truy vấn tương ứng với hệ thống. Tránh suy ra kết luận từ một lần đo đơn lẻ có ảnh hưởng của JIT/GC trên JVM.

Trong chương trình mẫu, cả ba phương pháp dùng chung đặc tả `boolean`, nên có thể đối chiếu chính xác kết quả. Kết quả giống nhau ở vài test **không thay thế chứng minh đúng**; test giúp tìm phản ví dụ cho các giả định sai.

## 7. Những sai lầm thường gặp

- **Nhìn tên kỹ thuật rồi ép vào đề:** “Tìm kiếm” không tự động là binary search; “đoạn liên tiếp” không tự động dùng sliding window.
- **Bỏ qua thông tin cần trả:** Sắp xếp mảng để tìm tổng đôi có thể ổn khi chỉ trả boolean, nhưng gây lỗi nếu bài bắt giữ chỉ số gốc.
- **Cho rằng Big-O là thời gian thực tế:** `O(n)` với bảng băm có chi phí cấp phát và phụ thuộc phân phối khóa; `O(n log n)` có thể hợp lý hơn trong giới hạn RAM nhất định.
- **Quên những dữ liệu khó:** Trùng, số âm, đầu vào rỗng, một phần tử, số gần biên kiểu `int`, các trường hợp không có nghiệm.
- **Tối ưu mà mất tính đúng:** Dịch chuyển con trỏ hoặc tham lam phải có cơ sở loại trừ/chứng minh; không suy diễn từ một vài ví dụ.
- **Tính mỗi lần chạy mà quên tiền xử lý:** Khi `q` truy vấn trên dữ liệu tĩnh, phải tính tổng chi phí xây dựng chỉ mục + tất cả truy vấn; khi cập nhật nhiều, phải tính thêm chi phí duy trì chỉ mục.

## 8. Bài tự luyện để hình thành phản xạ chọn thuật toán

1. Bài cặp tổng chỉ có một truy vấn, `n = 30`, giới hạn RAM rất chặt. Vì sao cách duyệt trực tiếp vẫn là ứng viên tốt?
2. Cùng bài đó, `n = 1.000.000`, mảng đã tăng dần, chỉ cần boolean. Chọn hai con trỏ hay HashSet? Giải thích bằng tiền điều kiện và bộ nhớ.
3. Nếu đề đổi thành “trả về hai chỉ số gốc”, cần thay đổi gì trong lời giải dùng sort hoặc bảng băm?
4. Nếu đề chuyển thành “có đoạn liên tiếp tổng bằng `k`” và phần tử có thể âm, hãy thử phá cách sliding window dựa trên quy tắc “tổng lớn thì co”. Sau đó xem xét prefix sum.
5. Đường đi ngắn nhất có trọng số: vì sao cần hỏi có cạnh âm không trước khi chọn Dijkstra?

**Tiêu chí hoàn thành:** Với một đề mới, bạn có thể phát biểu rõ input/output/ràng buộc, đưa ra baseline đúng, chỉ ra điểm nghẽn, chọn một họ kỹ thuật dựa trên tính chất dữ liệu, chứng minh không bỏ nghiệm, so sánh thời gian–bộ nhớ–chi phí cập nhật và kiểm thử các trường hợp biên. Khi đủ căn cứ, mới kết luận giải pháp nào **phù hợp nhất với bài toán cụ thể**.
