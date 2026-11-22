# Trie và cấu trúc chỉ mục cho tiền tố

Khi cần tra cứu hàng nghìn hoặc hàng triệu khóa theo **phần đầu của chuỗi**, việc quét toàn bộ danh sách sau mỗi lần người dùng nhập một ký tự thường tốn kém. Ví dụ, ô tìm kiếm cần trả về các từ bắt đầu bằng `"an"`, chức năng gợi ý tên lệnh cần tìm mọi lệnh có tiền tố `"git "`, hoặc một bộ định tuyến cần tra cứu các khóa được phân cấp theo các thành phần đầu.

**Trie (cây tiền tố)** lưu các chuỗi theo phần đầu dùng chung. Đường đi từ gốc tới một nút biểu diễn một tiền tố; dấu kết thúc từ xác định đường đi nào còn là một từ/khóa hoàn chỉnh. Trie là một **cấu trúc hỗ trợ** các thuật toán tìm kiếm, lập chỉ mục, gợi ý và đối sánh chuỗi.

Mục tiêu bài học: hiểu mô hình nút–cạnh, phân biệt từ hoàn chỉnh với tiền tố, xây dựng và kiểm chứng các thao tác, biết cách đánh giá chi phí bộ nhớ, cũng như chọn trie hay cấu trúc chỉ mục khác cho đúng bài toán.

## 1. Bài toán tiền tố và đặc tả cần thống nhất

Giả sử tập từ phân biệt là `S = {"an", "anh", "ăn", "bàn"}`. Với truy vấn `"an"`:

- **Tra cứu từ hoàn chỉnh:** `"an"` có nằm trong S không? Có.
- **Tra cứu tiền tố:** có từ nào trong S bắt đầu bằng `"an"` không? Có.
- **Đếm theo tiền tố:** có bao nhiêu từ phân biệt bắt đầu bằng `"an"`? Có **2** từ: `"an"`, `"anh"`.
- **Liệt kê theo tiền tố:** trả về `["an", "anh"]`; danh sách kết quả có thể giới hạn `k` phần tử.
- **Xóa một từ:** xóa `"an"` nhưng vẫn giữ `"anh"` nếu chưa xóa nó.

`"a"` là tiền tố của `"an"` nhưng không nhất thiết là từ hoàn chỉnh đã lưu. Trái lại, **tìm chuỗi con** là bài toán khác: `"nh"` xuất hiện trong `"anh"` nhưng không phải tiền tố của nó. Trie thông thường không giải quyết truy vấn chuỗi con tùy ý bằng cùng cơ chế tìm đường đi từ gốc.

Trong bài này, mỗi từ lưu **một lần** theo ngữ nghĩa tập hợp (set): thêm từ đã có trả về `false`, không làm tăng bộ đếm. Từ được thêm/xóa phải khác `null` và không rỗng; **tiền tố rỗng** được phép dùng cho truy vấn toàn bộ từ. Kết quả gợi ý có thứ tự theo **mã điểm Unicode tăng dần**. Không tự động chuyển chữ hoa thành chữ thường hoặc chuẩn hóa Unicode.

## 2. Mô hình của trie

Một trie được xây dựng từ các thành phần:

1. **Nút gốc (root)** biểu diễn tiền tố rỗng.
2. **Cạnh từ nút cha sang nút con** mang một đơn vị ký tự (ở ví dụ Java bên dưới là một *Unicode code point*).
3. **Nút kết thúc (terminal)** đánh dấu một đường đi từ gốc là một khóa hoàn chỉnh.
4. **Trạng thái bổ sung (tùy chọn)** như số khóa nằm trong cây con, tần suất tìm kiếm, giá trị gắn với khóa hoặc thông tin xếp hạng.

Ví dụ giản lược với `"an"`, `"anh"`, `"ăn"`:

~~~text
(root)
 ├─ a
 │   └─ n [kết thúc "an"]
 │       └─ h [kết thúc "anh"]
 └─ ă [nhánh riêng]
     └─ n [kết thúc "ăn"]
~~~

Hai từ `"an"` và `"anh"` dùng chung đường đi `a → n`. Nút `n` vừa là nút kết thúc từ `"an"`, vừa có con `h` cho từ dài hơn. Nút `a` chỉ là một tiền tố, không phải từ hoàn chỉnh nếu chưa thêm `"a"`.

**Bất biến cấu trúc:** mỗi nút tương ứng với đúng một tiền tố được xây dựng từ đường đi từ gốc; mỗi cạnh có một nhãn duy nhất trong tập con của cùng một nút cha. Muốn biết từ có tồn tại hay không, phải đi hết chuỗi **và** thấy nút cuối mang dấu terminal.

Không cần mỗi nút phải có đủ 26 con hoặc đủ bảng Unicode. Với bảng chữ cái rộng, có thể dùng một map `nhãn cạnh → nút con` để chỉ lưu các cạnh thực sự xuất hiện.

## 3. Các thao tác cơ bản và ý nghĩa kết quả

| Thao tác | Quy tắc | Điều cần chú ý |
| --- | --- | --- |
| `add(word)` | Đi theo từng ký tự, tạo cạnh thiếu, đánh dấu nút cuối | Chỉ tăng số từ khi từ chưa tồn tại |
| `containsWord(word)` | Đi hết `word` rồi kiểm tra terminal | Đường đi tồn tại chưa đủ |
| `hasPrefix(prefix)` | Đi tới nút tiền tố và kiểm tra có từ hoàn chỉnh nằm dưới nó | Với tiền tố rỗng, đúng khi kho từ không rỗng |
| `countWithPrefix(prefix)` | Đọc số từ phân biệt trong cây con của nút tiền tố | Có thể O(độ dài tiền tố) nếu lưu sẵn bộ đếm |
| `suggest(prefix, limit)` | Tới nút tiền tố, duyệt các nhánh con để lấy tối đa `limit` từ | Thứ tự và tiêu chí xếp hạng phải được định nghĩa |
| `remove(word)` | Bỏ dấu terminal, cập nhật đếm, cắt nhánh không còn từ | Không làm mất từ khác dùng chung tiền tố |

**Phân biệt `containsWord` và `hasPrefix`:** với trie chỉ chứa `"anh"`, `containsWord("an") = false` vì `"an"` chưa được thêm; nhưng `hasPrefix("an") = true` vì có từ `"anh"` bắt đầu bằng `"an"`.

**Tiền tố rỗng:** theo đặc tả bài này, `countWithPrefix("")` là tổng số từ trong trie, còn `suggest("", k)` là danh sách tối đa `k` từ đầu theo thứ tự được chọn. `hasPrefix("")` là `false` nếu chưa có từ nào, vì truy vấn hỏi “có ít nhất một từ mang tiền tố này hay không?”.

## 4. Vì sao cần cờ terminal và bộ đếm cây con?

Xét hai lần thêm `"an"` và `"anh"`. Nếu chỉ dựa vào việc tìm được đường đi `a → n`, ta không thể biết `"an"` đã được thêm riêng hay chưa. Cờ `terminal` giải quyết điểm này.

Để trả lời nhanh câu hỏi “bao nhiêu từ bắt đầu bằng tiền tố p?”, mỗi nút có thể giữ `wordCount` — **số từ hoàn chỉnh phân biệt trong cây con** của nó. Khi thêm thành công một từ mới, tăng `wordCount` của gốc và tất cả nút trên đường đi của từ đó. Nếu thêm từ trùng, không tăng gì. Khi xóa thành công, giảm các bộ đếm tương ứng.

Ví dụ sau khi thêm `"an"`, `"anh"`, `"ăn"`:

| Nút/tiền tố | `terminal` | `wordCount` |
| --- | --- | ---: |
| Gốc `""` | false | 3 |
| `"a"` | false | 2 |
| `"an"` | true | 2 |
| `"anh"` | true | 1 |
| `"ă"` | false | 1 |
| `"ăn"` | true | 1 |

Sau khi xóa `"an"`, nút `"an"` vẫn cần tồn tại vì `"anh"` dựa vào nó; `terminal` chuyển thành `false` và `wordCount` tại nút đó còn 1. Chỉ cắt nhánh khi không còn từ nào trong cây con. **Không được xóa đường đi chỉ vì từ bị xóa là tiền tố của một từ khác.**

## 5. Hiện thực Java 17+ dùng Unicode code point

Mã bên dưới là **một chương trình hoàn chỉnh**. `TreeMap<Integer, Node>` lưu các cạnh theo mã điểm Unicode và giữ thứ tự xác định khi liệt kê. `String.codePoints()` duyệt theo code point, nên một ký tự ngoài BMP không bị tách thành hai cạnh surrogate UTF-16 trong trường hợp chuỗi Unicode hợp lệ.

Bản cài đặt dùng tập hợp từ phân biệt; hỗ trợ thêm, tìm từ đầy đủ, kiểm tra/đếm tiền tố, gợi ý có giới hạn và xóa an toàn. Hàm gợi ý dùng `StringBuilder` để bổ sung nhãn cạnh và quay lui sau khi duyệt nhánh.

Lưu vào tệp **PrefixTrieDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.NavigableMap;
import java.util.TreeMap;

public final class PrefixTrieDemo {
    private static final class Node {
        final NavigableMap<Integer, Node> children = new TreeMap<>();
        boolean terminal;
        int wordCount;
    }

    private final Node root = new Node();

    private static void requireWord(String word) {
        if (word == null || word.isEmpty()) {
            throw new IllegalArgumentException("word must be non-null and non-empty");
        }
    }

    private static void requirePrefix(String prefix) {
        if (prefix == null) {
            throw new IllegalArgumentException("prefix must be non-null");
        }
    }

    private Node nodeFor(String prefix) {
        Node current = root;
        for (int point : prefix.codePoints().toArray()) {
            current = current.children.get(point);
            if (current == null) {
                return null;
            }
        }
        return current;
    }

    public boolean add(String word) {
        requireWord(word);
        Node current = root;
        List<Node> path = new ArrayList<>();
        path.add(current);

        for (int point : word.codePoints().toArray()) {
            current = current.children.computeIfAbsent(point, p -> new Node());
            path.add(current);
        }

        if (current.terminal) {
            return false;
        }

        current.terminal = true;
        for (Node node : path) {
            node.wordCount++;
        }
        return true;
    }

    public boolean containsWord(String word) {
        requireWord(word);
        Node node = nodeFor(word);
        return node != null && node.terminal;
    }

    public boolean hasPrefix(String prefix) {
        requirePrefix(prefix);
        Node node = nodeFor(prefix);
        return node != null && node.wordCount > 0;
    }

    public int countWithPrefix(String prefix) {
        requirePrefix(prefix);
        Node node = nodeFor(prefix);
        return node == null ? 0 : node.wordCount;
    }

    public List<String> suggest(String prefix, int limit) {
        requirePrefix(prefix);
        if (limit < 0) {
            throw new IllegalArgumentException("limit must be non-negative");
        }

        List<String> found = new ArrayList<>();
        if (limit == 0) {
            return found;
        }

        Node node = nodeFor(prefix);
        if (node != null) {
            collect(node, new StringBuilder(prefix), limit, found);
        }
        return found;
    }

    private static void collect(Node node, StringBuilder text, int limit,
                                List<String> found) {
        if (found.size() >= limit) {
            return;
        }
        if (node.terminal) {
            found.add(text.toString());
        }
        for (Map.Entry<Integer, Node> edge : node.children.entrySet()) {
            if (found.size() >= limit) {
                break;
            }
            int previousLength = text.length();
            text.appendCodePoint(edge.getKey());
            collect(edge.getValue(), text, limit, found);
            text.setLength(previousLength);
        }
    }

    public boolean remove(String word) {
        requireWord(word);
        int[] points = word.codePoints().toArray();
        List<Node> path = new ArrayList<>();
        Node current = root;
        path.add(current);

        for (int point : points) {
            current = current.children.get(point);
            if (current == null) {
                return false;
            }
            path.add(current);
        }
        if (!current.terminal) {
            return false;
        }

        current.terminal = false;
        for (Node node : path) {
            node.wordCount--;
        }
        for (int i = points.length - 1; i >= 0; i--) {
            if (path.get(i + 1).wordCount != 0) {
                break;
            }
            path.get(i).children.remove(points[i]);
        }
        return true;
    }

    public static void main(String[] args) {
        PrefixTrieDemo trie = new PrefixTrieDemo();

        System.out.println(trie.add("an"));
        System.out.println(trie.add("anh"));
        System.out.println(trie.add("ăn"));
        System.out.println(trie.add("an"));
        System.out.println(trie.containsWord("a"));
        System.out.println(trie.hasPrefix("a"));
        System.out.println(trie.countWithPrefix("an"));
        System.out.println(trie.suggest("a", 10));
        System.out.println(trie.suggest("an", 1));
        System.out.println(trie.remove("an"));
        System.out.println(trie.containsWord("an"));
        System.out.println(trie.hasPrefix("an"));
        System.out.println(trie.countWithPrefix("an"));
        System.out.println(trie.suggest("an", 5));
        System.out.println(trie.remove("an"));
        System.out.println(trie.hasPrefix("z"));
        System.out.println(trie.countWithPrefix(""));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac PrefixTrieDemo.java
java PrefixTrieDemo
~~~

Đầu ra chính xác với dữ liệu trong `main`:

~~~text
true
true
true
false
false
true
2
[an, anh]
[an]
true
false
true
1
[anh]
false
false
2
~~~

Giải thích theo trình tự:

- Ba lần thêm đầu trả `true`; thêm trùng `"an"` trả `false`, nên không tăng bộ đếm.
- `containsWord("a")` trả `false`; `hasPrefix("a")` trả `true`, vì `"a"` chỉ là tiền tố của một số từ.
- Trước khi xóa, có hai từ `"an"` và `"anh"` bắt đầu bằng `"an"`; gợi ý `"a"` gồm hai từ theo thứ tự mã điểm Unicode.
- Sau `remove("an")`, truy vấn từ hoàn chỉnh cho `"an"` trả `false`, nhưng tiền tố `"an"` vẫn có vì từ `"anh"` chưa bị xóa.
- Xóa lần thứ hai trả `false`; tiền tố `"z"` không có; đếm tiền tố rỗng là 2 vì còn `"anh"` và `"ăn"`.

## 6. Chứng minh tính đúng đắn của các thao tác

**Tìm kiếm:** từ gốc, mỗi bước chọn đúng cạnh mang code point tiếp theo. Vì mỗi nút có tối đa một cạnh ứng với mỗi nhãn, đường đi của một chuỗi là duy nhất. Nếu không tìm được cạnh, không có khóa nào mang tiền tố đó. Nếu đến cuối, cờ `terminal` phản ánh chính xác khóa đầy đủ đã được thêm và chưa bị xóa.

**Thêm mới:** quá trình đi qua toàn bộ chuỗi tạo các nút còn thiếu. Nếu nút cuối đã terminal thì từ đã tồn tại, không cần đổi bộ đếm. Nếu chưa terminal, đánh dấu terminal và tăng bộ đếm ở mọi nút trên đường đi đúng một đơn vị: chính xác thêm một từ hoàn chỉnh vào mọi cây con chứa đường đi của từ đó.

**Xóa:** chỉ xóa nếu nút cuối đang terminal. Đổi terminal thành false và giảm bộ đếm mọi nút trên đường đi đúng một đơn vị. Khi duyệt ngược, một cây con có `wordCount = 0` không còn từ hoàn chỉnh nên có thể loại khỏi cha; gặp cây con có bộ đếm dương thì dừng cắt nhánh. Do đó các từ dùng chung tiền tố còn tồn tại.

**Gợi ý:** duyệt sâu từ nút tiền tố. Mỗi khi gặp terminal, đường đi hiện tại tương ứng một từ đầy đủ có tiền tố truy vấn. Duyệt qua mỗi con theo nhãn tăng dần và xử lý từ ngắn hơn trước các phần mở rộng của nó, nên kết quả được liệt kê theo thứ tự từ điển **theo mã điểm Unicode**. Dừng sau `limit` từ tránh tạo toàn bộ danh sách khi chỉ cần vài gợi ý.

Bất biến quan trọng nhất là **`wordCount(node)` bằng số nút terminal trong cây con của node**. Khi thao tác thêm/xóa bảo toàn bất biến này, truy vấn đếm tiền tố chỉ cần đọc trường `wordCount` tại nút đích.

## 7. Độ phức tạp: độ dài khóa và cấu trúc lưu cạnh

Gọi `L` là số code point trong từ cần thêm/xóa, `P` là số code point của tiền tố, `d` là số cạnh con lớn nhất tại một nút, và `N` là số nút hiện có trong trie (tính cả gốc).

| Thao tác | Nếu tra cứu cạnh O(1) trung bình, chẳng hạn HashMap | Với TreeMap trong ví dụ |
| --- | --- | --- |
| Thêm một từ mới | O(L) | O(L log(d + 1)) |
| Tra cứu một từ | O(L) | O(L log(d + 1)) |
| Kiểm tra hoặc đếm tiền tố | O(P) | O(P log(d + 1)) |
| Xóa một từ | O(L) | O(L log(d + 1)) |
| Liệt kê tối đa k từ | Phụ thuộc số nút/cạnh phải duyệt và tổng độ dài từ được tạo | Tương tự, cộng chi phí quản lý cạnh có thứ tự |

Khi một nút không có con, `log(d + 1)` là cách viết để tránh nói `log 0`; với bậc nhỏ, chi phí tra cứu được xem là hằng số. `TreeMap` duyệt con theo thứ tự tăng dần mà không cần sắp xếp lại ở mỗi truy vấn.

**Bộ nhớ cấu trúc:** O(N) nút và cạnh, với N không vượt quá 1 cộng tổng chiều dài của tất cả từ phân biệt; các tiền tố chung giúp giảm số nút thực tế. `TreeMap`, đối tượng Node và các entry của map có overhead; vì vậy trie thường dùng **nhiều bộ nhớ hơn** lưu danh sách chuỗi gọn, nhất là khi các khóa ít chia sẻ tiền tố.

**Bộ nhớ tạm của ví dụ Java:** `codePoints().toArray()` cấp một mảng theo số code point của chuỗi; `add` và `remove` còn lưu danh sách nút trên đường đi, vì vậy dùng O(L) bộ nhớ phụ tạm thời. `nodeFor` dùng O(P) bộ nhớ tạm cho mảng code point. Hàm `collect` có ngăn xếp đệ quy theo độ sâu nhánh và bộ nhớ cho chuỗi kết quả. Có thể dùng iterator để tránh các mảng tạm, hoặc duyệt lặp thay đệ quy khi từ có thể rất dài.

**Truy vấn gợi ý không tự động là O(P + k):** nó còn mất công lần theo nhánh, sao chép các chuỗi kết quả và có thể thăm nhiều nút. Nếu cần top-k theo độ phổ biến thay vì thứ tự từ điển, phải bổ sung dữ liệu xếp hạng/caching hoặc thuật toán chọn lọc phù hợp.

## 8. Chọn trie hay cấu trúc chỉ mục tiền tố khác?

| Cấu trúc | Cách truy vấn tiền tố | Điểm mạnh | Giới hạn cần cân nhắc |
| --- | --- | --- | --- |
| **Trie nút-ký tự** | Đi theo P ký tự rồi duyệt cây con | Truy vấn tiền tố trực tiếp, chia sẻ đường đi | Nhiều nút/map; overhead bộ nhớ cao |
| **Radix tree / compact trie** | Cạnh mang cả một đoạn chuỗi, so khớp từng đoạn | Giảm nút trên các nhánh một-con | Chèn/xóa phải tách hoặc gộp cạnh |
| **Danh sách đã sắp xếp** | Tìm điểm bắt đầu bằng tìm kiếm nhị phân, sau đó quét các khóa khớp | Lưu trữ đơn giản, quét liên tiếp thân thiện cache | Cập nhật chèn/xóa tốn công nếu dùng mảng |
| **TreeMap / balanced BST theo khóa** | Dùng `tailMap(prefix)`, duyệt cho tới khi khóa không còn bắt đầu bằng prefix | Kết hợp sắp xếp với các truy vấn khoảng | Tra cứu phụ thuộc số khóa và phép so sánh chuỗi |
| **HashMap chỉ theo khóa đầy đủ** | Thường phải quét các khóa nếu không có chỉ mục bổ sung | Tra cứu chính xác rất hiệu quả trung bình | Không hỗ trợ tiền tố trực tiếp |
| **Bảng ánh xạ mọi tiền tố tới danh sách từ** | Lấy danh sách đã chuẩn bị sẵn theo prefix | Trả kết quả nhanh cho dữ liệu nhỏ/ít thay đổi | Trùng lặp dữ liệu lớn và cập nhật phức tạp |

**Không có cấu trúc tốt nhất cho mọi tải công việc.** Với tập từ gần như bất biến và cần liệt kê theo thứ tự, mảng đã sắp xếp + binary search có thể đơn giản và tiết kiệm bộ nhớ. Với cập nhật thường xuyên, tìm tiền tố liên tục và chia sẻ tiền tố mạnh, trie phù hợp hơn. Với kho dữ liệu cực lớn, cân nhắc radix/compact trie, chỉ mục trên đĩa, hoặc công cụ tìm kiếm chuyên dụng.

**Lưu ý về thứ tự so sánh:** muốn dùng cấu trúc chuỗi đã sắp xếp để truy vấn tiền tố, bộ so sánh được dùng để sắp xếp phải tương thích với điều kiện `startsWith`. Một bộ so sánh địa phương hóa phức tạp có thể cho thứ tự khác thứ tự code point; khi đó phải thiết kế giới hạn khoảng truy vấn và việc lọc kết quả đúng theo chính bộ so sánh đã chọn.

## 9. Unicode, chuẩn hóa và gợi ý thực tế

Trong Java, `String.length()` trả về số **đơn vị mã UTF-16**, không phải luôn bằng số code point. Duyệt từng `char` có thể tách một ký tự ngoài BMP thành hai cạnh. Ví dụ dùng `codePoints()` để lưu một cạnh cho mỗi code point. Tuy vậy, **code point không đồng nghĩa với ký tự nhìn thấy (grapheme cluster)**: chữ có dấu có thể được biểu diễn bằng một code point dựng sẵn hoặc bằng chữ cơ sở cộng dấu kết hợp.

Hai chuỗi trông giống nhau có thể có mã Unicode khác nhau. Nếu bài toán yêu cầu coi chúng là cùng một từ, hãy áp dụng **chính sách chuẩn hóa nhất quán** (chẳng hạn NFC) lúc thêm, xóa và truy vấn. Nếu cần không phân biệt hoa/thường, đặt thêm quy tắc case folding/lowercasing phù hợp ngôn ngữ và locale; làm một chiều ở lúc thêm mà quên lúc truy vấn sẽ dẫn tới tìm không ra dữ liệu.

Vì ví dụ dùng `TreeMap<Integer, Node>`, thứ tự gợi ý là thứ tự mã điểm Unicode, **không phải thứ tự từ điển tiếng Việt theo ngữ cảnh ngôn ngữ**. Nếu ứng dụng yêu cầu sắp xếp địa phương hóa hoặc xếp hạng theo tần suất, cần tách logic **tìm ứng viên theo tiền tố** khỏi logic **chọn và xếp hạng gợi ý**.

Trong hệ thống autocomplete, thường cần thêm: giới hạn số kết quả, xếp hạng theo tần suất hoặc mức liên quan, cập nhật khi dữ liệu đổi, tránh tính toán lại toàn bộ danh sách theo từng phím bấm, và giới hạn kích thước nhập vào để kiểm soát thời gian/bộ nhớ.

## 10. Các lỗi thường gặp khi tự viết trie

1. **Đánh đồng tiền tố với từ:** tìm được đường đi `"an"` không chứng minh từ `"an"` đã được thêm; phải kiểm tra terminal.
2. **Đếm trùng khi thêm:** không kiểm tra nút cuối terminal trước khi tăng `wordCount` sẽ làm sai cả số gợi ý và số từ.
3. **Xóa quá tay:** xóa cả nút `"an"` khi bỏ từ `"an"` sẽ làm mất `"anh"`, vì vậy phải giữ nút có cây con còn từ.
4. **Lẫn tiền tố với chuỗi con:** truy vấn `"nh"` không tìm thấy `"anh"` trong trie tiền tố, dù `"nh"` là chuỗi con.
5. **Không thống nhất quy tắc Unicode/chữ hoa:** thêm dạng NFC, tìm dạng không chuẩn hóa, hoặc dùng `char` chỗ này và code point chỗ khác.
6. **Mặc định HashMap có thứ tự:** không được suy ra thứ tự đầu ra ổn định từ một hash map thông thường; ví dụ dùng TreeMap để minh định thứ tự.
7. **Quên bộ nhớ:** trie với rất nhiều nhánh một-con có thể tiêu tốn đáng kể; hãy đánh giá radix tree hoặc cấu trúc nén.
8. **Không giới hạn liệt kê:** quét mọi lá rồi dựng toàn bộ chuỗi có thể tốn nhiều bộ nhớ dù người dùng chỉ cần vài gợi ý.
9. **Coi bộ đếm bằng số đường đi:** `wordCount` là số **từ terminal phân biệt** trong cây con, không phải số nút hoặc số lần gọi add.
10. **Quên độ sâu đệ quy:** một chuỗi cực dài có thể làm `collect` tràn stack; khi cần hỗ trợ dữ liệu như vậy, thay bằng duyệt stack tường minh.

## 11. Kiểm thử trie theo đặc tả

| Trường hợp | Thao tác | Kết quả đúng |
| --- | --- | --- |
| Kho rỗng | `hasPrefix("")`, `countWithPrefix("")` | `false`, `0` |
| Thêm từ và trùng | `add("an")`, sau đó `add("an")` | `true`, rồi `false` |
| Tiền tố chưa là từ | Chỉ thêm `"anh"`, hỏi `containsWord("an")` | `false` |
| Có hậu duệ | Chỉ thêm `"anh"`, hỏi `hasPrefix("an")` | `true` |
| Nhánh dùng chung | Thêm `"an"` và `"anh"`, xóa `"an"` | `"anh"` vẫn tồn tại |
| Giới hạn gợi ý | `suggest("a", 0)` | Danh sách rỗng |
| Không có tiền tố | `suggest("xyz", 5)` | Danh sách rỗng |
| Kho chỉ còn một từ | Xóa các từ khác | Bộ đếm ở gốc bằng 1 |
| Đầu vào lỗi | `add("")`, `containsWord(null)`, `suggest("a", -1)` | `IllegalArgumentException` |
| Thứ tự | Thêm `"ăn"`, `"anh"`, `"an"`, gọi `suggest("a", 10)` | `[an, anh]` theo mã điểm Unicode |

Một phép kiểm thử tham chiếu hữu ích là duy trì đồng thời một `TreeSet<String>` theo cách sắp xếp tương thích. Sau các chuỗi thao tác thêm/xóa nhỏ, đối chiếu `contains` cho từng từ, đếm các phần tử thỏa `startsWith(prefix)`, và danh sách gợi ý theo đúng bộ so sánh. Khi so sánh thứ tự, nhớ rằng so sánh UTF-16 theo `String.compareTo` có thể khác thứ tự code point đối với một số chuỗi có ký tự ngoài BMP; hoặc giới hạn dữ liệu kiểm thử cho miền mà hai thứ tự tương thích, hoặc dùng bộ so sánh code point thống nhất.

Có thể kiểm tra bằng **bất biến**: tổng số từ ở gốc bằng số từ phân biệt đã thêm nhưng chưa xóa; với mọi nút, bộ đếm bằng (1 nếu terminal, ngược lại 0) cộng bộ đếm của mọi nút con; sau khi xóa một từ, những từ khác vẫn tìm được.

## 12. Tự thực hành và hướng mở rộng

**Bài 1 — Tiền tố dài nhất:** với một chuỗi truy vấn, tìm độ dài tiền tố dài nhất có đường đi trong trie. Cẩn thận: “tiền tố dài nhất có đường đi” khác “từ hoàn chỉnh dài nhất là tiền tố của truy vấn”. Bài thứ hai phải ghi nhớ nút terminal gần nhất trên đường đi.

**Bài 2 — Top-k theo tần suất:** mỗi từ có điểm phổ biến. Mở rộng nút terminal để lưu điểm và đề xuất cách tìm k từ có điểm cao nhất trong cây con. Giải thích liệu có phải duyệt hết cây con hay không và khi nào cần lưu cache top-k.

**Bài 3 — Trie nén:** nếu đường đi `a → b → c → d` chỉ có một con ở các nút trung gian và không có từ kết thúc tại đó, có thể nén thành cạnh mang chuỗi `"abcd"`. Hãy mô tả thao tác tách cạnh khi thêm từ khác chung phần đầu.

**Bài 4 — Thêm đặc tả Unicode:** quyết định có dùng NFC hay không, có phân biệt hoa/thường hay không, giới hạn độ dài đầu vào, và thứ tự kết quả. Viết test cho các cặp chuỗi nhìn giống nhau nhưng có biểu diễn Unicode khác nhau.

**Câu hỏi tự kiểm tra:** nếu `containsWord(p)` sai nhưng `hasPrefix(p)` đúng, điều đó nói gì về nút cuối đường đi? Nếu xóa một từ là tiền tố của từ khác, điều kiện nào cho phép cắt nhánh? Vì sao số nút trie phụ thuộc vào **số tiền tố phân biệt** chứ không đơn thuần vào số từ?

Trie giải quyết hiệu quả bài toán mà **tiền tố chính là khóa dẫn đường**. Khi nắm rõ hợp đồng dữ liệu, dấu kết thúc từ, bộ đếm cây con, chi phí ánh xạ cạnh và chính sách Unicode, ta có thể xây dựng một chỉ mục tiền tố đúng đắn và chọn biến thể phù hợp cho từng hệ thống.
