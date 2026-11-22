# TreeMap: headMap, tailMap, subMap và cách lựa chọn biên

Một TreeMap có thể chứa nhiều khóa, nhưng một tác vụ thường chỉ cần một vùng: các mốc trước hạn, các bản ghi từ một mốc trở đi hoặc các sự kiện nằm giữa hai thời điểm.

`headMap`, `tailMap` và `subMap` biểu diễn những vùng ấy theo thứ tự khóa. Điều cần chọn không chỉ là hai con số. Phải xác định chiều thứ tự, mỗi biên có được bao gồm hay không và kết quả có còn dùng chung dữ liệu với map gốc hay không.

Bài dùng Java 17. Sau bài này, bạn cần đọc được một khoảng thành điều kiện so sánh, viết đúng lời gọi API, kiểm tra các trường hợp bằng biên và nhận ra tác động của thao tác qua view.

## 1. Mô hình: một cửa sổ khóa trên cùng dữ liệu

Giả sử TreeMap dùng thứ tự số tăng và có các khóa:

~~~text
10, 20, 30, 40, 50
~~~

Ba kiểu cửa sổ là:

- `headMap`: phần đứng trước một mốc kết thúc.
- `tailMap`: phần bắt đầu từ hoặc sau một mốc.
- `subMap`: phần nằm giữa hai mốc.

Kết quả trên TreeMap là góc nhìn (`view`) có phạm vi khóa, không phải một bản sao đã lọc xong. Bạn có thể giữ view để đọc vùng dữ liệu đó; khi gốc đổi trong phạm vi, view phản ánh thay đổi.

Tạo một view không tự thêm, xóa hay sửa ánh xạ. Những thao tác cập nhật hợp lệ thực hiện qua view về sau mới tác động đến dữ liệu gốc. [Java 17: các phương thức vùng của TreeMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/TreeMap.html)

### 1.1. Điều kiện xét trên khóa

View theo khoảng khóa không tự lọc theo nội dung giá trị. Nếu khóa là mã sản phẩm còn giá trị có trường ngày cập nhật, headMap theo mã không biến thành truy vấn trước một ngày.

Muốn các khoảng phục vụ thời gian, khóa phải có quy tắc thứ tự thể hiện thời gian phù hợp. Thiết kế khóa và câu hỏi nghiệp vụ phải khớp nhau trước khi chọn phương thức.

### 1.2. View không có nghĩa chỉ đọc

Từ “góc nhìn” chỉ nói về quan hệ với dữ liệu gốc, không có nghĩa mọi thao tác sửa bị cấm. TreeMap cung cấp những thao tác sửa được hỗ trợ trong vùng khóa.

Ví dụ, `view.remove(key)` có thể xóa ánh xạ tương ứng khỏi gốc; `view.clear()` có thể xóa cả vùng. Vì vậy, đừng dùng một view làm nơi “sửa thử” với giả định gốc không bị ảnh hưởng.

## 2. Ba mặc định của SortedMap

Các phương thức không có boolean dùng những biên cố định:

| Lời gọi | Điều kiện khóa k theo thứ tự map | Ký hiệu vùng |
|---|---|---|
| headMap(b) | k < b | Phần trước b, không gồm b |
| tailMap(a) | k ≥ a | Phần từ a, có gồm a |
| subMap(a, b) | a ≤ k < b | [a, b) |

Với khóa 10, 20, 30, 40, 50:

~~~text
headMap(30)   -> 10, 20
tailMap(30)   -> 30, 40, 50
subMap(20,40) -> 20, 30
~~~

Mặc định headMap loại mốc kết thúc; tailMap gồm mốc bắt đầu; subMap gồm đầu dưới và loại đầu trên. Không nên nhớ chung “các hàm này đều bỏ biên” hoặc “đều gồm biên”. [Java 17: SortedMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/SortedMap.html)

### 2.1. Ý nghĩa của khoảng nửa mở

`[a, b)` nghĩa là bắt đầu có a, kết thúc trước b. Hai vùng liền nhau `[a, b)` và `[b, c)` không lặp khóa bằng b.

Điều đó hữu ích khi chia dữ liệu thành các phiên hoặc các ngày. Mốc nối thuộc vùng thứ hai, không xuất hiện hai lần chỉ vì nó bằng đúng ranh giới.

Đây là quy tắc lựa chọn biên, không phải yêu cầu dữ liệu phải có a hoặc b. Nếu không có khóa ở biên, các khóa nằm giữa vẫn được chọn.

### 2.2. Kiểu trả về ở Java 17

Các dạng cũ không có boolean được khai báo trả SortedMap. Các dạng có boolean trong NavigableMap trả NavigableMap.

Đoạn minh họa một phần với biến `map` có kiểu NavigableMap:

~~~java
SortedMap<Integer, String> legacy = map.subMap(20, 40);

NavigableMap<Integer, String> explicit =
        map.subMap(20, true, 40, false);
~~~

Nếu cần tiếp tục dùng floorKey, firstEntry hoặc các dạng điều hướng khác trên kết quả, dạng có boolean cũng thể hiện được kiểu NavigableMap trực tiếp. Không ép kiểu tùy tiện chỉ để bỏ qua khác biệt khai báo.

## 3. Chọn rõ từng biên bằng boolean

NavigableMap bổ sung:

~~~text
headMap(toKey, inclusive)
tailMap(fromKey, inclusive)
subMap(fromKey, fromInclusive, toKey, toInclusive)
~~~

Đây là sơ đồ chữ ký để đọc tham số, không phải đoạn mã chạy độc lập.

`true` nghĩa là chấp nhận khóa so sánh bằng biên tương ứng; `false` nghĩa là loại khóa so sánh bằng biên đó. Với subMap, hai boolean áp dụng riêng cho hai đầu. [Java 17: NavigableMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/NavigableMap.html)

### 3.1. Một biên: trước hoặc sau mốc

Trên dãy số tăng:

| Yêu cầu | Lời gọi với mốc 30 | Khóa kết quả |
|---|---|---|
| Trước 30 | headMap(30, false) | 10, 20 |
| Không sau 30 | headMap(30, true) | 10, 20, 30 |
| Từ 30 trở đi | tailMap(30, true) | 30, 40, 50 |
| Sau 30 | tailMap(30, false) | 40, 50 |

Những từ như “đến”, “từ”, “trước” trong yêu cầu tự nhiên có thể được người dùng hiểu khác nhau. Trong mã, hãy chuyển chúng thành điều kiện có hoặc không có dấu bằng trước.

### 3.2. Hai biên: bốn vùng thường gặp

Với a = 20 và b = 40:

| Vùng | Lời gọi | Khóa kết quả |
|---|---|---|
| [20, 40] | subMap(20, true, 40, true) | 20, 30, 40 |
| [20, 40) | subMap(20, true, 40, false) | 20, 30 |
| (20, 40] | subMap(20, false, 40, true) | 30, 40 |
| (20, 40) | subMap(20, false, 40, false) | 30 |

Cặp boolean không nói “sắp tăng hay giảm”. Nó chỉ lựa chọn tính bao gồm của hai biên trong thứ tự mà map đã có.

Nếu lời gọi nhiều tham số khó đọc trong một đoạn mã quan trọng, có thể đặt tên biến diễn đạt ý định:

~~~java
boolean includeStart = true;
boolean includeEnd = false;

NavigableMap<Integer, String> selected =
        map.subMap(start, includeStart, end, includeEnd);
~~~

Đoạn trên là minh họa với map, start và end đã được xác định. Tên biến phải khớp nghiệp vụ, không chỉ thay true/false bằng những tên chung chung khó hiểu hơn.

### 3.3. Viết điều kiện so sánh khi còn nghi ngờ

Gọi c là quy tắc so sánh của map. Có thể đọc khoảng [a, b) thành:

~~~text
c(k, a) >= 0
và
c(k, b) < 0
~~~

Khoảng (a, b] chỉ thay hai dấu ở biên:

~~~text
c(k, a) > 0
và
c(k, b) <= 0
~~~

Đây là công cụ lập luận, không bắt buộc phải viết một vòng lọc thủ công thay cho API. Nó giúp xác định chính xác khóa bằng đầu hoặc cuối có được giữ hay không.

## 4. Biên không cần tồn tại, nhưng phải hợp lệ

### 4.1. Biên là mốc so sánh

Với khóa 10, 20, 30, 40, 50, `subMap(15, true, 45, false)` chọn 20, 30, 40. Không có 15 hay 45 trong map vẫn không làm lời gọi mất ý nghĩa.

Cũng không cần tự tìm khóa gần nhất trước khi gọi subMap. Các mốc đã định nghĩa được vùng so sánh mà ứng dụng muốn.

### 4.2. Hai biên bằng nhau

Trên map gốc không bị giới hạn phạm vi, với các biên và kiểu khóa hợp lệ:

- `subMap(a, true, a, true)` có thể chứa khóa so sánh bằng a nếu tồn tại.
- Nếu ít nhất một đầu bị loại, không có khóa nào thỏa đồng thời hai điều kiện khi hai mốc so sánh bằng nhau.
- `subMap(a, a)` mặc định là khoảng rỗng.

Ví dụ:

~~~text
subMap(20, true, 20, true)  -> 20
subMap(20, true, 20, false) -> rỗng
subMap(25, true, 25, true)  -> rỗng nếu map không có khóa 25
~~~

“Có thể chứa khóa ở mốc” không có nghĩa API tự tạo một khóa mới khi chưa có. Nó chỉ cho phép vị trí đó thuộc phạm vi.

### 4.3. Biên đảo chiều là lỗi yêu cầu

Nếu fromKey đứng sau toKey theo comparator, subMap ném IllegalArgumentException. Không nên tự coi đó là vùng rỗng rồi nuốt lỗi, trừ khi tầng ứng dụng đã có chính sách chuẩn hóa yêu cầu rõ ràng.

“Vùng hợp lệ nhưng hiện không có dữ liệu” khác với “hai biên không hợp lệ”. Hai trạng thái thường cần phản hồi khác nhau ở tầng nghiệp vụ.

### 4.4. Null không có nghĩa vô hạn

Không truyền null để ngụ ý “không có biên”. TreeMap tự nhiên không cho phép khóa hoặc biên null; có thể gặp NullPointerException. Comparator riêng chỉ cho phép null khi chính nó định nghĩa cách so sánh null.

Ngay cả khi null hợp lệ, nó là một mốc theo comparator, không tự có nghĩa âm vô hạn hay dương vô hạn cho mọi map. Muốn chỉ giới hạn một đầu, headMap hoặc tailMap đã biểu diễn đúng nhu cầu.

Khóa và biên còn phải so sánh được theo quy tắc của map. Một lỗi kiểu hoặc comparator không phù hợp khác với một khoảng rỗng hợp lệ.

## 5. Bao gồm biên theo compare, không theo equals

Giả sử comparator coi chữ hoa và chữ thường tương đương. Khóa `"b"` được so sánh bằng 0 với mốc `"B"`.

Khi ấy:

~~~text
headMap("B", false) -> loại khóa "b"
headMap("B", true)  -> có thể gồm khóa "b"
~~~

Inclusive xét kết quả so sánh bằng 0, không đòi hỏi đối tượng biên phải là đúng cùng đối tượng khóa hoặc bằng nhau theo một phép so khác.

Ví dụ comparator không phân biệt hoa thường trong chương trình chỉ dùng để minh họa cách xét biên. Khi thiết kế khóa thực, cần cân nhắc sự nhất quán giữa comparator và equals để map tuân thủ hợp đồng dữ liệu mong muốn. [Java 17: Comparator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Comparator.html)

Các thành phần khóa và trạng thái dùng trong comparator phải ổn định trong quá trình dùng map. Một quy tắc tự thay đổi theo biến bên ngoài không tạo một cửa sổ khóa đáng tin chỉ bằng cách gọi lại headMap.

## 6. View sống và tác động lên map gốc

### 6.1. Thay đổi hai chiều

Bắt đầu với gốc 10, 20, 30, 40, 50 và view [20, 40):

~~~text
gốc:  10, 20, 30, 40, 50
view: 20, 30

gốc thêm 25:
view thấy 20, 25, 30

view thêm 35:
gốc có 10, 20, 25, 30, 35, 40, 50

view xóa 20:
gốc còn 10, 25, 30, 35, 40, 50
~~~

Không cần lấy lại view để thấy những ánh xạ mới nằm trong phạm vi. Nhưng một List khóa đã sao chép trước đó là cấu trúc khác và không tự được thêm phần tử như view.

### 6.2. Đọc ngoài vùng và chèn ngoài vùng khác nhau

Trên view [20, 40), khóa 40 ngoài phạm vi dù map gốc đang chứa 40.

Với dữ liệu không có giá trị null trong ví dụ:

- Get 40 qua view không tìm thấy ánh xạ trong view.
- Remove 40 qua view không loại ánh xạ ngoài vùng ở gốc.
- Put 40 qua view bị từ chối bằng IllegalArgumentException.

Không lấy quyền của map gốc để suy ra view cũng có quyền ghi mọi khóa. View chỉ đại diện phần dữ liệu thuộc phạm vi của nó.

### 6.3. Clear view là xóa vùng

Sau khi view chứa 25, 30, 35, gọi clear trên view sẽ xóa ba ánh xạ ấy khỏi gốc, để lại 10, 40, 50.

Đây là một cách diễn đạt thao tác xóa theo khoảng rất trực tiếp. Cần hiểu đây là thay đổi dữ liệu, không phải chỉ dọn một đối tượng tạm giữ kết quả lọc.

Không vừa giữ iterator cũ trên cấu trúc chung vừa tùy ý thêm, xóa qua map hoặc view khác. Các đối tượng nhìn khác tên vẫn có thể cùng dựa trên một dữ liệu gốc.

### 6.4. Bản sao khi cần dữ liệu độc lập

Đoạn minh họa:

~~~java
NavigableMap<Integer, String> window =
        source.subMap(20, true, 40, false);

TreeMap<Integer, String> independent = new TreeMap<>(window);
~~~

Constructor nhận SortedMap phù hợp với kiểu NavigableMap nguồn nên bản TreeMap mới giữ thứ tự của nguồn. Cấu trúc ánh xạ độc lập với window về các thao tác thêm hoặc xóa sau đó.

Đây vẫn là sao chép ánh xạ, không tự sao chép sâu đối tượng khóa và giá trị. Nếu giá trị là đối tượng có thể thay đổi, cần chọn mức độ sao chép theo yêu cầu.

Nếu nguồn có sửa đổi cạnh tranh, tạo bản sao cũng cần chính sách đọc nguồn phù hợp. Một cấu trúc kết quả độc lập không tự giải quyết thời điểm đang thu thập dữ liệu từ nguồn.

## 7. View lồng nhau: không thể mở rộng quyền biên

### 7.1. Giới hạn của view cha vẫn còn

Giả sử outer là [20, 40). Gọi một phương thức vùng trên outer không được tự mở rộng nó để lấy thêm 10 hoặc bao gồm 40.

Ví dụ:

~~~text
outer.headMap(40, false) -> giữ phần trước 40, vẫn loại 40: hợp lệ
outer.headMap(40, true)  -> muốn gồm 40: bị từ chối
outer.tailMap(10, false) -> đặt biên thấp ngoài phạm vi outer: bị từ chối
~~~

Không nên tưởng một yêu cầu vượt biên luôn được API tự cắt về giao với phạm vi cha. Các hợp đồng vùng quy định việc tạo view với biên không hợp lệ có thể bị từ chối.

### 7.2. Biên bằng đầu bị loại không phải lúc nào cũng bị cấm

Một điểm cần đọc kỹ là cờ bao gồm. Trên outer [20, 40), `tailMap(40, false)` tạo vùng rỗng hợp lệ trong TreeMap: nó vẫn loại mốc 40 và không lấy bất kỳ khóa nào ngoài quyền của outer.

Trong khi đó, yêu cầu gồm 40 sẽ đòi một mốc cha đã loại. Vì vậy, chỉ hỏi “40 có xuất hiện trong outer không?” chưa đủ để quyết định mọi lời gọi lồng có biên 40.

Cách lập luận là xét cả giá trị mốc và quyền bao gồm mốc. Chương trình đầy đủ kiểm chứng cặp trường hợp giữ biên trên bị loại và yêu cầu bao gồm nó.

### 7.3. Rỗng không làm mất các ràng buộc tạo vùng

Một view có thể rỗng vì dữ liệu chưa có khóa trong phạm vi. Nó vẫn mang giới hạn biên; không được dùng việc rỗng để suy ra có thể chèn hoặc tạo view con tùy ý.

Tách hai khái niệm:

- Miền khóa mà view cho phép đại diện.
- Những ánh xạ đang thực sự tồn tại trong miền ấy.

Khi kiểm tra lỗi biên, phải xét miền cho phép, không chỉ nhìn danh sách khóa đang in ra.

## 8. Thứ tự đảo: head không còn đồng nghĩa số nhỏ hơn

### 8.1. Đọc chiều comparator trước

Với view đảo của các khóa 10, 20, 30, 40, 50:

~~~text
50, 40, 30, 20, 10
~~~

Head là phần đứng trước mốc theo thứ tự này. Tail là phần từ hoặc sau mốc theo thứ tự này.

| Lời gọi trên view đảo | Khóa kết quả theo thứ tự view |
|---|---|
| headMap(30, true) | 50, 40, 30 |
| tailMap(30, false) | 20, 10 |
| subMap(40, true, 20, false) | 40, 30 |

Không có lỗi đảo dấu ngẫu nhiên. Quy tắc so sánh của view đã đảo nên quan hệ trước/sau thay đổi tương ứng.

### 8.2. From và to phải đúng chiều map

Trên view đảo, 40 đứng trước 20 nên cặp from = 40, to = 20 hợp lệ. Truyền from = 20, to = 40 theo thói quen số tăng làm from đứng sau to trong comparator của view và bị từ chối.

Đừng tự sắp hai mốc bằng Math.min và Math.max khi hàm được thiết kế nhận một sorted map bất kỳ. Cách đó ngầm áp thứ tự số tăng, có thể trái comparator nguồn.

View đảo vẫn dùng chung dữ liệu. Tác động thêm, xóa hợp lệ qua vùng của view đảo vẫn đi vào gốc, không có lớp dữ liệu độc lập chỉ vì chiều duyệt khác.

## 9. Chọn biên từ nghiệp vụ, không tạo “mốc giả”

### 9.1. Dùng inclusive thay vì cộng một đơn vị

Muốn bao gồm b, nên dùng cờ bao gồm b thay vì luôn đổi thành “nhỏ hơn b + 1”.

Cách cộng một đơn vị có nhiều giả định: khóa phải có phép cộng, miền phải rời rạc theo đúng đơn vị đó và phép cộng không được tràn. Với Integer.MAX_VALUE, cộng thêm một là sai trong kiểu int.

Dạng `subMap(max, true, max, true)` biểu diễn khoảng một mốc ở giá trị tối đa mà không cần tạo một số kế tiếp. Với chuỗi hoặc khóa nghiệp vụ phức tạp, khái niệm “b + 1” thậm chí có thể không tồn tại.

### 9.2. Khoảng một ngày

Nếu khóa là LocalDateTime của thời gian địa phương trong ví dụ, muốn lấy các sự kiện thuộc ngày d:

~~~text
start = đầu ngày d
end   = đầu ngày d + 1 ngày theo lịch
chọn [start, end)
~~~

Sự kiện đúng tại start được giữ. Sự kiện đúng tại end thuộc ngày tiếp theo và bị loại. Không cần đoán một “giây cuối ngày” rồi bỏ sót phần độ chính xác nhỏ hơn giây.

Mã minh họa một phần:

~~~java
LocalDateTime start = day.atStartOfDay();
LocalDateTime end = day.plusDays(1).atStartOfDay();

NavigableMap<LocalDateTime, String> daily =
        events.subMap(start, true, end, false);
~~~

Ví dụ đang dùng LocalDate và LocalDateTime trong phạm vi ngày hợp lệ; một hệ thống lưu mốc theo kiểu thời gian khác cần xác định biên theo mô hình thời gian của nó. [Java 17: LocalDate.plusDays và atStartOfDay](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/LocalDate.html)

### 9.3. Ma trận kiểm tra biên

Trước khi dùng trong tác vụ thật, chọn các dữ liệu thử:

| Vị trí khóa | Câu hỏi |
|---|---|
| Ngay trước from | Bị loại chưa? |
| Bằng from | Đúng theo fromInclusive chưa? |
| Nằm giữa | Được giữ chưa? |
| Bằng to | Đúng theo toInclusive chưa? |
| Ngay sau to | Bị loại chưa? |

Bổ sung trường hợp không có khóa ở biên, hai biên bằng nhau và comparator đảo nếu hàm cho phép thứ tự tùy chọn. Các trường hợp bằng mốc là nơi khác biệt giữa hai boolean thật sự xuất hiện.

## 10. Chương trình Java đầy đủ

Lưu toàn bộ mã sau vào `TreeMapRangeBoundsDemo.java`. Chương trình không cần thư viện ngoài.

Nó dùng các nhóm dữ liệu riêng để việc clear hoặc xóa ở một nhóm không ảnh hưởng các nhóm còn lại. Các phép kiểm tra xác nhận view sống, bản sao độc lập, lỗi biên và dữ liệu trong khoảng ngày.

~~~java
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.List;
import java.util.NavigableMap;
import java.util.TreeMap;

public class TreeMapRangeBoundsDemo {
    private static TreeMap<Integer, String> sample() {
        TreeMap<Integer, String> map = new TreeMap<>();
        for (int key : new int[] {10, 20, 30, 40, 50}) {
            map.put(key, "v" + key);
        }
        return map;
    }

    private static <K, V> List<K> keys(java.util.Map<K, V> map) {
        return new ArrayList<>(map.keySet());
    }

    private static void require(boolean condition) {
        if (!condition) {
            throw new AssertionError("Unexpected range result");
        }
    }

    private static boolean rejected(Runnable action) {
        try {
            action.run();
            return false;
        } catch (IllegalArgumentException exception) {
            return true;
        }
    }

    public static void main(String[] args) {
        TreeMap<Integer, String> map = sample();
        System.out.println("default/head30=" + keys(map.headMap(30)));
        System.out.println("default/tail30=" + keys(map.tailMap(30)));
        System.out.println("default/sub20to40=" + keys(map.subMap(20, 40)));
        System.out.println("flags/head30Inclusive="
                + keys(map.headMap(30, true)));
        System.out.println("flags/tail30Exclusive="
                + keys(map.tailMap(30, false)));
        System.out.println("flags/open20to40="
                + keys(map.subMap(20, false, 40, false)));
        System.out.println("flags/closed20to40="
                + keys(map.subMap(20, true, 40, true)));
        System.out.println("bounds/notPresent="
                + keys(map.subMap(15, true, 45, false)));
        System.out.println("equal/closed="
                + keys(map.subMap(20, true, 20, true)));
        System.out.println("equal/halfOpen="
                + keys(map.subMap(20, true, 20, false)));
        System.out.println("equal/missing="
                + keys(map.subMap(25, true, 25, true)));

        TreeMap<Integer, String> parent = sample();
        NavigableMap<Integer, String> window =
                parent.subMap(20, true, 40, false);
        TreeMap<Integer, String> independent = new TreeMap<>(window);
        parent.put(25, "v25");
        window.put(35, "v35");
        window.remove(20);
        require(keys(window).equals(List.of(25, 30, 35)));
        require(keys(parent).equals(List.of(10, 25, 30, 35, 40, 50)));
        require(keys(independent).equals(List.of(20, 30)));
        System.out.println("live/window=" + keys(window));
        System.out.println("live/parent=" + keys(parent));
        System.out.println("live/copy=" + keys(independent));
        boolean outside = rejected(() -> window.put(40, "not-allowed"));
        require(outside && parent.get(40).equals("v40"));
        System.out.println("live/outsidePutRejected=" + outside);
        System.out.println("live/outsideGet=" + window.get(40)
                + ", outsideRemove=" + window.remove(40));
        window.clear();
        require(keys(parent).equals(List.of(10, 40, 50)));
        System.out.println("live/parentAfterClear=" + keys(parent));

        NavigableMap<Integer, String> outer =
                sample().subMap(20, true, 40, false);
        System.out.println("nested/sameExcludedUpper="
                + keys(outer.headMap(40, false)));
        boolean includeUpper = rejected(() -> outer.headMap(40, true));
        boolean expandLower = rejected(() -> outer.tailMap(10, false));
        require(includeUpper && expandLower);
        System.out.println("nested/includeUpperRejected=" + includeUpper);
        System.out.println("nested/emptyAtUpper="
                + keys(outer.tailMap(40, false)));
        System.out.println("nested/expandLowerRejected=" + expandLower);

        NavigableMap<Integer, String> descending = sample().descendingMap();
        System.out.println("descending/head30Inclusive="
                + keys(descending.headMap(30, true)));
        System.out.println("descending/tail30Exclusive="
                + keys(descending.tailMap(30, false)));
        System.out.println("descending/sub40to20="
                + keys(descending.subMap(40, true, 20, false)));
        boolean wrongDirection =
                rejected(() -> descending.subMap(20, true, 40, false));
        require(wrongDirection);
        System.out.println("descending/wrongDirectionRejected="
                + wrongDirection);

        TreeMap<String, Integer> words =
                new TreeMap<>(String.CASE_INSENSITIVE_ORDER);
        words.put("a", 1);
        words.put("b", 2);
        words.put("c", 3);
        System.out.println("comparison/headBExclusive="
                + keys(words.headMap("B", false)));
        System.out.println("comparison/headBInclusive="
                + keys(words.headMap("B", true)));

        TreeMap<Integer, String> maximum = new TreeMap<>();
        maximum.put(Integer.MAX_VALUE, "maximum");
        System.out.println("max/closed="
                + keys(maximum.subMap(Integer.MAX_VALUE, true,
                        Integer.MAX_VALUE, true)));

        LocalDate day = LocalDate.of(2026, 10, 20);
        LocalDateTime start = day.atStartOfDay();
        LocalDateTime nextStart = day.plusDays(1).atStartOfDay();
        TreeMap<LocalDateTime, String> events = new TreeMap<>();
        events.put(start.minusNanos(1), "previous");
        events.put(start, "start");
        events.put(start.plusHours(8), "morning");
        events.put(nextStart, "next");
        NavigableMap<LocalDateTime, String> today =
                events.subMap(start, true, nextStart, false);
        require(new ArrayList<>(today.values())
                .equals(List.of("start", "morning")));
        System.out.println("day/values=" + new ArrayList<>(today.values()));
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~shell
javac --release 17 -encoding UTF-8 TreeMapRangeBoundsDemo.java
java TreeMapRangeBoundsDemo
~~~

Stdout của lần chạy kiểm chứng:

~~~text
default/head30=[10, 20]
default/tail30=[30, 40, 50]
default/sub20to40=[20, 30]
flags/head30Inclusive=[10, 20, 30]
flags/tail30Exclusive=[40, 50]
flags/open20to40=[30]
flags/closed20to40=[20, 30, 40]
bounds/notPresent=[20, 30, 40]
equal/closed=[20]
equal/halfOpen=[]
equal/missing=[]
live/window=[25, 30, 35]
live/parent=[10, 25, 30, 35, 40, 50]
live/copy=[20, 30]
live/outsidePutRejected=true
live/outsideGet=null, outsideRemove=null
live/parentAfterClear=[10, 40, 50]
nested/sameExcludedUpper=[20, 30]
nested/includeUpperRejected=true
nested/emptyAtUpper=[]
nested/expandLowerRejected=true
descending/head30Inclusive=[50, 40, 30]
descending/tail30Exclusive=[20, 10]
descending/sub40to20=[40, 30]
descending/wrongDirectionRejected=true
comparison/headBExclusive=[a]
comparison/headBInclusive=[a, b]
max/closed=[2147483647]
day/values=[start, morning]
~~~

Mã đã được biên dịch với `--release 17` và chạy thành công. Tùy chọn release xác định mức API và mã đích tương thích; nó không khẳng định JVM thực thi là đúng bản JDK 17.

## 11. Giải thích kết quả quan trọng

### 11.1. Default, flags và equal

Ba dòng default đối chiếu ba mặc định khác nhau. Nhóm flags cho thấy boolean thay việc có lấy đúng mốc hay không, không thay thứ tự map.

Nhóm equal phân biệt vùng một mốc có dữ liệu, vùng loại một đầu nên rỗng và vùng một mốc hợp lệ nhưng chưa có ánh xạ ở mốc ấy. Rỗng không luôn là lỗi.

### 11.2. Live

Bản copy được tạo lúc window chứa 20 và 30. Gốc thêm 25, view thêm 35 rồi xóa 20; window và gốc cùng phản ánh trạng thái mới, copy giữ các ánh xạ đã sao chép.

Put 40 qua window bị từ chối. Get hoặc remove 40 qua window không đi xuyên giới hạn để lấy hoặc xóa ánh xạ 40 ở gốc. Clear window sau đó chỉ loại vùng hiện tại, để gốc còn 10, 40, 50.

### 11.3. Nested

HeadMap ở biên trên 40 với inclusive false hợp lệ, nhưng đổi thành true bị từ chối. TailMap tại 40 với false cho vùng rỗng; tailMap từ 10 bị từ chối vì nằm ngoài giới hạn cha.

Các kết quả này nhắc rằng miền khóa cho phép và tập ánh xạ đang có là hai đối tượng suy nghĩ khác nhau.

### 11.4. Descending và comparison

Nhóm descending đọc head, tail và from/to theo chiều 50 xuống 10. Trường hợp truyền biên sai chiều bị từ chối bằng IllegalArgumentException.

Nhóm comparison dùng mốc B trên khóa b để cho thấy inclusive phụ thuộc phép so sánh. Chương trình không dựa vào sự bằng nhau theo equals giữa hai chuỗi để lựa chọn biên.

### 11.5. Max và day

Khoảng đóng tại Integer.MAX_VALUE không cần cộng một đơn vị. Khoảng ngày giữ sự kiện đúng đầu ngày và lúc sáng, loại sự kiện ngay trước đầu ngày cùng sự kiện đúng đầu ngày kế tiếp.

Những ví dụ này cho thấy cờ biên giải quyết trực tiếp yêu cầu thay vì cần mẹo tạo một khóa kế tiếp giả định.

## 12. Lỗi thường gặp

| Lỗi | Cách sửa |
|---|---|
| HeadMap mặc định có gồm mốc | Dạng không boolean loại mốc kết thúc |
| TailMap mặc định loại mốc | Dạng không boolean gồm mốc bắt đầu |
| SubMap hai đối số gồm cả hai đầu | Nó là [from, to) |
| Biên phải có trong map | Biên là mốc so sánh |
| Hai biên bằng nhau luôn là lỗi | Có thể là vùng hợp lệ một mốc hoặc rỗng |
| Biên sai chiều cứ trả vùng rỗng | Đó có thể là IllegalArgumentException |
| View là bản sao để sửa thử | Thao tác sửa hợp lệ tác động vào gốc |
| Clear view chỉ dọn đối tượng tạm | Nó xóa các ánh xạ trong vùng khỏi gốc |
| Gốc có khóa thì view ghi được khóa đó | View còn bị ràng buộc bởi phạm vi |
| View con tự cắt mọi biên về vùng cha | Yêu cầu vượt giới hạn có thể bị từ chối |
| Head luôn là các số nhỏ hơn | Phải đọc theo comparator, kể cả thứ tự đảo |
| Bao gồm b phải đổi thành b + 1 | Dùng inclusive; không giả định có khóa kế tiếp |
| Null biểu diễn không giới hạn | Null tuân thủ quy tắc so sánh, không là ký hiệu vô hạn |
| Sao chép view làm đối tượng giá trị bất biến | Sao chép ánh xạ không tự sao chép sâu |

## 13. Thực hành và lời giải

### Bài 1. Ba mặc định

Map có 5, 10, 15, 20, 25. Hãy cho khóa trong headMap(15), tailMap(15) và subMap(10, 20).

**Lời giải:** Head là 5, 10. Tail là 15, 20, 25. Sub là 10, 15 vì đầu dưới được gồm còn đầu trên bị loại.

### Bài 2. Hai đầu đều có dấu bằng

Cần chọn các khóa từ 10 đến 20, bao gồm cả hai mốc. Viết lời gọi và giải thích vì sao không cần dùng 21.

**Lời giải:** SubMap(10, true, 20, true). Cờ cuối biểu diễn trực tiếp việc gồm 20. Dùng 21 giả định một miền số rời rạc và có thể gây lỗi ở giới hạn kiểu hoặc không áp dụng được cho loại khóa khác.

### Bài 3. Mốc vắng và mốc bằng nhau

Với khóa 10, 20, 30, 40, kết quả subMap(15, true, 35, false) là gì? SubMap(20, true, 20, true) và subMap(20, false, 20, true) khác nhau thế nào?

**Lời giải:** Khoảng thứ nhất chứa 20, 30 dù không có hai mốc 15 và 35. Khoảng đóng một mốc chứa 20; khoảng loại đầu dưới với cùng hai mốc là rỗng.

### Bài 4. View ghi vào đâu?

Gốc có 10, 20, 30, 40, 50; view là [20, 40). Thêm 35 qua view, rồi clear view. Gốc còn khóa nào? Có thể put 40 qua view trước khi clear không?

**Lời giải:** Clear loại 20, 30 và 35 khỏi gốc, để lại 10, 40, 50. Put 40 qua view bị từ chối do đầu trên loại 40, dù gốc có sẵn khóa ấy.

### Bài 5. View lồng nhau

Outer là [20, 40). Phân biệt outer.headMap(40, false), outer.headMap(40, true) và outer.tailMap(10, false).

**Lời giải:** Trường hợp đầu giữ giới hạn loại 40 nên hợp lệ. Trường hợp thứ hai đòi gồm biên mà cha đã loại nên bị từ chối. Trường hợp thứ ba đặt mốc ngoài giới hạn cha; không được mặc nhiên cắt về khoảng của outer.

### Bài 6. Thứ tự đảo

View đảo có 50, 40, 30, 20, 10. HeadMap(30, true), tailMap(30, false) và subMap(40, true, 20, false) chứa gì?

**Lời giải:** Lần lượt là 50, 40, 30; 20, 10; và 40, 30. Các quan hệ trước/sau theo comparator đảo, không theo phép so số tăng dần.

### Bài 7. Chọn một ngày

Các sự kiện nằm ở ngay trước đầu ngày, đúng đầu ngày, giữa ngày và đúng đầu ngày kế tiếp. Cần vùng ngày hiện tại. Dùng khoảng nào và những sự kiện nào được giữ?

**Lời giải:** Dùng [đầu ngày, đầu ngày kế tiếp). Giữ đúng đầu ngày và giữa ngày; loại sự kiện trước đầu ngày cùng sự kiện tại đầu ngày kế tiếp. Không cần tự tính giây cuối cùng của ngày.

### Bài 8. Một vùng rỗng vẫn có giới hạn

View [100, 200) hiện không có ánh xạ. Có thể put 50 qua view vì “view chưa có dữ liệu” không? Bản copy của view có còn bị giới hạn [100, 200) giống view không?

**Lời giải:** Không thể put 50 qua view; miền cho phép không phụ thuộc việc đang rỗng. Một TreeMap mới sao chép các ánh xạ từ view có cấu trúc map riêng, không tiếp tục là cửa sổ giới hạn của gốc chỉ vì được tạo từ view. Comparator được giữ qua constructor SortedMap, nhưng quyền phạm vi của view không biến thành giới hạn chèn của một TreeMap mới.

## 14. Tự đọc lại lời gọi vùng

Trước khi chạy, hãy diễn giải lời gọi thành một câu đầy đủ: “theo thứ tự này, lấy khóa sau hoặc bằng mốc nào, trước hay bằng mốc nào, và kết quả là view của dữ liệu nào”.

Nếu câu ấy rõ, các cờ boolean bớt trở thành điều phải học thuộc. HeadMap, tailMap và subMap là cách biểu diễn miền khóa; chọn đúng biên và hiểu dữ liệu dùng chung là hai phần cùng cần để dùng chúng đúng.
