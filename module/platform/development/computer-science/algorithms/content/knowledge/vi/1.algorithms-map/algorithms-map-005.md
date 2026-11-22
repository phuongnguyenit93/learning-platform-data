# Vai trò của biểu diễn dữ liệu trong thiết kế lời giải

Trong thiết kế thuật toán, **biểu diễn dữ liệu** là cách chuyển những đối tượng và quan hệ của bài toán thành trạng thái có thể lưu trữ, truy cập và biến đổi trong chương trình. Cùng một dữ liệu đầu vào, ta có thể chọn mảng, tập hợp, bảng băm, danh sách kề, ma trận, các khoảng, bit hoặc những cấu trúc khác. Mỗi lựa chọn làm cho một số thao tác trở nên thuận tiện, nhưng có thể khiến thao tác khác tốn thời gian, bộ nhớ hoặc khó bảo toàn tính đúng đắn.

Trong “bản đồ thuật toán”, cần phân biệt ba lớp:
- **Mô hình bài toán:** đối tượng nào tồn tại, quan hệ nào quan trọng, kết quả nào phải trả về.
- **Biểu diễn dữ liệu:** trạng thái được mã hóa ra sao; thông tin nào được giữ lại; những phép đọc, cập nhật, kiểm tra được hỗ trợ.
- **Thuật toán:** trình tự các bước trên biểu diễn đó nhằm trả kết quả đúng.

Biểu diễn không thay đổi yêu cầu toán học của bài toán. Nó thay đổi **chi phí thực hiện**, khả năng áp dụng thuật toán và những điều kiện phải duy trì để lời giải đúng.

## 1. Từ dữ liệu thực tế đến trạng thái của thuật toán

Giả sử đầu vào là dãy số 4, 1, 4, 7, 2 và nhiệm vụ là trả lời “x có xuất hiện trong dãy không?”.

- Nếu giữ **mảng**, ta bảo toàn thứ tự, số lần xuất hiện và có thể duyệt từng phần tử.
- Nếu chuyển sang **tập hợp**, ta biểu diễn đúng thông tin “có/không có”; phép kiểm tra thành viên thường nhanh hơn khi có nhiều truy vấn, nhưng mất thứ tự ban đầu và số lần lặp.
- Nếu **sắp xếp một bản sao của mảng**, ta dùng tìm kiếm nhị phân mà vẫn giữ được số lần lặp trong bản sao; đổi lại phải trả chi phí sắp xếp và không còn thứ tự đầu vào trong bản đã sắp.

Không có biểu diễn tốt nhất cho mọi mục tiêu: nếu cần vị trí xuất hiện đầu tiên, chỉ tập hợp là không đủ; nếu chỉ cần kiểm tra sự tồn tại nhiều lần, tập hợp có thể phù hợp.

Một biểu diễn tốt cần thỏa đồng thời:
1. **Đủ thông tin:** không làm mất dữ kiện mà đầu ra hoặc các bước tiếp theo cần.
2. **Thao tác phù hợp:** hỗ trợ nhanh những thao tác lặp lại nhiều nhất.
3. **Bất biến rõ ràng:** trạng thái luôn thỏa các quy tắc mà thuật toán dựa vào.
4. **Chi phí chấp nhận được:** gồm dựng cấu trúc, chuyển đổi, truy vấn, cập nhật và bộ nhớ.
5. **Có thể kiểm chứng:** dễ thử với dữ liệu biên và giải thích vì sao biểu diễn tương ứng đúng với mô hình bài toán.

## 2. Biểu diễn quyết định chi phí của các phép toán

Khi chọn biểu diễn, đừng chỉ hỏi “dùng cấu trúc dữ liệu nào?”, mà hãy liệt kê các thao tác thực tế: tìm theo giá trị, tìm theo chỉ số, duyệt phần tử lân cận, kiểm tra cạnh, thêm/xóa, đếm số lần xuất hiện, lấy phần tử nhỏ nhất, xử lý truy vấn khoảng hoặc nối các nhóm.

Ví dụ với n giá trị và q truy vấn kiểm tra sự tồn tại:

| Biểu diễn | Chuẩn bị | Một truy vấn | Tổng thời gian điển hình | Bộ nhớ bổ sung |
| --- | --- | --- | --- | --- |
| Mảng chưa sắp xếp, duyệt tuyến tính | O(1) nếu mảng đã có | O(n) | O(nq) | O(1) |
| HashSet | O(n) kỳ vọng để tạo chỉ mục | O(1) trung bình | O(n + q) kỳ vọng | O(n) |
| Mảng đã sắp xếp + tìm kiếm nhị phân | O(n log n) để sắp xếp | O(log n) | O(n log n + q log n) | tùy cách sắp xếp/bản sao |
| TreeSet | O(n log n) để dựng | O(log n) | O(n log n + q log n) | O(n) |

Các mức trên giả sử truy vấn chỉ yêu cầu **tồn tại hay không**. Chúng không nói rằng HashSet luôn nhanh nhất: với n hoặc q rất nhỏ, chi phí tạo chỉ mục, cấp phát bộ nhớ và boxing của Integer có thể lớn hơn lợi ích. Độ phức tạp O(1) của bảng băm là **trung bình/kỳ vọng**, không phải cam kết cho mọi tình huống va chạm khóa.

Có thể diễn đạt ngân sách thuật toán bằng:

**Tổng thời gian = thời gian chuyển đổi/dựng biểu diễn + tổng chi phí các thao tác trên biểu diễn đó.**

Với nhiều lượt truy vấn, chi phí dựng ban đầu có thể được “thu hồi” qua những lần tra cứu rẻ hơn. Với một lượt quét duy nhất, cấu trúc trung gian có thể không cần thiết.

## 3. Ví dụ Java 17: từ mảng sang tập hợp

Chương trình sau giữ nguyên mảng ban đầu, đồng thời xây một HashSet để trả lời nhiều truy vấn. Hai cách trả lời cùng một ý nghĩa nhưng mang chi phí khác nhau.

~~~java
import java.util.HashSet;
import java.util.Set;

public class RepresentationDemo {
    static boolean containsLinear(int[] values, int target) {
        for (int value : values) {
            if (value == target) {
                return true;
            }
        }
        return false;
    }

    public static void main(String[] args) {
        int[] values = {4, 1, 4, 7, 2};
        int[] queries = {4, 6, 2};

        Set<Integer> membership = new HashSet<>();
        for (int value : values) {
            membership.add(value);
        }

        for (int query : queries) {
            boolean fromArray = containsLinear(values, query);
            boolean fromSet = membership.contains(query);
            if (fromArray != fromSet) {
                throw new AssertionError("Inconsistent representation");
            }
            System.out.println(query + ": " + fromSet);
        }

        System.out.println("originalCount=" + values.length);
        System.out.println("distinctCount=" + membership.size());
    }
}
~~~

Lưu vào tệp **RepresentationDemo.java**, sau đó chạy:

~~~bash
javac RepresentationDemo.java
java RepresentationDemo
~~~

Kết quả chuẩn:

~~~text
4: true
6: false
2: true
originalCount=5
distinctCount=4
~~~

**Vì sao đúng?** Với mọi số nguyên x, x nằm trong HashSet sau quá trình dựng khi và chỉ khi có ít nhất một phần tử của mảng bằng x. Hai phép kiểm tra vì thế trả cùng đáp án cho yêu cầu tồn tại. Giá trị 4 xuất hiện hai lần trong mảng nhưng chỉ một lần trong tập hợp; các số đếm khác nhau là có chủ ý. Nếu bài yêu cầu **đếm số lần xuất hiện**, dùng Map<Integer, Integer> để lưu tần suất, hoặc giữ mảng và đếm, mới là biểu diễn thích hợp.

**Phân tích:** dựng tập hợp tốn O(n) thời gian kỳ vọng và O(n) bộ nhớ; q lần kiểm tra tốn O(q) thời gian trung bình. Cách quét mảng tốn O(nq) trong trường hợp xấu nhất, nhưng chỉ cần O(1) bộ nhớ bổ sung. Ví dụ nhỏ này dùng một phép đối chiếu kết quả để minh họa tính tương đương; kiểm thử đối chiếu không thay thế lập luận tính đúng đắn.

Trong Java, nếu khóa là đối tượng tự định nghĩa, HashSet/HashMap còn phụ thuộc hợp đồng equals() và hashCode(). Một khóa bị thay đổi các thuộc tính dùng tính hash sau khi thêm vào tập hợp có thể khiến tra cứu sai; nên ưu tiên khóa bất biến.

## 4. Ví dụ quan trọng: cùng một đồ thị, ba cách biểu diễn

Cho đồ thị có V đỉnh và E cạnh. Thuật toán cần gì: duyệt hàng xóm của đỉnh, kiểm tra hai đỉnh có nối trực tiếp hay không, hay chỉ duyệt mọi cạnh?

| Biểu diễn | Dung lượng | Liệt kê hàng xóm của u | Kiểm tra cạnh (u, v) | Phù hợp |
| --- | --- | --- | --- | --- |
| Danh sách cạnh | O(V + E) nếu lưu cả tập đỉnh | O(E) khi phải quét các cạnh | O(E) khi quét tuyến tính | Đọc/ghi danh sách cạnh, duyệt toàn bộ cạnh |
| Danh sách kề | O(V + E) | O(deg(u)) | O(deg(u)) nếu tìm tuyến tính | Đồ thị thưa, BFS/DFS |
| Ma trận kề | O(V²) | O(V) | O(1) | Nhiều truy vấn kiểm tra cạnh, đồ thị có số đỉnh vừa phải |

Ở đồ thị vô hướng, mỗi cạnh thường được ghi vào danh sách kề của cả hai đầu mút; bậc deg(u) là số mục kề của u. Với đồ thị có hướng, chỉ thêm theo chiều quy định. Nếu có trọng số, mục kề phải lưu cả **đỉnh đích và trọng số**; nếu cho phép nhiều cạnh song song, một ô Boolean trong ma trận kề sẽ làm mất thông tin đó.

Khi dùng **BFS/DFS**:
- Trên danh sách kề, duyệt mỗi đỉnh và mỗi mục kề một số lần hằng số: **O(V + E)**.
- Trên ma trận kề, để tìm hàng xóm thường phải quét cả V cột cho mỗi đỉnh: **O(V²)**.

Với V = 100.000 và E xấp xỉ V, danh sách kề thường khả thi hơn rất nhiều về bộ nhớ. Ma trận có V² = 10.000.000.000 ô, chưa kể kiểu lưu và overhead; không thể mặc nhiên chọn ma trận chỉ vì kiểm tra cạnh O(1). Ngược lại, nếu V nhỏ và bài có rất nhiều câu hỏi “có cạnh (u, v) không?”, ma trận có thể đơn giản và nhanh hơn.

**Hệ quả thiết kế:** một ý tưởng “duyệt hàng xóm” tưởng như giống nhau sẽ có chi phí khác nhau tùy cách mã hóa đồ thị. Vì vậy biểu diễn và thuật toán phải được chọn cùng nhau.

## 5. Biểu diễn còn quyết định tính đúng đắn

Tính đúng không chỉ nằm ở vòng lặp; nó phụ thuộc việc mã hóa có giữ nguyên ngữ nghĩa của dữ liệu hay không.

### 5.1. Phần tử trùng, thứ tự và danh tính
- Set giữ **tập giá trị phân biệt**; List hoặc mảng có thể giữ thứ tự và bội số xuất hiện.
- Map từ khóa sang một giá trị sẽ ghi đè khi khóa trùng; nếu một khóa có nhiều kết quả, cần Map<K, List<V>> hoặc cấu trúc tương ứng.
- Hai đối tượng có cùng thuộc tính có thể được coi là cùng khóa hay hai thực thể khác nhau tùy yêu cầu. Phải định nghĩa quan hệ bằng nhau trước khi dùng cấu trúc tra cứu.

### 5.2. Trạng thái thiếu, giá trị mặc định và trường hợp biên
- Trong ma trận trọng số, **0 không tự động có nghĩa “không có cạnh”**, vì cạnh trọng số 0 có thể hợp lệ. Cần một biểu diễn thiếu cạnh rõ ràng, ví dụ cờ hiện diện hoặc giá trị sentinel được chứng minh không đụng miền dữ liệu.
- Dùng chỉ số 0-based hay 1-based phải thống nhất với kích thước mảng và cách chuyển mã đỉnh.
- Khoảng **[l, r]** bao gồm r khác khoảng **[l, r)**. Biểu diễn nửa mở thường giúp tính độ dài r - l và ghép các đoạn liền kề, nhưng chỉ đúng khi đã thống nhất quy ước.
- Mã hóa số lượng bằng int có thể tràn nếu tổng, tích hoặc khoảng giá trị lớn; khi cần, chuyển sang long hoặc BigInteger và kiểm tra phép tính trung gian.

### 5.3. Bất biến sau mỗi thao tác
Một cấu trúc được sắp xếp chỉ hỗ trợ tìm kiếm nhị phân đúng nếu **thứ tự sắp xếp vẫn được duy trì**. Danh sách kề của đồ thị vô hướng phải cập nhật hai phía khi thêm cạnh nếu bất biến yêu cầu. Bảng đếm tần suất phải tăng/giảm chính xác khi thêm/xóa phần tử. Nếu cập nhật phá vỡ bất biến, một thuật toán đúng trên lý thuyết vẫn cho kết quả sai.

**Quy tắc kiểm tra:** hãy phát biểu một câu “trạng thái hiện tại tương đương dữ liệu gốc ở khía cạnh nào?” và chứng minh khía cạnh đó được bảo toàn qua bước dựng, mọi phép cập nhật và lúc đọc kết quả.

## 6. Những phép biến đổi biểu diễn thường gặp

**Sắp xếp:** chuyển dãy thành thứ tự tăng/giảm để hỗ trợ tìm kiếm nhị phân, hai con trỏ hoặc xử lý khoảng. Hãy giữ cặp (giá trị, vị trí gốc) nếu đầu ra cần chỉ số ban đầu.

**Lập chỉ mục:** tạo map giá trị → vị trí, set phần tử, hoặc map khóa → danh sách bản ghi để trả lời truy vấn nhanh. Chỉ mục cần được đồng bộ khi dữ liệu gốc thay đổi.

**Nén tọa độ:** với nhiều giá trị nguyên lớn nhưng chỉ k giá trị phân biệt, sắp xếp các giá trị phân biệt và ánh xạ chúng sang chỉ số 0 đến k-1. Điều này hỗ trợ mảng đếm, Fenwick tree/segment tree theo số lượng giá trị phân biệt thay vì theo miền số khổng lồ. Nén theo thứ tự tăng bảo toàn thứ tự so sánh giữa các giá trị; nếu cần khôi phục giá trị gốc, giữ bảng ánh xạ ngược.

**Mảng cộng dồn:** từ mảng a tạo prefix sao cho prefix[0] = 0 và prefix[i + 1] = prefix[i] + a[i]. Khi đó tổng đoạn nửa mở [l, r) bằng prefix[r] - prefix[l]. Dựng O(n), mỗi truy vấn O(1), thêm O(n) bộ nhớ; cập nhật một phần tử sẽ làm hỏng nhiều giá trị prefix nên không thích hợp cho cập nhật động thường xuyên.

**Bitset/bitmask:** mã hóa các cờ Boolean hay một tập chỉ số nhỏ thành các bit để kiểm tra, hợp, giao nhanh. Phải giới hạn số bit theo kiểu lưu và định nghĩa chính xác mỗi vị trí bit tương ứng đối tượng nào.

**Chuyển sang biểu diễn thưa:** thay ma trận gần như toàn số 0 bằng danh sách các mục khác 0 hoặc map tọa độ → giá trị; tiết kiệm bộ nhớ khi số mục có dữ liệu nhỏ hơn rất nhiều tổng số ô, đổi lại một số tra cứu ngẫu nhiên kém trực tiếp hơn.

Một phép biến đổi chỉ có giá trị khi lợi ích của thao tác phía sau bù được chi phí chuyển đổi và khi thông tin đầu ra cần vẫn được giữ đầy đủ.

## 7. Quy trình chọn biểu diễn khi giải bài

1. **Xác định đầu ra và ngữ nghĩa.** Cần kiểm tra tồn tại, đếm số lần, tìm vị trí, đường đi, tổng đoạn, hay thứ tự? Giá trị trùng và thứ tự đầu vào có quan trọng không?
2. **Rút ra miền dữ liệu và ràng buộc.** n, V, E, số truy vấn, giới hạn giá trị, mức độ thưa/dày, dữ liệu có cập nhật không, giới hạn bộ nhớ là gì?
3. **Liệt kê thao tác cùng tần suất.** Truy cập theo chỉ số, tra cứu khóa, lấy hàng xóm, cập nhật, xóa, duyệt toàn bộ — mỗi thao tác xuất hiện bao nhiêu lần?
4. **Đề xuất vài biểu diễn và thuật toán đi cùng.** Không chọn cấu trúc dữ liệu chỉ theo tên quen thuộc. So sánh các phương án dựa trên thao tác thực tế.
5. **Tính tổng chi phí.** Bao gồm tạo cấu trúc, sắp xếp, chuyển mã, mọi truy vấn/cập nhật và bộ nhớ. Phân biệt trung bình với trường hợp xấu nhất.
6. **Phát biểu bất biến và cách chuyển đổi.** Chỉ rõ dữ kiện nào được giữ, dữ kiện nào bị mất, điều kiện để phép toán trên biểu diễn tương đương bài toán gốc.
7. **Kiểm thử biên và đo khi cần.** Dữ liệu rỗng, một phần tử, trùng nhiều, giá trị âm/0, đồ thị không liên thông, dữ liệu rất thưa/rất dày, truy vấn lặp lại, thay đổi dữ liệu; đo hiệu năng nếu nhiều phương án có chi phí lý thuyết gần nhau.

### Một bảng quyết định nhanh

| Nhu cầu nổi bật | Ứng viên nên cân nhắc | Câu hỏi kiểm tra |
| --- | --- | --- |
| Truy cập theo vị trí | Mảng, List | Có cần chèn/xóa giữa thường xuyên không? |
| Kiểm tra tồn tại thường xuyên | HashSet, boolean array, bitset | Miền giá trị có nhỏ, khóa có ổn định không? |
| Đếm số lần xuất hiện | Map khóa → tần suất, mảng đếm | Có cần giữ cả thứ tự xuất hiện không? |
| Dữ liệu luôn có thứ tự | Mảng sắp xếp, TreeSet/TreeMap | Có cập nhật động hay giá trị trùng không? |
| Duyệt hàng xóm trên đồ thị thưa | Danh sách kề | Có trọng số, đa cạnh, hướng không? |
| Rất nhiều truy vấn kiểm tra cạnh, V nhỏ | Ma trận kề | O(V²) bộ nhớ có chấp nhận được không? |
| Tổng của nhiều đoạn, ít cập nhật | Prefix sum | Quy ước biên là [l, r] hay [l, r)? |
| Trạng thái gồm ít cờ Boolean | Bitmask/bitset | Số bit và thứ tự ánh xạ có rõ ràng không? |

Bảng là gợi ý để đặt câu hỏi, không phải quy tắc chọn cứng. Ví dụ, boolean array rất tốt nếu khóa là số nguyên trong miền nhỏ, nhưng có thể lãng phí cực lớn nếu khóa rất thưa trong miền tỷ tỷ giá trị.

## 8. Sai lầm phổ biến và cách tránh

- **Chọn trước cấu trúc, nghĩ sau đến bài toán:** hãy bắt đầu từ phép toán cần nhanh và các ràng buộc.
- **Nhầm trung bình với bảo đảm:** HashMap/HashSet thường tra cứu O(1) trung bình; không lấy mức đó làm chứng minh cho mọi trường hợp xấu nhất.
- **Quên chi phí dựng và chuyển đổi:** sắp xếp O(n log n) để phục vụ duy nhất một truy vấn có thể không đáng.
- **Đánh mất thông tin:** dùng Set cho bài đếm trùng, map một giá trị cho bài một khóa nhiều bản ghi, hoặc bỏ chỉ số ban đầu trước khi cần trả vị trí.
- **Bỏ qua tính thưa/dày:** dùng ma trận V × V cho đồ thị V rất lớn, E rất nhỏ có thể vượt bộ nhớ.
- **Sai quy ước biểu diễn:** lẫn 0-based/1-based, khoảng đóng/nửa mở, cạnh vô hướng/có hướng hoặc sentinel trùng giá trị hợp lệ.
- **Không duy trì cấu trúc sau cập nhật:** thay dữ liệu gốc nhưng quên làm mới chỉ mục, prefix sum hoặc bất biến sắp xếp.
- **Lẫn mô hình toán học với cách lưu trong Java:** số lượng phần tử, kiểu primitive/boxed, equals/hashCode và giới hạn kiểu số đều ảnh hưởng tính đúng và chi phí thực tế.

## 9. Hai tình huống tự kiểm tra

**Tình huống A.** Có 200.000 mã sản phẩm (có thể trùng), cần trả lời 100.000 câu hỏi “mã x có từng xuất hiện không?”, không cần thứ tự hay số lần xuất hiện. Phương án hợp lý: giữ dữ liệu nguồn nếu cần và dựng HashSet mã → tra cứu trung bình nhanh. Nếu bài đổi thành “mã x xuất hiện bao nhiêu lần?”, chuyển sang map tần suất; không thể suy ra số lần từ Set đã loại trùng.

**Tình huống B.** Đồ thị có 50.000 đỉnh, 80.000 cạnh, yêu cầu tìm các đỉnh đạt được từ một đỉnh bắt đầu. Phương án hợp lý: danh sách kề + BFS/DFS, chi phí O(V + E), kể cả đồ thị không liên thông thì chỉ thăm được thành phần đạt tới từ đỉnh bắt đầu. Ma trận kề phải cấp phát O(V²) ô và khiến thao tác tìm hàng xóm tốn O(V), vì thế thường không phù hợp với ràng buộc này.

Khi trả lời cả hai tình huống, lý do quan trọng nhất không phải tên cấu trúc, mà là **biểu diễn giữ đúng thông tin cần thiết và làm rẻ thao tác chi phối tổng chi phí**.

## Kết luận

Thiết kế lời giải có thể xem như một chuỗi quyết định: **mô hình bài toán → biểu diễn dữ liệu → thuật toán → chứng minh đúng → phân tích chi phí**. Thường phải quay lại điều chỉnh biểu diễn khi thấy thuật toán cần thao tác quá đắt hoặc một bất biến khó duy trì. Một thay đổi biểu diễn đúng chỗ đôi khi cải thiện lời giải nhiều hơn việc tối ưu cú pháp hay vòng lặp; nhưng chỉ thực sự tốt khi bảo toàn đầy đủ ý nghĩa dữ liệu mà bài toán yêu cầu.