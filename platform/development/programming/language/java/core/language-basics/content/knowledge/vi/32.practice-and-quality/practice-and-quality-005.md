# Gỡ lỗi bằng breakpoint, chạy từng bước và xem giá trị biến trong Java

## 1. Gỡ lỗi (debugging) là gì?

**Debugging** là quá trình xác định nguyên nhân chương trình hoạt động sai và kiểm tra cách sửa. Chương trình có thể **biên dịch thành công** nhưng vẫn tính sai, đi nhầm nhánh `if`, bỏ sót phần tử hoặc ném ngoại lệ khi chạy. Công cụ **debugger** cho phép quan sát trạng thái thực tế của chương trình tại từng thời điểm, thay vì chỉ đoán nguyên nhân từ kết quả cuối.

Ba kỹ năng nền tảng:

- **Đặt breakpoint:** yêu cầu debugger tạm dừng một luồng khi tới vị trí hoặc điều kiện đã chọn.
- **Chạy từng bước:** kiểm soát lệnh tiếp theo được thực hiện, có thể bước qua hoặc đi vào lời gọi phương thức.
- **Xem giá trị biến:** kiểm tra biến cục bộ, tham số, trường đối tượng, biểu thức theo dõi (*watch*) và ngăn xếp lời gọi (*call stack*) tại thời điểm chương trình đang dừng.

Debugger giúp bạn **quan sát lỗi**, không tự chứng minh thuật toán đúng. Sau khi sửa vẫn cần biên dịch, chạy test và kiểm tra các trường hợp biên.

## 2. Breakpoint là gì, đặt ở đâu?

**Breakpoint** là điểm dừng được cấu hình trong debugger. Khi thực thi đạt đến điểm đó, debugger thường **tạm dừng** trước khi thực thi dòng tương ứng và cho phép xem trạng thái chương trình tại vị trí hiện tại. Cách debugger hiển thị vị trí và thời điểm dừng có thể khác khi một dòng có nhiều biểu thức, mã được tối ưu hoặc không có thông tin debug phù hợp.

Cách đặt trong những IDE phổ biến như IntelliJ IDEA, Eclipse hoặc Visual Studio Code (với Java debugging extension):

1. Mở tệp `.java` chứa mã muốn kiểm tra.
2. Nhấp vào phần lề cạnh **dòng có câu lệnh thực thi** để bật breakpoint; biểu tượng thường là một chấm màu.
3. Chạy bằng **Debug**, không phải chỉ **Run**, để debugger quản lý các điểm dừng.
4. Khi dừng, xem dòng hiện tại, các biến trong scope và **Call Stack**.
5. Dùng các điều khiển như Continue/Resume, Step Over, Step Into hoặc Step Out để tiếp tục.

**Nên đặt ở nơi trạng thái có thể đổi hoặc điều kiện quyết định hành vi**, ví dụ:

- Ngay trước `if (value > 0)`: giá trị nào sẽ đi vào nhánh?
- Dòng `sum += value;`: `sum` trước và sau khi cộng là bao nhiêu?
- Dòng `count++;`: có đang đếm đúng loại phần tử không?
- Ngay trước `return`: các biến tổng hợp có đúng kết quả kỳ vọng?

Breakpoint chỉ quan sát được khi luồng thực thi thật sự tới vị trí đó. Nếu đặt trong một nhánh không bao giờ chạy với dữ liệu hiện tại, chương trình sẽ không dừng ở đó. Breakpoint thường cần được đặt trên **dòng có mã thực thi**; không thể kỳ vọng đặt breakpoint trên một dòng chú thích hoặc dòng trống sẽ luôn có tác dụng.

## 3. Các thao tác Step Over, Step Into, Step Out và Resume

| Điều khiển | Ý nghĩa khi đang dừng | Khi nên sử dụng |
| --- | --- | --- |
| **Step Over** | Thực thi bước hiện tại rồi dừng ở bước tiếp theo phù hợp trong ngữ cảnh hiện tại, **không đi sâu vào phương thức được gọi** | Muốn biết một lệnh làm thay đổi biến thế nào mà không cần xem nội bộ lời gọi |
| **Step Into** | Bước vào phần mã của phương thức được gọi khi debugger có thể truy cập được | Nghi ngờ lỗi nằm trong phương thức tự viết như `analyze(...)` |
| **Step Out** | Tiếp tục thực thi đến khi thoát khỏi phương thức hiện tại, quay lại ngữ cảnh gọi khi có thể | Đã hiểu logic bên trong phương thức, muốn xem kết quả ở nơi gọi |
| **Resume/Continue** | Tiếp tục chạy cho tới breakpoint tiếp theo, điểm dừng do lỗi/sự kiện khác hoặc kết thúc | Không cần quan sát từng lệnh |
| **Stop/Terminate** | Kết thúc phiên debug hoặc chương trình theo cách công cụ hỗ trợ | Muốn hủy phiên hiện tại; không giống Resume |

Ví dụ:

```java
int result = computeTotal(values);
System.out.println(result);
```

Đây là **đoạn minh họa**, giả sử `computeTotal` là phương thức do bạn định nghĩa. Nếu đang dừng ở lệnh gọi:

- **Step Into** có thể đưa bạn vào mã `computeTotal` để quan sát tính toán.
- **Step Over** chạy lời gọi rồi chuyển sang bước tiếp theo ở phương thức hiện tại, trong khi kết quả `result` đã được gán nếu lời gọi hoàn tất bình thường.
- Nếu đã vào `computeTotal`, **Step Out** cho phép trở lại nơi gọi sau khi phương thức kết thúc.

Đừng nhầm **Step Over** là “bỏ qua không chạy lệnh”: lệnh vẫn được thực thi. Tương tự, debugger có thể có **Step Into** nhiều biến thể như Smart Step Into; tên và phím tắt phụ thuộc IDE. Khi một bước có ngoại lệ hoặc breakpoint khác, điểm dừng tiếp theo có thể không giống đường đi bình thường.

## 4. Xem Locals, Watches và Call Stack

Khi debugger tạm dừng, một số khung thông tin quan trọng là:

| Khung / chức năng | Bạn xem được gì? | Ví dụ cần kiểm tra |
| --- | --- | --- |
| **Variables/Locals** | Tham số và biến cục bộ hiện nằm trong scope của khung gọi đang chọn | `i`, `value`, `count`, `sum`, `max` |
| **Watch/Expressions** | Giá trị biểu thức muốn theo dõi tại vị trí dừng | `value > 0`, `sum + value`, `count == 0` |
| **Call Stack** | Chuỗi lời gọi phương thức dẫn tới điểm dừng | `main → printReport → analyze` |
| **Breakpoints** | Danh sách điểm dừng, điều kiện hoặc trạng thái bật/tắt | Điểm dừng có đang được bật? |
| **Debug Console/Evaluate** | Đánh giá biểu thức trong bối cảnh đang dừng, nếu debugger hỗ trợ | `nums.length`, `sum`, `i + 1` |

**Giá trị biến gắn với thời điểm dừng.** Nếu debugger dừng **trước** câu `sum += value;`, `sum` thường chưa bao gồm `value` hiện tại. Sau khi Step Over dòng đó, `sum` mới phản ánh phép cộng. Vì vậy khi so với bảng theo dõi, hãy ghi rõ **trước hay sau lệnh**.

**Phạm vi biến (scope)** cũng quan trọng. Biến `value` được khai báo trong thân vòng lặp không nhất thiết có thể xem được khi đã rời vòng lặp. Biểu thức watch của một biến ngoài scope có thể báo lỗi hoặc không có giá trị, không có nghĩa bản thân biến đã bị đặt về `null`.

Trong debugger, việc Evaluate một lời gọi phương thức hoặc sửa trực tiếp giá trị biến **có thể làm thay đổi trạng thái thực thi**. Khi đang học, nên ưu tiên biểu thức chỉ đọc, ví dụ `i < nums.length` hoặc `sum + value`. Không dùng biểu thức có tác dụng phụ như `list.remove(0)` hoặc `i++` trong cửa sổ Evaluate nếu không chủ đích thay đổi chương trình.

## 5. Đầu vào chuẩn để đối chiếu khi debug

Bài thực hành dùng `int[] nums = {4, -2, 7, 0, 3}`: đếm, cộng và tìm giá trị lớn nhất **chỉ trong các phần tử dương**. `-2` và `0` phải đi qua nhánh bỏ qua; nếu không có số dương thì không tính trung bình hoặc in giá trị `max` giữ chỗ.

Kết quả chạy tay cần đối chiếu khi dừng bằng debugger: `count = 3`, `sum = 14`, `max = 7` và `average = 4.67` (định dạng hai chữ số). Bảng trace của bài mã giả giải thích cách tính các kết quả này; ở đây trọng tâm chuyển sang **quan sát trạng thái ngay trước và sau từng lệnh** để biết bước nào khiến kết quả lệch.

### Chương trình Java 17+ độc lập

Tạo tệp **`DebugStepDemo.java`**:

```java
import java.util.Locale;
import java.util.Objects;

public class DebugStepDemo {
    record Stats(int count, long sum, int max) {}

    static Stats analyze(int[] nums) {
        Objects.requireNonNull(nums, "nums");

        int count = 0;
        long sum = 0;
        int max = 0;

        for (int i = 0; i < nums.length; i++) {
            int value = nums[i]; // BREAKPOINT A: quan sát i và value

            if (value > 0) {
                if (count == 0 || value > max) {
                    max = value;
                }
                sum += value;     // BREAKPOINT B: xem sum trước/sau
                count++;         // BREAKPOINT C: xem count trước/sau
            }
        }

        return new Stats(count, sum, max); // BREAKPOINT D
    }

    static void printReport(String title, int[] values) {
        Stats result = analyze(values);    // BREAKPOINT E
        System.out.println(title);
        System.out.println("count=" + result.count());
        System.out.println("sum=" + result.sum());

        if (result.count() == 0) {
            System.out.println("no positive numbers");
        } else {
            System.out.println("max=" + result.max());
            double average = result.sum() / (double) result.count();
            System.out.printf(Locale.US, "average=%.2f%n", average);
        }
    }

    public static void main(String[] args) {
        printReport("Case A", new int[] {4, -2, 7, 0, 3});
        printReport("Case B", new int[] {0, -1});
    }
}
```

Dùng **JDK 17 trở lên**. Từ terminal tại thư mục có file:

```bash
javac -g -encoding UTF-8 DebugStepDemo.java
java DebugStepDemo
```

Tùy chọn **`-g`** yêu cầu `javac` sinh thông tin debug như dòng nguồn và biến cục bộ, giúp debugger quan sát tốt hơn; nó không thay đổi kết quả thuật toán.

**Stdout chính xác khi chạy bình thường:**

```text
Case A
count=3
sum=14
max=7
average=4.67
Case B
count=0
sum=0
no positive numbers
```

`record Stats` là cách gói kết quả ngắn gọn có sẵn trong Java 17; các accessor là `count()`, `sum()`, `max()`. Biến `max = 0` chỉ là giá trị giữ chỗ khi chưa gặp số dương, không được coi là kết quả có nghĩa nếu `count == 0`.

## 6. Thực hành một phiên debug theo trình tự

Mở `DebugStepDemo.java` trong IDE có hỗ trợ Java debugger, bảo đảm dự án dùng **JDK 17+** và chạy **Debug**.

### Bước 1 — Dừng tại nơi gọi phương thức

Đặt breakpoint E tại:

```java
Stats result = analyze(values);
```

Lần dừng đầu xảy ra trong lời gọi `printReport("Case A", ...)`. Trên cửa sổ Variables, có thể xem `title = "Case A"` và `values = [4, -2, 7, 0, 3]`. Biến `result` chưa có kết quả được gán tại thời điểm dừng trước lời gọi.

Bấm **Step Into** để vào `analyze(values)`. Khi đã vào, chọn khung gọi `analyze` sẽ thấy tham số `nums` và, sau khi thực hiện các lệnh khởi tạo, các biến `count`, `sum`, `max`. Ban đầu chúng lần lượt bằng `0`, `0`, `0`.

### Bước 2 — Dừng ở đầu mỗi lần lặp

Đặt breakpoint A tại `int value = nums[i];`. Ở lần lặp đầu tiên, `i = 0`; nếu debugger dừng **trước** câu lệnh này, `value` chưa được gán cho vòng lặp hiện tại. Step Over một lần để thực thi phép gán rồi xem `value = 4`.

Thêm các watch chỉ đọc:

```text
i
nums.length
value
value > 0
count
sum
max
```

Khi `value` đã ở trong scope, watch `value > 0` phải là `true` cho `4` và `7`, nhưng `false` cho `-2` và `0`.

### Bước 3 — Theo dõi cập nhật trạng thái

Khi `value = 4`, đi vào nhánh `if`. Trước `sum += value;`, `sum = 0`; sau khi Step Over, `sum = 4`. Trước `count++;`, `count = 0`; sau khi Step Over, `count = 1`. Vì `count == 0` khi xử lý số dương đầu tiên, `max` được gán thành `4`.

Nếu nhấn **Resume** và dừng lại ở breakpoint A ở lần lặp tiếp theo, `i = 1` và `nums[1] = -2`. Khi điều kiện `value > 0` sai, các biến tổng hợp không thay đổi: `count = 1`, `sum = 4`, `max = 4`.

### Bước 4 — Kiểm chứng trạng thái **trước và sau breakpoint**

Thay vì chỉ đọc bảng kết quả cuối mỗi lượt, hãy quan sát **thời điểm dừng của debugger**. Với `nums = {4, -2, 7, 0, 3}`, bảng dưới chọn những checkpoint có ý nghĩa trong chương trình `DebugStepDemo`:

| Vị trí dừng | Điều đang/đã xảy ra | Giá trị cần thấy |
| --- | --- | --- |
| A, `i=0`, trước `int value = nums[i]` | Phần tử đầu chưa được gán cho local `value` ở lượt này | `i=0`, `count=0`, `sum=0`; **không đánh giá** watch `value` trước khi gán |
| B, `i=0`, trước `sum += value` | `value=4`, `max` đã thành 4; phép cộng chưa chạy | `count=0`, `sum=0`, `max=4` |
| C, `i=0`, trước `count++` | Phép cộng vừa thực hiện; bộ đếm chưa tăng | `sum=4`, `count=0`; Step Over → `count=1` |
| A, `i=1`, sau gán `value=-2` | Điều kiện `value > 0` sai, bỏ qua B và C | Sau lượt này: `count=1`, `sum=4`, `max=4` |
| B, `i=2`, `value=7` | Đã cập nhật `max=7` nhưng chưa cộng 7 | Trước B: `sum=4`, `count=1`; sau B: `sum=11` |
| A, `i=3`, `value=0` | Không vào nhánh số dương | Sau lượt này: `sum=11`, `count=2`, `max=7` |
| B/C, `i=4`, `value=3` | `max` giữ 7; cộng rồi mới tăng đếm | Trước B: `sum=11`, `count=2`; sau C: `sum=14`, `count=3` |
| D, trước `return new Stats(...)` | Mọi lượt đã hoàn thành | `count=3`, `sum=14`, `max=7` |

**Lưu ý về thời điểm:** Nếu breakpoint A tạm dừng *trước* lệnh gán, local `value` có thể chưa được gán cho lượt hiện tại. Chỉ kiểm tra `value > 0` khi đã Step Over qua phép gán hoặc dừng ở lệnh `if`. Các điểm B/C không được chạm tới ở lượt `i=1` và `i=3`, vì điều kiện sai; đó là dấu hiệu đúng, không phải breakpoint bị lỗi.

Ở điểm D, dùng **Step Out** để quay về `printReport`, kiểm tra `result` sau khi `analyze` trả về và xác nhận trung bình `14 / 3.0` được in là `4.67`. Bảng này bổ sung góc nhìn **trạng thái trước/sau lệnh** cho bảng chạy tay; không thay thế việc kiểm thử toàn bộ đầu vào biên.

### Bước 5 — Quan sát trường hợp không có số dương

Resume cho tới lời gọi `printReport("Case B", new int[] {0, -1})`. Ở trường hợp này, `value > 0` luôn sai, các biến `count`, `sum` giữ `0`; chương trình đi vào nhánh `if (result.count() == 0)` và in `no positive numbers`, không thực hiện phép chia.

Cách kiểm tra trường hợp biên giúp xác nhận rằng chương trình không chỉ đúng với một mảng “đẹp”.

## 7. Dùng breakpoint có điều kiện để tránh dừng quá nhiều

Trong vòng lặp có hàng nghìn phần tử, breakpoint thông thường có thể làm chương trình dừng hàng nghìn lần. **Conditional breakpoint** chỉ yêu cầu tạm dừng khi một biểu thức điều kiện đúng.

Ví dụ với chương trình trên:

- Điều kiện `i == 2`: dừng khi chuẩn bị xử lý phần tử thứ ba.
- Điều kiện `value == 7`: dừng tại một vị trí mà biến `value` đã được gán và đang nằm trong scope.
- Điều kiện `count > 1`: tập trung vào trạng thái sau khi đã gặp nhiều số dương; cần đặt breakpoint tại dòng thích hợp để hiểu `count` trước/sau cập nhật.

**Cẩn thận với vị trí:** nếu đặt breakpoint ngay tại `int value = nums[i];`, biến `value` của vòng lặp hiện tại có thể **chưa có giá trị hợp lệ để dùng cho điều kiện**. Khi đó dùng điều kiện `i == 2` tại dòng này; hoặc đặt breakpoint ở dòng `if (value > 0)` để kiểm tra `value == 7` sau khi phép gán đã thực hiện.

Một số IDE hỗ trợ **logpoint/tracepoint**: ghi một thông báo mà không luôn dừng chương trình. Đây là lựa chọn khi cần quan sát nhiều lần lặp, nhưng nếu muốn nhìn kỹ trạng thái ở một thời điểm thì breakpoint tạm dừng vẫn trực quan hơn.

Trong chương trình nhiều luồng, breakpoint có thể tạm dừng **một luồng hoặc nhiều luồng** tùy cấu hình debugger. Đừng giả định các luồng khác cũng đã dừng; xem chế độ suspend và cửa sổ Threads của công cụ khi cần phân tích lỗi đồng thời.

## 8. Ví dụ lỗi logic: tìm dòng sai bằng debugger

Một phiên bản chưa đúng của vòng lặp:

```java
for (int i = 0; i < nums.length - 1; i++) {
    int value = nums[i];
    if (value > 0) {
        sum += value;
        count++;
    }
}
```

Đây là **đoạn minh họa lỗi**, không phải toàn bộ tệp Java. Với mảng `{4, -2, 7, 0, 3}`, điều kiện `i < nums.length - 1` chỉ cho chạy `i = 0, 1, 2, 3`; phần tử cuối ở `i = 4` bị bỏ sót. Nếu chỉ dựa vào câu `sum += value`, người mới học có thể tưởng lỗi nằm ở phép cộng.

Cách dùng debugger:

1. Đặt breakpoint trong vòng lặp, theo dõi `i`, `nums.length`, `value`, `sum`, `count`.
2. Resume từng lần lặp hoặc đặt breakpoint có điều kiện ở gần lần lặp cuối.
3. Nhận thấy giá trị `i` **không bao giờ đạt `4`**, dù `nums.length = 5`.
4. Kiểm tra điều kiện vòng lặp và đổi thành `i < nums.length`.
5. Chạy lại, xác nhận tổng là `14` và số phần tử dương là `3`.

Với lỗi cập nhật sai nhánh, ví dụ đặt `count++` **ngoài** `if (value > 0)`, breakpoint sau câu tăng sẽ cho thấy `count` thay đổi ngay cả với `value = -2` hoặc `0`. Kiểm tra bảng theo dõi sẽ chỉ ra bước đầu tiên khiến trạng thái sai.

**Bài học:** đặt breakpoint dựa trên **giả thuyết về nguyên nhân**, quan sát trạng thái **trước và sau** một lệnh, sau đó sửa lệnh gây sai thay vì che triệu chứng bằng một giá trị kết quả được gán cứng.

## 9. Call Stack giúp hiểu chương trình đang ở đâu

Ở breakpoint A/B/C nằm trong `analyze`, Call Stack của một lần chạy thông thường có thể cho thấy thứ tự lời gọi:

```text
DebugStepDemo.analyze(...)
DebugStepDemo.printReport(...)
DebugStepDemo.main(...)
```

Khung trên cùng là phương thức hiện tại. Chọn một khung khác có thể hiển thị các biến cục bộ ở **ngữ cảnh của phương thức đó**, không phải giá trị của cùng tên biến trong mọi phương thức. Khi đang bước trong `analyze`, `nums` là tham số của `analyze`; ở `printReport`, tham số tên `values`. Đó là hai tên biến cục bộ khác nhau đang tham chiếu tới cùng đối tượng mảng trong ví dụ.

Khi có exception, xem stack trace hoặc bật **exception breakpoint** để tạm dừng khi một loại ngoại lệ được ném (hoặc chưa được bắt, tùy tùy chọn IDE). Exception breakpoint hữu ích khi lỗi bị bắt ở tầng cao hơn và thông báo cuối cùng không cho biết nơi phát sinh đầu tiên.

Cần phân biệt **call stack** với nội dung mảng/collection: call stack cho biết chuỗi lời gọi; Variables cho biết dữ liệu hiện có ở từng khung.

## 10. Chạy từ terminal và kết nối debugger (tùy chọn)

Chạy bình thường bằng `java DebugStepDemo` sẽ **không tự dừng** tại breakpoint do IDE cấu hình. Muốn debug trong IDE, dùng chức năng **Debug** hoặc cấu hình debugger **Attach** đến JVM đã bật giao thức JDWP.

Ví dụ với **JDK 17+**, sau khi biên dịch bằng `javac -g`:

```bash
java -agentlib:jdwp=transport=dt_socket,server=y,suspend=y,address=127.0.0.1:5005 DebugStepDemo
```

Ý nghĩa:

- `transport=dt_socket`: dùng kết nối socket để debugger giao tiếp.
- `server=y`: JVM mở đầu nhận kết nối debugger.
- `suspend=y`: JVM tạm dừng khi khởi động để chờ debugger kết nối trước khi thực thi ứng dụng.
- `address=127.0.0.1:5005`: chỉ lắng nghe trên **loopback** của máy đó, tại cổng 5005.

Trong IDE, tạo cấu hình **Attach to Remote JVM/Remote Debug** kết nối `127.0.0.1:5005`, trỏ đến đúng mã nguồn và class đã biên dịch; sau khi attach và tiếp tục, debugger có thể dừng tại breakpoint. Chế độ này **không phải stdout thông thường của ví dụ** vì JVM có thể in một dòng thông báo đang lắng nghe và dừng chờ kết nối.

**An toàn:** cổng JDWP cho phép điều khiển sâu tiến trình Java; không mở công khai qua Internet hoặc địa chỉ mạng không tin cậy, đặc biệt không dùng `address=*:5005` nếu không có biện pháp bảo vệ phù hợp. Với người mới học, debug trực tiếp bằng IDE thường đơn giản hơn và tránh phải tự quản lý cổng.

## 11. Những điều debugger không thay thế được

- **Không có breakpoint nào được kích hoạt:** kiểm tra đã chạy chế độ Debug chưa, đặt tại dòng thực thi chưa, đường đi có tới dòng ấy không, breakpoint có bị tắt không, source và class đang chạy có khớp nhau không.
- **Không xem được biến cục bộ:** kiểm tra đúng Call Stack frame, phạm vi của biến, và thử biên dịch với `javac -g`. Một số mã/thư viện hoặc môi trường tối ưu có thể hạn chế thông tin.
- **Step Into đi vào mã thư viện thay vì mã tự viết:** dùng Step Over, Smart Step Into hoặc các bộ lọc bước (*step filters*) nếu IDE hỗ trợ.
- **Breakpoint trong loop dừng quá thường xuyên:** dùng conditional breakpoint hoặc logpoint.
- **Kết quả thay đổi khi dùng debugger:** debugger có thể làm thay đổi thời gian thực thi, nhất là trong code đa luồng; tránh kết luận một lỗi race condition đã biến mất chỉ vì chạy từng bước.
- **Watch hiển thị lỗi scope:** đặt biểu thức tại dòng/khung mà biến thực sự tồn tại.
- **Debugger cho thấy kết quả đúng ở một đầu vào:** vẫn phải thử mảng rỗng, chỉ số biên, đầu vào sai, số lượng lớn và các tình huống đặc biệt.
- **Debug Console Evaluate làm đổi trạng thái:** hạn chế biểu thức có tác dụng phụ hoặc can thiệp dữ liệu khi mục đích chỉ là quan sát.

### Checklist gỡ lỗi nhanh

1. Mô tả **kết quả mong đợi** và **kết quả đang xảy ra**.
2. Tạo dữ liệu đầu vào nhỏ **tái hiện được lỗi**.
3. Đặt breakpoint **trước vị trí nghi ngờ**, chạy Debug.
4. Xem Locals/Watch/Call Stack, phân biệt giá trị **trước và sau lệnh**.
5. Step Into khi cần xem nội bộ, Step Over khi chỉ cần kết quả, Step Out khi muốn quay về nơi gọi, Resume đến điểm quan trọng tiếp theo.
6. So với bảng theo dõi hoặc phép tính tay để xác định **bước đầu tiên bị lệch**.
7. Sửa **nguyên nhân**, chạy lại test bình thường và trường hợp biên.
8. Tắt hoặc bỏ những breakpoint không cần thiết sau khi hoàn tất.

**Ghi nhớ:** breakpoint giúp dừng đúng thời điểm; chạy từng bước giúp thấy lệnh nào thay đổi trạng thái; Variables/Watch/Call Stack giúp trả lời “giá trị nào đang sai, ở đâu và do đường gọi nào?”. Kết hợp quan sát bằng debugger với phép tính tay và kiểm thử sẽ giúp tìm lỗi Java chính xác hơn việc thêm nhiều dòng `println()` một cách ngẫu nhiên.