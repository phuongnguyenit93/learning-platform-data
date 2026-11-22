# Ngăn xếp đơn điệu và phần tử gần nhất thỏa điều kiện

Khi xử lý dãy, nhiều bài toán hỏi: “phần tử **gần vị trí i nhất** ở bên trái hoặc bên phải có giá trị **lớn hơn/nhỏ hơn** a[i] là phần tử nào?”. Ví dụ: ngày tiếp theo có nhiệt độ cao hơn, giá cổ phiếu gần nhất ở quá khứ cao hơn giá hôm nay, hoặc thanh biểu đồ gần nhất có chiều cao thấp hơn để xác định độ rộng một hình chữ nhật.

Nếu với mỗi i ta quét tuyến tính đến khi gặp phần tử phù hợp, độ phức tạp có thể đạt **O(n²)**. **Ngăn xếp đơn điệu (monotonic stack)** khai thác quan hệ thứ tự để xử lý toàn bộ n vị trí trong **O(n)** thời gian.

## 1. Định nghĩa chính xác “phần tử gần nhất”

Cho dãy a[0..n−1]. “Gần nhất” là **gần theo chỉ số trong dãy**, không phải phần tử có giá trị gần a[i] nhất. Khi hỏi bên trái, chỉ xét j < i và chọn j **lớn nhất** thỏa điều kiện; khi hỏi bên phải, chỉ xét j > i và chọn j **nhỏ nhất** thỏa điều kiện.

Bốn dạng thường gặp:

| Dạng truy vấn tại i | Điều kiện của vị trí j | Chọn j |
| --- | --- | --- |
| **Previous Greater Element (PGE)** – lớn hơn gần nhất bên trái | j < i và a[j] > a[i] | j lớn nhất |
| **Next Greater Element (NGE)** – lớn hơn gần nhất bên phải | j > i và a[j] > a[i] | j nhỏ nhất |
| **Previous Smaller Element (PSE)** – nhỏ hơn gần nhất bên trái | j < i và a[j] < a[i] | j lớn nhất |
| **Next Smaller Element (NSE)** – nhỏ hơn gần nhất bên phải | j > i và a[j] < a[i] | j nhỏ nhất |

Bảng dùng so sánh **nghiêm ngặt** (> hoặc <). Nếu đề hỏi **lớn hơn hoặc bằng** (≥) hay **nhỏ hơn hoặc bằng** (≤), điều kiện loại phần tử khỏi stack sẽ thay đổi.

Ví dụ với dãy:

~~~text
index:    0  1  2  3  4  5
a[index]: 2  1  2  4  3  4
~~~

Các chỉ số kết quả là:

| i | a[i] | PGE | NGE | PSE | NSE |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 0 | 2 | −1 | 3 | −1 | 1 |
| 1 | 1 | 0 | 2 | −1 | −1 |
| 2 | 2 | −1 | 3 | 1 | −1 |
| 3 | 4 | −1 | −1 | 2 | 4 |
| 4 | 3 | 3 | 5 | 2 | −1 |
| 5 | 4 | −1 | −1 | 4 | −1 |

**−1** là ký hiệu “không tồn tại”. Chẳng hạn tại i = 4, a[i] = 3: phần tử lớn hơn gần nhất bên trái là a[3] = 4; phần tử lớn hơn gần nhất bên phải là a[5] = 4. Tại i = 2, giá trị a[0] = 2 **không** được tính là “lớn hơn” a[2] = 2 do hai giá trị bằng nhau.

Một bài có thể yêu cầu **chỉ số**, **giá trị** hoặc **khoảng cách**:

- Chỉ số: trả j (hoặc −1 nếu không có).
- Giá trị: trả a[j] khi j tồn tại.
- Khoảng cách: bên phải là j − i; bên trái là i − j.

Giữ **chỉ số** trong stack thường linh hoạt hơn giữ riêng giá trị, vì từ chỉ số có thể lấy cả giá trị và khoảng cách.

## 2. Bất biến của ngăn xếp đơn điệu

Stack thường được biểu diễn bằng cấu trúc **LIFO**: phần tử thêm sau nằm trên đỉnh và được lấy ra trước. Với ngăn xếp đơn điệu, ta chủ động **pop** những ứng viên không còn hữu ích để giá trị ứng với các chỉ số còn trong stack duy trì một thứ tự nhất định.

- **Stack giảm dần theo giá trị**: từ đáy đến đỉnh, giá trị giảm dần; hữu ích khi tìm phần tử **lớn hơn**.
- **Stack tăng dần theo giá trị**: từ đáy đến đỉnh, giá trị tăng dần; hữu ích khi tìm phần tử **nhỏ hơn**.

Cụm từ “stack tăng/giảm” dễ gây nhầm nếu người nói tính từ **đỉnh đến đáy**; ở đây mọi mô tả đều tính **từ đáy đến đỉnh**. Với bài strict, quy tắc pop được chọn để các giá trị còn lại là **strictly increasing/decreasing**. Với phiên bản không nghiêm ngặt, stack có thể giữ các giá trị bằng nhau.

Nguyên tắc nền tảng: một ứng viên cũ có thể bị loại nếu đã có ứng viên mới **gần hơn** và có giá trị ít nhất phù hợp bằng ứng viên cũ cho mọi so sánh tiếp theo.

### Tại sao có thể bỏ phần tử bị pop?

Khi quét trái sang phải để tìm **lớn hơn gần nhất bên trái**, giả sử đang xử lý a[i] và đỉnh stack là j < i với **a[j] ≤ a[i]**. Ta có thể pop j:

- j không thể là đáp án của i vì a[j] không lớn hơn a[i].
- Với bất cứ vị trí tương lai k > i, nếu a[j] > a[k] thì a[i] ≥ a[j] > a[k], đồng thời i nằm gần k hơn j. Vì vậy j sẽ không thể thắng i trong vai trò phần tử lớn hơn gần nhất bên trái của k.

Đây là lập luận **ứng viên bị ứng viên khác che khuất (dominated)**. Sau khi loại các ứng viên bị che khuất, phần tử còn trên đỉnh là phần tử phù hợp gần nhất.

## 3. Công thức quét một chiều cho bốn trường hợp

Ta lưu **index** trong một **Deque<Integer>** (Java), dùng thao tác push/pop/peek tại cùng một đầu.

| Truy vấn strict | Hướng quét | Pop khi | Đáp án sau khi pop |
| --- | --- | --- | --- |
| **PGE: previous >** | Trái → phải | a[top] ≤ a[i] | Chỉ số trên đỉnh còn lại |
| **NGE: next >** | Phải → trái | a[top] ≤ a[i] | Chỉ số trên đỉnh còn lại |
| **PSE: previous <** | Trái → phải | a[top] ≥ a[i] | Chỉ số trên đỉnh còn lại |
| **NSE: next <** | Phải → trái | a[top] ≥ a[i] | Chỉ số trên đỉnh còn lại |

Sau khi xác định đáp án (hoặc −1 nếu stack trống), **push i**.

Để dễ nhớ: muốn tìm **lớn hơn nghiêm ngặt**, loại các phần tử **≤** giá trị hiện tại; muốn tìm **nhỏ hơn nghiêm ngặt**, loại các phần tử **≥** giá trị hiện tại. Muốn tìm **previous** thì duyệt từ trái qua; muốn tìm **next** bằng phương pháp “đỉnh sau khi pop” thì duyệt từ phải qua.

### Giả mã: lớn hơn gần nhất bên trái

~~~text
stack = ngăn xếp rỗng chứa chỉ số
answer[0..n-1] = -1

for i = 0..n-1:
    while stack không rỗng và a[stack.top] <= a[i]:
        stack.pop()
    if stack không rỗng:
        answer[i] = stack.top
    stack.push(i)
~~~

Các phần tử bị pop không quay lại stack. Một chỉ số chỉ được push **một lần** và pop **tối đa một lần**.

### Truy vết từng bước với dãy [2, 1, 2, 4, 3, 4]

Tìm **PGE** (lớn hơn strict gần nhất bên trái), mô tả stack theo thứ tự đáy → đỉnh:

| i | a[i] | Pop do ≤ a[i] | PGE[i] | Stack sau khi push i (dạng chỉ số) |
| ---: | ---: | --- | ---: | --- |
| 0 | 2 | Không | −1 | [0] |
| 1 | 1 | Không | 0 | [0, 1] |
| 2 | 2 | 1, 0 | −1 | [2] |
| 3 | 4 | 2 | −1 | [3] |
| 4 | 3 | Không | 3 | [3, 4] |
| 5 | 4 | 4, 3 | −1 | [5] |

Khi i = 2, a[2] = 2, việc pop cả chỉ số 1 (giá trị 1) và chỉ số 0 (giá trị 2) cho thấy **phần tử bằng nhau không được xem là lớn hơn strict**.

## 4. Phân biệt strict và không strict khi có phần tử bằng nhau

Đây là một trong các nguồn gây sai đáp án thường gặp nhất.

| Muốn tìm | Giữ lại đỉnh nếu | Pop khi |
| --- | --- | --- |
| Lớn hơn **>** | a[top] > a[i] | a[top] ≤ a[i] |
| Lớn hơn hoặc bằng **≥** | a[top] ≥ a[i] | a[top] < a[i] |
| Nhỏ hơn **<** | a[top] < a[i] | a[top] ≥ a[i] |
| Nhỏ hơn hoặc bằng **≤** | a[top] ≤ a[i] | a[top] > a[i] |

Quy tắc này áp dụng cho cách làm **pop rồi lấy đỉnh** ở mục 3, bất kể duyệt từ phía nào. Ví dụ, với **[5, 5, 3]**:

- Previous greater **strict** của phần tử ở i = 1 là **−1**, bởi 5 không lớn hơn 5.
- Previous greater **or equal** của i = 1 là chỉ số **0**.
- Next smaller strict của i = 0 là chỉ số **2**, vì a[1] = 5 bằng nhau còn a[2] = 3 nhỏ hơn.
- Next smaller or equal của i = 0 là chỉ số **1**, vì a[1] = 5 thỏa ≤ 5 và gần hơn.

Không nên chọn dấu pop theo tên “stack tăng dần” mà quên so sánh **nghiêm ngặt** hay **không nghiêm ngặt** trong đề bài.

## 5. Hai cách phổ biến để tìm phần tử bên phải

Có hai khuôn mẫu đều có thể chạy **O(n)**.

### Cách A: quét phải → trái rồi lấy đỉnh

Đây là cách trong bảng ở mục 3. Khi tới i, stack chứa ứng viên ở **bên phải** i; loại các ứng viên không thỏa điều kiện rồi lấy đỉnh làm đáp án. Sau đó push i.

Ví dụ tìm next greater strict, dùng quy tắc pop **a[top] ≤ a[i]**.

### Cách B: quét trái → phải, giải đáp cho chỉ số khi nó bị pop

~~~text
answer[0..n-1] = -1
stack = rỗng

for i = 0..n-1:
    while stack không rỗng và a[i] > a[stack.top]:
        j = stack.pop()
        answer[j] = i
    stack.push(i)
~~~

Ở cách B, các chỉ số còn trên stack **đang chờ** một phần tử lớn hơn ở bên phải. Khi a[i] thực sự lớn hơn a[j], i là phần tử đầu tiên thỏa điều kiện cho j vì mọi vị trí trung gian đã được xử lý mà chưa khiến j bị pop.

Điểm dễ nhầm: **dấu so sánh trong vòng while của cách B đảo vị trí hai toán hạng** so với cách A. Với “next greater strict”, cách A pop khi **a[top] ≤ a[i]** trong vòng quét ngược; cách B pop khi **a[i] > a[top]** trong vòng quét xuôi. Ở cách B, phần tử **bằng nhau vẫn được giữ chờ**, vì không thỏa “lớn hơn strict”.

Cách B đặc biệt thuận tiện cho dạng bài “bao nhiêu ngày nữa nhiệt độ cao hơn?”, vì ngay khi pop j, có thể gán **answer[j] = i − j**.

## 6. Java 17+: cài đặt đầy đủ bốn dạng và bài toán nhiệt độ

Mã dưới đây là một chương trình độc lập. Tất cả kết quả nearest đều là **chỉ số 0-based**; **−1** nghĩa là không có phần tử thỏa. Bốn hàm đầu áp dụng khuôn mẫu A, còn hàm **daysUntilWarmer** áp dụng khuôn mẫu B.

~~~java
import java.util.ArrayDeque;
import java.util.Arrays;
import java.util.Deque;

public class MonotonicStackDemo {

    // Chỉ số lớn hơn strict gần nhất bên trái.
    static int[] previousGreater(int[] a) {
        int[] answer = new int[a.length];
        Arrays.fill(answer, -1);
        Deque<Integer> stack = new ArrayDeque<>();

        for (int i = 0; i < a.length; i++) {
            while (!stack.isEmpty() && a[stack.peek()] <= a[i]) {
                stack.pop();
            }
            if (!stack.isEmpty()) {
                answer[i] = stack.peek();
            }
            stack.push(i);
        }
        return answer;
    }

    // Chỉ số lớn hơn strict gần nhất bên phải.
    static int[] nextGreater(int[] a) {
        int[] answer = new int[a.length];
        Arrays.fill(answer, -1);
        Deque<Integer> stack = new ArrayDeque<>();

        for (int i = a.length - 1; i >= 0; i--) {
            while (!stack.isEmpty() && a[stack.peek()] <= a[i]) {
                stack.pop();
            }
            if (!stack.isEmpty()) {
                answer[i] = stack.peek();
            }
            stack.push(i);
        }
        return answer;
    }

    // Chỉ số nhỏ hơn strict gần nhất bên trái.
    static int[] previousSmaller(int[] a) {
        int[] answer = new int[a.length];
        Arrays.fill(answer, -1);
        Deque<Integer> stack = new ArrayDeque<>();

        for (int i = 0; i < a.length; i++) {
            while (!stack.isEmpty() && a[stack.peek()] >= a[i]) {
                stack.pop();
            }
            if (!stack.isEmpty()) {
                answer[i] = stack.peek();
            }
            stack.push(i);
        }
        return answer;
    }

    // Chỉ số nhỏ hơn strict gần nhất bên phải.
    static int[] nextSmaller(int[] a) {
        int[] answer = new int[a.length];
        Arrays.fill(answer, -1);
        Deque<Integer> stack = new ArrayDeque<>();

        for (int i = a.length - 1; i >= 0; i--) {
            while (!stack.isEmpty() && a[stack.peek()] >= a[i]) {
                stack.pop();
            }
            if (!stack.isEmpty()) {
                answer[i] = stack.peek();
            }
            stack.push(i);
        }
        return answer;
    }

    // Số ngày phải chờ để có nhiệt độ lớn hơn strict.
    static int[] daysUntilWarmer(int[] temperatures) {
        int[] answer = new int[temperatures.length];
        Deque<Integer> waiting = new ArrayDeque<>();

        for (int i = 0; i < temperatures.length; i++) {
            while (!waiting.isEmpty()
                    && temperatures[i] > temperatures[waiting.peek()]) {
                int previousDay = waiting.pop();
                answer[previousDay] = i - previousDay;
            }
            waiting.push(i);
        }
        return answer; // Vị trí không có ngày ấm hơn giữ giá trị 0.
    }

    public static void main(String[] args) {
        int[] a = {2, 1, 2, 4, 3, 4};
        System.out.println("Gia tri: " + Arrays.toString(a));
        System.out.println("Truoc lon hon: "
                + Arrays.toString(previousGreater(a)));
        System.out.println("Sau lon hon: "
                + Arrays.toString(nextGreater(a)));
        System.out.println("Truoc nho hon: "
                + Arrays.toString(previousSmaller(a)));
        System.out.println("Sau nho hon: "
                + Arrays.toString(nextSmaller(a)));

        int[] temperatures = {73, 74, 75, 71, 69, 72, 76, 73};
        System.out.println("Ngay cho am hon: "
                + Arrays.toString(daysUntilWarmer(temperatures)));
    }
}
~~~

Lưu tệp với tên đúng **MonotonicStackDemo.java**, sau đó biên dịch và chạy với JDK 17 hoặc mới hơn:

~~~bash
javac MonotonicStackDemo.java
java MonotonicStackDemo
~~~

Đầu ra dự kiến chính xác:

~~~text
Gia tri: [2, 1, 2, 4, 3, 4]
Truoc lon hon: [-1, 0, -1, -1, 3, -1]
Sau lon hon: [3, 2, 3, -1, 5, -1]
Truoc nho hon: [-1, -1, 1, 2, 2, 4]
Sau nho hon: [1, -1, -1, 4, -1, -1]
Ngay cho am hon: [1, 1, 4, 2, 1, 1, 0, 0]
~~~

Giải thích đầu ra:

- Tại i = 2, a[i] = 2, **PGE = −1** vì giá trị 2 ở vị trí 0 không lớn hơn nghiêm ngặt.
- Tại i = 3, a[i] = 4, **NGE = −1** vì phần tử 4 ở vị trí 5 bằng 4.
- Tại i = 4, a[i] = 3, **NGE = 5**; khoảng cách là 5 − 4 = 1.
- Với chuỗi nhiệt độ, ngày i = 2 có nhiệt độ 75; ngày i = 6 mới có 76 > 75, nên phải chờ **4 ngày**.
- Giá trị mặc định 0 của **daysUntilWarmer** không có nghĩa là một ngày có độ chênh bằng 0; nó báo **không tồn tại ngày ấm hơn ở phía sau** theo quy ước của bài này.

Trong Java, **ArrayDeque** được ưu tiên cho thao tác stack phổ biến thay cho lớp **Stack** cũ. Không dùng **peek()** khi stack rỗng; các vòng lặp kiểm tra **!stack.isEmpty()** trước khi truy cập đỉnh.

## 7. Vì sao tổng thời gian là O(n), dù có vòng while lồng nhau?

Nhìn vào mã sẽ thấy vòng **for** và một vòng **while** bên trong, nhưng không thể kết luận ngay O(n²).

Trong một lượt xử lý:

1. Mỗi chỉ số i được **push đúng một lần**.
2. Một chỉ số đã pop không được push lại trong lượt đó.
3. Vì vậy tổng số lần pop trong cả vòng for là **tối đa n**, dù tại một i có thể pop rất nhiều chỉ số.
4. Mỗi push, pop và peek của ArrayDeque có chi phí O(1) theo phân tích thông thường.

Tổng cộng có n lần push và tối đa n lần pop → **O(n) thời gian** để tạo n kết quả. Đây là **phân tích chi phí khấu hao (amortized analysis)**: một vòng while đơn lẻ có thể làm O(n) việc, nhưng không thể làm vậy tại mọi i.

Bộ nhớ phụ: **O(n)** trong trường hợp xấu nhất cho stack. Mảng answer thêm **O(n)** đầu ra. Nếu phải giữ toàn bộ n đáp án, bộ nhớ tổng cũng là O(n).

Đối với dãy rỗng, các hàm Java trả mảng rỗng; đối với dãy chỉ có một phần tử, cả bốn truy vấn nearest strict trả **[−1]**. Với dữ liệu toàn phần tử bằng nhau, truy vấn strict không tìm được phần tử lớn hơn/nhỏ hơn; nên tất cả chỉ số nearest là −1.

## 8. Ứng dụng: stock span và vùng hình chữ nhật lớn nhất

### 8.1. Stock span: liên tiếp bao nhiêu ngày trước có giá ≤ hôm nay?

Cho giá cổ phiếu từng ngày, **span[i]** là số ngày liên tiếp tính cả hôm nay và đi ngược về trước mà giá **≤ price[i]**.

Ví dụ:

~~~text
price: [100, 80, 60, 70, 60, 75, 85]
span:  [  1,  1,  1,  2,  1,  4,  6]
~~~

Tìm **previous greater strict** j (giá > price[i]); khi không có, đặt j = −1. Khi đó:

**span[i] = i − j**.

Vì các ngày nằm giữa j và i (nếu có) không có giá cao hơn giá hôm nay, chúng thuộc khoảng span. Ngày tại j bị loại vì có giá lớn hơn.

Ví dụ i = 5, price[5] = 75; previous greater strict nằm tại i = 1 (giá 80), nên span = 5 − 1 = 4, ứng với các ngày 2, 3, 4, 5. Nếu thay điều kiện thành “giá thấp hơn strict” thì công thức cho bài stock span này sẽ sai ở trường hợp giá bằng nhau.

### 8.2. Largest rectangle in histogram: thanh thấp hơn gần nhất

Cho biểu đồ với chiều cao không âm **h[0..n−1]**, các thanh có bề rộng đơn vị. Muốn tìm hình chữ nhật diện tích lớn nhất nằm hoàn toàn trong các thanh, ta có thể chọn mỗi vị trí i làm **chiều cao tối thiểu h[i]**.

Gọi:

- **L[i]**: chỉ số thanh thấp hơn strict (< h[i]) gần nhất ở bên trái, hoặc −1 nếu không có.
- **R[i]**: chỉ số thanh thấp hơn strict (< h[i]) gần nhất ở bên phải, hoặc n nếu không có.

Khi đó:

**width[i] = R[i] − L[i] − 1**,  
**area[i] = h[i] × width[i]**,  
**answer = max area[i]**.

Ví dụ:

~~~text
h: [2, 1, 5, 6, 2, 3]
          ^
   hai thanh 5 và 6 tạo hình chữ nhật cao 5, rộng 2
~~~

Đối với h[2] = 5, L[2] = 1 (cao 1), R[2] = 4 (cao 2), nên width = 4 − 1 − 1 = 2 và area = 5 × 2 = **10**. Đây là diện tích lớn nhất của ví dụ.

**Với thanh bằng chiều cao:** nếu tính biên bằng phần tử thấp hơn **strict**, các thanh bằng nhau vẫn được xem là thuộc vùng có chiều cao tối thiểu ấy. Một cách giải tương đương có thể dùng quy ước bất đối xứng giữa hai phía (một bên strict, bên kia không strict), miễn là chiều rộng và cách xử lý các phần tử bằng nhau nhất quán. Khi sử dụng **−1** ở trái và **n** ở phải làm sentinel, không được nhầm sentinel này với quy ước **−1** cho cả hai phía của hàm nearest thông thường.

## 9. Khi nào ngăn xếp đơn điệu không phải lựa chọn đúng?

Ngăn xếp đơn điệu giải tốt bài toán mà **điều kiện thứ tự cho phép loại bỏ vĩnh viễn ứng viên bị che khuất**. Không nên mặc định nó giải mọi câu hỏi “gần nhất”.

- **Nearest greater/smaller theo chỉ số**: phù hợp, vì điều kiện so sánh tạo được tính chất che khuất.
- **Giá trị gần nhất theo độ lớn |a[j] − a[i]|**: đó là bài toán khác; chỉ số gần nhất theo vị trí và giá trị gần nhất là hai khái niệm khác nhau.
- **Phần tử có tổng chữ số thỏa một ràng buộc tùy ý**: không thể lấy một quy tắc pop greater/smaller rồi mặc định đúng; cần chứng minh điều kiện loại bỏ ứng viên.
- **Cực đại/cực tiểu trong cửa sổ trượt độ dài k**: thường dùng **deque đơn điệu** (monotonic deque), vì phải loại phần tử đã **ra ngoài cửa sổ ở đầu deque**, bên cạnh việc loại phần tử kém ưu thế ở đuôi.
- **Truy vấn cập nhật điểm và hỏi max/min trên nhiều đoạn tùy ý**: có thể cần segment tree hoặc cấu trúc truy vấn đoạn, thay vì chạy lại một stack từ đầu cho mỗi truy vấn.

Ngăn xếp đơn điệu cũng không có nghĩa là dữ liệu đầu vào đã được sắp xếp. Chính **tập ứng viên còn lại trên stack** mới duy trì thứ tự đơn điệu.

## 10. Quy trình giải một bài nearest element

1. **Đặc tả đầu ra.** Cần chỉ số, giá trị, khoảng cách, số ngày chờ hay độ rộng? Với trường hợp không tồn tại dùng −1, 0 hay n?
2. **Xác định hướng tìm.** “Trước/bên trái” khác “sau/bên phải”; chọn hướng quét hoặc chọn khuôn mẫu gán kết quả khi pop.
3. **Xác định dấu so sánh.** Strict >, strict <, ≥ và ≤ cho bốn quy tắc pop khác nhau. Dùng một ca có hai giá trị bằng nhau để tự kiểm tra.
4. **Chọn bất biến stack.** Với truy vấn greater, giữ ứng viên có giá trị giảm dần từ đáy đến đỉnh; với smaller, giữ tăng dần, theo quy ước mục 2.
5. **Lưu chỉ số.** Từ index có thể tính value, distance; tránh mất thông tin khi giá trị trùng nhau.
6. **Chốt xử lý không tồn tại.** Với nearest thông thường, điền −1; với daily temperatures, 0; với histogram, biên phải dùng n.
7. **Kiểm tra ca đặc biệt.** n = 0, n = 1, tất cả bằng nhau, tăng nghiêm ngặt, giảm nghiêm ngặt, có số âm, phần tử cực trị nằm ở đầu/cuối.
8. **Chứng minh.** Giải thích vì sao phần tử bị pop không thể là đáp án trong tương lai và vì sao phần tử còn trên đỉnh là gần nhất hợp lệ. Sau đó phân tích push/pop để ra O(n).

### Các lỗi thường gặp

- **Dùng >= thay vì > (hoặc ngược lại).** Dãy có phần tử bằng nhau sẽ cho đáp án khác.
- **Trả giá trị thay vì chỉ số.** Nếu đề cần khoảng cách, chỉ giá trị không đủ để tính i − j.
- **Nhầm hướng duyệt.** Quét trái → phải và lấy đỉnh tạo đáp án bên trái; muốn đáp án bên phải bằng cách ấy phải duyệt ngược hoặc dùng cơ chế trả lời khi pop.
- **Quên khởi tạo sentinel.** Các chỉ số không bao giờ tìm thấy ứng viên phải mang giá trị không tồn tại đúng quy ước.
- **Không pop hết ứng viên bị che khuất.** Chỉ kiểm tra một lần bằng if không bảo đảm bất biến; cần while.
- **Đếm O(n²) chỉ từ vòng lặp lồng nhau.** Cần phân tích tổng số lần push/pop trong suốt vòng for.
- **Dùng quy tắc histogram không thống nhất với trùng chiều cao.** Kiểm tra bằng [2, 2], [2, 2, 2] và các thanh lặp.
- **Tràn số khi tính diện tích/khoảng cách lớn.** Nếu h[i] và n lớn, dùng long cho phép nhân **(long) h[i] × width[i]** dù chỉ số vẫn là int.
- **Sửa dãy sau khi dựng kết quả.** Mảng nearest đã tính dựa trên dữ liệu cũ; khi dữ liệu thay đổi, phải cập nhật hoặc tính lại bằng cơ chế phù hợp.

## 11. Tự kiểm tra

**Câu 1.** Với a = [4, 4, 2], next smaller strict của i = 0 là chỉ số nào?  
**Đáp án:** 2, vì phần tử ở i = 1 bằng 4 nên không thỏa dấu <.

**Câu 2.** Với a = [4, 4, 2], next smaller or equal của i = 0 là chỉ số nào?  
**Đáp án:** 1, vì a[1] = 4 ≤ a[0] = 4 và là phần tử gần nhất ở bên phải.

**Câu 3.** Với a = [1, 3, 2], previous greater strict của phần tử a[2] = 2 là gì?  
**Đáp án:** Chỉ số 1, giá trị 3; khoảng cách bên trái là 2 − 1 = 1.

**Câu 4.** Vì sao thuật toán có while bên trong for vẫn O(n)?  
**Đáp án:** Trong một lần quét, mỗi chỉ số được push đúng một lần và pop tối đa một lần; tổng số lần pop bị chặn bởi n.

**Câu 5.** Stock span có cần gộp các ngày có giá **bằng** giá hôm nay không?  
**Đáp án:** Có, theo định nghĩa span sử dụng điều kiện giá ≤ giá hôm nay. Vì vậy phải tìm previous **strictly greater**, không phải previous greater-or-equal.

## 12. Ghi nhớ

**Ngăn xếp đơn điệu** biến n lần tìm phần tử gần nhất theo quan hệ lớn/nhỏ thành một lượt quét **O(n)** bằng cách lưu chỉ số các ứng viên còn hữu ích. Trước khi viết code, luôn chốt ba điều: **trái hay phải**, **lớn hay nhỏ**, **nghiêm ngặt hay cho phép bằng nhau**. Quy tắc pop đúng, sentinel đúng và lập luận “mỗi chỉ số push một lần, pop tối đa một lần” là ba yếu tố quan trọng nhất để cài đặt và chứng minh thuật toán.