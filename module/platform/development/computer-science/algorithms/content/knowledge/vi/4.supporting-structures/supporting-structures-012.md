# Tính bất biến, quyền sửa dữ liệu và ảnh hưởng đến lời giải

Trong thuật toán, đôi khi một lời giải “nhanh và tiết kiệm bộ nhớ” lại âm thầm làm thay đổi dữ liệu đầu vào. Một lời giải khác trả đúng kết quả cho bài kiểm thử đơn lẻ nhưng gây lỗi khi người gọi tiếp tục dùng mảng, khi nhiều nơi cùng giữ tham chiếu đến một đối tượng, hoặc khi cấu trúc băm chứa khóa đã bị sửa. Vì vậy, **quyền được sửa dữ liệu** là một phần của đặc tả thuật toán, quan trọng như đầu vào, đầu ra, thời gian và bộ nhớ.

Bài học này giải thích dữ liệu bất biến, trạng thái có thể thay đổi, quyền sở hữu và chia sẻ tham chiếu, sự khác biệt giữa lời giải tại chỗ và lời giải bảo toàn đầu vào, cùng cách những lựa chọn này tác động đến **tính đúng, độ phức tạp, cách kiểm thử và thiết kế API**. Ví dụ sử dụng Java 17+.

## 1. Hai khái niệm dễ nhầm: dữ liệu bất biến và bất biến thuật toán

**Bất biến dữ liệu (immutability)** nghĩa là trạng thái có thể quan sát của một giá trị không thay đổi sau khi tạo. Ví dụ `String` trong Java là immutable: thao tác nối chuỗi tạo chuỗi mới, không chỉnh các ký tự của chuỗi cũ. Ngược lại, `int[]`, `ArrayList` và `HashMap` là các cấu trúc **mutable**: nội dung có thể thay đổi.

**Bất biến thuật toán (invariant)** là một mệnh đề logic **luôn đúng tại các mốc đã xác định** trong quá trình chạy, dù biến và dữ liệu có thể được cập nhật. Ví dụ trong thuật toán hai con trỏ trên mảng tăng dần: “mọi cặp chưa bị chứng minh vô nghiệm đều nằm trong đoạn từ `left` đến `right`” là một bất biến hỗ trợ chứng minh tính đúng.

Hai khái niệm độc lập:

- Dùng **input không thay đổi** nhưng vẫn cập nhật các biến `left`, `right` để duyệt. Thuật toán có thể có bất biến vòng lặp tốt mà không sửa dữ liệu gốc.
- Cập nhật **mảng tại chỗ** trong sắp xếp hoặc quy hoạch động nhưng vẫn duy trì bất biến: “tiền tố đã xử lý được sắp xếp” hoặc “`dp[c]` là kết quả từ các món hàng đã xét”.
- Khai báo `final int[] a` chỉ cấm **gán lại tham chiếu `a`** trong phạm vi đó; `a[0] = 7` vẫn hợp lệ. `final` không tự biến mảng thành immutable.

**Quy tắc thực hành:** Khi đọc đề, tách riêng (1) **dữ liệu nào được phép thay đổi?** và (2) **mệnh đề nào phải luôn đúng để thuật toán chính xác?**. Nhầm lẫn hai câu hỏi sẽ dẫn tới lời giải sai hợp đồng hoặc chứng minh thiếu.

## 2. Trước khi chọn cấu trúc hỗ trợ, hãy xác định quyền sửa

Trong bài toán thuật toán, phân loại dữ liệu thành:

| Loại dữ liệu | Ví dụ | Quyền sửa cần nêu rõ |
| --- | --- | --- |
| **Input của người gọi** | `int[] values`, danh sách sự kiện, đồ thị được truyền vào | Chỉ được sửa nếu đặc tả/API cho phép; mặc định nên hỏi hoặc bảo toàn khi chưa rõ |
| **Bản sao làm việc** | `values.clone()`, bản sao danh sách cạnh | Thuật toán sở hữu, có thể sắp xếp/đánh dấu mà không ảnh hưởng trực tiếp đến input gốc |
| **Trạng thái cục bộ** | `left`, `right`, `visited`, `dp`, bộ đếm | Được cập nhật theo bất biến và quy tắc quay lui; không để lọt ra ngoài ngoài ý muốn |
| **Kết quả trả về** | Mảng nghiệm, danh sách tổ hợp, đối tượng đường đi | Cần quyết định người gọi có thể sửa kết quả hay không; kết quả có chia sẻ phần tử với input không |
| **Dữ liệu chia sẻ** | Cache, khóa trong `HashMap`, đồ thị dùng lại qua nhiều lời gọi | Mutation có thể tác động đến nhiều thuật toán hoặc luồng khác, đòi hỏi hợp đồng rõ ràng |

Hai kiểu hợp đồng tiêu biểu:

- **Không sửa input:** Hàm chỉ đọc đầu vào, nếu cần sắp xếp thì sao chép trước. Hữu ích khi dữ liệu được dùng lại, khi phải giữ thứ tự/chỉ số gốc, hoặc khi muốn dễ kiểm thử và tái sử dụng.
- **Được sửa input tại chỗ (in-place):** Hàm có thể đổi thứ tự, thay phần tử hoặc chỉ giữ lại một **tiền tố kết quả**. Đổi lại có thể giảm bộ nhớ phụ và tránh sao chép; caller phải chấp nhận trạng thái sau khi chạy.

*“Có thể sửa” không đồng nghĩa “phải sửa”.* Một API nên mô tả **phần nào bị sửa, trạng thái nào được bảo đảm sau khi trả về**, và liệu một lỗi/ngoại lệ có thể để lại dữ liệu đã bị sửa một phần hay không.

Ví dụ đầu vào `[4,1,3,2]`, câu hỏi “có hai số tổng bằng 5?” có thể trả `true` sau khi sort, nhưng nếu hàm sort trực tiếp thì input trở thành `[1,2,3,4]`. Kết quả boolean đúng vẫn có thể **vi phạm đặc tả bảo toàn đầu vào**.

## 3. Aliasing: hai biến cùng trỏ một vùng dữ liệu

Trong Java, gán một mảng vào biến thứ hai **không sao chép phần tử**:

```java
int[] original = {4, 1, 3, 2};
int[] alias = original;
Arrays.sort(alias); // Cũng sửa original, vì cả hai trỏ cùng mảng.
```

Đây là đoạn minh họa; cần `import java.util.Arrays;` trong chương trình đầy đủ.

Sau câu lệnh trên, cả `alias` và `original` đều nhìn thấy `[1,2,3,4]`. Tương tự, nếu một phương thức nhận `int[]` rồi sửa phần tử trong mảng, người gọi thấy thay đổi đó vì tham chiếu được truyền theo giá trị, nhưng **đối tượng mảng được chia sẻ**.

Phân biệt ba thao tác:

- `int[] b = a;`: **thêm tham chiếu**, `O(1)`, cả hai cùng mảng.
- `int[] b = a.clone();`: **sao chép mảng một chiều**, `O(n)` thời gian và `O(n)` bộ nhớ cho mảng mới.
- `int[][] b = a.clone();`: chỉ sao chép **mảng ngoài**; các mảng con như `a[0]` và `b[0]` vẫn là cùng đối tượng. Muốn bản sao sâu của dữ liệu lồng nhau, phải sao chép cả các tầng cần độc lập.

**Bất biến tham chiếu không kéo theo bất biến nội dung.** Nếu một `List` không được phép thêm/xóa phần tử nhưng chứa các đối tượng mutable, người khác vẫn có thể sửa trường của từng phần tử và làm thay đổi kết quả quan sát được.

### Bẫy `record` và `final`

`record Holder(int[] data) {}` tự sinh accessor `data()` trả về **tham chiếu đến cùng mảng**. Dù thành phần record không thể gán lại, gọi `holder.data()[0] = 42` vẫn sửa phần tử. Nếu muốn một đối tượng thực sự bảo vệ mảng, cần sao chép đầu vào khi tạo và sao chép đầu ra khi cung cấp mảng; hoặc chỉ cung cấp các phép đọc cần thiết.

## 4. Tại sao quyền sửa dữ liệu làm thay đổi **thuật toán phù hợp**

Cùng một yêu cầu tính toán có thể có những lời giải khác nhau chỉ vì một ràng buộc về mutation.

### Trường hợp A — Tìm cặp có tổng bằng target

Nếu chỉ cần `boolean`, ta có thể:

1. **Sắp xếp tại chỗ + hai con trỏ:** Sửa thứ tự `values`; sau bước sort, phần quét hai con trỏ dùng `O(1)` bộ nhớ phụ và `O(n)` thời gian. **Tổng** chi phí vẫn gồm sort, bộ nhớ phụ của sort phụ thuộc cách triển khai, không nên tự mặc định toàn bộ thuật toán là `O(1)` bộ nhớ.
2. **Sao chép + sắp xếp + hai con trỏ:** Bảo toàn input. Trả cùng boolean, đổi lại `O(n)` bộ nhớ cho bản sao và `O(n)` thời gian sao chép, cộng thời gian sort.
3. **Tra cứu phần bù bằng `HashSet`:** Không cần sắp xếp và không sửa input; trung bình `O(n)` thời gian, `O(n)` bộ nhớ. Kiểm tra phần bù trong tập các phần tử **đã gặp** trước khi thêm phần tử hiện tại để không dùng cùng một vị trí hai lần.

Nếu đề chuyển sang **trả về chỉ số gốc**, sắp xếp mảng trực tiếp mà không giữ ánh xạ chỉ số sẽ phá thông tin cần trả; dùng `HashMap<giá trị, chỉ số>` hoặc sort các cặp `(giá trị,chỉ số)` sẽ phù hợp hơn. Đặc tả output và quyền sửa dữ liệu cùng ảnh hưởng lựa chọn.

### Trường hợp B — Loại phần tử trùng trong mảng đã sắp xếp

Hai con trỏ `read`/`write` có thể ghi đè một phần mảng để nén giá trị duy nhất về **tiền tố**. Với `[1,1,2,2,3]`, sau xử lý độ dài logic là `3` và tiền tố là `[1,2,3]`. **Độ dài vật lý của mảng Java vẫn là 5**; phần đuôi sau vị trí logic không còn ý nghĩa kết quả, có thể chứa dữ liệu cũ. Vì vậy API phải trả về độ dài logic hoặc tạo một mảng kết quả mới.

- Nếu cho phép sửa input đã sắp xếp: có thể làm `O(n)` thời gian và `O(1)` bộ nhớ phụ, không tính phần output phải lưu riêng.
- Nếu cần giữ input: sao chép trước, hoặc tạo cấu trúc kết quả mới. Với dữ liệu chưa sắp xếp, cần tính cả việc sort hoặc cơ chế đánh dấu đã thấy.
- Nếu cần giữ **thứ tự xuất hiện đầu tiên**, sort rồi nén sẽ thay đổi thứ tự; một `LinkedHashSet` hoặc thuật toán khác có thể phù hợp, tùy yêu cầu bộ nhớ và hiệu năng.

### Trường hợp C — Sắp xếp hoặc cập nhật dữ liệu làm mất khóa tra cứu

Nếu một đối tượng mutable được dùng làm khóa trong `HashMap`/`HashSet` rồi các trường tham gia `equals`/`hashCode` bị sửa, cấu trúc băm có thể không tìm lại được khóa tại vị trí băm cũ. Một khóa nên có **giá trị ổn định trong suốt thời gian nó nằm trong bảng băm**; record chỉ an toàn theo nghĩa này khi các trường có ảnh hưởng đến bằng nhau/hash cũng không thay đổi theo cách quan sát được.

Trong thuật toán dựa trên chỉ số, thứ tự là một phần bản sắc của vị trí. Việc sort, xóa hoặc chèn vào danh sách có thể khiến chỉ số lưu trong cấu trúc hỗ trợ trở nên lỗi thời. Nếu input thay đổi sau khi xây **prefix sum** hay chỉ mục tìm kiếm, các giá trị đã tiền xử lý có thể không còn tương ứng với dữ liệu.

**Câu hỏi quan trọng:** Bài toán cần một **ảnh chụp trạng thái** tại thời điểm xử lý hay cần phản ánh **mọi thay đổi mới nhất**? Với nhiều truy vấn, quyền cập nhật quyết định liệu có thể tiền xử lý một lần hay phải duy trì chỉ mục động.

## 5. Bất biến thuật toán vẫn cần được chứng minh khi dùng mutation

Đổi chỗ, nén hoặc cập nhật `dp` không tự sai. Cần xác định **mệnh đề bất biến sau mỗi bước**.

### Hai con trỏ trên mảng đã sắp xếp

Khi tìm cặp tổng bằng target, mảng tăng dần cho phép lập luận: nếu `a[left]+a[right] < target` thì phần tử ở `left` không thể ghép với bất kỳ phần tử còn lại trong đoạn để đạt target, nên được phép tăng `left`. Nếu tổng lớn thì giảm `right`. Các con trỏ thay đổi nhưng tính chất cần bảo toàn là **không bỏ qua bất kỳ cặp hợp lệ chưa loại trừ**.

Chính giả định mảng tăng dần, chứ không phải việc được phép sửa dữ liệu, tạo điều kiện cho bước loại trừ. Nếu chỉ có mảng chưa sắp xếp và không được sort input, có thể sort bản sao hoặc chọn một thuật toán khác.

### Nén mảng tăng dần tại chỗ

Đặt `write` là số lượng giá trị phân biệt đã ghi ở tiền tố; sau khi xét `read` phần tử, bất biến là **`a[0..write)` chứa chính các giá trị phân biệt trong tiền tố input đã duyệt, theo thứ tự tăng dần**. Nếu phần tử mới khác giá trị cuối đã ghi, chép nó vào `a[write]` rồi tăng `write`. Vì `write≤read`, các phần tử chưa đọc ở bên phải không bị ghi đè trước khi đọc.

Kết thúc, `write` là độ dài logic của kết quả. Đó là một chứng minh về trạng thái **có thay đổi**, không phải về tính immutable của input.

### Cập nhật quy hoạch động: thứ tự duyệt có thể đổi **nghĩa** bài toán

Trong 0/1 knapsack, mỗi món có thể chọn **tối đa một lần**. Khi tối ưu từ bảng 2D xuống `dp[capacity+1]` một chiều, cập nhật dung lượng theo **chiều giảm** cho từng món:

```java
// Đoạn minh họa: weight > 0, value >= 0, capacity >= 0;
// dp là long[capacity + 1] và thể hiện giá trị tốt nhất.
for (int c = capacity; c >= weight; c--) {
    dp[c] = Math.max(dp[c], dp[c - weight] + value);
}
```

**Bất biến sau mỗi món:** `dp[c]` chỉ dùng các món đã xử lý, mỗi món tối đa một lần. Duyệt `c` giảm giúp phần `dp[c-weight]` còn thuộc trạng thái **trước khi xử lý món hiện tại**, nên không sử dụng lại cùng món.

Nếu duyệt `c` **tăng**, có thể đọc giá trị `dp[c-weight]` vừa được cập nhật bằng **món hiện tại**, khiến món đó được dùng nhiều lần. Ví dụ chỉ có một món `weight=2, value=3`, túi `capacity=4`: 0/1 knapsack đúng là `3`; duyệt tăng có thể tạo `dp[4]=6`, biến thành hành vi kiểu unbounded knapsack. Đây là trường hợp quyền cập nhật **cùng một mảng trạng thái** đòi hỏi chọn đúng hướng duyệt để không phá bất biến.

## 6. Copy, view và immutable collection trong Java

Java có nhiều cách nhìn giống “không sửa được”, nhưng ngữ nghĩa khác nhau:

| Cách tạo | Có sửa được nội dung trực tiếp? | Có phản ánh thay đổi từ nguồn? |
| --- | --- | --- |
| `List.of("A","B")` | Không thêm, xóa hoặc thay phần tử qua API list | Không có danh sách nguồn mutable để theo dõi |
| `List.copyOf(existing)` | Không sửa cấu trúc list qua API trả về | Đưa ra cấu trúc phần tử chụp tại thời điểm copy; **không sao chép sâu** các đối tượng phần tử |
| `Collections.unmodifiableList(existing)` | Không sửa qua view trả về | **Có**: nếu nơi khác giữ `existing` và sửa, view phản ánh thay đổi |
| `Arrays.asList(array)` với mảng object | Không thêm/xóa (size cố định), nhưng có thể `set` | **Có**: list và mảng backing có thể nhìn thấy các sửa đổi của nhau |
| `new ArrayList<>(existing)` | Có thể thêm/xóa/thay phần tử | Sao chép cấu trúc tại thời điểm tạo; các phần tử mutable vẫn có thể được chia sẻ |
| `int[] copy = original.clone()` | Các phần tử `copy` có thể sửa | Mảng 1D `int[]` có vùng chứa riêng, không bị ảnh hưởng bởi sửa phần tử của `original` |

**Điểm khó:** Một list bất biến về **cấu trúc** không mặc nhiên bất biến về **đối tượng phần tử**. `List.copyOf` chứa một đối tượng mutable thì đối tượng đó vẫn có thể bị sửa thông qua tham chiếu khác. Muốn bảo đảm ảnh chụp sâu, phải sao chép dữ liệu phần tử cần thiết; nếu các phần tử đã immutable, sao chép sâu thường không cần.

`List.copyOf` và `List.of` không chấp nhận phần tử `null`. `Collections.unmodifiableList` là **view không sửa được qua tham chiếu đó**, không phải snapshot. Chọn sai loại có thể dẫn đến bug “đọc lại thì thấy dữ liệu tự thay đổi”.

Với `record Snapshot(int[] data)` hoặc một lớp giữ mảng, cần **defensive copy** cả lúc nhận và lúc trả mảng. Ví dụ bên dưới dùng lớp cung cấp `get(index)` và `copy()`, không phơi tham chiếu nội bộ.

## 7. Java 17+ — chương trình độc lập so sánh các hợp đồng

Ví dụ dưới đây cố tình đặt hai hàm với tên rõ ràng:

- `hasPairWithoutMutation` nhận input chỉ đọc, sort bản sao.
- `hasPairInPlace` được phép sort trực tiếp input, làm đổi thứ tự.
- `twoSumOriginalIndexes` trả **chỉ số gốc** bằng bảng băm và không làm đổi input.
- `uniqueSortedInPlace` nén **tiền tố hợp lệ** thay vì rút ngắn độ dài vật lý.
- `IntSnapshot` bảo vệ mảng bằng bản sao khi nhận và trả.
- `knapsack01` cập nhật một mảng `dp` theo chiều giảm để giữ tính đúng của 0/1 knapsack.

Lưu thành **MutationContractDemo.java**:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

public class MutationContractDemo {
    // Tiền điều kiện: input đã tăng dần. Hàm không sửa mảng.
    static boolean hasPairOnSorted(int[] sorted, int target) {
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

    // Bảo toàn mọi phần tử và thứ tự của input.
    static boolean hasPairWithoutMutation(int[] input, int target) {
        int[] copy = input.clone();
        Arrays.sort(copy);
        return hasPairOnSorted(copy, target);
    }

    // Hợp đồng: được phép đổi thứ tự của input.
    static boolean hasPairInPlace(int[] input, int target) {
        Arrays.sort(input);
        return hasPairOnSorted(input, target);
    }

    // Trả chỉ số của input gốc; không sắp xếp input.
    static int[] twoSumOriginalIndexes(int[] input, int target) {
        Map<Long, Integer> firstIndex = new HashMap<>();
        for (int i = 0; i < input.length; i++) {
            long complement = (long) target - input[i];
            Integer j = firstIndex.get(complement);
            if (j != null) {
                return new int[]{j, i};
            }
            firstIndex.putIfAbsent((long) input[i], i);
        }
        return new int[0];
    }

    // Tiền điều kiện: sorted đã tăng dần.
    // Trả độ dài logic; chỉ a[0..write) là kết quả.
    static int uniqueSortedInPlace(int[] sorted) {
        if (sorted.length == 0) {
            return 0;
        }
        int write = 1;
        for (int read = 1; read < sorted.length; read++) {
            if (sorted[read] != sorted[write - 1]) {
                sorted[write] = sorted[read];
                write++;
            }
        }
        return write;
    }

    static int[] uniqueValuesWithoutMutation(int[] input) {
        int[] copy = input.clone();
        Arrays.sort(copy);
        int used = uniqueSortedInPlace(copy);
        return Arrays.copyOf(copy, used);
    }

    // Không phơi tham chiếu đến mảng nội bộ.
    static final class IntSnapshot {
        private final int[] data;

        IntSnapshot(int[] source) {
            data = source.clone();
        }

        int get(int index) {
            return data[index];
        }

        int[] copy() {
            return data.clone();
        }
    }

    // weights > 0, values >= 0, capacity >= 0;
    // weights.length == values.length.
    static long knapsack01(int[] weights, int[] values, int capacity) {
        if (capacity < 0 || weights.length != values.length) {
            throw new IllegalArgumentException("Invalid dimensions");
        }
        long[] dp = new long[capacity + 1];
        for (int i = 0; i < weights.length; i++) {
            if (weights[i] <= 0 || values[i] < 0) {
                throw new IllegalArgumentException("Invalid item");
            }
            for (int c = capacity; c >= weights[i]; c--) {
                dp[c] = Math.max(dp[c],
                                 dp[c - weights[i]] + values[i]);
            }
        }
        return dp[capacity];
    }

    public static void main(String[] args) {
        int[] numbers = {4, 1, 3, 2};
        int[] alias = numbers;

        System.out.println("Pure pair: "
                           + hasPairWithoutMutation(numbers, 5));
        System.out.println("After pure: "
                           + Arrays.toString(numbers));
        System.out.println("Original indexes: "
                           + Arrays.toString(twoSumOriginalIndexes(numbers, 5)));
        System.out.println("In-place pair: "
                           + hasPairInPlace(numbers, 5));
        System.out.println("Alias sees: "
                           + Arrays.toString(alias));

        int[] withDuplicates = {3, 1, 3, 2, 1};
        System.out.println("Unique copy: "
                           + Arrays.toString(
                               uniqueValuesWithoutMutation(withDuplicates)));
        System.out.println("Original duplicates: "
                           + Arrays.toString(withDuplicates));

        int[] sortedDuplicates = {1, 1, 2, 2, 3};
        int used = uniqueSortedInPlace(sortedDuplicates);
        System.out.println("Logical prefix: "
                           + Arrays.toString(
                               Arrays.copyOf(sortedDuplicates, used)));
        System.out.println("Physical length: "
                           + sortedDuplicates.length);

        int[] mutableSource = {7, 9};
        IntSnapshot snapshot = new IntSnapshot(mutableSource);
        mutableSource[0] = 99;
        int[] outwardCopy = snapshot.copy();
        outwardCopy[1] = 55;
        System.out.println("Defensive snapshot: "
                           + snapshot.get(0) + "," + snapshot.get(1));

        List<String> base = new ArrayList<>(List.of("A"));
        List<String> liveView = Collections.unmodifiableList(base);
        List<String> snapshotList = List.copyOf(base);
        base.add("B");
        System.out.println("Read-only view: " + liveView);
        System.out.println("Snapshot list: " + snapshotList);

        System.out.println("0/1 knapsack: "
                           + knapsack01(new int[]{2}, new int[]{3}, 4));
    }
}
```

Biên dịch và chạy với JDK 17 trở lên:

```bash
javac -encoding UTF-8 MutationContractDemo.java
java MutationContractDemo
```

Stdout:

```text
Pure pair: true
After pure: [4, 1, 3, 2]
Original indexes: [0, 1]
In-place pair: true
Alias sees: [1, 2, 3, 4]
Unique copy: [1, 2, 3]
Original duplicates: [3, 1, 3, 2, 1]
Logical prefix: [1, 2, 3]
Physical length: 5
Defensive snapshot: 7,9
Read-only view: [A, B]
Snapshot list: [A]
0/1 knapsack: 3
```

### Cách đọc kết quả

- `hasPairWithoutMutation` và `hasPairInPlace` đều trả `true`. Chỉ phương án thứ hai đổi input. Vì `alias` trỏ cùng mảng, nó thấy thứ tự đã sắp.
- `twoSumOriginalIndexes` trả `[0,1]` vì `numbers[0]=4` và `numbers[1]=1` có tổng bằng `5`; kết quả được tính **trước** khi mảng bị sắp xếp.
- `uniqueValuesWithoutMutation` không thay `withDuplicates`; `uniqueSortedInPlace` chỉ trả về **độ dài logic** thay vì “rút” được kích thước mảng.
- `IntSnapshot` sao chép khi tạo và khi trả, nên sửa `mutableSource` hay `outwardCopy` không sửa dữ liệu bên trong.
- `Collections.unmodifiableList(base)` phản ánh việc `base.add("B")`, trong khi `List.copyOf(base)` đã chụp cấu trúc danh sách trước thay đổi.
- Ví dụ túi chỉ có một món trọng lượng 2 và giá trị 3, dung lượng 4: đáp án **0/1** là 3, không phải 6. Vòng `c` giảm bảo đảm món không bị dùng lại.

Code chủ đích xem `input` không null và đối với `uniqueSortedInPlace`, dữ liệu đã sắp xếp. Kiểm tra tiền điều kiện ở **biên API** nếu xây thư viện công khai. Tổng hai số `int` được nâng lên `long` để tránh tràn; bảng băm dùng `Long` cho phần bù nhằm giữ phép tính đúng theo giá trị toán học.

## 8. Đánh đổi về thời gian, bộ nhớ và độ tin cậy

Không có quy tắc “immutable lúc nào cũng tốt hơn” hay “in-place lúc nào cũng nhanh hơn”; phụ thuộc kích thước dữ liệu, số lần dùng lại và điều kiện hệ thống.

| Quyết định | Thời gian bổ sung | Bộ nhớ bổ sung | Ảnh hưởng |
| --- | --- | --- | --- |
| Truyền thêm tham chiếu `b=a` | `O(1)` | `O(1)` | Mọi nơi cùng nhìn đối tượng; thay đổi ở một nơi ảnh hưởng nơi khác |
| `int[] b=a.clone()` | `O(n)` | `O(n)` | Hai mảng nguyên thủy độc lập, đổi phần tử không tác động lẫn nhau |
| Sort bản sao + hai con trỏ | `O(n)` sao chép + chi phí sort + `O(n)` quét | `O(n)` bản sao và bộ nhớ sort | Bảo toàn thứ tự input, nhưng vẫn có chi phí |
| Sort input tại chỗ + hai con trỏ | Chi phí sort + `O(n)` quét | Không cấp phát **bản sao input**; sort có thể có bộ nhớ làm việc | Đổi thứ tự input, có thể làm chỉ số/cấu trúc phụ trợ cũ mất nghĩa |
| `HashMap` tìm hai chỉ số gốc | Trung bình `O(n)` | `O(n)` | Không sửa input, giữ chỉ số, dùng thêm bảng băm |
| Nén mảng tăng dần tại chỗ | `O(n)` | `O(1)` phụ cho phần nén | Chỉ tiền tố độ dài logic là kết quả; phần đuôi vẫn tồn tại |
| Tạo snapshot sâu của cấu trúc lồng nhau | Theo tổng lượng dữ liệu được sao chép | Theo tổng dữ liệu được sao chép | Có thể tốn kém, nhưng loại liên kết mutation giữa các nhánh sở hữu |

Nếu một input được dùng qua **nhiều truy vấn**, bản sao hoặc cấu trúc chỉ mục duy nhất được xây một lần có thể hợp lý; nhưng việc dữ liệu thay đổi giữa các truy vấn sẽ ảnh hưởng hiệu lực của chỉ mục. Không nên chỉ so độ phức tạp một lần gọi mà quên **chi phí khởi tạo, cập nhật và sao chép**.

### Tính thuần (purity) không đồng nghĩa “không có biến thay đổi”

Một hàm **không sửa input** vẫn có thể thay các biến cục bộ hoặc tạo mảng tạm và cập nhật nó. Một hàm thực sự *thuần* có cùng output cho cùng input và không có tác dụng phụ quan sát được; nếu hàm đọc cache toàn cục thay đổi, thời gian, số ngẫu nhiên hoặc I/O thì không thuần dù không sửa tham số. Đối với bài thuật toán, lời hứa thực tế thường là **không mutate dữ liệu đầu vào**; đừng tự suy ra mọi đặc tính thuần từ lời hứa đó.

Lợi ích của việc giảm mutation chia sẻ gồm: kiểm thử dễ vì ít phụ thuộc thứ tự gọi, có thể tái dùng kết quả làm mốc, và giảm nguy cơ race condition. **Immutable snapshot không tự làm mọi thuật toán đa luồng trở nên an toàn** nếu các thành phần còn lại vẫn là trạng thái chia sẻ có thể sửa.

## 9. Quy ước API để tránh sai hợp đồng

Một hàm dễ dùng nên ghi rõ:

1. **Tiền điều kiện:** mảng đã sắp xếp? `null` hợp lệ? Có số âm? Độ dài các danh sách đi kèm có phải bằng nhau?
2. **Quyền sửa:** Có thể sort, ghi đè, thêm/xóa? Phần tử hay cả cấu trúc? Có sửa input khi gặp ngoại lệ không?
3. **Kết quả:** Trả giá trị mới, view, snapshot hay tham chiếu tới chính input? Kết quả có thể thay đổi sau lần gọi không?
4. **Ý nghĩa chỉ số:** Tham chiếu vị trí trước hay sau khi sort? Kết quả nén mảng có độ dài logic bao nhiêu?
5. **Chi phí:** Có sao chép `O(n)`, sort `O(n log n)`, cấp phát bảng băm, hay giữ bộ nhớ theo dung lượng `capacity`?
6. **Tính ổn định khi dùng lại:** Input có thể bị cập nhật bởi phần khác? Nếu đang dùng cache/index từ dữ liệu cũ thì khi nào phải xây lại?

Đặt tên rõ nghĩa như `sortInPlace`, `sortedCopy`, `removeDuplicatesInPlace` hoặc `getImmutableSnapshot` giúp người gọi nhận biết hợp đồng. Tên gọi hữu ích nhưng **không thay thế mô tả hành vi**.

### Giữ đầu vào an toàn khi có lỗi

Một thuật toán chỉnh input tại chỗ có thể đã thay đổi dữ liệu **một phần** rồi mới ném ngoại lệ. Nếu ứng dụng yêu cầu tính nguyên tử về dữ liệu, có thể xử lý trên bản sao, kiểm tra trước toàn bộ điều kiện, rồi mới áp dụng cập nhật; đổi lại có chi phí bộ nhớ và/hoặc thời gian. Với hệ thống nhiều luồng, sao chép **cùng lúc đang có người sửa** cũng cần cơ chế đồng bộ hoặc snapshot có ngữ nghĩa phù hợp; `clone()` đơn thuần không chứng minh được một bức ảnh nhất quán khi tác giả khác sửa đồng thời.

Trong thuật toán đồ thị, nếu tạm thêm/xóa cạnh để thử phương án, cần hoàn tác chính xác ở mọi nhánh và mọi đường thoát được dự kiến. Trạng thái hỗ trợ như `visited` có thể là mutable và **cần** mutable; điều quan trọng là nó không làm rò thay đổi trái hợp đồng và luôn thỏa bất biến của tìm kiếm.

## 10. Lỗi phổ biến và checklist kiểm thử

- **Bỏ qua alias:** Gọi `Arrays.sort(a)` rồi nghĩ chỉ thay biến cục bộ; thực tế caller giữ tham chiếu tới chính mảng đó.
- **Hiểu sai `final`:** Cấm gán lại tên biến, không cấm sửa phần tử mảng hoặc trường mutable của đối tượng.
- **Nhầm view với snapshot:** `Collections.unmodifiableList(list)` không đóng băng trạng thái của `list`.
- **Sao chép nông dữ liệu lồng nhau:** Mảng 2D hoặc list chứa đối tượng vẫn chia sẻ mảng con/phần tử mutable.
- **Dùng khóa mutable trong bảng băm:** Thay trường ảnh hưởng `equals/hashCode` có thể làm lookup sai.
- **Làm mất chỉ số gốc sau khi sort:** Trả chỉ số của mảng đã sắp thay cho input ban đầu.
- **Gọi nén tại chỗ rồi coi toàn mảng là kết quả:** Phần đuôi chưa được xóa và kích thước mảng không thay đổi.
- **Duyệt sai chiều khi tối ưu DP 2D xuống 1D:** Dùng lại cùng món trong 0/1 knapsack, phá bất biến “mỗi món tối đa một lần”.
- **Kết luận in-place luôn `O(1)`:** Cấu trúc hỗ trợ của sort, recursion stack, bảng băm và output có thể vẫn tiêu tốn bộ nhớ.

**Checklist cho một bài mới:**

1. Ghi rõ phần dữ liệu caller giao có được mutate không; có cần giữ thứ tự/chỉ số gốc không.
2. Đánh dấu tham chiếu nào là alias; cấu trúc nào dùng chung với nơi khác; bản sao cần sâu đến mức nào.
3. Chọn phương pháp: xử lý trực tiếp, tạo working copy, hoặc cấu trúc hỗ trợ không phá input; tính đúng chi phí thực tế.
4. Nêu bất biến thuật toán và chứng minh mọi cập nhật, đặc biệt điều kiện skip/cắt nhánh/thứ tự DP, vẫn bảo toàn mệnh đề.
5. Kiểm tra input trước và sau lời gọi; nếu hàm “không mutate”, so sánh **toàn bộ nội dung** trước/sau chứ không chỉ kết quả trả về.
6. Thử hai biến cùng giữ tham chiếu; cấu trúc lồng nhau; khóa băm; mảng rỗng, một phần tử, giá trị lặp, giá trị biên kiểu số.
7. Nếu có tiền xử lý, chạy thêm phép cập nhật dữ liệu rồi kiểm tra chỉ mục/cache có cần tạo lại không.

## 11. Bài tự luyện

**Bài 1 — Hợp đồng hai sum.** Với `[4,1,3,2]`, cần trả `boolean` và giữ nguyên input. Trình bày hai cách hợp lệ, độ phức tạp và lý do sort trực tiếp không phù hợp. Nếu đổi đề thành trả **chỉ số gốc**, cần làm gì?

**Bài 2 — Aliasing.** Cho `int[][] grid = {{1},{2}}; int[][] copy = grid.clone(); copy[0][0] = 9;`. Giá trị `grid[0][0]` là bao nhiêu? Tạo bản sao thế nào để không còn chia sẻ mảng con? Giải thích chi phí theo tổng số phần tử.

**Bài 3 — Unmodifiable view.** Tạo một `ArrayList`, rồi lần lượt gọi `Collections.unmodifiableList` và `List.copyOf`. Sửa list gốc; mô tả kết quả quan sát được từ hai tham chiếu, cùng trường hợp phần tử trong list là đối tượng mutable.

**Bài 4 — DP một chiều.** Chỉ có một món `(weight=2,value=3)`, túi dung lượng 4. Viết tay bảng `dp[0..4]` khi duyệt chiều tăng và chiều giảm. Chứng minh vì sao mỗi hướng tương ứng với những giả định khác nhau về số lần được dùng một món.

**Bài 5 — Nén mảng tại chỗ.** Với `[1,1,2,2,3]`, chứng minh tiền tố độ dài `write` luôn có đúng những giá trị phân biệt đã xét. Sau khi kết thúc, tại sao không được hứa rằng phần đuôi mảng là rỗng?

**Bài 6 — Khóa bảng băm.** Thiết kế `record Key(List<Integer> values)` rồi đưa vào `HashSet`. Nếu list gốc vẫn có thể thay đổi, điều gì có thể xảy ra với `hashCode` và phép kiểm tra `contains`? Hãy đề xuất cách tạo khóa có dữ liệu ổn định.

**Tiêu chí hoàn thành:** Bạn có thể phân biệt **immutability của dữ liệu** và **invariant của thuật toán**; xác định chính xác ai sở hữu/được sửa từng cấu trúc, phát hiện alias và copy nông, chọn phương án in-place hay copy theo đặc tả, chứng minh cập nhật giữ đúng thuật toán, và phân tích đầy đủ thời gian/bộ nhớ cùng những ảnh hưởng quan sát được đối với caller.
