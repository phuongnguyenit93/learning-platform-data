# Chi phí khấu hao, trường hợp trung bình và trường hợp xấu

## 1. Vì sao cùng một thao tác có thể được mô tả bằng nhiều mức chi phí?

Khi đọc rằng `ArrayList.add(element)` có chi phí hằng số khấu hao, ta có thể đặt câu hỏi: nếu danh sách đã đầy, Java phải tạo mảng lớn hơn và sao chép các phần tử; vậy thao tác đó có thật sự là `O(1)` không?

Câu trả lời phụ thuộc vào **đối tượng đang được đánh giá**:

- Một lần gọi đắt nhất khi collection đang có `n` phần tử: phân tích **trường hợp xấu**.
- Một lần gọi lấy trung bình theo một phân phối đầu vào đã nêu: phân tích **trường hợp trung bình**.
- Cả một chuỗi thao tác, sau đó phân bổ tổng chi phí cho các thao tác trong chuỗi: phân tích **khấu hao**.

Ba cách nhìn này trả lời những câu hỏi khác nhau. Một thao tác có thể đồng thời có chi phí khấu hao `O(1)` và chi phí trường hợp xấu `O(n)`. Không có mâu thuẫn: một vài lần gọi đắt được bù bởi nhiều lần gọi rẻ trong một chuỗi mà tổng chi phí vẫn tăng tuyến tính.

Mục tiêu của bài là biết đọc đúng các phát biểu hiệu năng của Java Collections, nêu được giả định phía sau chúng và tránh suy từ một con số Big-O sang lời hứa về độ trễ của mọi lần gọi.

## 2. Xác định mô hình chi phí trước khi nói Big-O

### 2.1. `n` là gì, và ta đang đếm điều gì?

Trong bài này:

- `n` thường là số phần tử hiện có trong collection trước một thao tác.
- `m` là số thao tác trong một chuỗi.
- Khi cần phân tích độ dài khóa, dùng thêm `L` thay vì giấu mọi chi phí trong `n`.
- Một đơn vị chi phí có thể là một lần so sánh, một lần ghi phần tử hoặc một lần sao chép một tham chiếu. Phải nói rõ mô hình được dùng.

Ví dụ, sao chép `n` tham chiếu từ mảng cũ sang mảng mới là công việc tuyến tính theo `n`. Nó không sao chép sâu mọi đối tượng được các tham chiếu trỏ đến. Đối tượng có nhiều trường không có nghĩa mỗi lần tăng dung lượng `ArrayList` phải nhân bản toàn bộ các đối tượng đó.

Phân tích thường giả định truy cập một ô mảng và thao tác với một tham chiếu có chi phí hằng số. Với `HashMap`, ta còn phải xét giả định về `hashCode()` và `equals()`. Với `TreeMap`, chi phí của `Comparator.compare()` hoặc `compareTo()` cũng cần được tính nếu việc so sánh không hằng số.

### 2.2. Big-O không phải tên gọi của trường hợp xấu

`O(f(n))` là một cận trên về tốc độ tăng của một đại lượng chi phí. Đại lượng đó có thể là chi phí trường hợp xấu, chi phí kỳ vọng hoặc chi phí khấu hao. Ký hiệu `O` tự nó không chỉ ra ta đang xét loại nào.

`Θ(f(n))` diễn tả cận chặt theo bậc tăng, còn `Ω(f(n))` diễn tả cận dưới. Vì vậy, một chi phí hằng số cũng có cận trên `O(n)`, nhưng mô tả `Θ(1)` cung cấp thông tin chặt hơn.

Trong trao đổi thực tế, người ta hay nói ngắn “thao tác này `O(1)`”. Khi điều đó ảnh hưởng tới thiết kế, hãy hỏi tiếp: đối với loại dữ liệu nào, một lần gọi hay cả chuỗi, và có giả định nào về khóa hoặc vị trí thao tác?

## 3. Trường hợp xấu: lần gọi tốn nhiều nhất ở kích thước đã cho

Với một thao tác và tập trạng thái/đầu vào hợp lệ ở kích thước `n`, chi phí trường hợp xấu là chi phí lớn nhất trong tập đó.

Có thể viết:

```text
W(n) = max chi phí của một thao tác trên các đầu vào/trạng thái kích thước n
```

Ví dụ, tìm kiếm tuyến tính trong danh sách `n` phần tử:

- Nếu phần tử cần tìm ở đầu: có thể chỉ cần một lần so sánh.
- Nếu nó ở cuối: cần `n` lần so sánh.
- Nếu không tồn tại: cần kiểm tra cả `n` phần tử.

Chi phí trường hợp xấu của việc tìm kiếm này là `Θ(n)`. Không cần biết người dùng “thường tìm gì” để đưa ra cận đó.

Với mảng động đang đầy, thêm một phần tử có thể phải sao chép `n` phần tử cũ rồi ghi phần tử mới. Trong mô hình sao chép từng phần tử, riêng lần thêm đó có chi phí `Θ(n)`.

**Giá trị của phân tích trường hợp xấu:** nó giúp nhận diện lần gọi có thể đắt và kiểm tra tính ổn định của số bước thuật toán. Tuy nhiên, một cận Big-O về số bước không phải cam kết số mili giây trên JVM. Cấp phát bộ nhớ, thu gom rác, JIT, lịch chạy luồng và trạng thái hệ điều hành vẫn ảnh hưởng đến thời gian thực tế.

Cũng cần phân biệt:

- Trường hợp xấu của **một thao tác** khi đang có `n` phần tử.
- Trường hợp xấu của **toàn bộ chuỗi** `m` thao tác hợp lệ.

Không phải lúc nào cũng có thể tạo chuỗi mà mọi thao tác đều đạt mức đắt nhất của một lần gọi. Ràng buộc này là cơ sở quan trọng của phân tích khấu hao.

## 4. Trường hợp trung bình: phải có phân phối đầu vào

### 4.1. Trung bình theo cái gì?

Phân tích trường hợp trung bình tính kỳ vọng chi phí khi đầu vào hoặc trạng thái được lấy theo một phân phối xác suất đã xác định.

```text
A(n) = tổng của [xác suất đầu vào x × chi phí xử lý x]
       trên các đầu vào kích thước n
```

Không thể chỉ nói “dữ liệu bình thường” rồi mặc nhiên xem đó là một mô hình xác suất. Kết luận phụ thuộc vào việc các trường hợp xuất hiện thường xuyên đến mức nào.

Xét tìm kiếm tuyến tính trong danh sách có `n` giá trị phân biệt, với hai giả định:

1. Chắc chắn tìm một giá trị đang có trong danh sách.
2. Mỗi vị trí có xác suất được tìm bằng nhau: `1/n`.

Số lần so sánh kỳ vọng là:

```text
A(n) = (1 + 2 + ... + n) / n
     = [n(n + 1) / 2] / n
     = (n + 1) / 2
     = Θ(n)
```

Một nửa số phần tử vẫn là tuyến tính. “Trung bình chỉ tìm nửa danh sách” không biến thuật toán thành `O(1)`.

### 4.2. Thay đổi phân phối có thể thay đổi kết quả

Nếu phần lớn truy vấn nhắm vào vài phần tử đầu danh sách thì chi phí kỳ vọng có thể nhỏ hơn. Nếu truy vấn thường không tìm thấy thì mỗi truy vấn đó vẫn phải quét toàn bộ danh sách.

Giả sử xác suất truy vấn thành công là `p`; khi thành công, vị trí cần tìm phân bố đều. Khi thất bại phải kiểm tra `n` phần tử. Ta có:

```text
E[số lần so sánh] = p × (n + 1) / 2 + (1 - p) × n
```

Với mô hình này, chi phí vẫn là `Θ(n)` đối với `n` tăng. Công thức giúp ta thấy rõ cả ảnh hưởng của truy vấn thất bại thay vì âm thầm bỏ chúng ra khỏi phép tính.

Cần phân biệt thêm:

- **Trung bình lý thuyết:** kỳ vọng theo một mô hình xác suất.
- **Trung bình đo được:** trung bình các mẫu thời gian trên máy và dữ liệu đã chạy.

Trung bình đo được là bằng chứng về tập mẫu đó. Nó không tự chứng minh mô hình xác suất đúng, không chứng minh cận thuật toán và không cung cấp cận cho lần gọi chậm nhất.

## 5. Khấu hao: đánh giá cả chuỗi, không cần giả định ngẫu nhiên

### 5.1. Tổng chi phí mới là điểm xuất phát

Giả sử một chuỗi có `m` thao tác với chi phí thực tế lần lượt là `c1, c2, ..., cm`.

```text
T(m) = c1 + c2 + ... + cm
```

Nếu chứng minh được rằng mọi chuỗi thuộc phạm vi đang xét đều có `T(m) = O(m)`, thì chi phí khấu hao trên một thao tác là `O(1)`.

Đây là việc phân bổ chi phí trong một chứng minh. Không phải thao tác nào cũng thực sự dùng cùng số bước. Không cần cho rằng đầu vào ngẫu nhiên, may mắn, hoặc các lần gọi đắt có xác suất thấp.

Ví dụ điển hình: một mảng động tăng dung lượng theo hệ số cố định lớn hơn `1`. Sau một lần tăng dung lượng, có thêm nhiều ô trống. Các lần thêm tiếp theo dùng các ô đó trước khi cần sao chép lần nữa. Chính quy tắc thay đổi trạng thái tạo ra bảo đảm tổng chi phí.

### 5.2. “Chia tổng cho số thao tác” chưa đủ để chứng minh

Ta có thể lấy tổng thời gian một lần chạy bất kỳ chia cho số thao tác. Đó mới chỉ là một số trung bình của lần chạy.

Để kết luận khấu hao, cần chứng minh cận tổng cho **mọi chuỗi thao tác được phép trong mô hình**, hoặc dùng một phương pháp tương đương. Phải nêu:

- Trạng thái khởi đầu.
- Tập thao tác được phép.
- Cách collection tăng/giảm dung lượng.
- Những chi phí được tính.

Ví dụ, cận `O(m)` cho `m` lần thêm bắt đầu từ mảng động rỗng không thể được áp dụng nguyên xi cho một lần thêm vào mảng đang đầy sẵn `n` phần tử. Nếu chỉ có một thao tác, chi phí sao chép `n` phần tử không thể biến mất. Khi bắt đầu từ một cấu trúc có sẵn, cận tổng cần tính cả chi phí hoặc trạng thái ban đầu, chẳng hạn `O(n + m)` trong mô hình tăng dung lượng tương ứng.

## 6. Chứng minh với mảng động tăng gấp đôi

Để thấy rõ cơ chế, dùng một **mô hình giảng giải**:

- Bắt đầu với dung lượng `0`.
- Lần thêm đầu tạo mảng dung lượng `1`.
- Khi mảng đầy, tạo mảng mới có dung lượng gấp đôi.
- Chi phí của một lần thêm = số phần tử cũ phải sao chép + một lần ghi phần tử mới.

Mô hình này không khẳng định `ArrayList` của mọi JDK luôn tăng đúng gấp đôi. Chính sách tăng dung lượng cụ thể của `ArrayList` không được API quy định; bảo đảm được công bố là chi phí thêm khấu hao hằng số. [Tài liệu ArrayList của Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayList.html)

### 6.1. Theo dõi 16 lần thêm

| Lần thêm | Dung lượng trước | Có tăng dung lượng? | Số phần tử sao chép | Tổng đơn vị chi phí |
| --- | --- | --- | --- | --- |
| 1 | 0 | Có, lên 1 | 0 | 1 |
| 2 | 1 | Có, lên 2 | 1 | 2 |
| 3 | 2 | Có, lên 4 | 2 | 3 |
| 4 | 4 | Không | 0 | 1 |
| 5 | 4 | Có, lên 8 | 4 | 5 |
| 6–8 | 8 | Không | 0 mỗi lần | 1 mỗi lần |
| 9 | 8 | Có, lên 16 | 8 | 9 |
| 10–16 | 16 | Không | 0 mỗi lần | 1 mỗi lần |

Có `16` lần ghi giá trị mới. Tổng số phần tử được sao chép là:

```text
1 + 2 + 4 + 8 = 15
```

Tổng chi phí là `16 + 15 = 31`, trong khi lần thêm đắt nhất tốn `9` đơn vị. Tổng nhỏ không loại bỏ lần gọi đắt.

### 6.2. Tổng hợp chi phí cho `m` lần thêm

Các lần sao chép có kích thước là các lũy thừa của `2`:

```text
1 + 2 + 4 + ... + 2^k = 2^(k + 1) - 1
```

Với `m` lần thêm, lũy thừa lớn nhất phải sao chép nhỏ hơn `m`. Do đó tổng số phần tử sao chép nhỏ hơn `2m` và:

```text
T(m) < m + 2m = 3m
```

Kết luận:

- Tổng chi phí của `m` lần thêm là `Θ(m)` trong mô hình này: ít nhất cũng phải ghi `m` phần tử mới.
- Chi phí khấu hao mỗi lần thêm là `Θ(1)`.
- Một lần thêm khi mảng đầy vẫn có chi phí trường hợp xấu `Θ(n)`.

Chi phí cấp phát và khởi tạo mảng mới bị lược bỏ trong phép đếm đơn giản trên. Nếu tính chúng là tuyến tính theo dung lượng mảng mới, tổng các dung lượng được cấp phát vẫn là một cấp số nhân. Bậc tổng vẫn tuyến tính theo `m`; các hệ số cụ thể thay đổi.

### 6.3. Vì sao tăng thêm một ô lại khác?

Nếu mỗi lần đầy chỉ tăng dung lượng thêm `1`, để thêm `m` phần tử ta phải sao chép:

```text
0 + 1 + 2 + ... + (m - 1) = m(m - 1) / 2
```

Tổng là `Θ(m²)`, nên chi phí khấu hao một lần thêm là `Θ(m)`, không còn hằng số.

Điểm tạo ra bảo đảm không phải chỉ là “thỉnh thoảng có sao chép”, mà là **dung lượng tăng đủ nhanh để khoảng cách giữa các lần sao chép cũng tăng**. Một hệ số cố định lớn hơn `1` cho phép tổng hợp theo cấp số nhân; hệ số càng gần `1` thì chi phí sao chép và mức bộ nhớ dư có đánh đổi khác nhau.

### 6.4. Cách nghĩ bằng khoản dự trữ

Có thể hình dung mỗi lần thêm trả một khoản chi phí khấu hao cố định: một phần chi trả lần ghi hiện tại, phần còn lại được dự trữ để trả cho lần sao chép sau.

Khoản dự trữ là công cụ toán học, không phải một trường tiền hoặc một bộ đếm bắt buộc trong chương trình. Một chứng minh theo cách này phải bảo đảm khoản dự trữ không âm. Ta không được lấy một giá trị tùy ý rồi gọi đó là khấu hao.

Phương pháp tổng hợp ở trên đã đủ chứng minh cho mô hình tăng gấp đôi. Cách dự trữ giúp giải thích trực giác: các lần rẻ đã góp chi phí cho lần đắt; điều này không cần một phân phối đầu vào.

## 7. Chương trình Java: đếm thao tác và kiểm chứng phép tính

Chương trình dưới đây chạy với Java 17+. Lớp `DoublingBuffer` là mô hình mảng động tự viết để quan sát số phần tử sao chép. Nó không đọc dung lượng nội bộ hoặc đo thời gian của `ArrayList`.

Phần tìm kiếm cuối chương trình đếm số phép so sánh cho năm vị trí thành công, rồi tính trung bình khi cả năm vị trí có trọng số bằng nhau.

Lưu toàn bộ mã vào `CostModelsDemo.java`:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

public class CostModelsDemo {
    private static final class DoublingBuffer {
        private int[] elements = new int[0];
        private int size;
        private long copied;
        private long writes;

        int add(int value) {
            int copiedNow = 0;
            if (size == elements.length) {
                int newCapacity = elements.length == 0
                        ? 1
                        : elements.length * 2;
                copiedNow = size;
                elements = Arrays.copyOf(elements, newCapacity);
                copied += copiedNow;
            }
            elements[size++] = value;
            writes++;
            return copiedNow + 1;
        }
    }

    private static int comparisonsUntilFound(List<Integer> values, int target) {
        int comparisons = 0;
        for (int value : values) {
            comparisons++;
            if (value == target) {
                return comparisons;
            }
        }
        return comparisons;
    }

    public static void main(String[] args) {
        DoublingBuffer buffer = new DoublingBuffer();
        List<Integer> costs = new ArrayList<>();
        int worst = 0;
        for (int i = 0; i < 16; i++) {
            int cost = buffer.add(i);
            costs.add(cost);
            worst = Math.max(worst, cost);
        }

        System.out.println("append costs = " + costs);
        System.out.println("writes = " + buffer.writes);
        System.out.println("copied = " + buffer.copied);
        System.out.println("total units = " + (buffer.writes + buffer.copied));
        System.out.println("worst append = " + worst);

        List<Integer> values = List.of(10, 20, 30, 40, 50);
        int successfulTotal = 0;
        for (int target : values) {
            successfulTotal += comparisonsUntilFound(values, target);
        }
        System.out.println("successful search total = " + successfulTotal);
        System.out.println("uniform successful mean = "
                + (double) successfulTotal / values.size());
        System.out.println("unsuccessful search = "
                + comparisonsUntilFound(values, 99));
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 CostModelsDemo.java
java CostModelsDemo
```

Stdout:

```text
append costs = [1, 2, 3, 1, 5, 1, 1, 1, 9, 1, 1, 1, 1, 1, 1, 1]
writes = 16
copied = 15
total units = 31
worst append = 9
successful search total = 15
uniform successful mean = 3.0
unsuccessful search = 5
```

Cách đọc kết quả:

1. Các đỉnh `2`, `3`, `5`, `9` cho thấy chi phí thực tế mỗi lần thêm không cố định.
2. `31` đơn vị cho `16` lần thêm phù hợp với cận tổng nhỏ hơn `3m`.
3. `15 / 5 = 3` là trung bình theo giả định năm mục tiêu xuất hiện đều nhau; số `3` không phải cận trường hợp xấu.
4. Truy vấn không có kết quả vẫn kiểm tra đủ năm phần tử.

Chương trình dùng dữ liệu nhỏ để trình bày cơ chế, không phải một collection tổng quát có xử lý giới hạn dung lượng hay mọi tình huống lỗi. Một lần chạy là minh chứng cụ thể; chứng minh cấp số nhân mới giải thích vì sao cận khấu hao đúng với mọi số lần thêm trong mô hình.

## 8. Đọc đúng các phát biểu hiệu năng của Java Collections

### 8.1. `ArrayList`: phân biệt thêm cuối, chèn giữa và tìm kiếm

`ArrayList.add(element)` thêm vào cuối. Một lần gọi có thể phải tăng dung lượng; một chuỗi thêm cuối có bảo đảm khấu hao hằng số. API cũng cho phép chuẩn bị dung lượng bằng constructor hoặc `ensureCapacity()`, giúp giảm các lần cấp phát lại khi biết trước lượng phần tử sẽ thêm. Không suy ra một hệ số tăng cụ thể từ bảo đảm đó. [Tài liệu ArrayList của Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayList.html)

Không chuyển bảo đảm này sang mọi phương thức cùng tên:

- `add(0, element)` trên danh sách có `n` phần tử phải dịch `n` phần tử sang phải, kể cả khi vẫn còn dung lượng trống.
- `remove(0)` phải dịch các phần tử phía sau sang trái.
- `contains(value)` phải tìm giá trị; không có tra cứu bằng chỉ số miễn phí.
- `get(index)` truy cập vị trí đã biết, nên không phải làm bước tìm kiếm tuyến tính.

Nếu liên tục chèn `m` phần tử ở đầu một `ArrayList` rỗng, số phần tử cần dịch là `0 + 1 + ... + (m - 1)`. Tổng `Θ(m²)` xuất phát từ dịch chuyển, dù chi phí tăng dung lượng được khấu hao tốt.

### 8.2. `HashMap`: giả định phân tán băm và chi phí tăng bảng

Tài liệu `HashMap` nêu hiệu năng hằng số cho `get` và `put` với giả định hàm băm phân tán phần tử phù hợp giữa các bucket. Bảng tăng dung lượng khi số ánh xạ vượt ngưỡng liên quan đến dung lượng và hệ số tải. Dung lượng ban đầu và hệ số tải cũng ảnh hưởng hiệu năng, không chỉ số ánh xạ. [Tài liệu HashMap của Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HashMap.html)

Ở đây cần giữ riêng hai nguồn chi phí:

1. **Phân bố khóa trong các bucket:** ảnh hưởng số ứng viên phải kiểm tra khi tìm khóa. Nếu dùng mô hình ngẫu nhiên cho băm/khóa, ta có thể phân tích chi phí kỳ vọng theo mô hình đó.
2. **Tăng dung lượng:** một lần `put` có thể phải tổ chức lại bảng. Chi phí đắt này được phân bổ qua chuỗi chèn bằng phân tích khấu hao.

Vì vậy, một phát biểu chặt chẽ thường là: “Chèn có chi phí kỳ vọng khấu hao `O(1)` dưới giả định băm phân tán tốt, hệ số tải được kiểm soát, và chi phí băm/so sánh khóa là hằng số.” Chữ “kỳ vọng” nói về phân bố; chữ “khấu hao” nói về chuỗi tăng bảng. Chúng có thể cùng xuất hiện vì xử lý hai khía cạnh khác nhau.

Không coi `HashMap.get` hoặc `put` là lời hứa thời gian hằng số cho mọi khóa. Nhiều khóa va chạm, `hashCode()` tốn kém hoặc `equals()` phải duyệt dữ liệu lớn đều làm lời mô tả đơn giản kém chính xác. Cũng không suy ra cận trường hợp xấu `O(log n)` cho mọi khóa chỉ vì biết một triển khai có thể dùng cây trong bucket; đó không phải bảo đảm tổng quát được tài liệu API nêu cho mọi tình huống.

### 8.3. `ArrayDeque`: thao tác ở hai đầu khác thao tác tìm giá trị

Các thao tác phổ biến ở hai đầu `ArrayDeque` có chi phí khấu hao hằng số. Nhưng `contains`, xóa theo giá trị và một số thao tác khác phải làm công việc tuyến tính; không áp dụng đặc tính hai đầu cho mọi phương thức. [Tài liệu ArrayDeque của Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayDeque.html)

Nếu cần lần lượt đưa việc vào cuối và lấy việc ở đầu, cơ chế này tránh việc dịch chuyển toàn bộ phần tử như `ArrayList.remove(0)`.

### 8.4. `TreeMap`: cận theo cây và chi phí so sánh

`TreeMap` có bảo đảm `O(log n)` cho `containsKey`, `get`, `put` và `remove`. Khi quy đổi sang thời gian xử lý khóa, cần tính thêm chi phí phép so sánh nếu nó không hằng số. [Tài liệu TreeMap của Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/TreeMap.html)

Ví dụ, nếu mỗi phép so sánh khóa có chi phí tối đa `O(L)`, cận theo mô hình đó trở thành `O(L log n)`. “Cây có chiều cao logarit” không loại bỏ công việc bên trong mã so sánh do ứng dụng cung cấp.

### 8.5. Bảng đọc nhanh theo thao tác

Bảng dưới giả định chi phí thao tác với một phần tử, băm và so sánh liên quan là hằng số, trừ khi được nêu khác.

| Collection và thao tác | Cách mô tả phù hợp | Điều cần giữ trong đầu |
| --- | --- | --- |
| `ArrayList.get(index)` | `O(1)` | Đã có chỉ số hợp lệ, không cần tìm giá trị |
| `ArrayList.add(element)` | Khấu hao `O(1)`; một lần tăng mảng có thể `O(n)` | Áp dụng cho thêm cuối và chuỗi được phân tích |
| `ArrayList.add(0, element)` | `O(n)` | Cần dịch phần tử dù không tăng mảng |
| `ArrayList.contains(value)` | Trường hợp xấu `O(n)` | Trung bình phụ thuộc phân phối truy vấn |
| `HashMap.get(key)` | Hằng số với giả định băm phân tán tốt | Không có bảo đảm hằng số cho mọi khóa |
| Chuỗi `HashMap.put(key, value)` | Thường phân tích kỳ vọng khấu hao `O(1)` dưới các giả định đã nêu | Xét riêng va chạm và tăng bảng |
| Thêm/lấy ở hai đầu `ArrayDeque` | Khấu hao `O(1)` | Không suy sang tìm hoặc xóa theo giá trị |
| `TreeMap.get/put/remove` | Bảo đảm `O(log n)` theo số bước so sánh | Chi phí một phép so sánh có thể phụ thuộc dữ liệu khóa |

## 9. Phạm vi của chuỗi thao tác có thể làm thay đổi kết luận

### 9.1. Không bỏ qua thao tác chủ động thay đổi dung lượng

Phân tích khấu hao thêm cuối dựa vào việc giữ lại các ô trống sau tăng dung lượng. Nếu ứng dụng chủ động phá điều kiện đó, phải phân tích lại cả chuỗi.

Ví dụ mã minh họa, đặt bên trong một phương thức có sẵn:

```java
ArrayList<Integer> values = new ArrayList<>();
for (int i = 0; i < limit; i++) {
    values.add(i);
    values.trimToSize();
}
```

`trimToSize()` yêu cầu thu dung lượng về kích thước hiện tại. Gọi sau mỗi lần thêm có thể liên tục làm mất phần dung lượng dư và tạo lại công việc sao chép tuyến tính. Không được lấy cận khấu hao của một chuỗi chỉ thêm cuối rồi áp vào chuỗi mới mà bỏ qua chi phí `trimToSize()` và ảnh hưởng của nó. Trong mô hình mảng thực hiện sao chép tuyến tính để thu dung lượng, chuỗi này có thể có tổng chi phí bậc hai.

Đoạn trên không phải hướng dẫn tối ưu bộ nhớ. Nó minh họa việc **thêm một loại thao tác vào chuỗi có thể thay đổi chứng minh**.

### 9.2. Chuẩn bị dung lượng chuyển thời điểm trả chi phí

Nếu biết sẽ thêm khoảng `expectedCount` phần tử:

```java
List<String> names = new ArrayList<>(expectedCount);
```

Constructor tạo danh sách có **kích thước bằng `0`**, dung lượng dự kiến không phải số phần tử hiện có. Phần bộ nhớ chuẩn bị trước có chi phí và có thể giảm số lần tăng mảng trong giai đoạn thêm. Không có nghĩa toàn bộ công việc chuẩn bị trở thành miễn phí.

Với `HashMap`, tham số dung lượng ban đầu liên quan số bucket, không đồng nhất với số ánh xạ mong đợi do còn hệ số tải. Không sao chép cách suy luận của `ArrayList` sang `HashMap` mà bỏ điều kiện đó.

## 10. Từ độ phức tạp đến quyết định thiết kế và phép đo

### 10.1. Tổng lượng việc và độ trễ một lần gọi

Hai yêu cầu sau không đồng nhất:

- “Nạp một triệu phần tử với tổng lượng công việc tăng tuyến tính.”
- “Không một lần thêm nào được có đỉnh công việc tuyến tính.”

Khấu hao hằng số phù hợp để lập luận về tổng lượng công việc của quá trình nạp. Nó không đáp ứng tự động yêu cầu độ trễ chặt cho từng lần gọi.

Khi độ trễ quan trọng, có thể xem xét chuẩn bị dung lượng từ trước, giới hạn kích thước dữ liệu hoặc chọn cấu trúc phù hợp với mẫu thao tác. Sau đó vẫn cần đo trên JVM và tải thực tế. Không có collection tốt nhất chỉ từ một nhãn Big-O.

### 10.2. Đừng suy độ phức tạp từ một lần bấm đồng hồ

Một lần đo bằng `System.nanoTime()` có thể bị chi phối bởi khởi động JVM, JIT, GC, cấp phát, nhiễu hệ thống hoặc mã kiểm tra. Một khoảng thời gian nhỏ cũng không cho biết ta đang quan sát nhánh không tăng dung lượng hay nhánh phải sao chép.

Một đánh giá hữu ích cần xác định:

1. **Tác vụ:** thêm cuối, thêm đầu, tra cứu thành công, tra cứu thất bại hay trộn nhiều thao tác?
2. **Trạng thái:** collection mới, đã có sẵn dữ liệu, gần đầy hay đã được cấp đủ dung lượng?
3. **Dữ liệu:** số phần tử, kích thước khóa, chất lượng băm và tần suất truy vấn?
4. **Chỉ số:** tổng thời gian, số thao tác mỗi giây hay phân bố độ trễ từng thao tác?
5. **Cách so sánh:** cùng chức năng, cùng điều kiện khởi đầu và nhiều kích thước dữ liệu?

Đếm thao tác như chương trình trong bài giúp kiểm chứng cơ chế mà không bị nhiễu thời gian. Đo hiệu năng giúp biết cơ chế đó biểu hiện ra sao trong môi trường chạy cụ thể. Hai cách bổ sung cho nhau.

## 11. Những cách kết luận dễ sai

| Phát biểu dễ gây hiểu nhầm | Cách diễn đạt chính xác hơn |
| --- | --- |
| “Khấu hao là trường hợp trung bình.” | Khấu hao phân bổ tổng chi phí một chuỗi; trung bình cần phân phối xác suất đầu vào. |
| “`ArrayList.add` là `O(1)`, nên mọi lần gọi đều nhanh như nhau.” | Thêm cuối là khấu hao `O(1)`; lần phải tăng mảng có thể tuyến tính. |
| “Tìm kiếm trung bình qua nửa danh sách nên là `O(1)`.” | `(n + 1) / 2` vẫn là `Θ(n)`. |
| “Mọi thao tác đều có trường hợp xấu `O(n)`, nên tổng chắc chắn là `Θ(mn)`.” | Nhân các cận trên có thể tạo cận lỏng; muốn cận chặt phải xem các trạng thái đắt có lặp lại được sau mỗi bước không. |
| “Đo một nghìn lần rồi chia trung bình là chứng minh khấu hao.” | Đó là số đo trên một chuỗi; chứng minh phải bao quát mọi chuỗi trong phạm vi đã nêu. |
| “`HashMap` luôn hằng số vì đã có cây chống va chạm.” | Phải nêu giả định băm, đặc điểm khóa và chi phí phương thức khóa; không gán bảo đảm không có trong API. |
| “Đã chuẩn bị dung lượng nên mọi chi phí bộ nhớ đã biến mất.” | Công việc được chuyển về giai đoạn chuẩn bị; vẫn cần tính chi phí và bộ nhớ giữ lại. |
| “Một triệu lần thêm cuối và một triệu lần chèn đầu là cùng bài toán.” | Chèn đầu còn phải dịch phần tử; khấu hao tăng dung lượng không loại bỏ khoản đó. |

## 12. Tự kiểm tra cách lập luận

### Câu 1: Một mảng động tăng gấp đôi có một lần thêm tốn `n + 1` đơn vị. Có bác bỏ được khấu hao hằng số không?

Không. Phải xét tổng chi phí cả chuỗi. Các lần tăng dung lượng sao chép `1, 2, 4, ...` phần tử có tổng tuyến tính theo số lần thêm. Lần đắt vẫn tồn tại, nhưng không xảy ra ở mọi lần thêm trong chuỗi chỉ thêm cuối.

### Câu 2: Tìm một phần tử có sẵn, mọi vị trí đều được chọn như nhau. Trung bình có nhanh hơn trường hợp xấu về bậc tăng không?

Không. Trung bình cần `(n + 1) / 2` phép so sánh, trường hợp xấu cần `n`; cả hai đều có bậc tuyến tính. Hệ số khác nhau có ý nghĩa thực tế nhưng không thay đổi bậc tăng.

### Câu 3: Chương trình nhận dữ liệu không đáng tin cậy và tra cứu bằng `HashMap`. Có đủ cơ sở để hứa mọi truy vấn đều `O(1)` không?

Không. Cần xét khả năng va chạm, chi phí xử lý khóa và đặc điểm triển khai. Phát biểu dựa trên băm phân tán tốt không phải bảo đảm trường hợp xấu cho mọi đầu vào.

### Câu 4: Vì sao `ArrayList.add(0, value)` không hưởng tổng chi phí tuyến tính khi lặp lại nhiều lần từ danh sách rỗng?

Vì mỗi lần chèn phải dịch các phần tử hiện có. Tổng số phần tử dịch là `0 + 1 + ... + (m - 1) = Θ(m²)`. Cơ chế tăng dung lượng tốt chỉ xử lý chi phí cấp phát lại, không xử lý chi phí dịch vị trí.

### Bài thực hành

1. Đổi số lần thêm trong `CostModelsDemo` từ `16` sang `17`. Dự đoán số phần tử sao chép, tổng chi phí và chi phí lần thêm cuối trước khi chạy.
2. Tính số phép so sánh trung bình nếu mục tiêu chỉ là phần tử đầu với xác suất `0.9` và phần tử cuối với xác suất `0.1` trong danh sách `n` phần tử.
3. Viết một câu mô tả hiệu năng cho một tác vụ thực tế của bạn, nêu đủ thao tác, kích thước, loại phân tích và giả định.

Đáp án để đối chiếu:

- Với `17` lần thêm: thêm lần thứ `17` sao chép `16` phần tử; tổng sao chép là `31`, tổng chi phí là `48`, chi phí lần cuối là `17`.
- Mô hình truy vấn câu 2 có kỳ vọng `0.9 × 1 + 0.1 × n = 0.9 + 0.1n`, vẫn là `Θ(n)` khi `n` tăng.
- Ví dụ câu mô tả: “Khi nạp `m` phần tử bằng cách thêm cuối vào `ArrayList` mới, tổng chi phí thêm có bậc `O(m)` theo bảo đảm khấu hao; một lần tăng mảng vẫn có thể tốn công việc tuyến tính theo kích thước lúc đó.”

Khi đánh giá collection, hãy xác định rõ **một lần gọi hay cả chuỗi**, **phân phối nào nếu nói trung bình**, và **trạng thái/chi phí nào đã được tính**. Ba câu hỏi này giúp biến một nhãn Big-O thành một lập luận có thể kiểm tra.
