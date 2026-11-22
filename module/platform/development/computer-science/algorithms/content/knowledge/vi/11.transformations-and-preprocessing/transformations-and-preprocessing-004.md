# Lập chỉ mục bằng băm để giảm tra cứu lặp lại

**Lập chỉ mục bằng băm** (*hash-based indexing*) là kỹ thuật **tiền xử lý** tập dữ liệu thành một cấu trúc ánh xạ từ **khóa tra cứu** tới vị trí hoặc nhóm bản ghi mang khóa đó. Thay vì quét lại toàn bộ dữ liệu cho mỗi câu hỏi, chương trình trả lời bằng cách tra khóa trong **bảng băm** (*hash table*, thường là HashMap trong Java), rồi chỉ xử lý các bản ghi liên quan.

Đây là một sự đánh đổi có chủ đích: **trả chi phí xây dựng chỉ mục một lần và dùng thêm bộ nhớ để giảm thời gian của nhiều lượt truy vấn về sau**. Với \(n\) bản ghi, \(q\) truy vấn và phép băm có thời gian kỳ vọng hằng số, quét tuyến tính mất cỡ \(O(qn)\), còn tạo chỉ mục một lần rồi tra cứu có thể tốn khoảng \(O(n+q+\sum t_j)\), trong đó \(t_j\) là số kết quả mà truy vấn thứ \(j\) thật sự phải trả về.

Điểm quan trọng không chỉ là dùng HashMap. Cần xác định **khóa là gì**, **một khóa có bao nhiêu bản ghi**, **chỉ mục chứa ID, chỉ số hay bản ghi**, **dữ liệu có thay đổi sau khi lập chỉ mục không**, và **khi nào chi phí tiền xử lý thực sự đáng giá**.

## 1. Bài toán trước khi có chỉ mục

Giả sử có danh sách log sự kiện theo thứ tự thời gian, mỗi bản ghi gồm:

- **userId**: định danh người dùng, dùng làm khóa tra cứu.
- **action**: hành động đã xảy ra.

Ví dụ dữ liệu:

| Vị trí trong danh sách | userId | action |
|---:|---|---|
| 0 | u-10 | login |
| 1 | u-20 | view |
| 2 | u-10 | purchase |
| 3 | u-30 | logout |
| 4 | u-20 | purchase |

Câu hỏi: **“Tìm toàn bộ sự kiện của userId = u-10.”**

Cách đơn giản nhất là quét từ đầu tới cuối, so sánh userId ở mỗi hàng, rồi gom các bản ghi khớp. Kết quả là hai bản ghi ở vị trí **0 và 2**, theo đúng thứ tự nguồn:

~~~text
[u-10:login, u-10:purchase]
~~~

Một lần quét cần kiểm tra tới \(n\) bản ghi, tức \(O(n)\) phép kiểm tra khóa. Nếu có \(q\) truy vấn độc lập mà mỗi lần đều bắt đầu quét lại danh sách, phần công việc tìm kiếm có thể tăng thành **\(O(qn)\)**. Ví dụ dữ liệu gồm một triệu bản ghi và hàng chục nghìn câu hỏi lặp lại về userId: quét từ đầu cho mọi câu hỏi sẽ thực hiện nhiều lần những phép so sánh giống nhau.

**Nhưng không phải bài toán nào cũng cần chỉ mục.** Nếu dữ liệu rất nhỏ, chỉ có một truy vấn, hoặc phải đọc toàn bộ bản ghi bất kể khóa, một lần quét có thể đơn giản và nhanh hơn việc cấp phát HashMap.

## 2. Chỉ mục thực chất lưu điều gì?

Chỉ mục băm dùng ý tưởng:

\[
index[key] \longrightarrow \text{thông tin giúp định vị kết quả}.
\]

Tùy hợp đồng truy vấn, phần giá trị được lưu có thể là:

| Nhu cầu truy vấn | Dạng chỉ mục | Bộ nhớ/ý nghĩa |
|---|---|---|
| Kiểm tra khóa có tồn tại không | HashSet<Key> | Mỗi khóa phân biệt xuất hiện một lần |
| Một khóa ứng với đúng một bản ghi | HashMap<Key, Record> | Khóa ánh xạ tới bản ghi |
| Một khóa có nhiều bản ghi | HashMap<Key, List<Record>> | Giữ toàn bộ bản ghi mang khóa |
| Dữ liệu nằm trong danh sách cố định | **HashMap<Key, List<Integer>>** | Giữ các **vị trí** trong danh sách nguồn |
| Đếm số bản ghi của mỗi khóa | HashMap<Key, Integer> | Lưu **tần suất**, không cần giữ từng bản ghi |
| Cần tổng/số liệu gộp theo khóa | HashMap<Key, Aggregate> | Tiền xử lý sẵn các thống kê phù hợp |

**Không thể tùy ý dùng Map<Key, Record> nếu khóa không duy nhất.** Mỗi lần put cùng khóa thường thay thế giá trị trước đó, làm mất những bản ghi cũ. Với ví dụ, nếu đưa các sự kiện userId = u-10 vào một Map<String, Event> bằng put liên tiếp, bản ghi purchase có thể ghi đè bản ghi login. Chỉ mục đó không đáp ứng yêu cầu “tất cả sự kiện”.

Bài học sử dụng **Map<String, List<Integer>>**: khóa là userId, giá trị là danh sách vị trí khớp trong bảng nguồn. Dạng này giữ được dữ liệu nguồn tại một nơi; chỉ mục chỉ chứa các tham chiếu vị trí.

Với bảng ví dụ, cấu trúc logic thu được là:

~~~text
u-10 -> [0, 2]
u-20 -> [1, 4]
u-30 -> [3]
~~~

Trật tự ba **khóa** khi duyệt HashMap không được bảo đảm. Tuy nhiên, **thứ tự các vị trí trong từng danh sách** là thứ tự xuất hiện ở nguồn nếu xây chỉ mục bằng cách đi từ hàng đầu tới hàng cuối và thêm vị trí vào cuối danh sách.

## 3. Từ quét tuyến tính sang tiền xử lý một lần

Quy trình xây dựng chỉ mục từ danh sách nguồn ổn định gồm:

1. Tạo một HashMap rỗng, từ khóa tới danh sách chỉ số.
2. Duyệt lần lượt từng bản ghi ở vị trí **i = 0..n-1**.
3. Lấy khóa key từ bản ghi.
4. Nếu key chưa có trong Map, tạo danh sách vị trí rỗng cho key.
5. Thêm i vào **cuối** danh sách vị trí của key.
6. Sau khi duyệt xong, giữ Map lại để phục vụ nhiều truy vấn.

Mã giả:

~~~text
buildIndex(rows):
    index = HashMap rỗng
    for i = 0 .. n-1:
        key = rows[i].userId
        if key chưa có trong index:
            index[key] = danh sách rỗng
        index[key].append(i)
    return index
~~~

Trong Java, có thể rút gọn bước tìm/tạo nhóm bằng **computeIfAbsent**:

~~~java
index.computeIfAbsent(key, ignored -> new ArrayList<>()).add(i);
~~~

Biểu thức đó có nghĩa: lấy danh sách đang gắn với key; nếu chưa có giá trị tương ứng thì tạo một ArrayList mới; sau đó thêm chỉ số i vào danh sách. Trong ví dụ này **không lưu giá trị null** trong Map, nên không có sự nhập nhằng giữa khóa không tồn tại và khóa có giá trị null.

**Điểm quan trọng về thời gian:** HashMap không có gì thần kỳ giúp “bỏ qua” dữ liệu ban đầu. Bước xây dựng vẫn phải **đọc qua n bản ghi ít nhất một lần**. Lợi ích đến từ việc **không cần lặp lại bước quét đó cho mỗi câu hỏi**.

## 4. Mô phỏng việc tạo chỉ mục

Với năm bản ghi ở phần 1, trạng thái các nhóm sau mỗi bước như sau:

| i | Khóa đang đọc | Nhóm được cập nhật | Trạng thái logic sau bước đó |
|---:|---|---|---|
| 0 | u-10 | Tạo nhóm u-10, thêm 0 | u-10 → [0] |
| 1 | u-20 | Tạo nhóm u-20, thêm 1 | u-10 → [0]; u-20 → [1] |
| 2 | u-10 | Thêm 2 vào nhóm cũ | u-10 → [0,2]; u-20 → [1] |
| 3 | u-30 | Tạo nhóm u-30, thêm 3 | u-30 → [3] và các nhóm trước |
| 4 | u-20 | Thêm 4 vào nhóm cũ | u-10 → [0,2]; u-20 → [1,4]; u-30 → [3] |

Sau khi xây chỉ mục, để tìm userId u-10:

1. Tra **index.get("u-10")** và nhận **[0,2]** (kỳ vọng chi phí tra khóa gần hằng số với bảng băm phân bố tốt).
2. Đọc **rows.get(0)** và **rows.get(2)** để tạo kết quả.
3. Trả các bản ghi khớp.

Với userId u-99 không tồn tại, không cần quét tất cả bản ghi; Map cho biết không có nhóm. Hợp đồng ví dụ trả **danh sách rỗng**, không phải null.

Khi trả **toàn bộ** \(t\) bản ghi khớp, ngay cả truy vấn dùng chỉ mục cũng phải mất tối thiểu thời gian liên quan tới **\(t\)** để đọc/tạo/ghi những bản ghi kết quả. Vì vậy, độ phức tạp cho một truy vấn trả đầy đủ dữ liệu thường là **\(O(1+t)\) kỳ vọng**, không phải luôn O(1).

## 5. Bất biến và chứng minh tính đúng

Giả sử danh sách nguồn không thay đổi sau khi xây chỉ mục. Sau khi xử lý đúng i phần tử đầu, bất biến là:

> Với mọi khóa key đã xuất hiện, index[key] chứa **đúng và đủ** các vị trí j trong đoạn \([0,i)\) mà rows[j].userId bằng key, **theo thứ tự tăng dần của j**.

**Cơ sở.** Trước khi đọc phần tử nào, Map rỗng. Không có chỉ số hợp lệ trong đoạn [0,0), nên bất biến đúng.

**Bước quy nạp.** Giả sử bất biến đúng sau i phần tử. Khi đọc rows[i] có khóa key, thuật toán chỉ thêm vị trí i vào cuối nhóm key (tạo nhóm nếu cần). Mọi nhóm khác giữ nguyên. Vì i là vị trí mới lớn hơn tất cả vị trí đã duyệt, nhóm key vẫn được sắp tăng theo vị trí và nhận chính xác phần tử vừa đọc. Không có bản ghi nào khác bị thêm nhầm.

**Kết luận.** Sau n bước, với mỗi khóa key, danh sách chỉ số chứa **tất cả và chỉ những vị trí** có khóa bằng key trong toàn bộ nguồn. Lấy rows[position] cho từng vị trí trong danh sách trả đúng toàn bộ kết quả, không mất bản ghi và không tạo thêm bản ghi không khớp.

Chứng minh này dựa trên việc **khóa có ý nghĩa nhất quán**, **không sửa các bản ghi/vị trí nguồn sau lúc xây**, và **mỗi lần thêm một vị trí đúng nhóm**. Nếu những giả thiết đó thay đổi, phải cập nhật hoặc xây lại chỉ mục.

## 6. Tại sao HashMap giúp tra cứu nhanh?

HashMap dựa trên một **hàm băm** (*hash function*) chuyển khóa thành thông tin để chọn vùng lưu trữ thích hợp. Khi truy vấn cùng khóa, cấu trúc dùng hàm băm và kiểm tra tương đương để tìm mục tương ứng, thay vì duyệt tất cả các khóa từng lưu.

Một số khái niệm cần phân biệt:

- **hashCode:** giá trị băm do khóa cung cấp theo hợp đồng Java.
- **equals:** phép xác định hai khóa có được coi là bằng nhau hay không.
- **Bucket:** nhóm/vị trí lưu trữ ứng với kết quả phân bố băm; các khóa khác nhau vẫn có thể cùng bucket.
- **Collision (va chạm):** hai khóa khác nhau có băm hoặc bucket trùng nhau; HashMap phải xử lý bằng cơ chế nội bộ, không thể giả định hashCode khác nhau cho mọi khóa.
- **Load factor và resize:** khi số phần tử tăng, bảng có thể được mở rộng/rehash. Chi phí một lần mở rộng có thể lớn, nhưng khi phân tích nhiều lần thêm với giả định băm tốt thì chi phí trung bình khấu hao thường gần hằng số trên một lần thêm.

Với khóa có hashCode phân bố tốt và phép băm/so sánh có chi phí xem như O(1), thao tác tra khóa trong bảng băm có **thời gian kỳ vọng O(1)**. Đây là kỳ vọng/trung bình dưới các giả thiết thích hợp, **không phải cận trên O(1) chắc chắn cho mọi khóa và mọi đầu vào**. Va chạm nặng, phép tính hash/equals đắt hoặc hành vi bị khai thác có thể làm hiệu năng giảm. Java HashMap hiện đại có những biện pháp giảm tác động của va chạm như chuyển một số bucket sang cấu trúc cây, nhưng không nên suy ra hiệu năng luôn hằng số ở trường hợp xấu nhất.

**Hợp đồng quan trọng của khóa Java:** nếu **x.equals(y)** trả true, thì **x.hashCode()** phải bằng **y.hashCode()**. Nếu vi phạm, HashMap có thể không tìm lại được khóa tương đương. Đối với khóa là String, Java đã triển khai equals/hashCode phù hợp; với khóa tự định nghĩa, cần triển khai nhất quán. Những trường dùng trong equals/hashCode **không nên thay đổi khi đối tượng đang làm khóa trong Map**.

## 7. Java 17+: từ nhiều lần quét sang chỉ mục khóa → vị trí

Chương trình hoàn chỉnh minh họa một danh sách **Event(userId, action)**. Hàm buildIndex duyệt nguồn một lần, lưu Map từ userId tới các **vị trí**. Hàm findByScan quét nguồn cho mỗi truy vấn. Hàm findByIndex chỉ đọc danh sách vị trí của khóa cần tìm rồi lấy các bản ghi tương ứng.

Tạo tệp **HashIndexDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;

public class HashIndexDemo {
    record Event(String userId, String action) {}

    static Map<String, List<Integer>> buildIndex(List<Event> rows) {
        Objects.requireNonNull(rows, "rows");
        Map<String, List<Integer>> index = new HashMap<>();

        for (int i = 0; i < rows.size(); i++) {
            Event row = Objects.requireNonNull(rows.get(i), "row");
            String key = Objects.requireNonNull(row.userId(), "userId");
            index.computeIfAbsent(key, ignored -> new ArrayList<>()).add(i);
        }
        return index;
    }

    static List<Event> findByScan(List<Event> rows, String key) {
        Objects.requireNonNull(rows, "rows");
        Objects.requireNonNull(key, "key");

        List<Event> found = new ArrayList<>();
        for (Event row : rows) {
            if (row.userId().equals(key)) {
                found.add(row);
            }
        }
        return found;
    }

    static List<Event> findByIndex(
        List<Event> rows,
        Map<String, List<Integer>> index,
        String key
    ) {
        Objects.requireNonNull(rows, "rows");
        Objects.requireNonNull(index, "index");
        Objects.requireNonNull(key, "key");

        List<Integer> positions = index.getOrDefault(key, List.of());
        List<Event> found = new ArrayList<>(positions.size());

        for (int position : positions) {
            found.add(rows.get(position));
        }
        return found;
    }

    public static void main(String[] args) {
        List<Event> rows = List.of(
            new Event("u-10", "login"),
            new Event("u-20", "view"),
            new Event("u-10", "purchase"),
            new Event("u-30", "logout"),
            new Event("u-20", "purchase")
        );

        Map<String, List<Integer>> index = buildIndex(rows);

        System.out.println("Rows: " + rows.size());
        System.out.println("Distinct keys: " + index.size());
        System.out.println("Positions u-10: " + index.get("u-10"));
        System.out.println("Scan u-10: " + findByScan(rows, "u-10"));
        System.out.println("Index u-10: " + findByIndex(rows, index, "u-10"));
        System.out.println("Index missing: " + findByIndex(rows, index, "u-99"));
    }
}
~~~

Biên dịch và chạy bằng **JDK 17+**:

~~~bash
javac HashIndexDemo.java
java HashIndexDemo
~~~

**Stdout chính xác:**

~~~text
Rows: 5
Distinct keys: 3
Positions u-10: [0, 2]
Scan u-10: [Event[userId=u-10, action=login], Event[userId=u-10, action=purchase]]
Index u-10: [Event[userId=u-10, action=login], Event[userId=u-10, action=purchase]]
Index missing: []
~~~

**Giải thích các quyết định trong mã:**

- **record Event** (Java 17) tự tạo phương thức toString theo cú pháp Event[userId=..., action=...], vì vậy stdout ở trên có dạng đó.
- **List.of** tạo danh sách đầu vào không cho thêm/xóa/thay thế phần tử. Bản ghi Event là record không thể thay đổi các trường sau khi tạo; điều này giúp ví dụ tránh chỉ mục bị lỗi thời.
- **computeIfAbsent** tạo ArrayList chỉ khi userId chưa có nhóm. Các vị trí được thêm theo thứ tự i tăng nên kết quả trong một nhóm giữ thứ tự nguồn.
- **HashMap** không đảm bảo thứ tự duyệt các khóa. Mã chỉ in index.size() và index.get("u-10"), không in toàn Map; vì vậy stdout không phụ thuộc thứ tự bucket.
- **getOrDefault(key, List.of())** trả danh sách rỗng khi không có khóa. Điều này phù hợp với hợp đồng “không tìm thấy → không có bản ghi”.
- **findByIndex** tạo một List<Event> kết quả mới. Nếu khóa có t vị trí, truy vấn phải truy cập và đưa t bản ghi vào danh sách; chi phí lập danh sách là O(t) ngoài chi phí tra khóa.
- **String userId** được so sánh theo nội dung qua equals/hashCode của String. Trong chương trình, khóa null bị từ chối khi lập chỉ mục và khi truy vấn. Dữ liệu đã kiểm tra hợp lệ trong buildIndex nên findByScan có thể gọi equals an toàn trên những bản ghi đó.
- Vì danh sách **positions** của Map và bản ghi trong nguồn được trả lại dưới dạng tham chiếu, hệ thống thực nên tránh để bên gọi tùy tiện sửa cấu trúc chỉ mục. Ví dụ giữ mã ngắn để minh họa thuật toán; không phải API bất biến hoàn chỉnh cho môi trường đa luồng.

## 8. Phân tích độ phức tạp và lợi ích của tiền xử lý

Đặt:

- **n:** số bản ghi ban đầu.
- **m:** số khóa phân biệt; \(m\le n\) nếu n>0.
- **q:** số truy vấn tra theo khóa.
- **t_j:** số bản ghi phải trả cho truy vấn thứ j.

Giả sử đầu vào là List có **truy cập theo chỉ số O(1)** (ví dụ ArrayList hoặc List.of), thao tác băm/equals với khóa đủ ngắn được coi là O(1), phân bố hash hợp lý và thao tác thêm cuối ArrayList có chi phí khấu hao O(1).

| Phương án | Công việc ban đầu | Một truy vấn trả t bản ghi | Tổng cho q truy vấn |
|---|---:|---:|---:|
| **Quét lại nguồn** | O(1) phụ trợ | O(n+t), trong đó quét n thường đã trội | \(O(qn+\sum t_j)\) |
| **Tạo chỉ mục băm một lần** | O(n) kỳ vọng | **O(1+t) kỳ vọng** | **\(O(n+q+\sum t_j)\) kỳ vọng** |

Trong thực tế, quét nguồn cũng tạo danh sách các kết quả nếu API yêu cầu, còn truy vấn chỉ mục cũng cần đọc các bản ghi tương ứng. **Không được gọi truy vấn trả t bản ghi là O(1) khi t lớn.** Chỉ riêng bước lấy **danh sách vị trí đã lưu** từ Map có thể kỳ vọng O(1); việc trả toàn bộ dữ liệu có chi phí tỷ lệ kích thước kết quả.

**Bộ nhớ:** Map có m khóa và m danh sách vị trí; tổng cộng chứa đúng n vị trí khi mỗi bản ghi gắn với một khóa. Vì vậy chỉ mục chiếm **O(n+m) = O(n)** đơn vị lưu trữ ngoài danh sách nguồn, chưa tính overhead đối tượng. Nếu mỗi khóa chỉ cần đếm hoặc cờ tồn tại, có thể dùng cấu trúc **O(m)** thay cho n vị trí. Một truy vấn đang tạo danh sách trả t bản ghi cần thêm O(t) phần tử cho kết quả.

**Java cụ thể:** List<Integer> lưu chỉ số đã boxing, ArrayList có mảng lưu tham chiếu và HashMap có overhead theo bucket/node. Không thể lấy trực tiếp hệ số byte từ ký hiệu Big-O; nên benchmark lượng heap khi n, m rất lớn. Nếu dữ liệu nguồn không hỗ trợ rows.get(i) O(1), ví dụ LinkedList, thiết kế lưu **chỉ số rồi truy cập ngẫu nhiên** có thể làm mất lợi thế; lúc đó dùng danh sách bản ghi trực tiếp, chuyển nguồn sang cấu trúc truy cập nhanh, hoặc lưu offset/ID theo cách thích hợp.

### Khi nào chi phí xây chỉ mục được bù lại?

Chi phí xấp xỉ là:

\[
T_{\text{scan}} \approx q\cdot c_s n,\qquad
T_{\text{indexed}} \approx c_b n + q\cdot c_h + c_o\sum t_j,
\]

với các hệ số \(c_s,c_b,c_h,c_o\) phụ thuộc máy, dữ liệu, cách băm, cache CPU và cách trả kết quả. Không có **một ngưỡng q cố định** áp dụng cho mọi bài toán.

- Nếu q ít và n nhỏ, việc quét có thể đơn giản hơn.
- Nếu q nhiều, các truy vấn theo cùng trường khóa lặp lại, chỉ mục thường có lợi rõ rệt.
- Nếu một khóa khớp gần như toàn bộ n bản ghi, chi phí tạo/đọc kết quả vẫn gần O(n) cho truy vấn đó: chỉ mục không xóa chi phí đầu ra.
- Nếu dữ liệu thay đổi rất thường xuyên, việc cập nhật chỉ mục có thể tốn công hoặc làm phức tạp tính đúng; phải tính chi phí cập nhật vào mô hình.
- Nếu RAM hạn chế hoặc miền khóa quá lớn, cần cân nhắc cấu trúc lưu phù hợp, có thể là lưu trữ trên đĩa/cơ sở dữ liệu thay vì Map trong heap.

## 9. Các dạng truy vấn và chọn cấu trúc tương ứng

**Tra đúng một khóa (equality lookup).** Bảng băm phù hợp vì truy vấn dựa trên phép bằng: userId = "u-10". Không cần thứ tự từ điển của các khóa.

**Kiểm tra tồn tại.** Nếu chỉ muốn biết userId đã từng xuất hiện hay chưa, **HashSet<String>** thường gọn hơn Map<String, List<Integer>>: không cần lưu mọi vị trí.

**Đếm số lần xuất hiện.** Dùng Map<String, Integer> và tăng tần suất. Không cần trả từng bản ghi, nên bộ nhớ phụ chỉ theo m khóa phân biệt. Chú ý số đếm có thể cần long nếu tổng dữ liệu vượt miền int.

**Tìm tất cả vị trí xuất hiện.** Dùng Map<String, List<Integer>> như ví dụ. Nếu thêm các vị trí theo thứ tự nguồn, danh sách vị trí của từng khóa có thứ tự tăng.

**Lấy bản ghi trực tiếp.** Dùng Map<String, List<Event>> nếu nguồn không có truy cập theo chỉ số nhanh hoặc không muốn lệ thuộc vào vị trí. Tuy nhiên các bản ghi gốc còn phải tồn tại; tùy cách lưu mà bộ nhớ và vòng đời đối tượng khác nhau.

**Truy vấn khoảng hoặc thứ tự.** HashMap không tự hỗ trợ “mọi userId từ a đến m” hay “khóa nhỏ tiếp theo” theo thứ tự. Nếu cần truy vấn khoảng, min/max khóa, hoặc duyệt theo thứ tự, có thể cân nhắc **TreeMap**, mảng đã sắp + tìm kiếm nhị phân, B-tree/cơ sở dữ liệu, hay cấu trúc khác phù hợp với loại dữ liệu và khả năng cập nhật.

**Truy vấn nhiều điều kiện.** Chỉ mục theo userId giúp rút nhỏ tập ứng viên trước khi lọc action, nhưng không tự trả lời nhanh mọi câu hỏi như “userId là u-10 và action là purchase”. Có thể tạo khóa kết hợp (userId,action), nhiều chỉ mục hoặc thống kê gộp nếu các truy vấn thực tế cần thiết; mỗi chỉ mục thêm đều tăng bộ nhớ và chi phí bảo trì.

## 10. Khóa, đồng nhất và chuẩn hóa dữ liệu

Một chỉ mục chỉ đúng nếu chương trình nhất quán về **thế nào là cùng một khóa**. Ví dụ:

- "u-10" và "U-10" là **hai String khác nhau** trong Java nếu không chuẩn hóa.
- "u-10" và "u-10 " cũng khác nhau vì có khoảng trắng cuối.
- Nếu business yêu cầu không phân biệt chữ hoa/thường, cần quyết định rõ quy tắc chuẩn hóa khi **xây chỉ mục lẫn khi truy vấn**.
- Chuẩn hóa Unicode, khoảng trắng hoặc định dạng số điện thoại cần dựa trên hợp đồng dữ liệu; không tự động biến mọi chuỗi thành lowercase nếu điều đó làm mất ý nghĩa của mã phân biệt hoa/thường.

**Quy tắc tốt:** tạo một hàm **normalizeKey** được gọi thống nhất ở cả đường ghi và đường đọc, với quy tắc được tài liệu hóa. Không được xây Map bằng chuỗi nguyên bản nhưng truy vấn bằng chuỗi đã chuẩn hóa ở phía chỉ gọi; làm vậy dễ tạo “không tìm thấy” giả.

Với khóa là đối tượng tự viết, **equals và hashCode phải nhất quán** và các trường tham gia vào tính bằng/băm nên **bất biến** khi đối tượng nằm trong HashMap. Nếu thay đổi ID của đối tượng làm khóa sau khi chèn, entry có thể nằm ở bucket cũ trong khi truy vấn dùng giá trị băm mới, dẫn đến không tìm được dữ liệu.

Các chi tiết này thuộc **tính đúng của tiền xử lý**, không chỉ là tối ưu hiệu năng.

## 11. Dữ liệu thay đổi: chỉ mục có thể bị lỗi thời

Giả sử chỉ mục đã xây cho các hàng [0..n-1]. Sau đó có thao tác thêm, xóa hoặc sửa dữ liệu:

| Thao tác với nguồn | Hệ quả cho chỉ mục lưu vị trí | Cách xử lý |
|---|---|---|
| Thêm bản ghi vào cuối | Khóa mới chưa có vị trí mới | Thêm chỉ số mới vào đúng nhóm, nếu thiết kế cập nhật gia tăng |
| Thêm bản ghi vào giữa | Nhiều chỉ số cũ phía sau bị dịch | Có thể phải cập nhật nhiều vị trí hoặc **xây lại chỉ mục** |
| Xóa một bản ghi ở giữa | Nhiều chỉ số cũ không còn trỏ đúng bản ghi | Cập nhật các vị trí bị ảnh hưởng, dùng ID ổn định hoặc xây lại |
| Sửa userId của bản ghi | Vị trí đang nằm trong nhóm khóa cũ | Xóa khỏi nhóm cũ, đưa vào nhóm mới, hoặc xây lại |
| Sửa action nhưng userId không đổi | Vị trí vẫn trỏ đúng bản ghi, nếu cùng đối tượng/danh sách | Cần bảo đảm dữ liệu kết quả mới nhất được đọc từ nguồn |
| Sắp xếp lại danh sách | Các chỉ số thay đổi ý nghĩa | **Xây lại** hoặc cập nhật ánh xạ theo ID ổn định |

**Chỉ mục là dữ liệu dẫn xuất**, không phải nguồn sự thật. Nếu nguồn và chỉ mục không đồng bộ, tra cứu băm có thể **nhanh nhưng sai**. Vì vậy, cần thiết kế giao diện cập nhật dữ liệu và chỉ mục như **một đơn vị nhất quán**, hoặc công bố rằng chỉ mục chỉ phản ánh một **snapshot bất biến**.

Với hệ thống có ghi đồng thời, chỉ đọc HashMap từ nhiều luồng sau khi đã công bố an toàn một snapshot bất biến là tình huống khác với việc vừa đọc vừa sửa cùng một HashMap. **HashMap không hỗ trợ cập nhật đồng thời không đồng bộ an toàn**. Cân nhắc khóa đồng bộ, ConcurrentHashMap kết hợp cấu trúc nhóm thích hợp, copy-on-write, hoặc kiến trúc chỉ mục của cơ sở dữ liệu. ConcurrentHashMap chỉ bảo đảm an toàn cho các thao tác nó quản lý, **không tự biến ArrayList bên trong thành cấu trúc an toàn cho nhiều luồng ghi**.

## 12. Băm không phải lời giải cho mọi dạng tiền xử lý

Lập chỉ mục băm giải tốt một loại câu hỏi: **tra theo khóa chính xác**. Những trường hợp sau cần cân nhắc:

1. **Một lần tra duy nhất:** quét tuyến tính có thể rẻ hơn tạo toàn bộ Map.
2. **Đòi trả hầu hết dữ liệu:** phần đầu ra lớn vẫn phải xử lý, dù tra khóa nhanh.
3. **Phải duyệt khóa theo thứ tự:** HashMap không bảo đảm thứ tự; TreeMap hoặc mảng sắp phù hợp hơn.
4. **Cần so khớp tiền tố, khoảng hay gần đúng:** phải thiết kế chỉ mục chuyên biệt như trie, cây hoặc inverted index phù hợp với kiểu truy vấn.
5. **Dữ liệu biến đổi nhanh, nhiều phép chèn/xóa giữa danh sách:** chỉ số vị trí dễ lỗi thời; lưu ID ổn định hoặc chọn cấu trúc hỗ trợ cập nhật.
6. **Bộ nhớ không đủ:** chỉ mục có thể chiếm RAM đáng kể; dùng hệ thống lưu trữ/đánh chỉ mục ngoài bộ nhớ hoặc chiến lược caching chọn lọc.
7. **Dữ liệu do tác nhân không tin cậy tạo khóa:** phải quan tâm tới va chạm cố ý, chi phí hash/equals và phòng tránh tấn công gây cạn tài nguyên.
8. **Cần thứ tự và khả năng phân trang:** một Map tra đúng khóa không tự cung cấp thứ tự kết quả tổng thể; phải quy định thứ tự nguồn hoặc tiêu chí sắp riêng.

**HashMap khác cache.** Chỉ mục lưu quan hệ từ khóa tới dữ liệu nguồn; cache lưu kết quả tính toán/truy vấn đã thực hiện và có thể có quy tắc hết hạn, loại bỏ, kích thước tối đa. Có thể dùng HashMap triển khai cả hai, nhưng **hợp đồng tính đúng, vòng đời và cách cập nhật là khác nhau**.

## 13. Kiểm thử tính đúng và so sánh hiệu năng

Một phương pháp kiểm thử đáng tin là xem **quét tuyến tính** như **oracle** trên dữ liệu nhỏ: xây chỉ mục, rồi với mỗi khóa thử nghiệm so sánh **toàn bộ danh sách bản ghi trả về và thứ tự** của findByIndex với findByScan.

Các ca cần có:

| Ca kiểm thử | Kết quả mong đợi |
|---|---|
| Danh sách nguồn rỗng | Chỉ mục rỗng; mọi khóa hợp lệ trả [] |
| Một bản ghi | Khóa tồn tại trả một bản ghi; khóa khác trả [] |
| Nhiều bản ghi có cùng khóa | Trả **đầy đủ các bản ghi**, không ghi đè và không đảo thứ tự |
| Các khóa xuất hiện xen kẽ | Mỗi danh sách vị trí vẫn tăng theo thứ tự nguồn |
| Khóa không tồn tại | Trả [] theo hợp đồng |
| Khóa gần giống nhau về chữ hoa/space | Phù hợp quy tắc phân biệt hay chuẩn hóa đã công bố |
| Khóa null | Ví dụ Java từ chối, không lập nhóm ngầm khi không được phép |
| Cập nhật/xóa/sắp xếp lại nguồn | Cập nhật chỉ mục hoặc xây lại; không để vị trí cũ trỏ sai |
| Khóa khác nhau có cùng hashCode | HashMap vẫn phải dùng equals phân biệt đúng hai khóa |
| Rất nhiều khóa phân biệt | Đo RAM, thời gian tạo chỉ mục và số bucket/đối tượng |
| Một khóa có rất nhiều kết quả | Đo chi phí tạo/truyền danh sách lớn; không hứa hằng số |

Khi benchmark, nên đo **hai phần riêng**:

- **Thời gian xây chỉ mục:** đọc toàn bộ n bản ghi và tạo Map/list.
- **Thời gian xử lý q truy vấn:** bao gồm việc tạo hoặc duyệt kết quả, không chỉ một lệnh Map.get.

So sánh trên cùng dữ liệu, cùng tập khóa truy vấn, cùng kiểu kết quả; bỏ qua chi phí đầu ra ở một bên rồi tính ở bên kia sẽ dẫn đến kết luận sai. Với Java, môi trường JIT, GC, kích thước heap và phân bố khóa có thể làm thời gian thực tế khác biệt; cần warm-up và công cụ benchmark phù hợp nếu đo rất chính xác.

## 14. Bài tập tự kiểm tra

**Bài 1.** Cho userId theo thứ tự nguồn: [A,B,A,C,A,B]. Nếu lập Map từ khóa tới danh sách vị trí, chỉ mục của A và B là gì?

*Đáp án:* A → [0,2,4]; B → [1,5]. Mỗi danh sách vị trí tăng dần vì được thêm theo thứ tự nguồn.

**Bài 2.** Nếu dùng Map<String, Event> và put liên tục tất cả bản ghi, điều gì xảy ra khi một khóa xuất hiện ba lần?

*Đáp án:* Giá trị gắn với khóa thường bị thay bằng bản ghi put sau cùng; các bản ghi trước bị mất trong Map. Muốn lấy tất cả, cần lưu danh sách hoặc một cấu trúc đa ánh xạ phù hợp.

**Bài 3.** Giả sử cần trả t bản ghi cho một khóa. Vì sao không thể tuyên bố toàn bộ truy vấn chỉ mất O(1)?

*Đáp án:* HashMap có thể tìm **địa chỉ nhóm** trong O(1) kỳ vọng, nhưng tạo/đọc/trả t bản ghi cần O(t) công việc, nên tổng là **O(1+t) kỳ vọng** trong mô hình truy cập bản ghi O(1).

**Bài 4.** Với n bản ghi, m khóa phân biệt và q câu hỏi tra cứu lặp lại, hãy viết độ phức tạp kỳ vọng khi lập chỉ mục một lần rồi trả đầy đủ t_j bản ghi cho câu hỏi j.

*Đáp án:* Khoảng **O(n+q+\sum t_j)** thời gian kỳ vọng, bộ nhớ chỉ mục **O(n+m)** nếu giữ tất cả vị trí; so với **O(qn+\sum t_j)** cho quét lại mỗi lần.

**Bài 5.** Sau khi xây chỉ mục vị trí, dữ liệu được xóa một phần tử ở giữa và các phần tử còn lại dịch chỉ số. Có thể tiếp tục dùng nguyên chỉ mục không?

*Đáp án:* **Không**: các vị trí đã lưu có thể trỏ sai bản ghi. Cần cập nhật vị trí, xây lại chỉ mục hoặc chuyển sang ID ổn định và cơ chế đồng bộ tương ứng.

**Bài 6.** HashMap có đảm bảo liệt kê các khóa theo thứ tự tăng không? Nếu cần truy vấn mọi khóa từ A tới M thì nên làm gì?

*Đáp án:* **Không.** HashMap phù hợp tra chính xác theo khóa. Với yêu cầu theo thứ tự/khoảng, hãy cân nhắc TreeMap, mảng sắp kết hợp tìm kiếm biên hoặc chỉ mục có thứ tự khác.

**Ghi nhớ:** Lập chỉ mục bằng băm là **tiền xử lý để tái sử dụng kết quả phân nhóm theo khóa**, giúp tránh quét n bản ghi cho mọi truy vấn. Hãy thiết kế đúng dạng ánh xạ, xử lý khóa trùng, công bố chi phí **xây một lần O(n) kỳ vọng**, **tra cứu O(1+t) kỳ vọng** khi phải trả t kết quả, và giữ chỉ mục nhất quán với nguồn. Tốc độ tra cứu chỉ có ý nghĩa khi **kết quả vẫn đúng** và bộ nhớ/cập nhật phù hợp với khối lượng công việc.