# Ước lượng kích thước ban đầu và chi phí duyệt theo capacity

## 1. Bài toán: dành chỗ bao nhiêu cho một HashMap?

Một chương trình đọc dữ liệu rồi tạo HashMap để tra cứu theo mã. Nếu dự kiến có 1.000 khóa khác nhau, có thể viết new HashMap<>(1000). Câu lệnh này hợp lệ, nhưng ý nghĩa của số 1.000 dễ bị hiểu sai: đó là tham số dung lượng ban đầu, không phải lời cam kết chứa đúng 1.000 ánh xạ mà không cần tăng bảng.

Chọn quá nhỏ có thể làm map tăng bảng nhiều lần trong giai đoạn nạp. Chọn quá lớn lại dành nhiều chỗ cho bucket rỗng, tăng bộ nhớ và có thể làm việc duyệt toàn map tốn công.

Mục tiêu là **chọn dung lượng phù hợp với số ánh xạ dự kiến và cách dùng map**. Không phải tìm một con số càng lớn càng tốt.

Bài này dùng Java 17 làm mốc cho các chương trình chính. Những con số làm tròn theo lũy thừa hai và đường tăng bảng được giải thích theo cài đặt OpenJDK 17u; không coi chúng là API đọc cấu trúc nội bộ.

## 2. Phân biệt size, capacity, load factor và threshold

| Tên | Ý nghĩa | Ví dụ trong mô hình thông thường |
| --- | --- | --- |
| size | Số ánh xạ khóa–giá trị đang có | 1.000 khóa khác nhau tạo size bằng 1.000 |
| capacity | Số bucket của bảng băm đã cấp phát | 2.048 bucket có thể chứa 1.000 ánh xạ |
| initialCapacity | Tham số yêu cầu dung lượng khi tạo map | Truyền 1.334 vào constructor |
| load factor | Hệ số tải dùng để quyết định khi nào tăng bảng | Mặc định 0,75 |
| threshold | Ngưỡng kích thước gắn với bảng hiện tại trong đường xử lý thông thường | 2.048 × 0,75 = 1.536 |

Một bucket có thể chứa nhiều ánh xạ, nên capacity không phải số ánh xạ tối đa. Map cũng không phải mảng có một ô cho mỗi khóa.

### 2.1. Size là điều quan sát được qua API

Gọi size() để biết số ánh xạ hiện có. Ghi lại một giá trị mới cho khóa đã tồn tại thường không làm tăng size; thêm khóa khác mới tăng số ánh xạ.

Số lượt gọi put có thể lớn hơn nhiều so với size cuối cùng.

### 2.2. Capacity không có getter công khai của HashMap

Không có phương thức HashMap.capacity() để mã ứng dụng hỏi số bucket. Những chương trình bên dưới không dùng reflection hoặc mở trường private.

Ta có thể dùng mô hình để lập kế hoạch dung lượng, rồi kiểm tra tính đúng của dữ liệu qua size/get/entrySet. Mô hình không phải kết quả đo trực tiếp bảng của một đối tượng.

### 2.3. Constructor chưa có nghĩa đã nạp dữ liệu

Một HashMap mới vẫn rỗng dù truyền initialCapacity lớn. Trong OpenJDK 17u, bảng được khởi tạo khi cần dùng; constructor với tham số chủ yếu ghi lại cấu hình cho lần cấp phát sau.

Điều này giải thích vì sao chỉ đo thời gian chạy constructor là chưa đo chi phí dành bảng cho dữ liệu. Lần thêm đầu tiên có thể phải trả chi phí cấp phát đó.

Tham số initialCapacity cũng không đặt giới hạn cứng. Nếu tiếp tục thêm, map có thể tăng bảng; nó không tự từ chối khóa thứ N chỉ vì constructor nhận N.

## 3. Ước lượng N từ số khóa cùng tồn tại

Trước khi áp dụng công thức, hãy xác định N là gì: **số ánh xạ tối đa hợp lý mà map sẽ cùng giữ trong giai đoạn đang xét**.

| Tình huống | Đại lượng cần ước lượng |
| --- | --- |
| Lập chỉ mục người dùng theo userId | Số userId khác nhau được giữ |
| Đếm tần suất từ | Số từ khác nhau, không phải tổng số từ đọc |
| Ghi đè trạng thái theo deviceId | Số deviceId cùng có trong map |
| Gộp hai map | Số khóa trong hợp của hai tập khóa |
| Giữ dữ liệu trong một cửa sổ thời gian | Số khóa cùng tồn tại ở đỉnh của cửa sổ |

Ví dụ, đọc một triệu bản ghi nhưng chỉ cập nhật trạng thái của 500 thiết bị thì N liên quan tới 500 thiết bị. Đặt dung lượng theo một triệu lượt ghi có thể lãng phí rất nhiều.

Ngược lại, biết size hiện tại là 1.000 chưa đủ nếu chương trình còn nạp thêm 9.000 khóa mới. Cần ước lượng giai đoạn tăng trưởng phía trước.

Với hai map có size a và b, a + b chỉ là chặn trên khi gộp, vì khóa trùng sẽ cập nhật ánh xạ. Nếu biết mức chồng lấp, có thể ước lượng sát hơn.

Không nhất thiết phải quét dữ liệu hai lần chỉ để biết N chính xác. Chi phí đọc trước hoặc tạo thêm một Set để đếm khóa cũng cần được tính. Khi chưa biết quy mô đáng tin cậy, dùng cấu hình mặc định và để tăng trưởng có thể là lựa chọn hợp lý.

## 4. Từ số ánh xạ dự kiến tới yêu cầu dung lượng

### 4.1. Bắt đầu từ ngưỡng tải

Trong mô hình dung lượng thông thường, đặt:

- N: số ánh xạ dự kiến.
- C: số bucket.
- f: load factor.
- T: ngưỡng tăng theo tải.

Ta dùng gần đúng có kiểm soát:

T = floor(C × f)

Muốn N chưa vượt T, chọn C sao cho:

C ≥ ceil(N / f)

Với f = 0,75 và N = 1.000:

N / f = 1.333,333...

Yêu cầu dung lượng tính ra là 1.334, rồi cài đặt có thể làm tròn tiếp theo quy tắc bảng của nó.

Đây là cách **tránh tăng bảng do vượt ngưỡng tải trong phạm vi đã dự kiến**, không phải bảo đảm mọi đường nội bộ đều không thể tăng bảng. Ví dụ, trong OpenJDK, xử lý một nhóm va chạm quá đông khi bảng còn nhỏ có thể dẫn tới tăng bảng theo đường riêng.

### 4.2. Tại sao new HashMap<>(1000) khác ước lượng 1.000 ánh xạ?

Trong mô hình OpenJDK 17u với tải mặc định:

1. Yêu cầu dung lượng 1.000 được làm tròn thành bảng 1.024 bucket khi cấp phát.
2. Ngưỡng tải thông thường là 1.024 × 0,75 = 768.
3. Khi đường put thêm khóa khác làm size tăng lên 769, nó đã vượt ngưỡng ấy.
4. Bảng có thể tăng lên 2.048 bucket trước khi nạp đủ 1.000 khóa.

Nếu thay bằng yêu cầu 1.334, bảng ban đầu theo mô hình là 2.048 bucket, có ngưỡng 1.536. Vì thế 1.000 ánh xạ nằm trong khoảng tải dự kiến.

Hai cách có thể đi tới cùng dung lượng cuối. Khác biệt cần quan tâm là có đi qua một đợt tăng và chuyển dữ liệu giữa chừng hay không.

### 4.3. Hiểu đúng dấu bằng tại ngưỡng

Trong đường putVal của nguồn OpenJDK 17u được đối chiếu, thêm một khóa mới rồi kiểm tra size > threshold. Với bảng 16 và ngưỡng 12:

- Size bằng 12 chưa vượt ngưỡng tải.
- Thêm khóa khác làm size bằng 13 thì vượt.
- Thay giá trị của một khóa có sẵn không biến 12 khóa thành 13 khóa.

Vì vậy không tự cộng thêm 1 trong mọi công thức chỉ vì sợ trường hợp bằng ngưỡng. Với N = 12, ceil(12 / 0,75) bằng 16. Tính thêm một bucket thành 17 rồi làm tròn lũy thừa hai có thể đẩy bảng tới 32.

Tuy vậy, từng API xây dựng hoặc đường xử lý nội bộ có thể chọn cách dự phòng riêng. Khi dùng API công khai, ưu tiên đúng ý nghĩa tham số thay vì buộc nó phải đạt một dung lượng bí mật chính xác.

## 5. Lũy thừa hai làm ước lượng thay đổi theo nấc

Trong cài đặt OpenJDK 17u, bảng đã cấp phát có độ dài là lũy thừa hai. Vì vậy mức dành chỗ không tăng mượt theo từng ánh xạ.

Bảng dưới là **phép tính theo mô hình tải mặc định**, không phải kết quả gọi một getter của HashMap:

| N dự kiến | ceil(N / 0,75) | C sau làm tròn theo mô hình | floor(C × 0,75) |
| --- | --- | --- | --- |
| 1 | 2 | 2 | 1 |
| 12 | 16 | 16 | 12 |
| 13 | 18 | 32 | 24 |
| 768 | 1.024 | 1.024 | 768 |
| 769 | 1.026 | 2.048 | 1.536 |
| 1.000 | 1.334 | 2.048 | 1.536 |
| 10.000 | 13.334 | 16.384 | 12.288 |

Tăng dự kiến từ 768 lên 769 khóa có thể đẩy lựa chọn bảng từ 1.024 lên 2.048. Khoảng trống sau đó không nhất thiết là sai; nó đến từ bước làm tròn.

Điều này cũng giải thích vì sao hai giá trị initialCapacity khác nhau đôi khi dẫn tới cùng lựa chọn bảng. Tối ưu tham số từng đơn vị mà không xét nấc dung lượng có thể không thay đổi gì.

Các giá trị sát giới hạn tối đa của cài đặt có xử lý đặc biệt. Không kéo dài bảng tính thông thường đến mọi số int rồi kết luận đó là hành vi chính xác của HashMap.

## 6. Bài toán thực tế: 20.000 sự kiện nhưng chỉ giữ 180 khóa

Giả sử bộ tổng hợp xử lý 20.000 sự kiện trong một ca làm việc. Mỗi sự kiện cập nhật một bộ đếm theo mã thiết bị; các thiết bị cũ được loại khỏi Map khi không còn hoạt động. Đã có 240 thiết bị khác nhau xuất hiện trong cả ca, nhưng quan sát cho thấy **tối đa 180 thiết bị cùng tồn tại** trong Map.

Để ước lượng dung lượng, dùng đỉnh số **khóa đồng thời** `N = 180`, không dùng 20.000 lần gọi hay 240 mã từng xuất hiện. Với load factor mặc định 0.75:

~~~text
ceil(180 / 0.75) = 240
tableSizeFor(240) = 256       (mô hình làm tròn OpenJDK 17)
floor(256 × 0.75) = 192      (ngưỡng tải thông thường)
~~~

Vì `180 ≤ 192`, chọn yêu cầu dung lượng ban đầu khoảng 240 giúp bảng mục tiêu 256 bucket có đủ khoảng trống theo ngưỡng tải trong kịch bản này. Phép tính không chứng minh Map sẽ không bao giờ resize: bộ dữ liệu, va chạm hoặc đường triển khai cụ thể vẫn phải xét riêng. Constructor `new HashMap<>(240)` nhận **yêu cầu dung lượng**, không tự chèn 240 cặp.

| Cách chọn đầu vào | Điều xảy ra trong mô hình OpenJDK 17 |
| --- | --- |
| Dùng 20.000 sự kiện làm số ánh xạ | Ước lượng thừa vì nhiều sự kiện cập nhật cùng khóa |
| Dùng 240 khóa từng xuất hiện | Có thể thừa nếu không bao giờ cùng tồn tại |
| Dùng đỉnh 180 khóa cùng tồn tại | Phản ánh mức tải thực tế cần dự phòng |
| Dùng mặc định và không cấp trước | Đúng về ánh xạ; có thể phát sinh resize khi nạp nhiều khóa |

Ví dụ runnable ở mục 10 tiếp tục khai thác mặt còn lại của lựa chọn: khi Map trở nên rất thưa, chi phí duyệt có thể chịu ảnh hưởng của bảng đã cấp lớn. Chương trình đầy đủ tính dung lượng theo hệ số tải và quan sát các lần resize được trình bày trong bài về capacity/load factor.

## 7. Resize tốn gì, dù put thường nhanh?

Khi tăng bảng, cài đặt phải cấp phát một bảng mới và tổ chức lại việc đặt các node vào bucket. Công việc này liên quan tới bảng và những ánh xạ đang có, nên một lần put kích hoạt tăng bảng có thể tốn nhiều hơn một lần put thông thường.

Trong đường resize của OpenJDK 17u, các node giữ thông tin hash đã tính. Không nên giải thích tăng bảng thành “luôn gọi lại hashCode của mọi khóa từ đầu”; tổ chức lại bucket và gọi lại hàm người dùng là hai việc khác nhau.

### 7.1. Chi phí phân bổ theo nhiều lần thêm

Bảng tăng theo cấp số nhân trong miền thông thường. Khi nhìn cả chuỗi nhiều lần thêm, tổng công tăng trưởng có thể được phân bổ cho nhiều thao tác. Đây là lý do tăng động vẫn hữu ích.

Nhưng chi phí phân bổ trung bình không có nghĩa từng lệnh put đều có độ trễ giống nhau. Một chương trình nhạy với đột biến độ trễ có thể quan tâm tới thời điểm cấp phát và chuyển bảng.

Ước lượng đúng từ đầu giúp giảm các đợt tăng không cần thiết. Nó cũng dồn phần cấp phát bảng lớn hơn về giai đoạn đầu, nên vẫn có đánh đổi.

### 7.2. Bộ nhớ không chỉ gồm bucket rỗng

Một map còn có đối tượng map, bảng tham chiếu, các node, khóa, giá trị và những cấu trúc phụ có thể phát sinh. Không lấy capacity nhân một số byte tùy đoán rồi gọi đó là tổng bộ nhớ của map.

Khi tăng bảng hoặc tạo bản sao để thu gọn, hai cấu trúc có thể cùng tồn tại trong một khoảng thời gian. Ước lượng bộ nhớ đỉnh cũng có giá trị, đặc biệt với dữ liệu lớn.

Kích thước đối tượng phụ thuộc JVM và cấu hình. Nếu cần con số byte, phải đo trong môi trường liên quan thay vì biến một con số học được ở máy khác thành hằng số chung.

## 8. Vì sao duyệt HashMap phụ thuộc capacity + size?

### 8.1. Tìm một khóa khác duyệt tất cả

Get dùng hash để đi tới khu vực có thể chứa khóa. Với phân bố phù hợp, thao tác cơ bản có hiệu năng kỳ vọng tốt.

Duyệt toàn bộ entrySet, keySet hoặc values lại phải tìm những bucket có dữ liệu và đi qua các ánh xạ bên trong. Bucket rỗng cũng có thể phải được kiểm tra trong quá trình quét bảng.

Tài liệu [HashMap Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HashMap.html) nêu thời gian duyệt collection view tỉ lệ với capacity cộng size.

Mô hình học tập:

Chi phí duyệt toàn map ≈ chi phí quét C bucket + chi phí thăm N ánh xạ

Viết theo ký hiệu độ phức tạp: O(C + N).

Không đọc công thức này thành “mất đúng C + N nano giây” hay “mỗi bucket tốn đúng bằng mỗi entry”. Đây là mô hình số lượng công việc, không phải đơn vị thời gian.

### 8.2. Cùng 1.000 ánh xạ nhưng bảng khác nhau

Giả sử có hai trạng thái bảng:

| Trạng thái | C | N | C + N trong mô hình |
| --- | --- | --- | --- |
| Dành chỗ vừa mức dự kiến | 2.048 | 1.000 | 3.048 |
| Dành chỗ rất rộng | 1.048.576 | 1.000 | 1.049.576 |

Cả hai có cùng số entry để xử lý, nhưng trạng thái thứ hai có rất nhiều bucket rỗng. Nếu liên tục xuất báo cáo bằng cách duyệt toàn bộ map, khoảng trống đó có thể trở thành chi phí lặp lại.

Không suy ra tỉ lệ thời gian thực từ tỉ lệ hai tổng trên. Bộ nhớ đệm CPU, bố trí đối tượng, công việc trong thân vòng lặp và JVM đều ảnh hưởng phép đo.

### 8.3. Khi nào thường viết gọn là O(N)?

Nếu trong giai đoạn đang xét C luôn cùng bậc với N, thì C + N cũng cùng bậc với N. Lúc đó viết O(N) có thể là cách rút gọn phù hợp với giả định.

Nhưng C không tự luôn bám sát N. Nó có thể rất lớn vì cấu hình ban đầu hoặc vì map từng tăng mạnh rồi bị xóa nhiều dữ liệu. Bỏ C trong những tình huống đó làm mất điều cần giải thích.

### 8.4. Phạm vi của một lượt duyệt

Công thức đang nói về lượt duyệt đầy đủ, với công việc tại mỗi ánh xạ được xem riêng. Nếu thân vòng lặp ghi mạng, xử lý chuỗi dài hoặc làm phép toán đắt, chi phí ấy có thể lớn hơn phần duyệt cấu trúc.

Nếu chỉ lấy một vài phần tử rồi dừng, lượng quét phụ thuộc vị trí bucket có dữ liệu. Không xem O(C + N) như số bước chính xác cho mọi tiền tố của iterator.

Map hoàn toàn rỗng cũng có đường xử lý nhanh trong cài đặt được đối chiếu. Không khẳng định mọi iterator rỗng đều phải quét hết bảng cũ chỉ vì công thức tổng quát có chữ C.

Duyệt song song cũng không tự xóa chi phí bucket rỗng. Việc chia và xử lý dữ liệu là một bài toán khác cần đo theo khối lượng thực tế.

## 9. Xóa dữ liệu có tự làm bảng nhỏ lại không?

### 9.1. Size giảm chưa nói capacity giảm

Trong cài đặt OpenJDK 17u được đối chiếu, remove không tự thu nhỏ bảng băm chỉ vì tổng số ánh xạ giảm. Clear bỏ các ánh xạ nhưng giữ đối tượng bảng để có thể dùng lại.

Một map từng chứa rất nhiều khóa có thể trở nên thưa sau khi xóa. Khi còn một ít ánh xạ và tiếp tục duyệt toàn bộ, việc nhìn size nhỏ rồi cho rằng lượt duyệt chắc rẻ là thiếu dữ kiện.

Việc đổi biểu diễn bên trong một bucket và thu nhỏ toàn bộ bảng là hai việc khác nhau. Không dùng một thay đổi của nhóm va chạm làm bằng chứng bảng đã có ít bucket hơn.

### 9.2. Giữ lại hay tạo lại phụ thuộc vòng đời

Nếu ngay sau clear sẽ nạp lại lượng dữ liệu lớn tương tự, giữ bảng cũ có thể tránh cấp phát lại.

Nếu lượng dữ liệu đã giảm lâu dài và map tiếp tục được duyệt nhiều, tạo một HashMap mới từ các ánh xạ còn lại có thể giúp đưa dung lượng về mức hợp với quy mô mới.

HashMap không có phương thức public trimToSize tương tự một số cấu trúc khác. Một cách tạo cấu trúc mới là:

```java
Map<K, V> rebuilt = new HashMap<>(oldMap);
```

Đây là đoạn minh họa trong ngữ cảnh đã có kiểu K, V và biến oldMap, không phải chương trình độc lập.

Constructor sao chép giữ các ánh xạ theo hợp đồng công khai. Không yêu cầu nó phải chọn chính xác dung lượng tối thiểu theo bảng tính ở trên; quy tắc dự phòng có thể khác giữa đường xây dựng và phiên bản.

### 9.3. Sao chép có chi phí và thay đổi định danh đối tượng

Để xây bản mới, vẫn phải đọc ánh xạ từ bản cũ. Nếu bản cũ rất thưa, chính lượt duyệt phục vụ sao chép cũng có thể tốn theo bảng cũ.

Trong lúc sao chép, cấu trúc cũ và mới cùng tồn tại. Khóa và giá trị là các đối tượng được tham chiếu lại, không tự trở thành bản sao sâu.

Gán một biến sang bản mới không chuyển mọi người dùng khác sang cùng đối tượng ấy. Những nơi đang giữ map cũ, keySet/values/entrySet của nó hoặc iterator cũ vẫn gắn với bản cũ. Cần xác định rõ ai sở hữu map trước khi thay cấu trúc.

Bảng cũ chỉ có cơ hội được thu gom khi không còn đường tham chiếu giữ cấu trúc đó; không có cam kết thu gom ngay tại câu lệnh gán.

## 10. Ví dụ Java 17: map thưa và bản sao mới

Chương trình chủ động yêu cầu dung lượng ban đầu lớn, nạp 1.000 khóa rồi bỏ 990 khóa. Sau đó nó tạo một map mới từ 10 ánh xạ còn lại.

Mục đích của stdout là kiểm tra **ánh xạ và quan hệ giữa hai đối tượng**, không đo thời gian hay đọc capacity bí mật.

Lưu thành **SparseHashMapDemo.java**:

```java
import java.util.HashMap;
import java.util.Map;
import java.util.Set;

public class SparseHashMapDemo {
    static long checksum(Map<Integer, Integer> map) {
        long sum = 0;
        for (Map.Entry<Integer, Integer> entry : map.entrySet()) {
            sum += entry.getValue();
        }
        return sum;
    }

    public static void main(String[] args) {
        Map<Integer, Integer> original = new HashMap<>(1 << 18);
        for (int key = 0; key < 1000; key++) {
            original.put(key, key);
        }
        System.out.println("before removal size: " + original.size());

        for (int key = 0; key < 990; key++) {
            original.remove(key);
        }
        System.out.println("after removal size: " + original.size());
        System.out.println("remaining checksum: " + checksum(original));

        Set<Integer> oldKeysView = original.keySet();
        Map<Integer, Integer> rebuilt = new HashMap<>(original);
        System.out.println("same mappings after copy: " + original.equals(rebuilt));
        System.out.println("rebuilt size: " + rebuilt.size());

        original.clear();
        System.out.println("old view size after clear: " + oldKeysView.size());
        System.out.println("rebuilt size after original clear: " + rebuilt.size());
        System.out.println("rebuilt checksum: " + checksum(rebuilt));
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 SparseHashMapDemo.java
java SparseHashMapDemo
```

Stdout trên môi trường đã nêu:

```text
before removal size: 1000
after removal size: 10
remaining checksum: 9945
same mappings after copy: true
rebuilt size: 10
old view size after clear: 0
rebuilt size after original clear: 10
rebuilt checksum: 9945
```

### 10.1. Đọc kết quả

Các khóa còn lại là 990 tới 999, tổng giá trị 9.945. Bản sao giữ cùng các ánh xạ nên equals trả true và tổng vẫn đúng.

Biến oldKeysView là view của map gốc. Khi clear map gốc, view ấy có size bằng 0. Map mới vẫn giữ 10 ánh xạ vì cấu trúc chứa ánh xạ của nó độc lập với map gốc.

Việc clear map cũ trong ví dụ giúp quan sát quan hệ đó; đây không phải yêu cầu phải clear trước mỗi lần thay map. Nếu nơi khác còn cần dữ liệu cũ, clear sẽ có tác dụng thật lên nơi đó.

### 10.2. Điều stdout không chứng minh

Nó không chứng minh số bucket chính xác của hai map hoặc mức tăng tốc bao nhiêu phần trăm.

Lý do map có thể thưa sau xóa và lý do constructor có thể chọn bảng mới phù hợp hơn được giải thích bằng mô hình cùng mã nguồn cài đặt. Kết quả chạy kiểm tra tính đúng của các ánh xạ.

Một ví dụ in ra hai thời gian nano giây rồi khẳng định bản mới luôn nhanh hơn sẽ không đủ đáng tin. Tính đúng và phép đo hiệu năng cần có mục tiêu kiểm tra riêng.

## 11. Chọn dung lượng theo công việc của map

| Cách dùng chính | Điều nên cân nhắc |
| --- | --- |
| Nạp một lần, biết khá rõ số khóa | Ước lượng dung lượng để giảm tăng bảng trong giai đoạn nạp |
| Quy mô nhỏ hoặc chưa dự đoán được | Cấu hình mặc định thường là điểm khởi đầu hợp lý |
| Duyệt toàn map nhiều lần | Tránh dành dư quá mức; xem cả capacity và size |
| Thường clear rồi nạp lại cùng quy mô | Tái sử dụng bảng có thể có lợi |
| Tăng rất lớn một lần rồi giảm lâu dài | Cân nhắc tạo cấu trúc mới nếu lợi ích bù chi phí sao chép |
| Cần thứ tự duyệt ổn định | Chọn cấu trúc có hợp đồng thứ tự phù hợp, không dựa vào capacity |

### 11.1. Không giảm load factor một cách máy móc

Giảm f làm công thức N/f tăng. Với cùng N, cài đặt có thể phải chọn bảng lớn hơn. Điều đó có thể giảm mức dồn trung bình nhưng làm tăng bộ nhớ bảng và công quét khi duyệt.

Tăng f cũng không phải tiết kiệm miễn phí: nhiều ánh xạ hơn trên cùng số bucket có thể làm tra cứu tốn hơn. Hàm hash và đặc điểm dữ liệu vẫn quan trọng.

Giữ mặc định 0,75 thường giúp bắt đầu với một đánh đổi đã có sẵn. Chỉ đổi khi có yêu cầu và bằng chứng liên quan tới khối lượng công việc.

### 11.2. Một đối chiếu hữu ích với LinkedHashMap

Theo [LinkedHashMap Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/LinkedHashMap.html), duyệt collection view đi theo các liên kết của entry và có chi phí tỉ lệ với size, không phụ thuộc capacity theo cách quét bảng của HashMap.

Đó là một khác biệt đáng xem xét khi cần thứ tự duyệt hoặc thường duyệt map thưa. Tuy nhiên LinkedHashMap có thêm liên kết và chi phí duy trì chúng; không suy ra nó luôn dùng ít bộ nhớ hơn hoặc nhanh hơn mọi thao tác.

Việc lựa chọn cấu trúc phải xét cả hợp đồng cần có và công việc thực hiện, không chỉ một dòng độ phức tạp.

## 12. Java 19+: diễn đạt trực tiếp số ánh xạ dự kiến

Từ Java 19, HashMap có factory newHashMap(int numMappings). Tham số ở đây là **số ánh xạ dự kiến**, khác ý nghĩa initialCapacity của constructor.

Đoạn khai báo minh họa trong ngữ cảnh đã import Map và HashMap:

```java
Map<String, Integer> counts = HashMap.newHashMap(1000);
```

API dùng load factor mặc định và chọn dung lượng ban đầu phù hợp nói chung để nạp lượng ánh xạ dự kiến. Không cần tự truyền kết quả N/0,75 vào factory thêm lần nữa.

Đối chiếu mục newHashMap, Since 19 trong [HashMap Java 19](https://docs.oracle.com/en/java/javase/19/docs/api/java.base/java/util/HashMap.html#newHashMap(int)).

Đoạn này **không biên dịch với --release 17**, kể cả máy đang chạy JDK mới hơn. Hai chương trình đầy đủ phía trên chỉ dùng API có trong Java 17.

Factory vẫn trả về một map rỗng có thể tăng trưởng. Số 1.000 không tạo giới hạn cứng hay tự thu nhỏ map sau các lần xóa.

## 13. Đánh giá hiệu năng mà không nhầm mục tiêu

Trước hết kiểm tra các cấu hình chứa cùng ánh xạ, có cùng công việc trong thân vòng lặp và cho cùng kết quả. Nếu không, chênh lệch thời gian có thể chỉ là do xử lý lượng dữ liệu khác nhau.

Khi đo dung lượng, tách những câu hỏi sau:

- Nạp dữ liệu ban đầu tốn bao nhiêu?
- Một lượt duyệt sau khi nạp tốn bao nhiêu?
- Xóa nhiều rồi tiếp tục duyệt có ảnh hưởng thế nào?
- Sao chép để tạo map mới tốn bao nhiêu và được dùng lại bao nhiêu lần?

Đừng đặt việc dựng map trong mỗi lượt đo nếu câu hỏi là chi phí chỉ duyệt một map đã dựng xong. Ngược lại, nếu muốn đánh giá toàn bộ giai đoạn nạp, không loại chi phí cấp phát khỏi phép đo rồi gọi đó là tổng chi phí.

Cần có giai đoạn làm nóng JVM, nhiều lượt đo, kết quả được sử dụng để tránh công việc bị tối ưu bỏ, và dữ liệu đại diện. Ghi lại JDK, cấu hình và phân bố khóa.

Nếu thân vòng lặp in từng dòng ra console thì phần in có thể che gần hết khác biệt cấu trúc. Những chương trình trong bài dùng stdout để chứng minh kết quả, không dùng thời gian in làm phép đo HashMap.

Không cần tăng dung lượng lên mức cực lớn trên máy chỉ để chứng minh O(C + N). Mô hình giải thích quan hệ; phép đo có kiểm soát dùng để đánh giá mức ảnh hưởng thực tế của ứng dụng.

## 14. Lỗi phổ biến và cách sửa

| Hiểu nhầm | Hệ quả | Cách sửa |
| --- | --- | --- |
| initialCapacity là số ánh xạ không cần tăng bảng | Nạp vượt ngưỡng tải sớm hơn dự tính | Xét số khóa và load factor |
| Capacity là giới hạn số khóa | Thiết kế nhầm cơ chế từ chối hoặc loại dữ liệu | Đặt chính sách giới hạn riêng nếu cần |
| Một triệu bản ghi nghĩa là một triệu entry | Dành dư nếu nhiều bản ghi có cùng khóa | Ước lượng số khóa khác nhau cùng giữ |
| Cứ cộng 1 sau N/f | Có thể nhảy sang nấc bảng lớn hơn không cần thiết | Làm tròn lên đúng ngữ cảnh và hiểu điều kiện ngưỡng |
| Nhân int rồi mới chuyển long | Giá trị đã tràn trước khi chuyển kiểu | Dùng toán hạng long trước phép nhân |
| Map có size nhỏ nên duyệt chắc rẻ | Bỏ qua bảng lớn còn giữ sau xóa | Xét vòng đời và capacity |
| clear đồng nghĩa giải phóng bảng ngay | Dự đoán sai bộ nhớ và khả năng tái dùng | Phân biệt bỏ ánh xạ, giữ bảng và thu gom rác |
| Mô hình in capacity là đã đo đối tượng | Kết luận quá mức từ phép tính | Ghi rõ mô hình và phép quan sát public |
| Tạo bản sao là miễn phí | Bỏ qua lượt duyệt cũ và bộ nhớ đỉnh | Tính chi phí sao chép và số lần sử dụng sau đó |
| newHashMap(1000) cần tự chia 0,75 thêm | Dành chỗ quá mức do điều chỉnh hai lần | Factory nhận số ánh xạ dự kiến |
| Vòng duyệt nhanh một lần chứng minh mọi trường hợp | Dựa vào phép đo nhiễu hoặc sai phạm vi | Đo với mục tiêu, môi trường và dữ liệu rõ ràng |

## 15. Bài tập tự kiểm tra có lời giải

### Bài 1: Nạp đúng ngưỡng

Theo mô hình OpenJDK 17u với tải mặc định, bảng 16 bucket có ngưỡng thông thường 12. Nạp 12 khóa khác nhau có vượt ngưỡng tải không? Thêm khóa khác thứ 13 thì sao?

**Lời giải:** 12 chưa lớn hơn 12. Khóa mới thứ 13 làm size vượt ngưỡng theo đường put đang xét. Kết luận chỉ nói về đường tăng theo tải; không loại bỏ những cơ chế nội bộ khác trong dữ liệu va chạm đặc biệt.

### Bài 2: Tính cho 2.000 ánh xạ

Dùng f = 0,75. Yêu cầu dung lượng tính ra là bao nhiêu? Theo mô hình lũy thừa hai, bảng nào đủ?

**Lời giải:** ceil(2.000 / 0,75) = 2.667. Làm tròn lên thành 4.096, ngưỡng thông thường là 3.072.

### Bài 3: Bốn lượt ghi, hai khóa

Dữ liệu khóa lần lượt là a, a, b, a. Nếu chỉ giữ giá trị mới nhất theo khóa, N cuối cùng là 4 hay 2?

**Lời giải:** 2 khóa khác nhau. Số bản ghi đầu vào không bằng số ánh xạ cuối. Nếu bài toán là đếm tần suất, map vẫn có hai ánh xạ, còn các giá trị đếm là 3 và 1.

### Bài 4: Hai map cùng size

Map A có C = 4.096, N = 2.000; map B có C = 1.048.576, N = 2.000. Có được nói một lượt duyệt của chúng chắc bằng nhau vì cùng 2.000 entry không?

**Lời giải:** không. Duyệt HashMap còn liên quan tới bảng bucket. Tuy nhiên từ mô hình này cũng chưa tính được tỉ lệ thời gian chạy chính xác.

### Bài 5: Vừa xóa một lượng lớn

Một map giảm từ hàng trăm nghìn khóa xuống vài trăm rồi được dùng để xuất báo cáo nhiều lần. Có thể chỉ dựa vào size để kết luận chi phí duyệt đã giảm tương ứng không?

**Lời giải:** không. Cài đặt được đối chiếu không tự thu nhỏ bảng khi remove. Có thể cân nhắc map mới phù hợp với quy mô còn lại, sau khi xét chi phí sao chép, bộ nhớ đỉnh và các tham chiếu tới map cũ.

### Bài 6: Clear trước khi nạp lại

Một tác vụ lặp đều clear rồi nạp lại khoảng cùng số khóa như trước. Luôn thay map sau clear có chắc tốt hơn không?

**Lời giải:** không. Giữ bảng có thể giảm cấp phát lại. Chọn theo vòng đời dữ liệu và phép đo phù hợp.

### Bài 7: Dùng helper sai load factor

Đã tính dung lượng theo f = 0,75 nhưng lại truyền vào constructor có f = 0,5. Có được giữ nguyên kết luận về ngưỡng không?

**Lời giải:** không. Ngưỡng phụ thuộc f. Nếu thay f, phải tính lại hoặc dùng cách tạo map phù hợp với cấu hình thật.

### Bài 8: Factory và phiên bản Java

Một đoạn gọi HashMap.newHashMap(1000) chạy trên máy có JDK 24. Có chắc biên dịch được với --release 17 không?

**Lời giải:** không. API đó bắt đầu từ Java 19. JDK dùng để chạy công cụ và mức API đích khi biên dịch là hai thông tin cần phân biệt.

## 16. Tài liệu đối chiếu

- [HashMap Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HashMap.html): ý nghĩa dung lượng, hệ số tải, constructor và chi phí duyệt.
- [HashMap.java OpenJDK 17u](https://raw.githubusercontent.com/openjdk/jdk17u/master/src/java.base/share/classes/java/util/HashMap.java): cách làm tròn, khởi tạo bảng, tăng bảng, iterator và clear trong cài đặt được phân tích.
- [HashMap Java 19 — newHashMap](https://docs.oracle.com/en/java/javase/19/docs/api/java.base/java/util/HashMap.html#newHashMap(int)): API nhận số ánh xạ dự kiến.
- [LinkedHashMap Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/LinkedHashMap.html): đối chiếu chi phí duyệt theo size.

Ước lượng dung lượng bắt đầu từ số khóa cùng tồn tại, rồi xét hệ số tải và cách sử dụng map. Giảm những lần tăng bảng không cần thiết có ích, nhưng dành chỗ quá rộng có thể chuyển chi phí sang bộ nhớ và các lượt duyệt về sau.
