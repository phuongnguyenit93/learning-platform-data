# Tính lựa chọn tham lam và cấu trúc con tối ưu

Trong nhóm **thuật toán tham lam** (*greedy algorithms*), ta xây dựng một lời giải bằng cách liên tục đưa ra **lựa chọn có vẻ tốt nhất tại thời điểm hiện tại**, rồi xử lý phần bài toán còn lại. Điểm hấp dẫn là thường không cần quay lui hay liệt kê mọi phương án. Tuy nhiên, **một lựa chọn tốt ngay trước mắt không tự động tạo ra lời giải tối ưu toàn cục**.

Hai tính chất trung tâm cần nhận diện và chứng minh là:

1. **Tính lựa chọn tham lam (greedy-choice property):** Tồn tại một lời giải tối ưu chứa lựa chọn tham lam tại bước hiện tại. Vì vậy, ta có thể đưa ra lựa chọn ấy mà không đánh mất khả năng đạt tối ưu.
2. **Cấu trúc con tối ưu (optimal substructure):** Sau một lựa chọn phù hợp, phần lời giải còn lại phải giải tối ưu bài toán con tương ứng; nếu không, ta có thể thay phần ấy bằng một lời giải tốt hơn và cải thiện lời giải tổng.

Khi kết hợp với **tính khả thi của từng bước**, một bất biến/định lý đúng cho bài toán cụ thể, và lập luận kết thúc, hai tính chất cho phép chứng minh thuật toán tham lam là đúng. **Chỉ nêu tên hai tính chất mà không chứng minh chưa đủ** để tin một quy tắc greedy.

Bài học trình bày ý nghĩa toán học, cách chứng minh bằng **đổi chỗ** (*exchange argument*) và **luôn đi trước** (*stays-ahead*), ví dụ kinh điển **chọn tối đa số hoạt động không giao nhau**, các phản ví dụ, mối quan hệ với quy hoạch động và chương trình Java 17+ hoàn chỉnh.

## 1. Ba khái niệm khác nhau: khả thi, tối ưu, lựa chọn tham lam

Xét một bài toán tối ưu. Ta có:

- **Tập lời giải khả thi:** những phương án thỏa tất cả ràng buộc.
- **Hàm mục tiêu:** số lượng công việc, tổng chi phí, tổng giá trị, khoảng cách... cần tối đa hoặc tối thiểu.
- **Lựa chọn tham lam:** quy tắc chọn một phần tử/hành động **ở bước hiện tại**, dựa trên thông tin đang có, với kỳ vọng dẫn đến mục tiêu tốt nhất.

Ví dụ, trong bài chọn hoạt động không chồng lấn, có thể đề xuất nhiều quy tắc:

- Chọn hoạt động **bắt đầu sớm nhất**.
- Chọn hoạt động **kết thúc sớm nhất**.
- Chọn hoạt động **ngắn nhất**.
- Chọn hoạt động có **thời gian kết thúc muộn nhất**.

Chỉ một trong những quy tắc phổ biến trên — **kết thúc sớm nhất** — có chứng minh đơn giản cho bài toán **tối đa số hoạt động, mỗi hoạt động có cùng trọng số 1**, trên một máy/nguồn lực với các khoảng thời gian xác định.

Không thể chọn quy tắc chỉ vì nghe có vẻ “tham lam”. Cần chứng minh: sau mỗi lựa chọn, luôn còn một phương án tối ưu tương thích với những gì đã chọn.

### Ví dụ nhanh: lựa chọn địa phương không đủ

Cho hoạt động `[0,10)`, `[1,2)`, `[2,3)`, `[3,4)`. Chọn hoạt động **bắt đầu sớm nhất** sẽ lấy `[0,10)` rồi không lấy được hoạt động nào khác: tổng **1**. Trong khi chọn ba hoạt động `[1,2)`, `[2,3)` và `[3,4)` có tổng **3**.

Cùng một mục tiêu và cùng bài toán, chỉ cần đổi tiêu chí chọn là đáp án thay đổi. Điều ta cần là **chứng minh quy tắc lựa chọn**, không phải chỉ chứng minh chương trình chạy nhanh.

## 2. Tính lựa chọn tham lam (greedy-choice property)

**Định nghĩa trực quan:** Khi đứng trước một bài toán con còn lại, ta có thể chọn **một lựa chọn greedy g** sao cho **ít nhất một lời giải tối ưu** của bài toán con đó cũng có thể bắt đầu bằng g.

Điều này **không** nói rằng mọi lời giải tối ưu đều phải chọn g. Có thể tồn tại nhiều lời giải tối ưu khác nhau, đặc biệt khi có các giá trị bằng nhau hoặc nhiều phương án hòa.

Với bài toán tối ưu có tập trạng thái S, có thể phát biểu:

```text
g = lựa chọn được quy tắc greedy đề xuất từ S.

Greedy-choice property:
  tồn tại một lời giải tối ưu OPT(S)
  tương thích với việc chọn g trước.

Sau khi cố định g:
  phần còn lại được giải trên trạng thái S_g.
```

Trong một bài toán chọn nhiều phần tử, ta thường biểu diễn:

```text
OPT(S) = contribution(g) + OPT(S_g)
```

**Nhưng** công thức trên chỉ được dùng sau khi đã chứng minh rằng có một nghiệm tối ưu chứa g, trạng thái S_g mô tả chính xác các lựa chọn còn khả thi, và hàm mục tiêu có cách kết hợp tương ứng. Không được giả định phương trình này đúng cho mọi bài toán chỉ vì đã chọn một g nào đó.

### Ba câu hỏi để kiểm tra lựa chọn tham lam

1. **Chọn g có giữ được tính khả thi không?** Một bước không hợp lệ không thể là bước đầu của lời giải đúng.
2. **Có thể biến một nghiệm tối ưu bất kỳ thành một nghiệm tối ưu chứa g mà không làm mục tiêu tệ hơn không?** Đây là dạng chứng minh bằng **trao đổi/đổi chỗ**.
3. **Sau khi chọn g, những quyết định còn lại có thể được giải như một bài toán cùng cấu trúc hay không?** Nếu có, ta có cơ sở tiếp tục chọn tham lam ở trạng thái mới.

**Đặc biệt:** Một lựa chọn greedy không nhất thiết là lựa chọn có lợi ích tức thời lớn nhất theo mọi thước đo. Trong bài chọn hoạt động, lựa chọn kết thúc sớm nhất có thể không phải hoạt động dài nhất, quan trọng nhất hay bắt đầu sớm nhất; nó tốt vì **để lại nhiều không gian thời gian nhất cho các hoạt động phía sau**.

## 3. Cấu trúc con tối ưu (optimal substructure)

**Định nghĩa:** Một lời giải tối ưu của bài toán lớn được tạo từ các lời giải tối ưu của những bài toán con phù hợp; nếu một phần của lời giải không tối ưu cho bài toán con tương ứng, ta có thể thay bằng lời giải tốt hơn, dẫn đến mâu thuẫn với tính tối ưu ban đầu.

Giả sử lời giải tối ưu chứa một lựa chọn đầu g, rồi phần còn lại R. Nếu R chưa tối ưu đối với trạng thái còn lại S_g, tồn tại R' tốt hơn. Khi đó `g + R'` cũng khả thi và có mục tiêu tốt hơn `g + R`, trái giả thiết rằng lời giải ban đầu tối ưu.

Điểm quan trọng là **S_g phải chứa đúng các ràng buộc sau khi đã chọn g**. Không thể lấy lời giải tối ưu của một bài toán con độc lập rồi ghép vào nếu nó gây vi phạm ràng buộc của lời giải tổng.

### Tính con tối ưu không đồng nghĩa có greedy

Rất nhiều bài toán **quy hoạch động** có cấu trúc con tối ưu nhưng không có lựa chọn greedy đơn giản:

- **Ba lô 0/1 (0/1 knapsack):** Có thể phân theo việc lấy/không lấy từng món, nhưng chọn tỷ lệ giá trị/trọng lượng lớn nhất trước không luôn tối ưu.
- **Đổi tiền với hệ mệnh giá bất kỳ:** Có thể tối ưu số đồng tiền qua các số tiền nhỏ hơn, nhưng lấy đồng lớn nhất đang dùng được không luôn cho ít đồng nhất.
- **Lập lịch có trọng số:** Có cấu trúc bài toán con và công thức DP, nhưng chọn công việc kết thúc sớm nhất có thể không tối đa tổng giá trị.

Vì vậy, **optimal substructure không đủ để kết luận có thể áp dụng greedy**. Phải chứng minh thêm **greedy-choice property cho đúng quy tắc lựa chọn và đúng mục tiêu**.

Ngược lại, không nên chỉ nêu một phép “trao đổi” mơ hồ rồi bỏ qua bài toán con: thuật toán còn phải chỉ ra rằng sau khi chọn g, phần còn lại thật sự có thể giải tiếp và ghép lại thành nghiệm hợp lệ.

## 4. Ví dụ chuẩn: chọn tối đa số hoạt động không giao nhau

Cho n hoạt động. Hoạt động i có thời điểm bắt đầu `s_i` và kết thúc `f_i`, với `s_i < f_i`. Mỗi hoạt động dùng cùng một tài nguyên; hai hoạt động không được chồng lấn.

Bài học sử dụng **khoảng nửa mở [s_i, f_i)**: một hoạt động kết thúc ở t và hoạt động khác bắt đầu đúng t **không chồng lấn**. Do đó điều kiện nhận hoạt động tiếp theo là:

```text
next.start >= lastSelected.end
```

**Mục tiêu:** Chọn **nhiều hoạt động nhất**, không phải tổng thời lượng lớn nhất hay tổng giá trị lớn nhất. Mỗi hoạt động được tính **1 đơn vị** vào số lượng.

Các hoạt động ví dụ:

| ID | Bắt đầu | Kết thúc |
| --- | ---: | ---: |
| A | 1 | 4 |
| B | 3 | 5 |
| C | 0 | 6 |
| D | 5 | 7 |
| E | 3 | 9 |
| F | 5 | 9 |
| G | 6 | 10 |
| H | 8 | 11 |
| I | 8 | 12 |
| J | 2 | 14 |
| K | 12 | 16 |

Nếu chọn hoạt động theo **thời điểm kết thúc tăng dần**, đáp án greedy lần lượt là:

```text
Chọn A = [1,4)
B [3,5): bỏ vì 3 < 4
C [0,6): bỏ vì 0 < 4
Chọn D = [5,7) vì 5 >= 4
E [3,9), F [5,9), G [6,10): bỏ vì bắt đầu < 7
Chọn H = [8,11) vì 8 >= 7
I [8,12), J [2,14): bỏ vì bắt đầu < 11
Chọn K = [12,16) vì 12 >= 11

Kết quả: [A, D, H, K], tổng 4 hoạt động
```

Lưu ý sự khác biệt giữa **kết quả tối ưu về số lượng** và **thứ tự ưu tiên khi có nhiều phương án cùng số lượng**. Chẳng hạn có thể tồn tại bộ hoạt động tối ưu khác, nhưng thuật toán chỉ cần trả **một** bộ có số lượng tối đa.

## 5. Vì sao kết thúc sớm nhất là lựa chọn tham lam an toàn?

Gọi g là hoạt động kết thúc sớm nhất trong tập các hoạt động còn khả thi (sau mốc thời gian hiện tại). Cần chứng minh có **một** lịch tối ưu bắt đầu bằng g.

### Chứng minh bằng trao đổi (exchange argument)

1. Xét một lịch tối ưu O có các hoạt động không chồng lấn, sắp theo thứ tự thời gian. Gọi o là hoạt động **đầu tiên** trong lịch O.
2. Vì g kết thúc sớm nhất trong tập đang xét, ta có `finish(g) <= finish(o)`.
3. Thay o bằng g. Hoạt động g bắt đầu hợp lệ ở mốc hiện tại, nên không vi phạm ràng buộc từ những hoạt động đã chọn trước đó.
4. Mọi hoạt động sau o trong lịch O đều bắt đầu **không sớm hơn finish(o)**. Vì `finish(g) <= finish(o)`, chúng cũng bắt đầu **không sớm hơn finish(g)**. Do đó việc thay o bằng g **không gây chồng lấn** với các hoạt động tiếp theo.
5. Lịch sau thay có **cùng số hoạt động** với O, nên vẫn tối ưu và **có chứa g**.

Kết luận: **Lựa chọn hoạt động kết thúc sớm nhất là lựa chọn an toàn**. Có thể cố định g trước mà không làm giảm số hoạt động tối đa có thể chọn.

**Chú ý về mặt logic:** Không cần chứng minh g nằm trong **mọi** lịch tối ưu. Ta chỉ cần biến **một lịch tối ưu bất kỳ** thành **một lịch tối ưu chứa g**. Nếu nhiều hoạt động cùng kết thúc sớm nhất, chọn một theo quy tắc hòa xác định (ví dụ bắt đầu sớm rồi ID) vẫn an toàn vì cùng có thời điểm kết thúc nhỏ nhất.

### Hình dung việc trao đổi

```text
Trước:
    o: [----)
                  các hoạt động sau o
                   [---)  [---) ...

Sau khi thay:
    g: [--)
                  các hoạt động sau o giữ nguyên
                   [---)  [---) ...

Vì g kết thúc không muộn hơn o, khoảng thời gian dành
cho các hoạt động sau không bị thu hẹp.
```

Lập luận này dựa trực tiếp trên **mục tiêu đếm số hoạt động**. Nếu mỗi hoạt động có trọng số giá trị khác nhau, thay o bằng g có thể **giảm tổng giá trị**; khi ấy lập luận giữ nguyên hàm mục tiêu không còn đúng.

## 6. Cấu trúc con tối ưu của bài lập lịch

Khi đã chọn hoạt động g có thời điểm kết thúc f, **mọi hoạt động có start < f đều không thể chọn thêm**. Phần còn lại là tập:

```text
S_g = { hoạt động i | start_i >= finish(g) }
```

Một lịch tối ưu có chứa g phải có dạng:

```text
[g] + lịch tối ưu trên S_g
```

**Chứng minh:** Nếu phần lịch sau g **không tối ưu** trên S_g, tồn tại một phần lịch khác có nhiều hoạt động hơn và vẫn tương thích với g. Thay phần lịch cũ bằng phần lịch mới sẽ tạo lịch khả thi có **nhiều hoạt động hơn lịch tối ưu ban đầu**, vô lý.

Từ tính lựa chọn tham lam đã chứng minh và cấu trúc con tối ưu, ta có thể viết:

```text
OPT(S) = 0                          nếu S rỗng
OPT(S) = 1 + OPT(S_g)               nếu g kết thúc sớm nhất trong S
```

Ở đây OPT(S) là **số hoạt động tối đa**, còn S_g là tập còn tương thích với g. Đây là một hệ thức đúng nhờ chứng minh, **không phải công thức được giả định trước**.

Áp dụng lặp lại: trong S_g lại chọn hoạt động có thời điểm kết thúc sớm nhất, rồi tiếp tục đến khi không còn hoạt động nào khả thi.

## 7. Chứng minh bằng “luôn đi trước” (stays-ahead)

Ngoài trao đổi, ta có thể chứng minh greedy bằng một đại lượng so sánh tiến độ: **thời điểm kết thúc của hoạt động được chọn thứ j**.

Gọi:

- `g_1, g_2, ...` là dãy hoạt động greedy chọn, theo thứ tự kết thúc.
- `o_1, o_2, ...` là các hoạt động của một lịch tối ưu bất kỳ, theo thứ tự thời gian.

**Mệnh đề:** Với mọi j tồn tại trong cả hai dãy, ta có:

```text
finish(g_j) <= finish(o_j)
```

**Cơ sở j=1:** g_1 là hoạt động kết thúc sớm nhất, nên `finish(g_1) <= finish(o_1)`.

**Bước quy nạp:** Giả sử `finish(g_(j-1)) <= finish(o_(j-1))`. Vì lịch O khả thi, hoạt động o_j bắt đầu không trước khi o_(j-1) kết thúc:

```text
start(o_j) >= finish(o_(j-1)) >= finish(g_(j-1))
```

Vậy o_j **là ứng viên khả thi** sau g_(j-1). Greedy chọn ứng viên kết thúc sớm nhất trong các ứng viên khả thi, nên:

```text
finish(g_j) <= finish(o_j)
```

**Kết luận tối ưu:** Giả sử greedy chọn r hoạt động nhưng có lịch tối ưu chọn nhiều hơn r. Sau r lần chọn, kết thúc greedy không muộn hơn hoạt động thứ r của lịch tối ưu. Do đó hoạt động thứ r+1 của lịch tối ưu vẫn **khả thi sau g_r**; greedy sẽ còn chọn được một hoạt động nữa, mâu thuẫn với việc thuật toán đã dừng. Vậy số hoạt động greedy chọn là tối đa.

Chứng minh *stays-ahead* cho thấy tiêu chí **kết thúc sớm nhất** là đại lượng phù hợp. Không nên cố chứng minh “luôn đi trước” bằng số phút đã chiếm, nếu số phút không liên quan đến mục tiêu tối đa số hoạt động.

## 8. Thiết kế thuật toán tham lam từ các tính chất

Cho bài lập lịch không trọng số:

1. **Mô hình hóa chính xác:** Một hoạt động có start, end; mọi hoạt động dùng cùng tài nguyên; chọn tối đa số hoạt động không chồng lấn.
2. **Quy ước biên:** Các khoảng [start,end) với start<end. Hoạt động sau được chọn nếu `start >= lastEnd`.
3. **Đề xuất quy tắc:** Chọn hoạt động **kết thúc sớm nhất** trong những hoạt động đang còn khả thi.
4. **Chứng minh lựa chọn an toàn:** Dùng trao đổi với hoạt động đầu tiên trong một lịch tối ưu.
5. **Chứng minh bài toán con tối ưu:** Sau khi chọn g, phần còn lại phải là lịch tối ưu trên tập bắt đầu sau thời điểm g kết thúc.
6. **Hiện thực hiệu quả:** Sắp xếp hoạt động theo end tăng, quét một lần và nhận hoạt động phù hợp.
7. **Chứng minh bất biến/kết thúc:** Mỗi hoạt động được xét tối đa một lần, các hoạt động đã chọn luôn tương thích; kết quả có số lượng tối đa theo các chứng minh trước.
8. **Kiểm tra phản ví dụ và biên:** Mảng rỗng, hoạt động trùng khung giờ, hoạt động nối đầu–cuối, thời gian âm, quy tắc hòa, start=end không hợp lệ theo mô hình.

### Giả mã

```text
GREEDY-ACTIVITY-SELECTION(activities):
    sort activities by end increasing
    result = []
    lastEnd = -infinity

    for activity in activities:
        if activity.start >= lastEnd:
            append activity to result
            lastEnd = activity.end

    return result
```

**Bất biến quét:** Sau khi xét một tiền tố của danh sách đã sắp theo end, tập `result` gồm các hoạt động đôi một không chồng lấn, theo thứ tự kết thúc, và lastEnd là thời điểm kết thúc của hoạt động cuối đã chọn (hoặc -∞ nếu chưa chọn). Khi gặp hoạt động có start≥lastEnd, nhận nó không phá bất biến; nếu start<lastEnd, bỏ nó vì nó không phù hợp với những lựa chọn hiện tại.

Bất biến bảo đảm **tính khả thi**; các chứng minh trao đổi/luôn đi trước phía trên bảo đảm **tối ưu**. Hai kết luận này không nên đánh đồng: một tập hoạt động khả thi không nhất thiết là tập nhiều nhất.

## 9. Mã Java 17+ chạy được

Chương trình dùng `record Interval(String id, int start, int end)`, quy ước start < end và khoảng thời gian nửa mở. Dữ liệu đầu vào được **sao chép trước khi sắp xếp**, nên danh sách gốc không bị đổi thứ tự. Trong trường hợp cùng thời điểm kết thúc, comparator so sánh thêm thời điểm bắt đầu rồi ID để kết quả **tái lập được**; quy tắc hòa này không làm thay đổi tính tối ưu về số lượng.

Lưu file **`GreedyChoiceSubstructure.java`**:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Comparator;
import java.util.List;
import java.util.Objects;
import java.util.StringJoiner;

public class GreedyChoiceSubstructure {
    record Interval(String id, int start, int end) {
        Interval {
            Objects.requireNonNull(id, "id");
            if (start >= end) {
                throw new IllegalArgumentException(
                        "start must be less than end");
            }
        }
    }

    static List<Interval> selectMaxActivities(Interval[] input) {
        Objects.requireNonNull(input, "input must not be null");

        Interval[] byFinish = input.clone();
        for (Interval activity : byFinish) {
            Objects.requireNonNull(activity, "activity must not be null");
        }

        Arrays.sort(byFinish,
                Comparator.comparingInt(Interval::end)
                        .thenComparingInt(Interval::start)
                        .thenComparing(Interval::id));

        List<Interval> chosen = new ArrayList<>();
        long lastEnd = Long.MIN_VALUE;

        for (Interval activity : byFinish) {
            if (activity.start() >= lastEnd) {
                chosen.add(activity);
                lastEnd = activity.end();
            }
        }
        return List.copyOf(chosen);
    }

    static String ids(List<Interval> activities) {
        StringJoiner joiner = new StringJoiner(", ", "[", "]");
        for (Interval activity : activities) {
            joiner.add(activity.id());
        }
        return joiner.toString();
    }

    public static void main(String[] args) {
        Interval[] activities = {
            new Interval("A", 1, 4),
            new Interval("B", 3, 5),
            new Interval("C", 0, 6),
            new Interval("D", 5, 7),
            new Interval("E", 3, 9),
            new Interval("F", 5, 9),
            new Interval("G", 6, 10),
            new Interval("H", 8, 11),
            new Interval("I", 8, 12),
            new Interval("J", 2, 14),
            new Interval("K", 12, 16)
        };

        List<Interval> best = selectMaxActivities(activities);
        System.out.println("Sample: " + ids(best)
                + " (count=" + best.size() + ")");

        Interval[] ties = {
            new Interval("P", 0, 2),
            new Interval("R", 1, 4),
            new Interval("Q", 2, 4),
            new Interval("S", 4, 6)
        };
        System.out.println("Ties: "
                + ids(selectMaxActivities(ties)));

        Interval[] negative = {
            new Interval("N1", -7, -2),
            new Interval("N3", -5, 0),
            new Interval("N2", -2, 1),
            new Interval("N4", 1, 3)
        };
        System.out.println("Negative times: "
                + ids(selectMaxActivities(negative)));

        Interval[] overlapping = {
            new Interval("X", 0, 5),
            new Interval("Y", 1, 4),
            new Interval("Z", 2, 3)
        };
        System.out.println("Overlapping: "
                + ids(selectMaxActivities(overlapping)));

        Interval[] adjacent = {
            new Interval("L", 0, 2),
            new Interval("M", 2, 4),
            new Interval("N", 4, 6)
        };
        System.out.println("Adjacent: "
                + ids(selectMaxActivities(adjacent)));

        System.out.println("Empty: "
                + ids(selectMaxActivities(new Interval[0])));
        System.out.println("Extreme range: "
                + ids(selectMaxActivities(new Interval[]{
                    new Interval("Edge",
                            Integer.MIN_VALUE, Integer.MAX_VALUE)
                })));
        System.out.println("Input first unchanged: "
                + activities[0].id());

        try {
            new Interval("Bad", 4, 4);
        } catch (IllegalArgumentException ex) {
            System.out.println("Invalid interval: " + ex.getMessage());
        }
    }
}
```

Biên dịch và chạy với JDK 17 trở lên:

```bash
javac GreedyChoiceSubstructure.java
java GreedyChoiceSubstructure
```

Stdout dự kiến:

```text
Sample: [A, D, H, K] (count=4)
Ties: [P, Q, S]
Negative times: [N1, N2, N4]
Overlapping: [Z]
Adjacent: [L, M, N]
Empty: []
Extreme range: [Edge]
Input first unchanged: A
Invalid interval: start must be less than end
```

**Diễn giải:**

- **Sample:** Chọn bốn hoạt động theo thời điểm kết thúc; không hoạt động nào trong kết quả chồng lấn.
- **Ties:** Hai hoạt động Q và R cùng kết thúc tại 4, nhưng P kết thúc ở 2 nên Q có start=2 và được nhận, còn R có start=1 bị bỏ. Quy tắc phụ trong comparator cho thứ tự thử nghiệm xác định.
- **Negative times:** Dùng thời gian âm vẫn đúng. `lastEnd` là `long` khởi tạo `Long.MIN_VALUE` để hoạt động bắt đầu tại cả `Integer.MIN_VALUE` cũng được xét đúng.
- **Overlapping:** Trong ba hoạt động cùng chồng lấn, Z kết thúc sớm nhất nên được chọn; tối đa chỉ lấy một trong ba.
- **Adjacent:** Do dùng khoảng nửa mở, các hoạt động có `end=next.start` có thể cùng xuất hiện trong lịch.
- **Empty:** Không có hoạt động, kết quả rỗng.
- **Input first unchanged:** Phương thức sắp xếp **bản sao**, nên không sửa thứ tự mảng đầu vào.
- **Invalid interval:** Với start=end, constructor chủ động từ chối để tránh mơ hồ về thời lượng và quy ước không giao nhau.

### Phân tích độ phức tạp của mã

Với n hoạt động:

- Sao chép tham chiếu mảng: **O(n)**.
- Kiểm tra null: **O(n)**.
- Sắp xếp theo thời điểm kết thúc: **O(n log n)** ở phân tích theo phép so sánh.
- Quét chọn: **O(n)**.
- **Tổng:** **O(n log n)** thời gian, chi phí chi phối bởi sắp xếp. Nếu đầu vào đã theo thứ tự kết thúc và không cần sắp, lõi greedy chỉ **O(n)**.
- **Bộ nhớ:** Bản sao mảng `O(n)`, danh sách kết quả tối đa n phần tử `O(n)` và bộ nhớ tạm của hàm sort tùy hiện thực. Nhìn theo cấp tăng trưởng, tổng không gian phụ/đầu ra tối đa **O(n)**. Không thể nói “O(1) bộ nhớ toàn thuật toán” chỉ vì phép kiểm tra hoạt động tiếp theo dùng một biến lastEnd.

Nếu mã được thay để trả danh sách chọn theo thứ tự gốc, cần một bước chuyển đổi bổ sung; thứ tự theo kết thúc là hữu ích vì nó cho biết tại sao từng hoạt động được chọn.

## 10. Khi nào không thể dùng quy tắc tham lam này?

### 10.1. Bài toán đổi tiền không có hệ mệnh giá đặc biệt

Cho các mệnh giá `[1,3,4]` và số tiền cần đổi là 6, mục tiêu là **ít đồng nhất**.

**Greedy “luôn lấy đồng lớn nhất không vượt quá phần tiền còn lại”:**

```text
6 -> lấy 4, còn 2
2 -> lấy 1, còn 1
1 -> lấy 1, còn 0

Đáp án greedy: 4 + 1 + 1 = 3 đồng
```

**Phương án tối ưu:** `3 + 3 = 6`, chỉ **2 đồng**.

Bài này có thể biểu diễn thành các bài toán con theo số tiền còn lại, nhưng **không có tính lựa chọn tham lam đối với quy tắc “đồng lớn nhất” ở hệ mệnh giá này**. Đối với hệ mệnh giá tùy ý, quy hoạch động là một cách tổng quát hơn để tối thiểu số đồng (nếu tồn tại lời giải). Có những hệ mệnh giá được thiết kế đặc biệt mà greedy đổi tiền đúng, nhưng không được suy rộng cho mọi hệ.

### 10.2. Ba lô 0/1 không giống ba lô phân số

Bài **0/1 knapsack**: mỗi món chỉ được chọn **toàn bộ hoặc không chọn**, tổng khối lượng không vượt sức chứa. Giả sử sức chứa=50:

| Món | Trọng lượng | Giá trị | Giá trị/trọng lượng |
| --- | ---: | ---: | ---: |
| A | 10 | 60 | 6 |
| B | 20 | 100 | 5 |
| C | 30 | 120 | 4 |

Greedy theo tỷ lệ chọn A rồi B, tổng trọng lượng 30, tổng giá trị **160**; không thể nhận thêm C. Nghiệm tốt hơn là B+C, trọng lượng 50, giá trị **220**. Chọn tỷ lệ cao nhất trước **không an toàn** cho 0/1 knapsack.

Nếu **được phép lấy một phần món** (*fractional knapsack*) và giá trị tỷ lệ tuyến tính với phần được lấy, quy tắc ưu tiên tỷ lệ giá trị/trọng lượng cao nhất **có thể được chứng minh tối ưu bằng trao đổi**: thay một lượng trọng lượng của món tỷ lệ thấp bằng cùng lượng từ món tỷ lệ cao mà vẫn khả thi sẽ không làm giảm tổng giá trị. Đây là **một bài toán khác** với điều kiện cấu trúc khác.

### 10.3. Lập lịch có trọng số

Giữ ràng buộc không chồng lấn, nhưng mỗi hoạt động có một **giá trị**, mục tiêu tối đa **tổng giá trị**, không phải số hoạt động.

Ví dụ:

```text
A = [0,2), value=2
B = [2,4), value=2
C = [0,4), value=10

Greedy kết thúc sớm: A rồi B, tổng value=4
Nghiệm tốt hơn: chỉ C, tổng value=10
```

Ở đây, thay C bằng A có thể giữ **số lượng** không đổi ở bước thay, nhưng làm **tổng giá trị** thấp hơn. Vì thế chứng minh trao đổi cho bài toán không trọng số không áp dụng.

Một lời giải phổ biến cho **weighted interval scheduling** dùng quy hoạch động: sắp xếp theo thời điểm kết thúc, tìm hoạt động tương thích gần nhất, và xét việc nhận/bỏ từng hoạt động. Cấu trúc con tối ưu vẫn có, nhưng **lựa chọn kết thúc sớm nhất không còn đảm bảo tối ưu theo giá trị**.

### 10.4. Khi quy tắc có thể đúng nhưng bằng chứng bị thiếu

Đôi khi chạy hàng nghìn test mà greedy vẫn cho đáp án tốt. Điều đó **không phải chứng minh**. Để dùng greedy trong hệ thống cần tính đúng tuyệt đối:

- Định nghĩa rõ ràng đầu vào, ràng buộc, hàm mục tiêu và cách xử lý giá trị bằng nhau.
- Viết ra **lựa chọn greedy cụ thể**.
- Chứng minh mọi quyết định greedy **có thể gắn vào một nghiệm tối ưu**, thường bằng trao đổi hoặc tính chất cấu trúc như cut property.
- Chứng minh bài toán còn lại có cấu trúc con tối ưu và thao tác ghép không vi phạm ràng buộc.
- Chứng minh kết thúc, các biên và trường hợp n=0.
- Khi không tìm được chứng minh hoặc có phản ví dụ, dùng phương pháp khác (DP, tìm kiếm, nhánh cận, v.v.).

## 11. Liên hệ các thuật toán tham lam quen thuộc

| Bài toán | Lựa chọn tham lam | Ý tưởng đảm bảo tính đúng | Giới hạn cần nhớ |
| --- | --- | --- | --- |
| Chọn tối đa số hoạt động không giao nhau, không trọng số | Hoạt động **kết thúc sớm nhất** còn khả thi | Trao đổi hoạt động đầu và cấu trúc con tối ưu | Không áp dụng thẳng cho tổng trọng số |
| Cây khung nhỏ nhất – Kruskal | Chọn cạnh nhẹ nhất chưa gây chu trình, theo thứ tự trọng số | **Cut property** và lập luận trao đổi | Đồ thị vô hướng; xử lý liên thông/rừng khung phù hợp |
| Đường đi ngắn – Dijkstra | Cố định đỉnh chưa xử lý có khoảng cách tạm nhỏ nhất | Bất biến khoảng cách và trọng số cạnh **không âm** | Cạnh âm có thể làm bước chốt đỉnh không an toàn |
| Mã Huffman | Ghép hai nút/trọng số nhỏ nhất còn lại | Trao đổi/cấu trúc cây tiền tố tối ưu | Mục tiêu độ dài mã trung bình, trọng số phù hợp |
| Ba lô phân số | Chọn món theo tỷ lệ giá trị/trọng lượng cao nhất | Trao đổi một phần khối lượng | Không áp dụng cho ba lô 0/1 |
| Đổi tiền với hệ mệnh giá bất kỳ | Chọn đồng lớn nhất đang dùng được | **Không có bảo đảm chung** | Phản ví dụ [1,3,4], số tiền 6 |

Bảng trên chỉ nêu hướng trực giác chứng minh, **không thay thế** các giả thiết riêng của từng bài. Dijkstra, Kruskal và Huffman có những bất biến/cấu trúc đối tượng khác nhau; không thể sao chép nguyên văn chứng minh của bài chọn hoạt động cho mọi thuật toán greedy.

## 12. So sánh greedy với quy hoạch động và vét cạn

### Greedy

Ở mỗi bước, **cố định một lựa chọn** đã chứng minh là an toàn rồi giải bài toán còn lại. Nếu tiền xử lý dữ liệu và quản lý trạng thái hiệu quả, greedy thường có code ngắn và độ phức tạp thấp.

Tuy nhiên, thành công phụ thuộc **chứng minh tính lựa chọn tham lam**. Với quy tắc chưa chứng minh, code ngắn và tốc độ cao chỉ cho một kết quả nhanh, không chắc tối ưu.

### Quy hoạch động (dynamic programming)

DP xét **nhiều lựa chọn có thể** thông qua công thức chuyển trạng thái, lưu kết quả bài toán con để tránh tính lại. DP thường cần **optimal substructure** và **các bài toán con chồng lặp** để memoization/tabulation hiệu quả; không đòi hỏi biết trước một lựa chọn địa phương luôn đúng.

Trong bài lập lịch không trọng số, có thể xây DP xét nhận/bỏ công việc; nhưng khi đã chứng minh quy tắc kết thúc sớm nhất an toàn, greedy thường đơn giản hơn. Trong bài lịch có trọng số, DP thường là phương án phù hợp.

### Vét cạn/backtracking

Duyệt nhiều phương án hoặc nhánh lựa chọn, loại nhánh không hợp lệ và tìm nghiệm tốt nhất. Có thể cho kết quả đúng với input nhỏ để **kiểm chứng thử nghiệm** một cài đặt greedy, nhưng thường có chi phí lớn hơn khi n tăng.

**Kiểm thử so với brute force không chứng minh greedy:** Nó rất hữu ích để tìm lỗi code hoặc phản ví dụ nhỏ. Nhưng nếu không có phản ví dụ trong tập thử, vẫn cần lập luận toán học về mọi đầu vào hợp lệ.

## 13. Phương pháp chứng minh greedy: ba hướng phổ biến

### 13.1. Exchange argument – trao đổi không làm xấu nghiệm

Lấy một nghiệm tối ưu bất kỳ. Nếu nó không chứa lựa chọn greedy g, cố gắng **thay** một lựa chọn trong nghiệm bằng g mà vẫn khả thi, không giảm giá trị mục tiêu. Nếu làm được, tồn tại một nghiệm tối ưu chứa g.

Ví dụ bài chọn hoạt động: thay hoạt động đầu tiên của lịch tối ưu bằng hoạt động kết thúc sớm nhất. Vì hoạt động mới kết thúc không muộn hơn, mọi hoạt động phía sau vẫn khả thi.

**Dấu hiệu nên kiểm tra:** Khi thay g, liệu một ràng buộc phụ có bị phá? Nếu có trọng số, liệu mục tiêu có thể giảm? Chỉ cần một trong hai xảy ra là phép trao đổi đã thất bại.

### 13.2. Stays-ahead – luôn không kém theo đại lượng đúng

Chọn một đại lượng so sánh hai lời giải sau j bước, rồi chứng minh greedy **không kém** một lời giải tối ưu ở mỗi bước. Với lập lịch, đại lượng là **thời điểm kết thúc hoạt động thứ j**; càng kết thúc sớm, càng còn nhiều cơ hội chọn thêm hoạt động.

**Dấu hiệu nên kiểm tra:** Đại lượng có thực sự dự báo khả năng hoàn thành mục tiêu không? “Lợi ích tức thời” chưa chắc là đại lượng phù hợp.

### 13.3. Cut property / lựa chọn an toàn ở ranh giới

Một số bài toán đồ thị sử dụng tính chất rằng một phần tử qua một ranh giới/cut là **an toàn** để thêm vào một lời giải tối ưu. Ví dụ Kruskal chọn cạnh có trọng số nhỏ nhất qua một cut phù hợp; một phép trao đổi cạnh trên chu trình có thể chứng minh tồn tại cây khung tối ưu chứa cạnh ấy.

**Giới hạn:** Đây là một kiểu chứng minh có giả thiết về cấu trúc đồ thị và tập cạnh, không phải mệnh đề “chọn phần tử nhỏ nhất bất kỳ luôn đúng”.

## 14. Những sai lầm thường gặp

1. **Nhầm local optimum với global optimum.** Tối ưu ngay bước hiện tại chưa bảo đảm tối ưu sau tất cả bước; cần greedy-choice property.
2. **Chỉ kiểm tra optimal substructure rồi kết luận greedy đúng.** Nhiều bài DP có cấu trúc con tối ưu nhưng quy tắc greedy đề xuất sai.
3. **Chứng minh có nghiệm chứa g nhưng không nói phần còn lại giải ở đâu.** Phải xác định chính xác trạng thái sau g và các ràng buộc còn lại.
4. **Nhầm “tồn tại một nghiệm tối ưu chứa g” với “mọi nghiệm tối ưu đều chứa g”.** Chỉ cần sự tồn tại, không cần tính duy nhất.
5. **Trộn mục tiêu khác nhau.** Tối đa số hoạt động khác tối đa tổng giá trị, khác tối đa tổng thời lượng; mỗi mục tiêu cần quy tắc/chứng minh riêng.
6. **Chọn bắt đầu sớm nhất trong interval scheduling.** Một hoạt động dài có thể chặn nhiều hoạt động ngắn phía sau.
7. **Chọn hoạt động ngắn nhất theo thời lượng mà không chứng minh.** Một hoạt động ngắn nhưng nằm giữa hai hoạt động khác có thể làm mất cơ hội nhận cả hai.
8. **Xử lý sai biên tiếp giáp.** Với [start,end), `next.start == previous.end` là hợp lệ. Nếu bài dùng khoảng đóng có xung đột ở mút, phải thay điều kiện.
9. **Không xác thực start<end.** Khoảng rỗng hoặc thời gian đảo cần quy ước riêng, không tự mặc định theo code mẫu.
10. **Nhầm xét hoạt động theo thứ tự kết thúc với thứ tự nhập.** Nếu không sắp trước, một lượt quét tùy ý có thể chọn sai.
11. **Sắp theo end nhưng bỏ qua việc tính khả thi.** Hoạt động kết thúc sớm vẫn có thể chồng lấn với hoạt động đã chọn; phải kiểm tra start>=lastEnd.
12. **Giả định có lời giải tối ưu duy nhất.** Nhiều lịch có cùng số lượng; các quy tắc hòa có thể trả lịch khác nhau mà vẫn tối ưu.
13. **Không phân biệt tiền xử lý và lõi greedy.** Quét là O(n) sau sort, nhưng từ đầu vào bất kỳ tổng thường O(n log n).
14. **Bỏ qua chi phí bộ nhớ của clone/sort.** Mã dùng bản sao và danh sách kết quả; toàn bộ thuật toán không phải O(1) không gian.
15. **Suy rộng greedy đổi tiền cho mọi hệ mệnh giá.** Hệ [1,3,4], số tiền 6 là phản ví dụ rõ ràng.
16. **Áp dụng greedy theo tỷ lệ vào ba lô 0/1.** Chỉ đúng một cách tổng quát cho phiên bản phân số với giả thiết giá trị tuyến tính và trọng lượng dương.
17. **Sao chép lập luận trao đổi giữa các bài toán không tương đương.** Cần kiểm tra tính khả thi và hàm mục tiêu có được giữ hoặc cải thiện trong phép trao đổi mới hay không.
18. **Thử nhiều test rồi coi như đã chứng minh.** Test hỗ trợ phát hiện bug, không thay thế chứng minh toán học.
19. **Mọi lựa chọn greedy hợp lệ đều sẽ dẫn đến kết quả tối ưu.** Chỉ lựa chọn **được chứng minh an toàn** mới có kết luận này, không phải mọi lựa chọn khả thi.
20. **Dùng so sánh thời gian bằng phép trừ int.** `end1-end2` có thể tràn. Dùng `Comparator.comparingInt(Interval::end)` để so sánh an toàn.

## 15. Bài tập có đáp án và lời giải

**Bài 1.** Với các hoạt động [1,4), [3,5), [0,6), [5,7), [8,11), [12,16), một cách chọn tối ưu theo số lượng là gì?

**Đáp án:** Chọn [1,4), [5,7), [8,11), [12,16) được **4** hoạt động. Sắp theo thời điểm kết thúc rồi chọn hoạt động phù hợp tiếp theo cho đúng lịch này.

**Bài 2.** Tại sao hoạt động kết thúc sớm nhất có thể thay thế hoạt động đầu tiên trong một lịch tối ưu?

**Đáp án:** Vì nó không kết thúc muộn hơn hoạt động đầu của lịch tối ưu, nên toàn bộ các hoạt động tiếp theo vốn bắt đầu sau hoạt động đầu cũng bắt đầu sau hoạt động greedy. Lịch vẫn khả thi, cùng số lượng, do đó vẫn tối ưu.

**Bài 3.** Sau khi chọn hoạt động g, bài toán con đúng là gì?

**Đáp án:** Chỉ còn những hoạt động có `start >= finish(g)`. Cần chọn **nhiều hoạt động không giao nhau nhất** trong tập ấy. Những hoạt động bắt đầu sớm hơn finish(g) không còn khả thi.

**Bài 4.** Nêu một bài toán có optimal substructure nhưng greedy dễ sai.

**Đáp án:** Đổi tiền với mệnh giá [1,3,4], số tiền 6. Greedy lấy 4+1+1 dùng 3 đồng, còn tối ưu 3+3 dùng 2 đồng. Có thể dùng DP theo số tiền còn lại.

**Bài 5.** Nếu hoạt động có trọng số, quy tắc kết thúc sớm nhất có còn chắc chắn tối ưu không?

**Đáp án:** Không. Hai hoạt động A=[0,2), value2 và B=[2,4), value2 cho tổng 4; hoạt động C=[0,4), value10 một mình cho tổng 10. Quy tắc không trọng số không giải bài toán trọng số.

**Bài 6.** Greedy chọn hoạt động kết thúc sớm có chi phí thời gian bao nhiêu nếu chưa sắp thứ tự đầu vào? Nếu đã sắp?

**Đáp án:** Chưa sắp: O(n log n) cho sort và O(n) cho quét, tổng O(n log n). Nếu đã có thứ tự tăng theo end: chỉ O(n) để quét chọn.

**Bài 7.** Hai khoảng [2,5) và [5,7) có thể cùng được chọn không?

**Đáp án:** Có, vì khoảng nửa mở kết thúc tại 5 không chứa thời điểm 5, và khoảng sau bắt đầu ở 5. Điều kiện `start2 >= end1` được thỏa.

**Bài 8.** Nếu đổi mục tiêu từ “nhiều hoạt động nhất” thành “tổng thời lượng lớn nhất”, có được giữ nguyên chứng minh greedy không?

**Đáp án:** Không. Bước thay hoạt động đầu của lịch tối ưu bằng hoạt động kết thúc sớm nhất có thể làm giảm tổng thời lượng dù lịch vẫn có cùng số lượng. Phải xây dựng cách giải/chứng minh khác cho mục tiêu mới.

**Bài 9.** Điều gì thiếu nếu một báo cáo chỉ ghi “bài toán có cấu trúc con tối ưu, nên chọn phương án tốt nhất ở mỗi bước”?

**Đáp án:** Thiếu **chứng minh greedy-choice property** cho lựa chọn cụ thể, thiếu mô tả trạng thái còn lại và cách ghép, cũng có thể thiếu kiểm tra tính khả thi. Cấu trúc con tối ưu một mình không quyết định được nên chọn nhánh nào.

**Bài 10.** Trong lập luận stays-ahead, vì sao `finish(g_j) <= finish(o_j)` là hữu ích?

**Đáp án:** Vì greedy kết thúc hoạt động thứ j không muộn hơn lịch tối ưu, nên còn ít nhất cùng mức cơ hội chọn hoạt động tiếp theo. Nếu lịch tối ưu chọn được hoạt động thứ j+1, hoạt động đó cũng tương thích với mốc kết thúc greedy thứ j; greedy không thể dừng sớm hơn trong khi còn ứng viên như vậy.

## Ghi nhớ

**Greedy-choice property** trả lời: *Có an toàn khi cố định lựa chọn tham lam ngay bây giờ không?* **Optimal substructure** trả lời: *Sau khi cố định lựa chọn ấy, phần còn lại có thể được giải tối ưu như một bài toán con rồi ghép lại không?*

Trong bài **chọn nhiều hoạt động không giao nhau nhất, không trọng số**, quy tắc **chọn hoạt động kết thúc sớm nhất** có thể chứng minh bằng trao đổi hoặc luôn đi trước. Sau mỗi lựa chọn, chỉ xét các hoạt động bắt đầu không trước thời điểm kết thúc vừa chọn. Một lần sắp xếp theo end và một lần quét tạo thuật toán O(n log n), với lõi chọn O(n). Nhưng **đổi mục tiêu hoặc đổi ràng buộc** có thể khiến cùng lựa chọn greedy sai; phải xây dựng lại chứng minh trước khi áp dụng.
