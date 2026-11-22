# Cây tìm kiếm cân bằng và chi phí thao tác

## 1. TreeMap giải quyết bài toán gì?

Một chương trình giữ các mốc thời gian cùng dữ liệu của từng mốc. Nó cần tìm đúng một mốc, nhưng cũng cần biết mốc gần nhất phía trước, mốc tiếp theo và những mốc nằm trong một khoảng.

Nếu chỉ cần ánh xạ theo khóa, bảng băm là một lựa chọn quen thuộc. Khi cần **thứ tự khóa và khả năng điều hướng theo thứ tự ấy**, một cấu trúc tìm kiếm có thứ tự trở nên hữu ích.

TreeMap tổ chức ánh xạ bằng một cây tìm kiếm cân bằng. Trong Java, lớp này dựa trên cây đỏ–đen và thực hiện NavigableMap.

Hai ý tưởng cần gắn với nhau:

- **Tìm kiếm nhị phân theo thứ tự khóa** giúp loại bỏ một phần ứng viên sau mỗi lần so sánh.
- **Giữ chiều cao cây có giới hạn** ngăn đường tìm kiếm kéo dài thành một chuỗi tuyến tính.

Tài liệu [TreeMap Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/TreeMap.html) bảo đảm chi phí log(n) cho containsKey, get, put và remove. Để dùng phát biểu ấy đúng, cần hiểu n là số ánh xạ, phép so sánh có chi phí riêng và không phải mọi phương thức của lớp đều có cùng độ phức tạp.

## 2. Cây tìm kiếm nhị phân: mỗi nút giúp chọn một hướng

Một nút chứa khóa, giá trị và các liên kết cấu trúc. Trong mô hình thứ tự tăng thông thường:

- Khóa ở cây con trái nhỏ hơn khóa nút hiện tại.
- Khóa ở cây con phải lớn hơn khóa nút hiện tại.
- So sánh bằng 0 xác định cùng vị trí khóa theo thứ tự của TreeMap.

“Nhỏ hơn” và “lớn hơn” ở đây là theo compareTo hoặc Comparator được chọn, không nhất thiết là thứ tự số học tăng dần.

Hình minh họa:

```text
             40
           /    \
         20      60
        /  \    /  \
       10  30  50  70
```

Để tìm 50 theo thứ tự số tự nhiên:

1. So với 40: lớn hơn, đi phải.
2. So với 60: nhỏ hơn, đi trái.
3. So với 50: bằng, tìm được ánh xạ.

Không cần kiểm tra mọi khóa 10,20,30,40,50 theo một lượt quét danh sách.

Hình là mô hình cây tìm kiếm để giải thích đường đi, **không phải cam kết rằng TreeMap sau một dãy put cụ thể phải có đúng gốc, màu và hình dạng như hình**.

### 2.1. Cây có thứ tự không cần sắp xếp lại toàn bộ sau mỗi get

Cấu trúc đã được tổ chức theo quan hệ so sánh. Get đi theo các liên kết để tìm vị trí, không tạo một danh sách mới rồi sort mỗi lần.

Tương tự, duyệt theo thứ tự có thể đi trái–nút–phải trên cấu trúc đã có. Thứ tự là đặc tính của cách tổ chức cây.

### 2.2. Thứ tự chèn và thứ tự duyệt là hai chuyện khác nhau

Thêm 40,20,60,10 không có nghĩa TreeMap duyệt theo đúng trình tự thêm ấy.

Duyệt đi theo thứ tự khóa của map. Nếu Comparator đảo chiều, chiều “trái/phải” theo phép so sánh cũng phục vụ thứ tự đảo ấy.

Không cần biết màu nút hoặc gốc hiện tại để dùng hợp đồng thứ tự của lớp.

## 3. Vì sao một cây tìm kiếm thường chưa đủ?

Nếu chỉ thêm nút theo quy tắc tìm kiếm mà không cân bằng, một dãy khóa tăng có thể tạo chuỗi:

```text
1
 \
  2
   \
    3
     \
      4
       \
        5
```

Tìm khóa cuối phải đi gần hết chuỗi. Dù mỗi nút vẫn tuân quy tắc tìm kiếm, chiều cao đã cùng bậc với n, nên một lượt tìm có thể là O(n).

Vấn đề không phải dãy khóa sai. Cấu trúc cần có cách giữ hình dạng phù hợp bất kể dữ liệu đến theo thứ tự nào.

### 3.1. Chiều cao quyết định độ dài một đường tìm

Gọi h là chiều cao theo một quy ước thống nhất. Một lượt tìm từ gốc chỉ đi qua số nút tỉ lệ với h + 1.

Nếu h = O(log n), đường ấy ngắn theo cấp logarit. Nếu h = O(n), việc có hai liên kết trái/phải trên mỗi nút không tự giúp được nhiều.

Đây là mối liên hệ cần giữ: **cân bằng → chiều cao có giới hạn → đường tìm có giới hạn**.

### 3.2. Cân bằng không có nghĩa mọi tầng phải đầy

Một cây có thể chưa có đủ 2, 4, 8, ... nút ở từng tầng mà vẫn có chiều cao O(log n).

TreeMap không phải cây nhị phân hoàn hảo, không bắt buộc hai cây con của mọi nút có đúng cùng số phần tử, và không cần dùng một mảng đầy đủ để biểu diễn hình dạng.

Các điều kiện cân bằng được thiết kế để đủ mạnh cho giới hạn chiều cao, đồng thời vẫn có thể duy trì khi thêm hoặc xóa.

## 4. Cây đỏ–đen giữ chiều cao bằng các bất biến

Ở mô hình chuẩn:

1. Mỗi nút mang màu đỏ hoặc đen.
2. Gốc đen; lá NIL quy ước là đen.
3. Nút đỏ không có con đỏ.
4. Các đường từ một nút tới lá NIL có cùng số nút đen.

Với n nút dữ liệu, các điều kiện này dẫn tới h ≤ 2 log₂(n + 1), theo quy ước chiều cao chuẩn. Đếm nút thay vì cạnh có thể lệch một hằng số.

Lập luận cốt lõi: không có hai nút đỏ liên tiếp, nên số tầng chỉ tăng tối đa theo một hệ số hằng so với chiều cao đen; cây con với chiều cao đen b cần ít nhất 2^b − 1 nút. Suy ra chiều cao cùng bậc logarit.

Có thể đối chiếu phần chứng minh trong [bài giảng cây của Cornell CS2110](https://www.cs.cornell.edu/courses/cs2110/2018su/lectures/Lecture9-Trees.pdf). Điều cần dùng trong bài là giới hạn chiều cao, không phải học màu như một thuộc tính của dữ liệu nghiệp vụ.

### 4.1. Màu không tham gia so sánh khóa

Màu phục vụ duy trì cấu trúc. Nó không làm một khóa “ưu tiên hơn”, không thay Comparator và không phải thứ tự mới của map.

Hai cây có hình dạng hoặc màu khác nhau vẫn có thể biểu diễn cùng tập ánh xạ và cùng thứ tự khóa.

### 4.2. Java không yêu cầu người gọi tự quản lý màu

Các thao tác put/remove của TreeMap duy trì cấu trúc bên trong. Người dùng không cần cài các trường màu vào lớp khóa hoặc truyền thông tin cân bằng khi gọi API.

Nguồn [TreeMap.java OpenJDK 17u](https://raw.githubusercontent.com/openjdk/jdk17u/master/src/java.base/share/classes/java/util/TreeMap.java) có các đường xoay và sửa cân bằng sau thêm/xóa. Chúng giúp giải thích cơ chế; mã ứng dụng không dựa vào tên hàm private để sử dụng map.

## 5. Xoay và đổi màu: đổi hình dạng nhưng giữ thứ tự

Một phép xoay trái khái niệm:

```text
       x                         y
      / \                       / \
     A   y       xoay trái     x   C
        / \       ---->      / \
       B   C                A   B
```

A, B, C là các cây con. Trước và sau phép xoay, thứ tự duyệt vẫn là:

```text
A → x → B → y → C
```

Các liên kết được tổ chức lại cục bộ, trong khi quan hệ thứ tự giữa các vùng được giữ. Đổi màu đi kèm giúp khôi phục các bất biến cần thiết.

### 5.1. Một phép xoay cục bộ không phải sắp xếp toàn bộ map

Phép xoay cập nhật một số liên kết quanh các nút liên quan. Không cần lấy tất cả khóa ra rồi sort lại.

Cả quy trình sửa sau thao tác có thể đi qua các tổ tiên để xử lý những vi phạm còn lại. Giới hạn chiều cao giúp phần công việc đó vẫn có giới hạn thích hợp.

### 5.2. Không cần cây luôn có hình dạng duy nhất

Các lịch thêm/xóa khác nhau có thể dẫn tới những bố trí hợp lệ khác nhau.

Hợp đồng công khai không yêu cầu một khóa cụ thể luôn là gốc hoặc một lần put nhất định luôn thực hiện đúng số phép xoay nào đó.

Kiểm thử tính đúng nên kiểm tra ánh xạ, thứ tự và hành vi API. Nếu đo chi tiết cài đặt, phải ghi rõ phiên bản và mục tiêu của phép quan sát.

## 6. Get, put và remove đi qua cây như thế nào?

### 6.1. Get và containsKey

Bắt đầu từ gốc, so sánh khóa cần tìm với khóa hiện tại:

- Kết quả âm: đi tới cây con trái.
- Kết quả dương: đi tới cây con phải.
- Kết quả 0: đã tìm thấy vị trí khóa theo thứ tự.
- Gặp liên kết rỗng: không có khóa cần tìm.

Một đường như vậy có độ dài O(log n) khi cây được duy trì cân bằng.

ContainsKey không cần duyệt mọi giá trị. Nó kiểm tra sự tồn tại theo cùng cấu trúc chỉ mục khóa.

### 6.2. Put khóa đã có

Nếu phép so sánh xác định một khóa tương đương đã có, put thay giá trị gắn với ánh xạ đó. Size không tăng.

Việc tìm được vị trí vẫn có chi phí theo đường cây; “chỉ thay một giá trị” không làm cả lời gọi trở thành O(1) nếu trước đó vẫn phải tìm khóa.

Thứ tự của TreeMap phải nhất quán với equals nếu muốn tuân đầy đủ hợp đồng Map chung. Không dùng một Comparator thiếu tiêu chí khiến hai khóa nghiệp vụ khác nhau bị xem bằng 0 rồi mong cây tự tách chúng.

### 6.3. Put khóa mới

Lời gọi tìm vị trí thích hợp, nối thêm nút, rồi thực hiện phần duy trì cân bằng nếu cần.

Tổng công việc có đường tìm và phần điều chỉnh cấu trúc. Đây là lý do O(log n) vẫn phù hợp khi thêm khóa, kể cả khi đầu vào đã tăng hoặc giảm có thứ tự.

Không phải chỉ thêm lá rồi để cây lệch vô hạn.

### 6.4. Remove có cả tìm và sửa cấu trúc

Trước hết cần tìm nút theo khóa. Sau khi xác định được nút, xử lý xóa tùy số con và tiếp tục sửa các bất biến nếu cần.

Với nút có hai con, một hướng xử lý là dùng phần tử kế tiếp theo thứ tự để đưa bài toán về trường hợp xóa đơn giản hơn. Nguồn OpenJDK 17u có đường xử lý này.

Không suy ra remove chắc O(1) vì “đã biết khóa”. Biết giá trị khóa chưa có nghĩa đang giữ trực tiếp vị trí nút để bỏ qua tìm kiếm, và phần sửa sau xóa cũng có chi phí.

## 7. Bảng chi phí: phân biệt hợp đồng với phân tích cài đặt

Bảng dưới dùng n là số ánh xạ và giả định phép so sánh/so bằng có chi phí hằng số, dữ liệu và thứ tự được dùng đúng hợp đồng.

| Thao tác | Chi phí theo mô hình thông thường | Cơ sở |
| --- | --- | --- |
| containsKey, get, put, remove | O(log n) | Bảo đảm được nêu trong tài liệu TreeMap |
| firstKey, lastKey | O(log n) ở trường hợp xấu | Trong OpenJDK, đi tới biên trái/phải của cây |
| floor, ceiling, lower, higher theo khóa | O(log n) theo đường cây | Tìm vị trí lân cận trong cây cân bằng |
| pollFirstEntry, pollLastEntry | O(log n) | Tìm biên rồi xóa/sửa cây |
| Duyệt toàn bộ entry bằng iterator | O(n) | Đi theo thứ tự các nút, không tìm lại từ gốc cho mỗi entry |
| containsValue | O(n) ở trường hợp xấu | Cây được chỉ mục theo khóa, không phải giá trị |
| size của TreeMap gốc | O(1) trong cài đặt đối chiếu | Đọc số lượng được lưu |
| Duyệt k kết quả trong một khoảng khóa | O(log n + k) theo đường iterator | Định vị phần bắt đầu rồi thăm kết quả |

Với n rất nhỏ hoặc bằng 0, có thể viết dạng log(n + 1) để tránh đọc log(0). Ký hiệu ở bảng mô tả cách tăng trưởng, không phải số nano giây của một lời gọi.

Các dòng phân tích cài đặt không nên bị biến thành một cam kết chung cho mọi implementation của NavigableMap hoặc SortedMap. Khi dùng lớp khác, phải đọc hợp đồng của lớp ấy.

### 7.1. Gốc không nhất thiết là nhỏ nhất hoặc lớn nhất

Cân bằng giúp gốc có vai trò phân chia vùng, không có nghĩa gốc giữ khóa đầu hay khóa cuối.

Trong cài đặt được đối chiếu, tìm khóa nhỏ nhất có thể phải đi hết một đường trái, và tìm khóa lớn nhất đi một đường phải. Không mặc định hai thao tác ấy O(1) chỉ vì map “đã có thứ tự”.

### 7.2. Một view nhỏ không tự có mọi thao tác O(1)

SubMap là một view theo khoảng, không phải một cây mới độc lập chứa sẵn riêng từng kết quả.

Ví dụ, size của view giới hạn trong nguồn OpenJDK 17u có thể cần duyệt để đếm, và có cơ chế nhớ kết quả theo trạng thái sửa đổi. Không suy từ size của TreeMap gốc sang một cam kết rằng mọi lần gọi size trên mọi view đều O(1).

Cũng không cộng O(log n) cho từng phần tử nếu đang dùng một iterator liên tiếp của view. Phần bắt đầu và phần duyệt kết quả có vai trò khác nhau.

## 8. Ví dụ Java 17: chèn tăng dần và đếm so sánh khi tìm

Chương trình dùng Comparator đúng theo thứ tự số, có thêm bộ đếm số lần compare được gọi. Bộ đếm không tham gia quyết định thứ tự.

Map được nạp bằng các khóa tăng dần. Nếu đây là cây tìm kiếm không cân bằng đơn giản, đầu vào như vậy dễ tạo chuỗi dài. TreeMap duy trì cơ chế cân bằng của nó.

Lưu thành **TreeMapSearchCost.java**:

```java
import java.util.ArrayList;
import java.util.Comparator;
import java.util.Map;
import java.util.TreeMap;

public class TreeMapSearchCost {
    static final class CountingOrder implements Comparator<Integer> {
        int calls;

        @Override
        public int compare(Integer left, Integer right) {
            calls++;
            return Integer.compare(left, right);
        }

        void reset() {
            calls = 0;
        }
    }

    public static void main(String[] args) {
        System.out.println("ascending inserts; observed comparison counts");
        for (int n : new int[] {31, 127, 1023, 8191}) {
            CountingOrder order = new CountingOrder();
            TreeMap<Integer, Integer> map = new TreeMap<>(order);
            for (int key = 0; key < n; key++) {
                map.put(key, key * 10);
            }
            order.reset();
            Integer value = map.get(n - 1);
            System.out.println("n=" + n + "; value=" + value
                    + "; get comparisons=" + order.calls);
        }

        Map<Integer, String> sample = new TreeMap<>();
        for (int key : new int[] {40, 20, 60, 10, 30, 50, 70}) {
            sample.put(key, "v" + key);
        }
        System.out.println("get 30: " + sample.get(30));
        System.out.println("put old 30: " + sample.put(30, "updated"));
        System.out.println("remove 40: " + sample.remove(40));
        System.out.println("keys after removal: " + new ArrayList<>(sample.keySet()));
        System.out.println("value after update: " + sample.get(30));
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 TreeMapSearchCost.java
java TreeMapSearchCost
```

Stdout quan sát:

```text
ascending inserts; observed comparison counts
n=31; value=300; get comparisons=8
n=127; value=1260; get comparisons=12
n=1023; value=10220; get comparisons=18
n=8191; value=81900; get comparisons=24
get 30: v30
put old 30: v30
remove 40: v40
keys after removal: [10, 20, 30, 50, 60, 70]
value after update: updated
```

Các chương trình trong bài được biên dịch với --release 17 và chạy trên OpenJDK 24.0.2. Cờ --release chọn mức API/ngôn ngữ và bytecode đích; nó không biến JVM chạy thành Java 17.

### 8.1. Đọc bộ đếm đúng phạm vi

Khi n tăng từ 31 lên 8.191, số phép so sánh trong lượt tìm khóa cuối được quan sát tăng từ 8 lên 24, không thành một lượt đi qua 8.191 khóa.

Những con số chính xác này thuộc môi trường và lịch thao tác đã nêu. Một cài đặt hoặc hình dạng cây hợp lệ khác có thể có số khác mà vẫn đáp ứng O(log n).

Chương trình không dùng reflection để đo chiều cao hoặc xem màu. Nó quan sát các lời gọi Comparator được truyền vào công khai.

### 8.2. Đây chưa phải phép đo toàn bộ thời gian

Counter không đếm cấp phát, xoay, đổi màu, đi theo liên kết, quản lý bộ nhớ hoặc thời gian CPU cho các phần khác.

Đếm so sánh giúp làm rõ đường tìm; nó không biến toàn bộ chi phí put/remove thành đúng số lần compare. Lý do những thao tác ấy có giới hạn còn đến từ thuật toán duy trì cân bằng.

Không lấy một bộ đếm bằng 24 rồi diễn giải thành thời gian bằng 24 đơn vị tùy ý.

### 8.3. Nội dung vẫn phải đúng sau cập nhật và xóa

Phần map nhỏ kiểm tra get, put khóa cũ và remove, rồi duyệt các khóa còn lại.

Put 30 trả về v30 và thay giá trị thành updated. Remove 40 bỏ ánh xạ ấy. Dãy cuối vẫn tăng theo khóa: 10,20,30,50,60,70.

Không cần biết sau các thao tác ấy nút nào đang là gốc để xác nhận kết quả công khai.

## 9. Duyệt toàn cây không phải n lần tìm kiếm từ gốc

Một iterator có thể tìm nút đầu rồi tiếp tục qua phần tử kế tiếp theo thứ tự.

Trong OpenJDK 17u, các nút có liên kết con và cha; đường successor giúp đi tới phần tử kế tiếp mà không gọi một phép get mới cho mỗi khóa.

### 9.1. Một bước next có thể leo nhiều liên kết

Nếu nút có cây con phải, phần tử kế tiếp có thể là nút ngoài cùng trái của cây con ấy.

Nếu không, đường đi có thể phải leo lên tổ tiên thích hợp. Một bước riêng lẻ không nhất thiết chỉ thực hiện đúng một phép gán liên kết.

Nhưng xét cả lượt duyệt đầy đủ, tổng công đi qua các liên kết được phân bổ theo số nút. Ta không trả lại toàn bộ giá tìm từ gốc cho mỗi entry.

Vì thế có thể phân biệt:

- Chi phí trường hợp xấu của một bước đi kế tiếp.
- Chi phí trung bình phân bổ của các bước trong cả lượt duyệt.
- Chi phí tổng của việc duyệt toàn bộ n entry.

### 9.2. Duyệt entrySet thường thể hiện trực tiếp công việc hơn

Nếu cần cả khóa và giá trị, lấy chúng từ Map.Entry đang được duyệt.

Một vòng keySet rồi get từng khóa thực hiện thêm những lượt tìm kiếm theo khóa. Tính tổng có thể có phần O(n log n), dù chính iterator đang đi qua các khóa theo thứ tự.

Tương tự, tự gọi higherKey từ đầu cho từng bước là một dãy truy vấn điều hướng riêng. Không tự đồng nhất nó với đường iterator có trạng thái kế tiếp.

### 9.3. Xử lý kết quả cũng là công việc thật

Muốn xuất n ánh xạ thì ít nhất cần thăm n kết quả. Cây cân bằng không thể biến việc đọc mọi giá trị thành O(log n).

Nếu thân vòng lặp xử lý dữ liệu có kích thước khác nhau, hãy cộng cả chi phí xử lý ấy. O(n) của phần duyệt cấu trúc không phải bảo đảm mọi công việc trong vòng lặp đều hằng số.

## 10. ContainsValue không hưởng cùng chỉ mục với get

TreeMap tổ chức cây theo khóa. Khi chỉ cho một giá trị cần tìm, không có cơ sở dùng quan hệ khóa để quyết định bỏ cây con nào.

Trong cài đặt được đối chiếu, containsValue đi theo các entry để so giá trị và có thể dừng khi tìm thấy.

Nếu giá trị không có, có thể phải kiểm tra đủ n ánh xạ. Nếu giá trị xuất hiện gần đầu lượt duyệt, có thể dừng sớm hơn. O(n) ở đây là giới hạn trường hợp xấu.

Nếu một ứng dụng cần tra theo cả khóa lẫn giá trị rất thường xuyên, phải xem xét mô hình chỉ mục riêng phù hợp với quan hệ một–nhiều hoặc nhiều–nhiều của dữ liệu. Không giả định TreeMap đã tự có một cây thứ hai cho mọi giá trị.

Giá trị cũng có thể trùng ở nhiều khóa. Một thứ tự khóa không tạo quy tắc loại trùng giá trị.

## 11. Ví dụ Java 17: duyệt, tìm giá trị và một khoảng nhỏ

Chương trình tiếp theo tách hai loại bộ đếm:

- CountingOrder đếm so sánh khóa.
- Value.equalityChecks đếm phép equals trên giá trị được tìm.

Các bộ đếm chỉ phục vụ thí nghiệm một luồng, không được dùng để thay đổi kết quả so sánh hoặc so bằng.

Lưu thành **TreeMapTraversalCost.java**:

```java
import java.util.ArrayList;
import java.util.Comparator;
import java.util.Map;
import java.util.NavigableMap;
import java.util.TreeMap;

public class TreeMapTraversalCost {
    static final class CountingOrder implements Comparator<Integer> {
        int calls;

        @Override
        public int compare(Integer left, Integer right) {
            calls++;
            return Integer.compare(left, right);
        }
    }

    record Value(int number) {
        static int equalityChecks;

        @Override
        public boolean equals(Object other) {
            equalityChecks++;
            return other instanceof Value value && number == value.number;
        }

        @Override
        public int hashCode() {
            return Integer.hashCode(number);
        }
    }

    public static void main(String[] args) {
        CountingOrder order = new CountingOrder();
        TreeMap<Integer, Value> map = new TreeMap<>(order);
        for (int key = 0; key < 1000; key++) {
            map.put(key, new Value(key));
        }

        order.calls = 0;
        long sum = 0;
        int visited = 0;
        for (Map.Entry<Integer, Value> entry : map.entrySet()) {
            sum += entry.getValue().number();
            visited++;
        }
        System.out.println("full visited: " + visited);
        System.out.println("full sum: " + sum);
        System.out.println("observed full key comparisons: " + order.calls);

        Value.equalityChecks = 0;
        boolean found = map.containsValue(new Value(-1));
        System.out.println("missing value found: " + found);
        System.out.println("observed value equality checks: " + Value.equalityChecks);

        NavigableMap<Integer, Value> window = map.subMap(450, true, 455, false);
        long rangeSum = 0;
        int rangeVisited = 0;
        for (Map.Entry<Integer, Value> entry : window.entrySet()) {
            rangeSum += entry.getValue().number();
            rangeVisited++;
        }
        System.out.println("range keys: " + new ArrayList<>(window.keySet()));
        System.out.println("range visited: " + rangeVisited);
        System.out.println("range sum: " + rangeSum);
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 TreeMapTraversalCost.java
java TreeMapTraversalCost
```

Stdout trên môi trường đã nêu:

```text
full visited: 1000
full sum: 499500
observed full key comparisons: 0
missing value found: false
observed value equality checks: 1000
range keys: [450, 451, 452, 453, 454]
range visited: 5
range sum: 2260
```

### 11.1. Không gọi Comparator không có nghĩa không làm việc

Vòng entrySet đã thăm 1.000 entry và cộng được 499.500. Bộ đếm so sánh khóa bằng 0 trên môi trường này vì iterator đi theo cấu trúc thứ tự sẵn có.

Nó vẫn phải di chuyển qua các nút, lấy giá trị và cộng tổng. Không suy ra O(1) hoặc “không tốn thời gian” từ việc một loại hàm không được gọi.

### 11.2. Giá trị không có cần kiểm tra đủ dữ liệu

Map chứa các Value từ 0 tới 999. Tìm Value(-1) không thấy và bộ đếm equals là 1.000.

Kết quả làm rõ rằng chỉ mục đang theo khóa, không phải theo thành phần number của Value.

Một số phép so bằng có thể tốn hơn hằng số, nên chi phí thực còn phụ thuộc cách giá trị được biểu diễn.

### 11.3. Khoảng khóa chỉ đưa ra kết quả thuộc khoảng

SubMap dùng cận dưới 450 được lấy và cận trên 455 không được lấy, nên khóa là 450 tới 454, có 5 kết quả và tổng bằng 2.260.

View không tự sao chép toàn bộ 1.000 ánh xạ. Khi duyệt khoảng, mô hình công việc có phần định vị đầu và phần đi qua những entry thuộc kết quả.

Chương trình không thay đổi map trong khi duyệt. Không cần mở thêm một bài toán iterator bị sửa cấu trúc để quan sát chi phí ở đây.

### 11.4. Giới hạn của phép quan sát

Các số bộ đếm thuộc đường thực thi đã chạy, không phải yêu cầu rằng mọi phiên bản TreeMap phải gọi equals hoặc compare đúng cùng số lần.

Hợp đồng dữ liệu và giới hạn độ phức tạp là phần cần giữ. Thí nghiệm hỗ trợ giải thích cơ chế; nó không thay cho việc đọc hợp đồng và phân tích thuật toán.

## 12. Chi phí Comparator là một phần của thời gian thật

Khi viết O(log n), ta thường xem một phép so sánh khóa là hằng số. Giả định ấy cần được nói rõ.

Nếu một lần so sánh tốn S, phần chi phí so sánh có thể được mô tả bằng O(S log n) trong mô hình S là một chặn thích hợp cho các phép so sánh liên quan.

### 12.1. Chuỗi dài không giống số nguyên nhỏ

So sánh hai chuỗi có thể cần xét một đoạn ký tự chung trước khi tìm được khác biệt. Nếu độ dài liên quan là L, phần so sánh có thể phụ thuộc L.

Một cây có ít tầng không làm chi phí xử lý từng khóa dài tự biến mất.

Nếu Comparator phân tích lại văn bản hoặc tính một đại lượng đắt ở mỗi lượt, phần công việc ấy cũng được lặp theo số lần so sánh. Có thể cân nhắc biểu diễn khóa hoặc chuẩn bị dữ liệu trước, miễn giữ nguyên quy tắc thứ tự và hợp đồng khóa.

### 12.2. Comparator phải tạo một quan hệ thứ tự đúng

Một Comparator phải tuân các yêu cầu về dấu, tính bắc cầu và các trường hợp được xem bằng nhau theo hợp đồng của nó. Đối chiếu [Comparator Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Comparator.html).

Dùng Integer.compare thay cho phép trừ trực tiếp giúp tránh một lỗi tràn số phổ biến khi so số nguyên.

Không dùng số ngẫu nhiên, thời gian hiện tại hoặc trạng thái thay đổi tùy lần gọi để quyết định cùng một cặp khóa lúc lớn lúc nhỏ.

Cây cân bằng chỉ bảo vệ hình dạng theo thuật toán. Nó không sửa được một quan hệ thứ tự tự mâu thuẫn.

### 12.3. Không sửa thuộc tính dùng để sắp xếp khi khóa đang nằm trong cây

Nếu một đối tượng khóa đổi trường mà Comparator sử dụng, vị trí cũ có thể không còn phù hợp với thứ tự mới. Sau đó tìm kiếm hoặc điều hướng có thể cho kết quả không như mong đợi.

Việc cây vẫn còn nhiều nút và chiều cao vẫn thấp không chứng minh khóa đang được sử dụng đúng.

Giữ thông tin định danh/thứ tự ổn định; nếu cần thay đổi khóa logic, xử lý theo một quy trình bỏ ánh xạ cũ và thêm ánh xạ mới phù hợp với hợp đồng ứng dụng.

## 13. Nạp nhiều phần tử và sao chép: không áp một công thức cho mọi đường

### 13.1. N lần put riêng lẻ thường cho O(n log n)

Nạp n khóa mới vào một cây rỗng bằng các lời gọi put riêng lẻ có tổng chi phí O(n log n) theo mô hình so sánh hằng số.

Đầu vào đã sắp xếp không làm cây đỏ–đen biến thành chuỗi, nhưng cũng không tự biến một vòng n lần put thành một API dựng cây tuyến tính.

Từng lần vẫn có đường tìm vị trí cùng công duy trì cấu trúc tương ứng.

### 13.2. Nguồn đã sắp xếp có thể cho một đường dựng riêng

Constructor TreeMap nhận SortedMap được tài liệu mô tả là chạy tuyến tính và giữ thứ tự của nguồn.

Cài đặt OpenJDK 17u còn có đường buildFromSorted để dựng cấu trúc từ dữ liệu đã có thứ tự; putAll vào một map rỗng có những điều kiện tối ưu riêng liên quan loại nguồn và Comparator.

Vì vậy không phát biểu “mọi cách sao chép n entry vào TreeMap đều chắc mất n log n”. Phải biết constructor hoặc đường thao tác nào đang được dùng.

Nếu đối số chỉ là một Map bất kỳ, không được tự cho rằng nguồn đã có thứ tự đúng với Comparator của đích. Những overload và điều kiện khác nhau có ý nghĩa thật.

### 13.3. Kiểm tra lợi ích tổng thể

Nếu phải sort dữ liệu chưa có thứ tự chỉ để dùng một đường dựng tuyến tính, phần sort ấy cũng có chi phí. Không bỏ nó khỏi tổng rồi kết luận toàn bộ quy trình đã thành O(n).

Một tối ưu có lợi khi đầu vào đã phù hợp hoặc khi công chuẩn bị được dùng cho mục đích khác; cần tính toàn bộ đường dữ liệu.

## 14. Những điều cây cân bằng không tự cung cấp

### 14.1. Không có truy cập phần tử thứ k theo chỉ số chỉ vì cây cân bằng

TreeMap có thứ tự khóa, nhưng không có API get(index) như List để lấy mục thứ k theo vị trí.

Một cây thống kê thứ tự có thể lưu thêm số nút của từng cây con để phục vụ một loại truy vấn khác. Không tự gán khả năng đó cho TreeMap chỉ vì cũng dùng cây cân bằng.

Nếu tự duyệt tới vị trí k, công việc phải xét số bước duyệt ấy. Chỉ định vị bằng khóa và định vị bằng thứ hạng là hai yêu cầu khác nhau.

### 14.2. Không có chi phí bộ nhớ bằng một mảng khóa–giá trị

Nút cây cần giữ liên kết và thông tin phục vụ cân bằng bên cạnh khóa, giá trị. Bố trí đối tượng, các tham chiếu và tính cục bộ bộ nhớ có thể ảnh hưởng hiệu năng thực tế.

Không biến O(log n) thành kết luận rằng TreeMap luôn nhanh hoặc tiết kiệm bộ nhớ hơn mọi cấu trúc khác.

TreeMap cũng không có tham số initialCapacity kiểu bảng băm để người gọi chọn số bucket. Cơ chế tăng cấu trúc bằng nút và duy trì cân bằng khác với tăng một bảng bucket.

### 14.3. Không tự an toàn đa luồng

Cân bằng là một thuộc tính thuật toán của cấu trúc, không phải cơ chế phối hợp các luồng.

TreeMap không tự đồng bộ. Khi dùng chung với các thao tác sửa cấu trúc, cần một thiết kế phối hợp phù hợp; fail-fast không thay thế trách nhiệm ấy.

Không lấy việc các get/put có giới hạn logarit làm bằng chứng chúng tự nguyên tử hoặc an toàn trong mọi chuỗi thao tác đồng thời.

## 15. Chọn TreeMap theo loại truy vấn

| Yêu cầu chính | Điều cần cân nhắc |
| --- | --- |
| Tìm theo khóa và cần giữ thứ tự khóa | TreeMap cung cấp cả ánh xạ và thứ tự |
| Cần floor/ceiling, phần tử trước/sau hoặc khoảng khóa | Cây có thứ tự phục vụ trực tiếp những truy vấn này |
| Chỉ cần tìm theo khóa, không cần thứ tự | So sánh với cấu trúc băm theo điều kiện dữ liệu và hiệu năng |
| Cần thứ tự chèn | Thứ tự khóa của TreeMap không biểu diễn yêu cầu ấy |
| Cần lấy mục thứ k theo chỉ số | Cần xem mô hình dữ liệu/API khác phù hợp |
| Dữ liệu hầu như bất biến, chủ yếu duyệt hoặc tìm | Có thể đánh giá cả cách lưu liên tục đã sắp xếp theo toàn bộ quy trình |

Không chọn chỉ bằng một ký hiệu O. Cần xét loại truy vấn, chi phí khóa, tần suất thêm/xóa, bộ nhớ và khối lượng thực tế.

Nếu đo hiệu năng, tách công dựng dữ liệu khỏi công truy vấn khi câu hỏi cần tách. Dùng kết quả truy vấn thật, làm nóng JVM và tránh lấy thời gian in console làm phép đo thao tác cấu trúc.

## 16. Lỗi thường gặp và cách sửa

| Hiểu nhầm | Cách hiểu đúng |
| --- | --- |
| Có hai nhánh nên tìm luôn log n | Cần chiều cao được giữ có giới hạn |
| Chèn tăng dần làm mọi TreeMap lệch thành chuỗi | Cây đỏ–đen duy trì cân bằng khi cập nhật |
| Cân bằng nghĩa hai bên có đúng cùng số nút | Chỉ cần các bất biến đủ để chặn chiều cao |
| Gốc luôn là khóa nhỏ nhất | Biên trái/phải và gốc là các vai trò khác nhau |
| Đã biết khóa nên remove O(1) | Vẫn cần tìm vị trí và duy trì cấu trúc |
| Mọi phương thức TreeMap đều log n | Duyệt toàn bộ và containsValue có chi phí khác |
| Iterator next giống một get từ gốc | Iterator có trạng thái để đi tiếp qua cấu trúc |
| Không gọi Comparator khi duyệt nghĩa duyệt miễn phí | Vẫn phải thăm và xử lý các entry |
| Comparator đắt không ảnh hưởng kết luận thời gian | Chi phí so sánh là một phần của tổng |
| Cây tự sửa được khóa thay trường sắp xếp | Khóa vẫn phải ổn định theo hợp đồng |
| N lần put lên dữ liệu đã sắp xếp luôn là O(n) | Phân biệt vòng put với đường dựng chuyên biệt |
| Số compare trong một lần chạy là hằng số API | Đó là quan sát môi trường, không phải cam kết số lần chính xác |
| Có thứ tự là có truy cập theo chỉ số | Thứ tự khóa không tự tạo truy vấn thứ hạng |
| Cân bằng đồng nghĩa an toàn nhiều luồng | Đồng bộ là một trách nhiệm khác |

## 17. Bài tập tự kiểm tra có lời giải

### Bài 1: Một cây tìm kiếm bị lệch

Một cây tìm kiếm không cân bằng nhận các khóa 1 tới n theo thứ tự tăng và chỉ nối khóa mới ở phía phải. Tìm n có thể tốn bao nhiêu?

**Lời giải:** O(n), vì phải đi qua một chuỗi có chiều dài cùng bậc n. Quy tắc tìm kiếm không tự bảo đảm chiều cao logarit.

### Bài 2: Cây đỏ–đen đã có thứ tự đầu vào

TreeMap nhận n khóa tăng dần bằng các lần put. Có được kết luận lượt get cuối chắc là O(n) chỉ vì đầu vào tăng dần không?

**Lời giải:** không. TreeMap duy trì cơ chế cân bằng; hợp đồng của nó bảo đảm chi phí log(n) cho các thao tác cơ bản được nêu.

### Bài 3: Thăm mọi ánh xạ

Cần tính tổng giá trị của n entry. Cây cân bằng có làm tổng công duyệt chỉ còn O(log n) không?

**Lời giải:** không. Phải thăm n kết quả, nên phần duyệt toàn bộ là O(n), chưa kể chi phí xử lý từng giá trị.

### Bài 4: Tìm theo giá trị không có

TreeMap có n khóa và không chứa giá trị v. ContainsValue(v) có dùng cùng đường chỉ mục khóa như get(key) không?

**Lời giải:** không. Không có khóa để chọn hướng theo quan hệ sắp xếp. Trường hợp xấu cần kiểm tra n giá trị.

### Bài 5: Comparator xử lý chuỗi dài

Nếu một phép so sánh khóa tốn tới O(L), chỉ viết “get tốn O(log n) thời gian bất kể độ dài chuỗi” có đủ chính xác không?

**Lời giải:** chưa đủ. Theo mô hình đó, phần công so sánh có thể là O(L log n). Cần nêu giả định về chi phí từng phép so sánh.

### Bài 6: Mỗi khóa lại tìm giá trị

Vòng lặp duyệt keySet rồi get từng khóa có nhất thiết giữ tổng chi phí bằng đường entrySet thuần không?

**Lời giải:** không. Nó thêm n lượt tìm theo khóa, có thể tạo phần O(n log n). Nếu cần cả hai thành phần, dùng Map.Entry đang duyệt.

### Bài 7: Một khoảng có k kết quả

Với iterator của view khoảng, mô hình O(log n + k) đang phân biệt hai loại công nào?

**Lời giải:** định vị biên bắt đầu trên cây và thăm các entry thuộc khoảng. Nó không cần một get mới cho mỗi kết quả.

### Bài 8: Dựng từ SortedMap

Có được nói mọi constructor sao chép TreeMap đều n log n mà không xem loại nguồn không?

**Lời giải:** không. Constructor nhận SortedMap được tài liệu mô tả chạy tuyến tính. Cần phân biệt đường xây dựng và cả chi phí chuẩn bị nguồn.

### Bài 9: Hình dạng cây trong kiểm thử

Một bản JDK khác có cùng ánh xạ, cùng thứ tự và đáp ứng giới hạn thao tác, nhưng gốc/màu khác hình minh họa. Có đủ để kết luận sai không?

**Lời giải:** không. Hình minh họa không phải hợp đồng về bố trí nội bộ; phải kiểm tra các bảo đảm công khai.

## 18. Tài liệu đối chiếu

- [TreeMap Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/TreeMap.html): cây đỏ–đen, bảo đảm thao tác cơ bản, containsValue và các constructor.
- [TreeMap.java OpenJDK 17u](https://raw.githubusercontent.com/openjdk/jdk17u/master/src/java.base/share/classes/java/util/TreeMap.java): tìm kiếm, xoay, sửa sau thêm/xóa, iterator và dựng từ nguồn có thứ tự.
- [NavigableMap Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/NavigableMap.html): truy vấn lân cận và view theo khoảng.
- [Comparator Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Comparator.html): hợp đồng phép so sánh khóa.
- [Cornell CS2110 — Trees](https://www.cs.cornell.edu/courses/cs2110/2018su/lectures/Lecture9-Trees.pdf): các bất biến và giới hạn chiều cao cây đỏ–đen.

Cân bằng giữ đường tìm theo khóa ngắn, còn tổng chi phí phụ thuộc thao tác đang làm và công việc tại mỗi bước. Hiểu cả cấu trúc lẫn phạm vi của bảng độ phức tạp giúp dùng TreeMap đúng cho tìm kiếm, cập nhật, duyệt và truy vấn theo thứ tự.
