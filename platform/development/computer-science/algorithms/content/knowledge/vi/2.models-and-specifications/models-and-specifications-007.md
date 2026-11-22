# Đặc tả thứ tự, tính duy nhất và cách xử lý kết quả bằng nhau

## Mục tiêu học tập

Sau bài này, bạn có thể: (1) viết đặc tả sắp xếp hoặc lựa chọn kết quả có thứ tự rõ ràng; (2) phân biệt **thứ tự**, **bằng nhau theo khóa so sánh** và **bằng nhau của bản ghi**; (3) xác định kết quả có duy nhất hay tồn tại nhiều đáp án hợp lệ; (4) quy định chính sách xử lý trường hợp hòa (**tie**) như chọn phần tử đầu tiên, cuối cùng, tất cả, sắp xếp ổn định hoặc dùng khóa phụ; (5) hiện thực và kiểm thử hợp đồng này trong Java 17+.

## 1. Vì sao đặc tả phải nói rõ cả thứ tự và trường hợp bằng nhau?

Đề bài “sắp xếp các thí sinh theo điểm giảm dần” còn thiếu thông tin khi hai thí sinh có cùng điểm. Xét dãy bản ghi theo thứ tự nhập:

| Vị trí đầu vào (từ 0) | Mã thí sinh | Điểm |
| ---: | :--- | ---: |
| 0 | C | 90 |
| 1 | B | 95 |
| 2 | A | 95 |
| 3 | D | 85 |

Dãy `[B, A, C, D]` và dãy `[A, B, C, D]` đều thỏa yêu cầu **điểm giảm dần**. Nhưng chúng khác nhau về thứ tự hai bản ghi đồng điểm. Nếu người dùng kỳ vọng “giữ thứ tự nộp hồ sơ” thì chỉ dãy đầu là đúng; nếu yêu cầu “khi đồng điểm, mã tăng dần” thì chỉ dãy thứ hai là đúng.

Tương tự, câu “chọn thí sinh có điểm cao nhất” xác định **điểm tối đa là 95**, nhưng chưa xác định **bản ghi được chọn**: B hay A. Một thuật toán tùy tiện chọn B và một thuật toán khác chọn A có thể đều đúng với đặc tả còn lỏng. Đặc tả càng chặt, việc chứng minh, kiểm thử và tái lập kết quả càng rõ.

**Cần phân biệt:**

- **Bài toán:** xác định tập đầu vào hợp lệ và hậu điều kiện của đầu ra.
- **Quan hệ thứ tự:** quyết định hai phần tử nào đứng trước/sau, dựa vào khóa gì và chiều nào.
- **Quan hệ bằng nhau khi so sánh:** khi nào hai phần tử được coi là hòa theo tiêu chí đang xét.
- **Tính duy nhất:** hậu điều kiện có xác định đúng một đầu ra (theo khái niệm “giống nhau” đã chọn) hay chấp nhận nhiều đầu ra?
- **Quy tắc phá hòa (tie-break):** khi có nhiều lựa chọn cùng tốt, lấy lựa chọn nào và dựa trên thông tin gì?

Không thể suy ra một chính sách phá hòa chỉ từ từ khóa “lớn nhất”, “nhỏ nhất”, “xếp hạng” hay “sắp xếp”.

## 2. Đặc tả thứ tự: miền dữ liệu, khóa, chiều và phạm vi áp dụng

Để mô tả một thứ tự, hãy trả lời các câu hỏi sau.

1. **Đối tượng so sánh là gì?** Số nguyên, chuỗi, bản ghi, thời điểm, đoạn đường hay một trạng thái?
2. **Khóa so sánh là gì?** Điểm, độ ưu tiên, thời gian, độ dài, hoặc bộ nhiều trường?
3. **Chiều sắp xếp là gì?** Tăng dần hay giảm dần, và chiều của từng khóa trong thứ tự nhiều khóa?
4. **Khi khóa chính bằng nhau thì sao?** Chấp nhận đồng hạng, giữ thứ tự đầu vào, dùng khóa phụ hay trả tất cả?
5. **Dữ liệu biên được xử lý thế nào?** `null`, mảng rỗng, số âm, trùng khóa, trùng mã, `NaN`, chuỗi khác chữ hoa/thường?
6. **Đầu ra cần dạng gì?** Giá trị, một bản ghi, vị trí trong đầu vào, danh sách có thứ tự, tập không thứ tự hay hạng có đồng hạng?

Ví dụ hợp đồng thứ tự nhiều khóa:

> Mỗi thí sinh có `id` khác nhau và `score` là số nguyên. Sắp xếp **`score` giảm dần**; nếu bằng điểm thì **`id` tăng dần theo phép so sánh chuỗi đã quy định**. Không thay đổi bản ghi, không làm mất hay thêm bản ghi.

Viết dưới dạng quan hệ “x đứng trước y”:

- Nếu `score(x) > score(y)` thì x đứng trước y.
- Nếu `score(x) = score(y)` và `id(x) < id(y)` thì x đứng trước y.
- Vì giả định các `id` khác nhau, hai bản ghi khác nhau không thể hòa trên cả cặp khóa `(score, id)`.

Trong ví dụ mã một ký tự ASCII `A`, `B`, `C`, `D`, kết quả được xác định là `[A, B, C, D]`.

**Lưu ý về chuỗi:** “theo thứ tự chữ cái” chưa đủ cho dữ liệu đa ngôn ngữ. Cần quy định quy tắc đối chiếu chuỗi (lexicographic, không phân biệt hoa/thường, locale, chuẩn hóa Unicode...), vì các cách này có thể đưa ra thứ tự khác nhau. Với mã ASCII trong ví dụ, `String.compareTo` của Java là đủ; với tên người dùng đa ngôn ngữ nên chọn quy tắc sắp xếp phù hợp và kiểm thử riêng.

### Thứ tự toàn phần, đồng hạng và thứ tự bộ phận

- **Thứ tự toàn phần (total order):** hai phần tử bất kỳ đều so sánh được; với hai phần tử phân biệt, một phần tử đứng trước phần tử còn lại. Ví dụ: cặp khóa `(score giảm, id tăng)` khi `id` duy nhất.
- **Đồng hạng theo khóa:** nếu chỉ so sánh `score`, hai thí sinh B và A đồng hạng dù là hai bản ghi khác nhau. Quy tắc so sánh này sắp thứ tự giữa **các nhóm điểm**, nhưng chưa xác định thứ tự bên trong nhóm.
- **Thứ tự bộ phận (partial order):** có thể tồn tại hai phần tử không so sánh được, ví dụ hai công việc độc lập trong đồ thị phụ thuộc. Có nhiều thứ tự tô pô hợp lệ; muốn thứ tự đầu ra tái lập được, phải xác định cách chọn khi có nhiều công việc cùng sẵn sàng.

Hãy phân biệt “hai phần tử **có khóa so sánh bằng nhau**” với “hai phần tử **chính là cùng một đối tượng/giá trị**”. Một `Comparator` trả `0` có thể chỉ nói rằng khóa đang xét giống nhau, không chứng minh hai bản ghi có cùng `id` hoặc cùng nội dung.

## 3. “Tính duy nhất” đang nói đến điều gì?

Có ít nhất bốn ý nghĩa cần tách riêng:

| Loại duy nhất | Câu hỏi | Với dữ liệu ví dụ |
| --- | --- | --- |
| **Giá trị kết quả duy nhất** | Giá trị cực đại có xác định duy nhất không? | Giá trị lớn nhất là `95`, dù xuất hiện hai lần. |
| **Bản ghi kết quả duy nhất** | Có đúng một bản ghi đạt cực đại không? | Không: cả B và A đều có điểm `95`. |
| **Thứ tự đầu ra duy nhất** | Có đúng một hoán vị thỏa thứ tự yêu cầu không? | Chỉ khóa `score`: không; thêm `id` duy nhất làm khóa phụ: có. |
| **Quy trình thực thi xác định** | Với cùng đầu vào và môi trường giả định, chương trình có luôn chọn cùng kết quả không? | Có thể có, ví dụ duyệt từ trái sang phải chọn người đầu; nhưng điều đó không tự làm đáp án toán học trở nên duy nhất. |

**Thuật toán xác định** và **bài toán có nghiệm duy nhất** là hai tính chất khác nhau. Một chương trình có thể luôn chọn B vì gặp B trước, dù A cũng là đáp án tối ưu theo đặc tả chỉ xét điểm. Ngược lại, bài toán có đầu ra được xác định duy nhất vẫn có thể được giải bằng một thuật toán sử dụng bước ngẫu nhiên nhưng luôn trả đúng đầu ra ấy.

Nếu yêu cầu **mỗi mã thí sinh xuất hiện tối đa một lần**, đó là ràng buộc **tính duy nhất của dữ liệu đầu vào**. Nếu muốn **chỉ trả một thí sinh**, đó là ràng buộc **số lượng phần tử đầu ra**. Hai ràng buộc không đồng nghĩa; kể cả mã đầu vào duy nhất, vẫn có thể có nhiều người đồng điểm cao nhất.

Khi phải chứng minh đầu ra là duy nhất, cần nêu rõ tiêu chuẩn phân biệt: theo **giá trị**, theo **mã định danh**, theo **vị trí ban đầu**, hay theo **toàn bộ thứ tự của dãy kết quả**.

## 4. Các chính sách xử lý kết quả bằng nhau

Giả sử cần chọn thí sinh điểm cao nhất trong dãy `[C(90), B(95), A(95), D(85)]`. Các đặc tả sau cho ra các kết quả khác nhau:

| Chính sách | Quy định rõ trong đặc tả | Kết quả ví dụ |
| --- | --- | --- |
| **Bất kỳ nghiệm tối ưu** | Trả một bản ghi có điểm lớn nhất; được phép chọn bất kỳ khi hòa. | B **hoặc** A đều hợp lệ. |
| **Đầu tiên** | Khi hòa, chọn bản ghi xuất hiện sớm nhất theo thứ tự **đầu vào**. | B |
| **Cuối cùng** | Khi hòa, chọn bản ghi xuất hiện muộn nhất theo thứ tự **đầu vào**. | A |
| **Tất cả** | Trả mọi bản ghi đạt điểm lớn nhất, theo đúng thứ tự xuất hiện ban đầu. | `[B, A]` |
| **Khóa phụ** | Khi điểm hòa, chọn bản ghi có mã nhỏ nhất theo thứ tự mã đã quy định. | A |
| **Trả nhóm đồng hạng** | Trả nhóm điểm cao nhất và biểu diễn việc đồng hạng, không ép một người thắng. | Nhóm hạng 1 gồm B và A. |

**Trước tiên phải định nghĩa “bằng nhau”**: bằng điểm tuyệt đối, bằng điểm sau làm tròn theo quy tắc cụ thể, cùng mức ưu tiên, hay cùng tổng trọng số? Những quan hệ này khác nhau và có thể làm thay đổi cả tập phần tử hòa.

Khi đề bài nói “chọn phần tử đầu tiên”, cần nêu **đầu tiên ở đâu**: trong thứ tự nhập, trong thứ tự đã sắp xếp, trong danh sách sau lọc hay trong cấu trúc duyệt? Nếu dữ liệu lấy từ một cấu trúc không bảo đảm thứ tự duyệt, khái niệm “đầu tiên” không xác định nếu chưa đặt thêm quy tắc.

### Sắp xếp ổn định (stable sorting)

Một thuật toán sắp xếp được gọi là **ổn định** nếu các phần tử có khóa so sánh bằng nhau giữ nguyên thứ tự tương đối như trong đầu vào. Nếu B đứng trước A ở đầu vào và `compare(B, A) == 0`, sau khi sắp xếp ổn định B vẫn đứng trước A.

- **Chỉ điểm giảm dần + sắp xếp ổn định:** `[B, A, C, D]`.
- **Điểm giảm dần, sau đó mã tăng dần:** `[A, B, C, D]`. Đây là một **khóa phụ** chủ động đổi thứ tự B/A theo mã, nên không thể đồng thời đòi B đứng trước A chỉ vì B có trước trong đầu vào.

Ổn định không có nghĩa là “bất kỳ thuật toán nào cũng cho thứ tự giống nhau”, cũng không đồng nghĩa với “mọi phần tử bằng điểm đều đứng đúng một vị trí cố định bất kể thứ tự nhập”. Ổn định luôn có ý nghĩa **tương đối với thứ tự đầu vào và quan hệ so sánh cụ thể**.

Một đặc tả có thể yêu cầu “điểm giảm dần, hòa thì giữ thứ tự đầu vào” mà không cần quyết định bằng tên/mã. Hoặc chọn “điểm giảm dần, hòa thì mã tăng dần” để có kết quả chuẩn hóa độc lập với thứ tự đầu vào (với điều kiện mã duy nhất).

## 5. Viết hậu điều kiện chặt chẽ

Với bài **sắp xếp**, đầu ra phải thỏa **cả tính bảo toàn lẫn thứ tự**. Gọi đầu vào là `S = [s₀, …, sₙ₋₁]` và đầu ra là `T = [t₀, …, tₙ₋₁]`:

1. **Giữ số lượng và phần tử:** `T` phải là một hoán vị của `S`, giữ đúng số lần xuất hiện của từng bản ghi (không tự thêm, xóa, làm trùng).
2. **Đúng quan hệ thứ tự:** với mọi chỉ số liền kề `i` hợp lệ, `compare(T[i], T[i+1]) ≤ 0` theo comparator đã quy định.
3. **Đúng chính sách hòa:** nếu ổn định, hai bản ghi phân biệt mà comparator coi bằng nhau phải giữ thứ tự tương đối của đầu vào; nếu khóa phụ, thứ tự trong nhóm phải theo khóa phụ.
4. **Đúng hợp đồng dữ liệu:** quy định kích thước rỗng, bản ghi `null`, khóa thiếu, mã trùng và cách báo lỗi.

Với bài **chọn một cực đại**, hãy xác định:

- **Tiền điều kiện:** dãy có ít nhất một bản ghi hợp lệ hay chấp nhận dãy rỗng?
- **Điều kiện tối ưu:** bản ghi trả về thuộc dãy đầu vào và có `score` lớn hơn hoặc bằng điểm của mọi bản ghi.
- **Quy tắc hòa:** nếu có nhiều bản ghi cùng `score` tối đa, chọn đầu tiên, cuối cùng, mã nhỏ nhất, hay bất kỳ?
- **Trường hợp không có đáp án:** ném ngoại lệ, trả `Optional.empty()`, trả danh sách rỗng, hay dùng một quy ước khác? Không âm thầm dùng `null` khi hợp đồng không cho phép.

Ví dụ đặc tả hoàn chỉnh, đủ để kiểm thử:

> **SORT-CANDIDATES** — Input: danh sách độ dài `n ≥ 0` gồm các bản ghi không `null`, mỗi bản ghi có `id` là chuỗi ASCII không `null` và **khác nhau trên toàn danh sách**, `score` là số nguyên Java. Output: một danh sách mới chứa mỗi bản ghi đúng một lần, sắp theo `score` giảm dần và khi bằng điểm thì theo `id` tăng dần theo `String.compareTo`. Danh sách rỗng trả danh sách rỗng. Không thay đổi đầu vào. Với các giả định này, thứ tự đầu ra là duy nhất theo `id`.

> **FIRST-MAX-CANDIDATE** — Input: danh sách không rỗng theo cùng miền trên. Output: bản ghi có điểm lớn nhất, chọn bản ghi có **vị trí đầu vào nhỏ nhất** nếu hòa. Nếu danh sách `null` hoặc rỗng thì ném `IllegalArgumentException`; mỗi phần tử đầu vào và `id` phải hợp lệ theo tiền điều kiện.

Đây là hai **bài toán khác nhau**; đừng giả định đầu ra FIRST-MAX là bản ghi đầu của SORT-CANDIDATES khi SORT dùng khóa phụ theo `id`. Trong ví dụ, FIRST-MAX trả B, còn bản ghi đầu sau SORT-CANDIDATES là A.

## 6. Giả mã: thay dấu so sánh là thay hợp đồng

Thuật toán chọn cực đại đầu tiên (dãy có ít nhất một phần tử):

```text
FIRST_MAX(items):
    best ← items[0]
    for i từ 1 đến length(items) - 1:
        if score(items[i]) > score(best):
            best ← items[i]
    return best
```

**Bất biến:** sau khi duyệt đoạn đầu dãy, `best` là bản ghi có điểm lớn nhất trong đoạn đó; nếu có nhiều bản ghi đồng điểm lớn nhất thì `best` có vị trí đầu tiên trong đoạn. Dùng so sánh **`>`** bảo toàn người xuất hiện trước khi bằng điểm.

Nếu yêu cầu bản ghi cuối cùng cùng điểm cao nhất, điều kiện cập nhật đổi thành **`>=`**, khiến bản ghi xuất hiện sau thay bản ghi trước khi hòa. Thay một ký hiệu trong chương trình có thể đổi **nghĩa đầu ra của thuật toán**, dù điểm được trả về vẫn giống nhau.

Muốn **tất cả** bản ghi đạt điểm tối đa, có thể duyệt một lần để tìm giá trị tối đa, rồi duyệt lại để thu thập tất cả bản ghi có điểm ấy vào danh sách theo thứ tự đầu vào. Nếu đầu vào có các bản ghi trùng nội dung nhưng khác vị trí và đặc tả yêu cầu giữ cả hai lần xuất hiện, danh sách kết quả phải giữ đúng số lần xuất hiện.

## 7. Chương trình Java 17+ có thể biên dịch và chạy

Tệp hoàn chỉnh `TiePolicyDemo.java` bên dưới minh họa bốn hợp đồng trên **cùng một đầu vào**: sắp xếp ổn định theo điểm, sắp xếp theo điểm và mã, lấy cực đại đầu tiên, cuối cùng và tất cả. Ví dụ giả định mỗi phần tử và mỗi `id` đều không `null`, các `id` là duy nhất, và chỉ sử dụng mã ASCII.

```java
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.stream.Collectors;

public class TiePolicyDemo {
    record Candidate(String id, int score) {}

    private static void requireNonEmpty(List<Candidate> items) {
        if (items == null || items.isEmpty()) {
            throw new IllegalArgumentException(
                    "items must contain at least one candidate");
        }
    }

    static Candidate firstMax(List<Candidate> items) {
        requireNonEmpty(items);
        Candidate best = items.get(0);
        for (int i = 1; i < items.size(); i++) {
            Candidate current = items.get(i);
            if (current.score() > best.score()) {
                best = current;
            }
        }
        return best;
    }

    static Candidate lastMax(List<Candidate> items) {
        requireNonEmpty(items);
        Candidate best = items.get(0);
        for (int i = 1; i < items.size(); i++) {
            Candidate current = items.get(i);
            if (current.score() >= best.score()) {
                best = current;
            }
        }
        return best;
    }

    static List<Candidate> allMax(List<Candidate> items) {
        int highest = firstMax(items).score();
        List<Candidate> result = new ArrayList<>();
        for (Candidate current : items) {
            if (current.score() == highest) {
                result.add(current);
            }
        }
        return result;
    }

    static String ids(List<Candidate> items) {
        return items.stream()
                .map(Candidate::id)
                .collect(Collectors.joining(", "));
    }

    public static void main(String[] args) {
        List<Candidate> input = List.of(
                new Candidate("C", 90),
                new Candidate("B", 95),
                new Candidate("A", 95),
                new Candidate("D", 85));

        // Tuong duong comparator khi cung diem; List.sort on dinh.
        List<Candidate> stable = new ArrayList<>(input);
        stable.sort(Comparator.comparingInt(Candidate::score).reversed());

        // Khoa phu ID de tao mot thu tu xac dinh duy nhat.
        List<Candidate> canonical = new ArrayList<>(input);
        canonical.sort(
                Comparator.comparingInt(Candidate::score)
                        .reversed()
                        .thenComparing(Candidate::id));

        System.out.println("Input: " + ids(input));
        System.out.println("Stable sort: " + ids(stable));
        System.out.println("Total order: " + ids(canonical));
        System.out.println("First max: " + firstMax(input).id());
        System.out.println("Last max: " + lastMax(input).id());
        System.out.println("All max: " + ids(allMax(input)));
    }
}
```

Chạy trong thư mục chứa tệp, với JDK 17 hoặc mới hơn:

```bash
javac TiePolicyDemo.java
java TiePolicyDemo
```

Đầu ra chuẩn **chính xác**:

```text
Input: C, B, A, D
Stable sort: B, A, C, D
Total order: A, B, C, D
First max: B
Last max: A
All max: B, A
```

Giải thích các lựa chọn quan trọng:

- `List.sort` với `Comparator` trên kiểu đối tượng là **ổn định** theo hợp đồng Java: khi chỉ so sánh `score`, B tiếp tục đứng trước A.
- `thenComparing(Candidate::id)` đặt ra **khóa phụ**. B và A không còn được coi là bằng nhau bởi comparator kết hợp: A đứng trước B vì mã tăng dần. Với `id` duy nhất, ta có một thứ tự toàn phần của các bản ghi theo hai khóa.
- `firstMax` dùng `>` để giữ phần tử đồng điểm gặp trước; `lastMax` dùng `>=` để giữ phần tử gặp sau.
- `allMax` giữ **tất cả bản ghi đạt điểm tối đa**, và thứ tự thu thập giống đầu vào.
- Việc sao chép bằng `new ArrayList<>(input)` bảo vệ thứ tự của danh sách đầu vào. Ví dụ không thay đổi các `Candidate` bất biến.
- `Comparator.comparingInt(...).reversed()` tránh lỗi tràn số có thể xảy ra nếu tự viết phép so sánh `return b.score() - a.score();` với các điểm nguyên rất lớn/trái dấu.

Đừng nhầm thứ tự kết quả được quyết định bởi khóa phụ với tính ổn định. Ngay cả một phép sắp xếp ổn định cũng sẽ đưa A lên trước B khi comparator yêu cầu mã tăng dần.

## 8. Làm sao chứng minh hợp đồng đã được thực hiện?

### Chọn cực đại có quy tắc hòa

Với `firstMax`, sau mỗi bước duyệt, bất biến là: **`best` có điểm tối đa trong đoạn đã xem, và là phần tử xuất hiện sớm nhất trong các phần tử cùng đạt mức tối đa đó**.

- **Ban đầu:** đoạn đã xem chỉ có phần tử đầu tiên; bất biến đúng.
- **Bước lặp:** nếu điểm mới lớn hơn, phần tử mới trở thành cực đại duy nhất của đoạn đã xem; nếu bằng hoặc nhỏ hơn, giữ `best` để bảo toàn vị trí đầu tiên.
- **Kết thúc:** toàn bộ dãy được xét; `best` thỏa hậu điều kiện. Vòng lặp đi qua đúng `n - 1` vị trí còn lại nên dừng với mọi đầu vào hữu hạn hợp lệ.

Với `lastMax`, thay tính “xuất hiện sớm nhất” bằng “xuất hiện muộn nhất”, vì gặp phần tử đồng điểm mới thì cập nhật. Đây là lập luận về **cả tối ưu lẫn cách phá hòa**, không chỉ về giá trị điểm.

### Sắp xếp có quy tắc hòa

Cần kiểm tra đồng thời:

- **Không mất dữ liệu:** mỗi bản ghi đầu vào xuất hiện đúng một lần ở đầu ra.
- **Thứ tự đúng:** mọi cặp kề nhau thỏa comparator được chọn.
- **Hòa đúng chính sách:** nếu chỉ so sánh điểm và yêu cầu ổn định thì vị trí tương đối của các bản ghi đồng điểm phải được giữ; nếu có khóa phụ, cặp đồng điểm được xếp theo khóa phụ.
- **Giả định cần thiết:** nếu chứng minh kết quả là thứ tự duy nhất dựa vào `id` thì phải bảo đảm `id` không trùng; nếu hai bản ghi có cùng cả `score` lẫn `id` thì comparator không phân biệt chúng.

Kiểm thử vài ví dụ giúp phát hiện vi phạm. Để bảo đảm thuật toán sắp xếp thực sự đúng trên mọi đầu vào hợp lệ, còn cần dựa vào tính đúng của thuật toán sắp xếp được dùng và hợp đồng của comparator; kiểm thử đơn lẻ không thay thế lập luận tính đúng.

## 9. Hợp đồng Comparator và các cạm bẫy khi hòa

Trong Java, `Comparator<T>` trả một số âm, `0`, hoặc số dương khi đối tượng thứ nhất lần lượt đứng trước, bằng hoặc đứng sau đối tượng thứ hai theo **quy tắc so sánh**. Không nên dựa vào độ lớn tuyệt đối của giá trị trả về.

Một comparator dùng cho sắp xếp phải nhất quán, đặc biệt:

- **Đảo dấu đối xứng:** dấu của `compare(a,b)` ngược với dấu của `compare(b,a)`.
- **Bắc cầu:** nếu a đứng trước b và b đứng trước c thì a phải đứng trước c.
- **Nhất quán khi coi bằng nhau:** nếu `compare(a,b) == 0` thì a và b phải có quan hệ so sánh như nhau với mọi đối tượng c theo quy tắc tương ứng.

Với comparator chỉ xét `score`, `compare(B,A) == 0` dù `B.id` khác `A.id`. Điều đó **không có nghĩa** `B.equals(A)` là true. Khi dùng `TreeSet` hoặc `TreeMap`, hai phần tử/khóa mà comparator trả `0` được coi là một khóa theo quan hệ thứ tự của cấu trúc, nên có thể làm mất bản ghi mong muốn nếu chỉ dùng `score` làm khóa. Nếu dữ liệu cần chứa nhiều bản ghi cùng điểm, không chọn comparator chỉ theo điểm cho một `TreeSet<Candidate>` mà lại kỳ vọng giữ đủ mọi thí sinh khác mã.

Một số lỗi cụ thể:

1. **Bỏ quy tắc hòa:** “sắp điểm giảm dần” nhưng test lại đòi một thứ tự đồng điểm duy nhất mà đề bài chưa quy định.
2. **Lẫn khóa và định danh:** coi hai bản ghi bằng nhau chỉ vì có cùng `score`.
3. **Viết comparator bằng phép trừ:** `b.score() - a.score()` có thể tràn `int`; nên dùng `Integer.compare(b.score(), a.score())` hoặc builder như trong ví dụ.
4. **Sắp xếp rồi dùng “vị trí đầu tiên” mà không nói vị trí thuộc dãy nào:** vị trí sau sắp xếp khác vị trí đầu vào.
5. **Dựa vào thứ tự không bảo đảm của cấu trúc:** `HashMap` không bảo đảm thứ tự duyệt; `PriorityQueue` không hứa trả các phần tử có cùng mức ưu tiên theo thứ tự thêm vào. Nếu cần FIFO khi hòa, thêm số thứ tự tăng dần làm khóa phụ.
6. **Bỏ qua ngoại lệ của miền dữ liệu:** `null` hoặc `NaN` cần quy tắc riêng, không tự coi là giá trị bình thường theo mọi phép so sánh.
7. **So sánh gần bằng bằng ngưỡng tùy tiện:** quy tắc “`|a-b| < ε` thì coi bằng nhau” có thể **không bắc cầu** (ví dụ `a=0`, `b=0.6`, `c=1.2`, `ε=1`: a gần b và b gần c nhưng a không gần c); dùng trực tiếp làm comparator sắp xếp có thể vi phạm hợp đồng. Nếu nghiệp vụ cần nhóm điểm gần nhau, hãy đặc tả bước phân nhóm/làm tròn hoặc bộ khóa có tính bắc cầu trước khi sắp xếp.

Đối với thuật toán có ràng buộc phụ thuộc (ví dụ lập lịch theo DAG), các phần tử “không so sánh được” không nên bị tùy tiện gán nghĩa “bằng nhau”. Cần nói rõ chọn một thứ tự tô pô bất kỳ hay một thứ tự tô pô chuẩn hóa bằng khóa phụ ở mỗi bước.

## 10. Chi phí và ảnh hưởng của quy tắc hòa

Các phương án đều có thể đúng, nhưng chi phí và bộ nhớ khác nhau:

| Yêu cầu | Một hướng thực hiện | Chi phí điển hình |
| --- | --- | --- |
| Chọn cực đại đầu tiên/cuối cùng | Duyệt một lần, cập nhật bằng `>`/`>=` | `O(n)` thời gian, `O(1)` bộ nhớ phụ |
| Lấy tất cả bản ghi cùng cực đại | Một lượt tìm cực đại, một lượt thu thập | `O(n)` thời gian, `O(k)` đầu ra với k bản ghi hòa |
| Sắp xếp ổn định theo một khóa | Thuật toán sắp xếp ổn định, comparator theo khóa | `O(n log n)` phép so sánh trong cách triển khai thông dụng |
| Sắp xếp theo khóa chính và khóa phụ | Sắp xếp bằng comparator kết hợp | Thường `O(n log n)` phép so sánh; tính cả chi phí so sánh khóa phụ khi cần |
| Chọn một bản ghi cực đại theo khóa phụ | Duyệt một lượt với phép so sánh hai khóa | `O(n)` thời gian, `O(1)` bộ nhớ phụ nếu chỉ giữ một bản ghi |

`n` là số bản ghi và `k` là số bản ghi đạt cực đại. Nếu mã là chuỗi dài, so sánh mã không nhất thiết có chi phí hằng số; phân tích thực tế cần xét độ dài và quy tắc đối chiếu chuỗi. Chương trình Java ở mục 7 còn sao chép danh sách để giữ nguyên đầu vào, nên phần sao chép dùng thêm `O(n)` bộ nhớ. Chi phí lưu danh sách đầu ra `allMax` tăng theo `k`.

**Không cần sắp xếp toàn bộ dãy chỉ để tìm một cực đại có quy tắc hòa.** Có thể duyệt tuyến tính và so sánh cặp khóa. Hãy chọn cách giải theo đầu ra thực sự cần: **một** phần tử, **tất cả** phần tử hòa, **nhóm đồng hạng**, hay **danh sách đã sắp xếp**.

## 11. Kiểm thử các trường hợp dễ bị bỏ sót

| Trường hợp | Điều cần xác nhận |
| --- | --- |
| Dãy rỗng | Sắp xếp trả dãy rỗng; FIRST-MAX xử lý theo quy tắc đã định, ví dụ ném `IllegalArgumentException`. |
| Một phần tử | Phần tử ấy được giữ nguyên; không có xung đột tie. |
| Hai điểm cao nhất bằng nhau | First/last/all/khóa phụ cho kết quả theo chính sách; không tự chọn ngẫu nhiên khi đặc tả không cho phép. |
| Mọi điểm bằng nhau | Stable sort giữ toàn bộ thứ tự đầu vào; khóa phụ có thể sắp xếp lại; allMax trả đủ n bản ghi. |
| Điểm âm và cực trị nguyên | So sánh đúng với cả số âm, `Integer.MIN_VALUE` và `Integer.MAX_VALUE`; không dùng phép trừ tràn số. |
| Mã trùng hoặc mã `null` | Đầu vào ngoài miền giả định bị từ chối theo hợp đồng; nếu muốn hỗ trợ phải bổ sung quy tắc. |
| Hoán vị đầu vào nhưng cùng các bản ghi | Khóa phụ `id` duy nhất cho thứ tự chuẩn hóa giống nhau; stable sort chỉ theo `score` có thể đổi thứ tự trong nhóm đồng điểm. |
| Bản ghi có khóa bằng nhau nhưng định danh khác | Cấu trúc phải giữ được cả hai nếu đặc tả yêu cầu đa tập bản ghi; không vô tình mất bản ghi vì comparator trả `0`. |

Có thể viết các **thuộc tính kiểm thử** (property-based tests) cho sắp xếp: độ dài đầu ra bằng đầu vào; mỗi `id` xuất hiện đúng một lần; điểm không tăng từ trái sang phải; nếu điểm kề nhau bằng nhau thì `id` không giảm khi có khóa phụ; nếu dùng stable sort thì thứ tự tương đối các bản ghi bằng điểm được giữ. Với FIRST-MAX, kiểm tra điểm của kết quả là cực đại và không có bản ghi cùng điểm nào đứng trước kết quả trong đầu vào.

## 12. Bài tập tự kiểm tra

**Bài 1.** Cho `[(X, 7), (Z, 9), (Y, 9), (W, 7)]` theo thứ tự nhập. Hãy viết đầu ra khi (a) sắp điểm giảm dần ổn định, (b) điểm giảm dần rồi mã tăng dần, (c) chỉ chọn cực đại đầu tiên, (d) trả tất cả cực đại theo thứ tự nhập.

**Bài 2.** Một API trả “vị trí của bản ghi điểm cao nhất” nhưng không quy định cách xử lý đồng điểm. Hãy nêu hai cách sửa đặc tả để kết quả kiểm thử có thể đối chiếu chính xác.

**Bài 3.** Có hai bản ghi khác mã cùng điểm. Nếu comparator chỉ so sánh điểm, `compare(a,b) == 0` có cho phép kết luận hai bản ghi là một không? Điều gì có thể xảy ra khi đưa chúng vào `TreeSet` dùng comparator ấy?

**Bài 4.** Tại sao một quy tắc phá hòa bằng vị trí đầu vào có thể cho kết quả khác nhau khi hai hệ thống nhận cùng tập bản ghi nhưng thứ tự nhập khác nhau? Làm thế nào để đầu ra chuẩn hóa giữa các hệ thống?

**Đáp án gợi ý:**

1. (a) `[Z, Y, X, W]`; (b) `[Y, Z, W, X]` (trong nhóm điểm 7, W đứng trước X theo mã); (c) Z; (d) `[Z, Y]`.
2. Ví dụ “lấy vị trí đầu tiên trong dãy gốc khi cùng điểm” hoặc “lấy vị trí có mã nhỏ nhất theo thứ tự mã quy định khi cùng điểm”; đồng thời quy định dãy rỗng và cách đếm vị trí.
3. Không; comparator chỉ nói hai điểm bằng nhau. `TreeSet` có thể coi chúng là cùng một khóa so sánh và chỉ giữ một bản ghi.
4. Vì chỉ số đầu vào thay đổi theo thứ tự nhận. Muốn độc lập với thứ tự nhập, dùng một khóa phụ ổn định, duy nhất, có quy tắc so sánh thống nhất, chẳng hạn mã định danh duy nhất.

## Ghi nhớ

**Đặc tả thứ tự** phải nêu đối tượng, khóa, chiều và quan hệ so sánh. **Tính duy nhất** phải chỉ rõ duy nhất của giá trị, bản ghi hay thứ tự đầu ra. **Khi hòa**, phải nói rõ chấp nhận bất kỳ, chọn đầu/cuối, trả tất cả, giữ thứ tự tương đối bằng sắp xếp ổn định, hay dùng khóa phụ. Chỉ khi những điều này đã rõ ta mới có thể chứng minh thuật toán đúng, viết comparator hợp lệ và tạo bộ kiểm thử không mơ hồ.
