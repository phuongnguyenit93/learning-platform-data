# Skip list ở mức khái niệm và chi phí thao tác

## 1. Vấn đề: dữ liệu có thứ tự nhưng vẫn cần thêm và xóa

Giả sử ứng dụng lưu các khóa tăng dần và thường xuyên hỏi:

- Có khóa 65 không?
- Khóa gần nhất ở phía dưới hoặc phía trên 65 là gì?
- Những khóa trong một khoảng nằm ở đâu?
- Thêm một khóa mới mà vẫn giữ thứ tự như thế nào?

Danh sách liên kết đã sắp xếp giữ được thứ tự, nhưng khi tìm một khóa ở xa, có thể phải đi qua nhiều nút. Cây tìm kiếm cân bằng là một hướng giải quyết. **Skip list**, thường gọi là danh sách nhảy, giải quyết bằng cách bổ sung nhiều tầng đường đi để bỏ qua các đoạn trung gian.

Trong Java hiện đại, `ConcurrentSkipListMap` và `ConcurrentSkipListSet` là các cấu trúc có thứ tự hỗ trợ truy cập đồng thời. Để hiểu chi phí của chúng, trước hết cần hiểu mô hình skip list, sau đó phân biệt mô hình lý thuyết với hợp đồng của lớp Java cụ thể.

## 2. Một danh sách đầy đủ, thêm các tầng chỉ dẫn thưa hơn

Ở tầng đáy, tất cả khóa xuất hiện theo thứ tự. Các tầng phía trên chỉ có một phần số khóa, tạo những liên kết đi xa hơn.

Ví dụ tự dựng để giải thích:

```text
Tầng 2: HEAD -----------------> 40 -----------------> 80 -> END
Tầng 1: HEAD ------> 20 ------> 40 ------> 60 ------> 80 -> END
Tầng 0: HEAD -> 10 -> 20 -> 30 -> 40 -> 50 -> 60 -> 70 -> 80 -> 90 -> END
```

Mỗi tầng đều giữ cùng quan hệ thứ tự. Tầng cao không chứa thêm khóa nghiệp vụ mới; nó hỗ trợ tìm đường đến vị trí ở tầng thấp.

Có thể hình dung tầng đáy là đường đi qua mọi nhà, còn tầng cao là những chặng đi qua ít điểm hơn. Khi một chặng đi xa sẽ vượt đích, ta hạ xuống tầng chi tiết hơn.

Đây là hình minh họa hợp lệ về ý tưởng, không phải hình dạng cố định mà mọi skip list hoặc mọi lần khởi tạo JDK phải tạo ra. Nghiên cứu gốc của William Pugh trình bày skip list như cấu trúc danh sách có các liên kết vượt qua nút trung gian: [Skip Lists: A Probabilistic Alternative to Balanced Trees](https://epaperpress.com/sortsearch/download/skiplist.pdf).

## 3. Tìm khóa bằng cách đi ngang rồi đi xuống

Tìm vị trí của 65 trên hình:

1. Bắt đầu tại HEAD ở tầng cao nhất.
2. Đi đến 40. Đi tiếp đến 80 sẽ vượt 65 nên dừng đi ngang.
3. Hạ xuống tầng 1 từ vị trí 40, đi đến 60. Liên kết tiếp theo đến 80 vẫn vượt đích.
4. Hạ xuống tầng 0 từ 60. Khóa kế tiếp là 70, nên không có khóa đúng 65.
5. Hai lân cận là 60 ở phía dưới và 70 ở phía trên.

Không cần quay về HEAD sau mỗi lần xuống tầng. Vị trí đã đạt được ở tầng trên cung cấp điểm bắt đầu gần đích cho tầng dưới.

Điểm cốt lõi của phép tìm là giữ một bất biến: không đi qua phía sau vị trí cần tìm theo thứ tự đang dùng. Khi xuống đến tầng đáy, vị trí dừng và nút kế tiếp giúp xác định có đúng khóa hay chỉ có các khóa lân cận.

Với khóa không phải số nguyên, các bước “trước/sau” dựa trên phép so sánh. Skip list không tự có khái niệm khoảng cách số học giữa các đối tượng.

## 4. Tại sao có ngẫu nhiên trong cấu trúc?

Trong mô hình skip list xác suất phổ biến, một nút luôn có mặt ở tầng đáy. Việc nút có được đưa lên tầng tiếp theo hay không được chọn ngẫu nhiên với một xác suất cố định.

Ví dụ giải thích với xác suất đưa lên mỗi tầng là 1/2:

```text
Số nút kỳ vọng có mặt:
Tầng 0: n
Tầng 1: n/2
Tầng 2: n/4
Tầng 3: n/8
...
```

Đây là số lượng kỳ vọng, không phải quy định “cứ nút chẵn phải lên tầng”. Dữ liệu của mỗi lần xây dựng có thể tạo hình dạng khác nhau nhưng vẫn giữ thứ tự và trả kết quả truy vấn đúng.

Từ mô hình trên, có thể tự suy ra hai ý:

- Mật độ giảm theo cấp số nhân, nên số tầng hữu ích tăng theo logarit của n.
- Tổng số lần xuất hiện kỳ vọng của các nút qua các tầng là `n + n/2 + n/4 + ...`, có bậc O(n).

Trong cách biểu diễn cơ bản bằng các liên kết tiến của mỗi nút, số liên kết kỳ vọng trên một nút với xác suất 1/2 là `1 + 1/2 + 1/4 + ... = 2`. Đây là phép tính của mô hình minh họa, không phải cam kết một đối tượng Java thực tế chỉ chiếm đúng hai tham chiếu.

Các cách cài đặt có thể dùng xác suất, giới hạn tầng và cách tổ chức nút khác nhau. Không lấy hằng số của ví dụ để dự đoán chính xác số byte của một map trong JVM.

## 5. Thêm và xóa ở mức ý tưởng

### Thêm khóa mới

Để thêm 65:

1. Tìm vị trí chèn theo thứ tự, đồng thời ghi nhận những nút đứng trước vị trí đó ở các tầng cần thiết.
2. Chọn độ cao của nút mới theo quy tắc của cấu trúc.
3. Nối nút mới vào tầng đáy giữa 60 và 70.
4. Nếu nút xuất hiện ở tầng cao hơn, cập nhật các liên kết tương ứng ở những tầng đó.

### Xóa khóa

Tìm khóa và những liên kết dẫn tới nó, rồi nối các liên kết qua nút kế tiếp để loại nó khỏi cấu trúc đang hoạt động.

Phép tìm vị trí là một phần quan trọng của chi phí. Không nên nói “thêm vào danh sách liên kết là O(1), vậy put của skip list cũng O(1)” khi vị trí cần chèn chưa được biết.

Skip list dùng cân bằng xác suất thay cho duy trì hình dạng bằng các phép xoay như một số cây cân bằng. Các phân tích và mở rộng của mô hình được trình bày trong [A Skip List Cookbook](https://drum.lib.umd.edu/items/56c44671-3973-46b6-9e52-f71dc95af178).

Khi có nhiều luồng, mô tả nối liên kết này chưa đủ để làm một thuật toán đúng. Cần cơ chế phối hợp cập nhật và xử lý tình huống một luồng khác vừa sửa vị trí đã tìm; đó là trách nhiệm của cách cài đặt đồng thời.

## 6. Đọc chi phí thao tác cho đúng

Với n phần tử, dưới mô hình skip list xác suất thông thường và cách chọn tầng phù hợp:

| Thao tác ở mức cấu trúc | Chi phí thường dùng khi phân tích |
| --- | --- |
| Tìm một khóa | O(log n) kỳ vọng |
| Thêm khóa, gồm tìm vị trí | O(log n) kỳ vọng |
| Xóa khóa, gồm tìm vị trí | O(log n) kỳ vọng |
| Duyệt hết tầng đáy | O(n) |
| Tìm đầu một khoảng rồi đọc k kết quả liên tiếp | O(log n + k) kỳ vọng trong mô hình tuần tự |
| Dung lượng cấu trúc | O(n) kỳ vọng |

“Kỳ vọng” nói về phân bố các lựa chọn ngẫu nhiên trong cấu trúc. Nó không có nghĩa cứ mỗi thao tác sẽ mất đúng `log2(n)` bước hoặc một số mili giây cố định.

Một skip list có thể nhận phân bố tầng không thuận lợi. Trong trường hợp xấu, đường tìm có thể gần với việc đi qua danh sách và có chi phí tuyến tính. Vì thế bảo đảm kỳ vọng không giống bảo đảm trường hợp xấu của một cây cân bằng được duy trì chặt chẽ.

Nếu n tăng từ khoảng một nghìn lên khoảng một triệu, số tầng hữu ích chỉ tăng theo logarit. Nhưng đây không phải phép đo tốc độ: số lần so sánh, vị trí bộ nhớ, độ dài khóa và mức tranh chấp vẫn ảnh hưởng đến thời gian thật.

Công thức `O(log n + k)` còn nhắc rằng lấy rất nhiều kết quả phải trả chi phí xử lý từng kết quả. Chỉ có cấu trúc tìm nhanh không làm việc xuất một triệu bản ghi trở thành thao tác hằng số.

## 7. Hợp đồng chi phí của lớp Java cụ thể

Tài liệu [ConcurrentSkipListMap](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/ConcurrentSkipListMap.html) mô tả chi phí trung bình kỳ vọng log(n) cho `containsKey`, `get`, `put`, `remove` và các biến thể. Các thao tác chèn, xóa, cập nhật và truy cập hỗ trợ nhiều luồng thực hiện đồng thời.

Điều đó không biến mọi phương thức thành O(log n):

- Tìm giá trị V theo `containsValue` không có cùng lợi thế chỉ mục khóa như `containsKey`.
- Duyệt để xử lý toàn bộ map vẫn phải xử lý các ánh xạ được thấy.
- Các thao tác hàng loạt phải thực hiện công việc trên nhiều phần tử.
- Comparator tốn kém làm mỗi lần so sánh khóa đắt hơn.

Với [ConcurrentSkipListSet](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/ConcurrentSkipListSet.html), `contains`, `add`, `remove` có chi phí trung bình kỳ vọng log(n). Tài liệu còn lưu ý `size()` không phải thao tác hằng số, cần duyệt phần tử và có thể không phản ánh một trạng thái nhất quán nếu tập hợp đang được sửa đồng thời.

Không suy luận chi phí của một phương thức chỉ từ tên lớp có chữ “SkipList”. Cần xem hợp đồng phương thức và phiên bản JDK dùng thực tế.

## 8. Ví dụ Java: dữ liệu có thứ tự dù cấu trúc tầng không được lộ ra

Chương trình tạo các khóa cách nhau 10 đơn vị để quan sát tìm chính xác, tìm lân cận và lấy khoảng. Không cần biết khóa nào nằm ở tầng nội bộ nào.

Lưu tệp `SkipListConceptDemo.java`:

```java
import java.util.concurrent.ConcurrentNavigableMap;
import java.util.concurrent.ConcurrentSkipListMap;

public class SkipListConceptDemo {
    public static void main(String[] args) {
        ConcurrentNavigableMap<Integer, String> map =
                new ConcurrentSkipListMap<>();

        for (int i = 0; i < 1000; i++) {
            map.put(i * 10, "v" + i);
        }

        System.out.println("first=" + map.firstKey());
        System.out.println("last=" + map.lastKey());
        System.out.println("get.5050=" + map.get(5050));
        System.out.println("floor.5055=" + map.floorEntry(5055));
        System.out.println("ceiling.5055=" + map.ceilingEntry(5055));
        System.out.println("range="
                + map.subMap(5050, true, 5080, false).keySet());
        System.out.println("putIfAbsent.existing="
                + map.putIfAbsent(5050, "replacement"));
        System.out.println("remove.5050=" + map.remove(5050));
        System.out.println("get.after.remove=" + map.get(5050));
    }
}
```

Biên dịch và chạy với JDK 17 trở lên:

```shell
javac --release 17 SkipListConceptDemo.java
java SkipListConceptDemo
```

Stdout:

```text
first=0
last=9990
get.5050=v505
floor.5055=5050=v505
ceiling.5055=5060=v506
range=[5050, 5060, 5070]
putIfAbsent.existing=v505
remove.5050=v505
get.after.remove=null
```

Các kết quả phụ thuộc vào dữ liệu và hợp đồng thứ tự, không phụ thuộc hình dạng ngẫu nhiên của các tầng. Hai lần chạy có thể tổ chức chỉ mục bên trong khác nhau mà vẫn cho cùng stdout.

Trong ví dụ không có luồng khác sửa dữ liệu nên kết quả được xác định như trên. Chương trình giúp quan sát API, chưa phải phép đo hiệu năng hoặc kiểm chứng mọi tình huống đồng thời.

## 9. Chi phí dưới tranh chấp và khi duyệt

Một cài đặt đồng thời phải xử lý việc vị trí vừa tìm có thể thay đổi trước khi cập nhật. Các bước xác minh hoặc thử lại có thể làm độ trễ thực tế khác nhau khi nhiều luồng cùng thao tác trên vùng khóa gần nhau.

Vì vậy không dùng ký hiệu O(log n) để hứa rằng:

- Mọi luồng luôn hoàn thành trong cùng thời gian.
- Tăng số luồng sẽ tăng tốc tuyến tính.
- Một chuỗi nhiều thao tác tự trở thành một giao dịch nguyên tử.
- Duyệt luôn nhận được toàn bộ dữ liệu tại đúng một thời điểm.

Iterator của các lớp skip list đồng thời trong Java có tính nhất quán yếu (`weakly consistent`): không nên hiểu nó là ảnh chụp bất biến của toàn bộ map. Thao tác hàng loạt của `ConcurrentSkipListMap` cũng không được bảo đảm nguyên tử như một khối. Tài liệu lớp còn phân biệt hiệu năng duyệt tăng dần và giảm dần; không mặc định hai hướng có cùng chi phí.

Các chi tiết này thuộc hợp đồng sử dụng. Không cần tự can thiệp vào các tầng liên kết để tối ưu ứng dụng.

## 10. Chọn cấu trúc theo yêu cầu, không theo tên thuật toán

| Yêu cầu | Hướng cân nhắc |
| --- | --- |
| Có thứ tự, truy vấn lân cận, dùng một luồng hoặc đã có cơ chế bảo vệ phù hợp | `TreeMap` / `TreeSet` |
| Có thứ tự và nhiều luồng cùng truy cập/cập nhật | `ConcurrentSkipListMap` / `ConcurrentSkipListSet` |
| Tra cứu theo khóa, không cần thứ tự hay khoảng | Xem xét cấu trúc băm phù hợp với yêu cầu đồng thời |
| Chủ yếu đọc một bộ dữ liệu đã cố định | Xem xét dữ liệu sắp xếp sẵn và cách tìm kiếm thích hợp |

`TreeMap` cung cấp bảo đảm log(n) cho các thao tác cơ bản dựa trên cây đỏ đen, nhưng không tự đồng bộ. Xem [TreeMap](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/TreeMap.html).

Không thể kết luận một cấu trúc luôn nhanh hơn cấu trúc khác chỉ từ cùng bậc O(log n). Khi cần chọn vì hiệu năng, đo đúng tỉ lệ đọc/ghi, phân bố khóa, số luồng và lượng dữ liệu, đồng thời giữ điều kiện đúng đắn tương đương.

## 11. Tự kiểm tra

1. Vì sao tìm trong danh sách liên kết có thứ tự vẫn có thể cần O(n)?
2. Khi một bước nhảy ở tầng cao sẽ vượt mốc, thuật toán làm gì?
3. Tại sao con số n/2 ở tầng 1 là kỳ vọng chứ không phải quy định chính xác?
4. Thêm nút có phải O(1) nếu chưa biết vị trí cần chèn không?
5. Vì sao đọc k kết quả trong khoảng vẫn phải có chi phí theo k?
6. Một luồng duyệt trong khi luồng khác ghi có được mặc định là ảnh chụp toàn bộ cấu trúc không?

Định hướng: (1) vẫn phải đi theo nhiều liên kết để tới vị trí; (2) hạ xuống tầng chi tiết hơn; (3) mức của nút được chọn theo quy tắc xác suất; (4) không, còn chi phí tìm vị trí; (5) phải xử lý từng kết quả; (6) không, phải theo hợp đồng iterator của lớp cụ thể.

Hiểu skip list là hiểu cách thêm các đường đi thưa để tìm vị trí nhanh theo kỳ vọng, rồi đọc riêng các bảo đảm về chi phí và đồng thời của lớp đang dùng.
