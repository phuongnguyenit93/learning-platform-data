# So sánh HashSet với LinkedHashSet theo thời gian và bộ nhớ

## 1. Chọn theo công việc cần làm, không chỉ theo tên cấu trúc

`HashSet` và `LinkedHashSet` đều là tập dùng băm: loại trùng và hỗ trợ thêm, kiểm tra thành viên, xóa theo giá trị. Khác biệt chính là `LinkedHashSet` duy trì thêm thứ tự chèn để việc duyệt có trình tự được bảo đảm.

Câu hỏi lựa chọn không chỉ là “lớp nào nhanh hơn?” mà gồm:

1. Kết quả có cần giữ thứ tự chèn không?
2. Chương trình chủ yếu tra cứu hay thường xuyên duyệt toàn bộ?
3. Có bao nhiêu phần tử khác nhau và bảng băm có thưa không?
4. Bộ nhớ dành cho cấu trúc có đáng kể so với dữ liệu phần tử không?
5. Đang cần phân tích độ phức tạp hay cần một số đo trên JVM cụ thể?

Nhận định ban đầu:

- Không cần thứ tự và chủ yếu kiểm tra thành viên: `HashSet` thường là lựa chọn trực tiếp, tránh phần liên kết thứ tự không cần thiết.
- Cần giữ thứ tự chèn: `LinkedHashSet` cung cấp đúng hành vi đó.
- Thường xuyên duyệt, đặc biệt khi bảng băm thưa: cần xét lợi thế của cách duyệt `LinkedHashSet` theo số phần tử.
- Cần số byte hoặc số nano giây: phải đo trong điều kiện cụ thể; tên lớp và ký hiệu O lớn chưa đủ.

Đây là các hướng suy luận từ cấu trúc và hợp đồng, không phải khẳng định một lớp thắng mọi phép đo. [HashSet Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HashSet.html), [LinkedHashSet Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/LinkedHashSet.html)

## 2. Cấu trúc nào tạo ra sự khác biệt?

### 2.1. Phần chung: bảng băm để nhận diện thành viên

Cả hai dựa vào cơ chế băm để thu hẹp vùng tìm:

```text
giá trị truy vấn
    → hashCode
    → vùng ứng viên trong bảng
    → so sánh bằng nhau
    → tìm thấy hoặc không tìm thấy
```

`LinkedHashSet` không phải một `LinkedList` mà mỗi lần `contains` đều phải đi từ đầu tới cuối. Từ “Linked” ở đây chỉ phần liên kết bổ sung phục vụ thứ tự duyệt; khả năng tìm thành viên vẫn dựa vào băm.

Vì vậy, cả hai đều cần:

- `equals` và `hashCode` nhất quán.
- Dữ liệu nhận diện của phần tử ổn định khi đang trong tập.
- Mã băm phân bố các giá trị phù hợp.
- Chi phí tính mã băm và so sánh bằng nhau có thể kiểm soát.

Đổi `HashSet` thành `LinkedHashSet` không tự sửa một khóa có `hashCode` sai, luôn trả một hằng số hoặc thay đổi sau khi chèn.

### 2.2. Phần thêm của LinkedHashSet: liên kết thứ tự

Có thể hình dung phần thứ tự như một chuỗi liên kết hai chiều giữa các mục:

```text
đầu → mục thứ nhất ↔ mục thứ hai ↔ mục thứ ba ← cuối
```

Liên kết đó giúp duyệt các phần tử đang lưu theo thứ tự chèn. Khi thêm mới hoặc xóa một mục, triển khai cần cập nhật các liên kết tương ứng.

`HashSet` không cần cung cấp chuỗi thứ tự chèn này. Nó không cam kết thứ tự duyệt, kể cả khi một ví dụ nhỏ tình cờ in ra giống thứ tự thêm.

Phần bổ sung của `LinkedHashSet` có hai mặt:

- Tốn tài nguyên để lưu và duy trì thứ tự.
- Cho phép duyệt mà không phải tìm phần tử qua mọi ngăn trống của bảng.

Đó là lý do một cấu trúc có thêm thông tin quản lý vẫn có thể phù hợp hơn cho một kiểu công việc cụ thể.

## 3. So sánh thời gian theo từng thao tác

Đặt:

- `n`: số phần tử đang lưu.
- `C`: capacity, tức số ngăn của bảng nền.
- Chi phí của `hashCode` và `equals` được xét riêng khi khóa phức tạp.

Bảng sau mô tả mô hình thông thường với băm phân bố phù hợp:

| Thao tác | HashSet | LinkedHashSet | Cách hiểu |
| --- | --- | --- | --- |
| `contains` | O(1) kỳ vọng | O(1) kỳ vọng | Cả hai dùng băm, không cần quét hết tập |
| `add` | O(1) kỳ vọng/khấu hao trong chuỗi thêm thông thường | Tương tự, có thêm duy trì liên kết khi thêm mới | Một lần tăng dung lượng vẫn có thể tốn nhiều việc |
| `remove` | O(1) kỳ vọng | O(1) kỳ vọng, có thêm bỏ liên kết thứ tự | Không suy ra một lớp luôn nhanh hơn với mọi khóa |
| Duyệt toàn bộ | O(n + C) theo mô hình của lớp | O(n) theo mô hình của lớp | Khác biệt đáng chú ý khi C lớn hơn nhiều so với n |
| `size` | O(1) | O(1) | Số phần tử được quản lý sẵn |

Các nhận định hằng số của thao tác cơ bản gắn với giả định phân bố băm. Ký hiệu O(1) không phải cam kết thời gian tuyệt đối cho mọi đầu vào hoặc mọi lần gọi. [HashSet: thao tác và iteration](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HashSet.html), [LinkedHashSet: thao tác và iteration](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/LinkedHashSet.html)

### 3.1. Tìm thành viên

Với cùng dữ liệu và cấu hình hợp lý, cả hai có cùng mô hình tìm kiếm dựa trên băm. `LinkedHashSet.contains` không cần sửa thứ tự chèn.

Không kết luận rằng thời gian thực tế của hai phương thức bắt buộc bằng nhau vì cùng O(1). Chúng có thể chịu ảnh hưởng của cách bố trí đối tượng, lượng dữ liệu nằm trong bộ nhớ và công việc mà JVM thực hiện.

Ngược lại, cũng không kết luận `LinkedHashSet.contains` là O(n) chỉ vì nhìn thấy một chuỗi liên kết trong mô tả cấu trúc.

### 3.2. Thêm mới, thêm trùng và tăng dung lượng

Thêm phần tử mới khác với thử thêm phần tử đã có:

- Thêm mới cần tạo thành viên mới trong cấu trúc; với `LinkedHashSet`, còn phải đặt nó vào chuỗi thứ tự.
- Thêm trùng trả về `false` và không tăng số phần tử.
- Một lần thêm mới có thể kéo theo tăng dung lượng bảng băm.

Vì vậy, một phép đo gọi `add("java")` nhiều lần sau khi tập đã chứa `"java"` không đại diện cho việc thêm nhiều giá trị khác nhau.

Chi phí tăng dung lượng giải thích cách nói “khấu hao” khi phân tích chuỗi thêm: một số lần làm nhiều việc hơn, nhưng không được coi mọi lần thêm riêng lẻ đều có cùng độ trễ. Cả hai cấu trúc vẫn có phần bảng băm chịu ảnh hưởng của capacity và load factor.

### 3.3. Xóa phần tử

Sau khi tìm được một mục, `LinkedHashSet` cần bỏ nó khỏi thứ tự liên kết. Với liên kết hai chiều và thông tin mục đã tìm, không phải quét cả chuỗi chỉ để tìm mục trước.

Phần công việc bổ sung thường làm chi phí hằng số khác với `HashSet`. Nhưng muốn biết mức khác biệt trên một tải cụ thể phải đo, không thể suy ra một tỷ lệ cố định như “chậm hơn 20%”.

### 3.4. Duyệt là trường hợp phải tách riêng

Với `HashSet`, mô hình duyệt bao gồm số ngăn của bảng và các phần tử đang có. Với `LinkedHashSet`, bộ duyệt đi theo chuỗi phần tử.

Nếu `C` luôn cùng bậc với `n`, cả `n + C` và `n` đều có thể được viết gọn là O(n). Nhưng điều đó không xóa khác biệt khi bảng thực tế rất thưa hoặc các hằng số khác nhau.

Ví dụ khái niệm:

```text
n = 1_000 phần tử
C lớn hơn nhiều so với n

HashSet:
    công việc duyệt liên quan cả vùng bảng và các phần tử

LinkedHashSet:
    công việc duyệt theo chuỗi 1_000 phần tử
```

Đây không phải phép tính số nano giây hoặc số lần truy cập bộ nhớ chính xác. Nó chỉ ra yếu tố cần đưa vào phân tích và thiết kế phép đo.

## 4. Capacity và load factor nối thời gian với bộ nhớ

`size` là số phần tử; `capacity` là số ngăn. Hai đại lượng không giống nhau.

Load factor, hay hệ số tải, liên quan tới mức đầy được cho phép trước khi bảng tăng dung lượng. Các hàm tạo mặc định của hai lớp sử dụng những tham số mặc định tương ứng `16` và `0.75`.

Điều chỉnh cấu hình có sự đánh đổi:

| Lựa chọn | Khía cạnh thời gian | Khía cạnh bộ nhớ |
| --- | --- | --- |
| Capacity ban đầu đủ cho số phần tử dự kiến | Có thể giảm số lần tăng dung lượng khi xây dựng | Cần dành chỗ cho bảng tương ứng |
| Capacity quá lớn | Không tự sửa được băm kém; duyệt HashSet chịu ảnh hưởng của bảng thưa | Có thể giữ nhiều ngăn trống |
| Load factor thấp hơn | Có thể làm bảng thưa hơn; chưa chắc mọi kiểu công việc đều nhanh hơn | Thường cần nhiều không gian bảng hơn |
| Load factor cao hơn | Có thể tăng công việc tìm ứng viên | Có thể giảm không gian bảng tương đối trong một số cấu hình |

`LinkedHashSet` không phải duyệt các ngăn trống theo cùng cách, nhưng bảng thưa vẫn có chi phí lưu trữ. Lợi thế duyệt không có nghĩa capacity lớn là miễn phí về bộ nhớ.

Tham số `new HashSet<>(1_000)` hoặc `new LinkedHashSet<>(1_000)` là gợi ý dung lượng ban đầu, không phải lệnh thêm sẵn 1.000 phần tử hoặc giới hạn tập chỉ chứa được từng đó.

Khi so sánh, cần giữ cấu hình tương đương. Một `HashSet` có bảng quá lớn và một `LinkedHashSet` có bảng vừa đủ không chỉ khác nhau ở liên kết thứ tự. [HashMap: capacity, load factor và tăng dung lượng](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HashMap.html)

## 5. So sánh bộ nhớ: phần tử dữ liệu và cấu trúc quản lý là hai phần khác nhau

### 5.1. Cả hai không sao chép sâu đối tượng phần tử

Nếu đưa cùng một đối tượng khóa vào hai tập, hai tập có thể cùng giữ tham chiếu tới đối tượng đó. Chúng không tự nhân bản toàn bộ dữ liệu của khóa.

Khi hỏi “tập dùng bao nhiêu bộ nhớ?”, cần xác định đang tính:

1. Chính đối tượng `Set`.
2. Bảng nền và các mục quản lý.
3. Các đối tượng phần tử mà tập tham chiếu tới.
4. Mọi đối tượng khác có thể đi tới từ các phần tử đó.
5. Bộ nhớ cấp phát tạm thời trong quá trình xây dựng hay bộ nhớ còn sống sau xây dựng.

Nếu không tách các ý nghĩa này, hai con số cùng mang nhãn “memory” có thể đang đo hai thứ khác nhau.

### 5.2. Một mô hình định tính

Với các mục thông thường, có thể hình dung:

```text
bộ nhớ HashSet
    ≈ đối tượng quản lý
      + bảng tham chiếu theo capacity
      + các mục theo số phần tử
      + đồ thị đối tượng phần tử được tính vào phép đo

bộ nhớ LinkedHashSet
    ≈ những thành phần tương ứng
      + thông tin liên kết thứ tự ở cấu trúc quản lý và từng mục
```

Nếu viết theo bậc tăng trưởng, cả hai đều cần bộ nhớ cho số ngăn và số phần tử: O(C + n), chưa kể kích thước dữ liệu phần tử. Khi `C` tỷ lệ với `n`, cả hai thường được mô tả là O(n).

Cùng O(n) không có nghĩa cùng số byte. `LinkedHashSet` giữ thêm thông tin thứ tự, nên với cấu hình tương đương và các mục thông thường, thường có chi phí cấu trúc lớn hơn.

Nhưng không dùng câu “LinkedHashSet dùng nhiều bộ nhớ hơn” để so hai cấu hình hoàn toàn khác nhau. Một `HashSet` có capacity cực lớn có thể lãng phí bảng nhiều hơn một `LinkedHashSet` được cấu hình vừa đủ. Cần giữ các điều kiện so sánh rõ ràng.

### 5.3. Vì sao thường nhắc tới hai liên kết thêm cho mỗi mục?

Trong triển khai OpenJDK 17, mục thông thường của cấu trúc liên kết nền có thêm các tham chiếu trước và sau so với dạng mục băm thông thường. Phần map nền còn quản lý đầu và cuối chuỗi.

Đó là cơ sở để nói có chi phí bổ sung theo số phần tử. Đây là chi tiết triển khai dùng để giải thích, không phải một định dạng đối tượng được giao diện Java cam kết. [Mục liên kết trong mã nguồn OpenJDK 17](https://github.com/openjdk/jdk17u/blob/master/src/java.base/share/classes/java/util/LinkedHashMap.java)

Không chuyển thẳng “hai tham chiếu thêm” thành “luôn thêm đúng 8 byte” hoặc “luôn thêm đúng 16 byte” cho mọi phần tử trên mọi JVM. Số byte còn phụ thuộc:

- Kích thước biểu diễn tham chiếu trên JVM đang dùng.
- Header và cách bố trí trường.
- Căn chỉnh kích thước đối tượng.
- Loại mục thực tế mà triển khai sử dụng khi xử lý va chạm.
- Các thông tin quản lý ở đối tượng nền.

Mô hình hai liên kết đặc biệt nói về mục thông thường. Một số dạng mục xử lý va chạm có cấu trúc khác; không lấy mô hình giản lược để khẳng định mọi đối tượng nội bộ luôn khác nhau đúng cùng số byte.

### 5.4. Một phép tính giả định để hiểu quy mô

Giả sử chỉ xét hai trường tham chiếu bổ sung, mỗi tham chiếu chiếm `r` byte, có `n` mục:

```text
phần kích thước trường bổ sung theo mô hình = n × 2 × r
```

Nếu **giả định** `n = 100_000` và `r = 4`:

```text
100_000 × 2 × 4 = 800_000 byte
```

Đây chỉ là phép tính của mô hình trường tham chiếu với các giả định đã nêu. Nó không phải số đo heap, không bao gồm căn chỉnh, các đối tượng quản lý khác hoặc dữ liệu phần tử, và không phải một mức chênh lệch được bảo đảm.

Điểm học tập là phần chi phí nhỏ ở mỗi mục có thể trở nên đáng kể khi có nhiều mục; số byte cụ thể cần được kiểm tra trên môi trường thực thi.

### 5.5. Dữ liệu phần tử lớn có thể che khác biệt tương đối

Nếu mỗi phần tử là một đối tượng rất nhỏ, chi phí quản lý tập có thể chiếm tỷ trọng đáng chú ý. Nếu mỗi phần tử giữ một đồ thị dữ liệu lớn, tỷ trọng phần liên kết có thể nhỏ hơn trong tổng footprint.

Điều đó không làm chi phí liên kết biến mất. Nó chỉ giải thích vì sao cùng một mức tăng tuyệt đối có thể có tỷ lệ khác nhau khi đổi loại dữ liệu.

Một phép so sánh dùng khóa nhỏ không tự đại diện cho một ứng dụng có khóa lớn và nhiều đối tượng đi kèm.

## 6. Chương trình đầy đủ: cùng giá trị tập, khác bảo đảm thứ tự

Lưu mã vào **HashSetChoiceDemo.java**:

```java
import java.util.HashSet;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;

public class HashSetChoiceDemo {
    public static void main(String[] args) {
        List<String> input = List.of("sql", "java", "sql", "http");
        Set<String> hashed = new HashSet<>(input);
        Set<String> linked = new LinkedHashSet<>(input);

        System.out.println("HashSet size: " + hashed.size());
        System.out.println("LinkedHashSet size: " + linked.size());
        System.out.println("same members: " + hashed.equals(linked));
        System.out.println("linked order: " + linked);
        System.out.println("hash contains java: " + hashed.contains("java"));
        System.out.println("linked contains java: " + linked.contains("java"));
        System.out.println("hash add duplicate: " + hashed.add("sql"));
        System.out.println("linked add duplicate: " + linked.add("sql"));
        System.out.println("hash remove java: " + hashed.remove("java"));
        System.out.println("linked remove java: " + linked.remove("java"));
        System.out.println("linked after removal: " + linked);

        hashed.add("java");
        linked.add("java");
        System.out.println("linked after re-add: " + linked);
        System.out.println("same members again: " + hashed.equals(linked));
        System.out.println("same set hash: "
                + (hashed.hashCode() == linked.hashCode()));
    }
}
```

Biên dịch theo mức Java 17 và chạy:

```shell
javac --release 17 -encoding UTF-8 HashSetChoiceDemo.java
java HashSetChoiceDemo
```

Stdout:

```text
HashSet size: 3
LinkedHashSet size: 3
same members: true
linked order: [sql, java, http]
hash contains java: true
linked contains java: true
hash add duplicate: false
linked add duplicate: false
hash remove java: true
linked remove java: true
linked after removal: [sql, http]
linked after re-add: [sql, http, java]
same members again: true
same set hash: true
```

Chương trình chỉ in trực tiếp nội dung của `LinkedHashSet`, vì thứ tự của nó được bảo đảm. Nó không in `HashSet` rồi dựa vào một thứ tự tình cờ để viết stdout.

Các kết quả cho thấy:

- Hai tập có cùng số phần tử và cùng thành viên.
- Cả hai từ chối thêm bản sao của một giá trị đã có.
- Cả hai tìm và xóa theo giá trị.
- `LinkedHashSet` cung cấp trình tự chèn có thể quan sát.
- Xóa rồi thêm lại `java` đưa nó xuống cuối trong tập liên kết.
- Khác thứ tự duyệt không làm hai tập có cùng thành viên khác giá trị tập.

Chương trình kiểm chứng hành vi. Nó không có phép đo thời gian hoặc bộ nhớ, nên không thể đọc các dòng stdout như một kết quả so sánh tốc độ.

## 7. Chuẩn bị dữ liệu tương đương trước khi đo

Một lỗi phổ biến là so hai tập có số phần tử khác nhau, dùng hai tập khóa được tạo theo cách khác nhau hoặc vô tình cho một bên nhận nhiều bản sao hơn.

Để chuẩn bị một phép so sánh có ý nghĩa, cần kiểm soát:

| Yếu tố | Cách giữ tương đương |
| --- | --- |
| Nội dung | Cùng các giá trị khóa khác nhau |
| Kiểu khóa | Cùng lớp, cùng quy tắc equals/hashCode |
| Đối tượng phần tử | Có thể dùng chung các đối tượng đầu vào khi so riêng cấu trúc |
| Cấu hình | Cùng gợi ý capacity và load factor trong từng cặp |
| Trạng thái | Cùng số phần tử trước thao tác |
| Công việc | Cùng chuỗi truy vấn hoặc cùng loại thêm/xóa |
| Kết quả | Kiểm tra không có bên nào làm ít việc vì dữ liệu sai |

Cùng gợi ý capacity không phải một API để đọc số ngăn thực tế. Nếu kết luận cần dựa vào cấu trúc heap thực tế, phải kiểm tra cấu trúc đó bằng công cụ phù hợp.

### Chương trình chuẩn bị hai cặp tập

Lưu mã vào **SetComparisonSetupDemo.java**:

```java
import java.util.Arrays;
import java.util.HashSet;
import java.util.LinkedHashSet;
import java.util.Set;

public class SetComparisonSetupDemo {
    private static Set<Integer> fill(Set<Integer> target, Integer[] keys) {
        target.addAll(Arrays.asList(keys));
        return target;
    }

    private static long checksum(Set<Integer> values) {
        long result = 0;
        for (Integer value : values) {
            result += value;
        }
        return result;
    }

    public static void main(String[] args) {
        int count = 1_000;
        Integer[] keys = new Integer[count];
        for (int value = 0; value < count; value++) {
            keys[value] = Integer.valueOf(value);
        }

        Set<Integer> hashDense =
                fill(new HashSet<>(2_048, 0.75f), keys);
        Set<Integer> linkedDense =
                fill(new LinkedHashSet<>(2_048, 0.75f), keys);
        Set<Integer> hashSparse =
                fill(new HashSet<>(262_144, 0.75f), keys);
        Set<Integer> linkedSparse =
                fill(new LinkedHashSet<>(262_144, 0.75f), keys);

        System.out.println("shared input keys: " + keys.length);
        System.out.println("hash dense size: " + hashDense.size());
        System.out.println("linked dense size: " + linkedDense.size());
        System.out.println("hash sparse size: " + hashSparse.size());
        System.out.println("linked sparse size: " + linkedSparse.size());
        System.out.println("dense sets equal: " + hashDense.equals(linkedDense));
        System.out.println("sparse sets equal: " + hashSparse.equals(linkedSparse));
        System.out.println("hash dense checksum: " + checksum(hashDense));
        System.out.println("linked dense checksum: " + checksum(linkedDense));
        System.out.println("hash sparse checksum: " + checksum(hashSparse));
        System.out.println("linked sparse checksum: " + checksum(linkedSparse));
        System.out.println("all contain 999: "
                + (hashDense.contains(999) && linkedDense.contains(999)
                && hashSparse.contains(999) && linkedSparse.contains(999)));
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 SetComparisonSetupDemo.java
java SetComparisonSetupDemo
```

Stdout:

```text
shared input keys: 1000
hash dense size: 1000
linked dense size: 1000
hash sparse size: 1000
linked sparse size: 1000
dense sets equal: true
sparse sets equal: true
hash dense checksum: 499500
linked dense checksum: 499500
hash sparse checksum: 499500
linked sparse checksum: 499500
all contain 999: true
```

Chương trình tạo một mảng đối tượng khóa chung, rồi đưa cùng các đối tượng đó vào bốn tập. Hai cặp dùng cùng số phần tử nhưng hai gợi ý capacity khác nhau.

Tên `Dense` và `Sparse` biểu đạt chủ đích cấu hình của ví dụ: một gợi ý vừa với quy mô hơn, một gợi ý rất lớn so với 1.000 phần tử. Chúng không phải kết quả đo tỷ lệ đầy hoặc kết quả đọc thuộc tính capacity từ API.

Checksum giúp kiểm tra các vòng duyệt đều xử lý nội dung tương ứng. Tổng từ `0` tới `999` là `499_500`, không phụ thuộc thứ tự duyệt.

Không có số đo thời gian hay số byte trong stdout. Chương trình là bước chuẩn bị và kiểm tra dữ liệu trước phép đo, không phải một benchmark.

Hai chương trình độc lập trong bài đã được biên dịch với `--release 17` và chạy đối chiếu đúng stdout. Tùy chọn này kiểm tra mức ngôn ngữ/API và tạo bytecode tương thích Java 17; nó không khẳng định JVM thực thi chính là JDK 17.

## 8. Đo thời gian: phải tách từng câu hỏi

[OpenJDK JMH](https://github.com/openjdk/jmh) là công cụ dùng để xây dựng và chạy các phép đo trên JVM. Công cụ không thay thế việc chọn đúng tải công việc.

Một kế hoạch đo có thể tách thành:

| Phép đo | Trạng thái và thao tác cần chuẩn bị | Kết luận có thể phục vụ |
| --- | --- | --- |
| Tìm có mặt | Tập đã xây dựng, truy vấn các khóa đang có | Chi phí tra cứu thành công |
| Tìm vắng mặt | Tập đã xây dựng, truy vấn khóa không có | Chi phí tra cứu thất bại |
| Thêm mới | Bảo đảm khóa chưa có và kiểm soát việc tăng dung lượng | Chi phí thay đổi tập theo tải thêm mới |
| Thêm trùng | Khóa đã có | Chi phí thử thêm giá trị trùng |
| Xóa có mặt | Chuẩn bị lại phần tử cho lượt đo tiếp theo theo thiết kế | Chi phí xóa thành công |
| Duyệt | Cùng tập đã xây dựng, xử lý toàn bộ phần tử | Ảnh hưởng của số phần tử và độ thưa |
| Xây dựng | Tạo tập và nạp cùng dữ liệu | Chi phí khởi tạo tổng thể, gồm cấp phát |

Những sai lệch cần tránh:

- Đặt `println` trong phần muốn đo riêng thao tác tập.
- Đo `add` cùng một khóa nhiều lần nhưng gọi đó là thêm mới.
- Xóa một lần rồi đo tiếp việc xóa vắng mặt như thể mọi lượt đều xóa thành công.
- Tạo dữ liệu hoặc xây dựng lại tập trong một phép đo được mô tả là chỉ `contains`.
- Bỏ kết quả mà không thiết kế đúng cách quan sát kết quả trong benchmark.
- Chỉ đo một kích thước hoặc một kiểu khóa rồi khái quát cho mọi ứng dụng.

Trên JVM, khởi động, biên dịch JIT, cấp phát và thu gom rác có thể làm phép đo tùy tiện khó diễn giải. Dùng cấu hình warmup, các lượt đo và các lần chạy độc lập phù hợp theo hướng dẫn của công cụ; vẫn phải xem dữ liệu có đại diện không.

Nếu mục tiêu là đánh giá độ trễ của từng yêu cầu có thể tăng dung lượng, đừng chỉ nhìn một giá trị trung bình đã gộp cả những lần thêm thông thường. Nếu mục tiêu là duyệt nhiều lần trên tập đã xây dựng, hãy tách thời gian xây dựng khỏi phần duyệt.

Một báo cáo cần nêu JDK/JVM, cấu hình chạy, loại khóa, kích thước tập, cấu hình dung lượng, phân bố truy vấn và đơn vị đo. Không ghi “LinkedHashSet luôn nhanh hơn” chỉ vì nó thắng một phép duyệt trên một bảng thưa.

## 9. Đo bộ nhớ: xem cả đồ thị đối tượng, không chỉ vỏ Set

### 9.1. Kích thước nông và footprint khác nhau

Kích thước nông của một đối tượng chỉ nói về chính đối tượng đó, không tự cộng toàn bộ các đối tượng mà nó tham chiếu.

Đo riêng vỏ `HashSet` và `LinkedHashSet` có thể không thể hiện được phần lớn khác biệt, vì bảng và các mục nằm ở những đối tượng khác trong đồ thị.

Muốn hiểu bộ nhớ của cấu trúc, cần xem các đối tượng có thể đi tới từ tập và xác định rõ có tính dữ liệu phần tử không.

### 9.2. Dùng công cụ để quan sát thay vì lấy một con số cố định từ trí nhớ

[OpenJDK JOL](https://github.com/openjdk/jol) hỗ trợ xem bố trí và footprint đối tượng trên JVM. Các thông tin như kích thước tham chiếu và căn chỉnh đối tượng cần được ghi cùng kết quả.

Với dữ liệu đã chuẩn bị trong chương trình thứ hai, một quy trình có thể là:

1. Thiết lập JOL trong một chương trình đo riêng theo hướng dẫn của công cụ.
2. Ghi cấu hình JVM và kiểu đối tượng đang đo.
3. Quan sát đồ thị bắt đầu từ `hashDense` và `linkedDense`, dùng khả năng phân tích đồ thị như `GraphLayout.parseInstance`.
4. Đọc tổng kích thước và phân bố các lớp đối tượng trong mỗi đồ thị, thay vì chỉ một con số tổng.
5. Lặp lại với cặp gợi ý capacity lớn để thấy phần bảng ảnh hưởng thế nào.
6. Giữ rõ cách tính các khóa chung giữa các tập.

`GraphLayout.totalSize()` mô tả tổng footprint của đồ thị được công cụ phân tích. Bài này không cung cấp output JOL giả định làm số đo: cần chạy công cụ trên môi trường thực tế để có kết quả tương ứng. [GraphLayout trong JOL](https://github.com/openjdk/jol/blob/master/jol-core/src/main/java/org/openjdk/jol/info/GraphLayout.java)

### 9.3. Không cộng hai footprint riêng rồi coi đó là tổng bộ nhớ độc quyền

Trong ví dụ, nhiều tập dùng chung các đối tượng khóa. Nếu phân tích từng tập riêng, đồ thị của mỗi tập đều có thể bao gồm các khóa đó.

Cộng thẳng hai tổng riêng có thể đếm các đối tượng dùng chung nhiều lần. Nếu đo cả hai như các gốc trong một đồ thị, cách đếm đối tượng dùng chung lại khác. Cần nói rõ phép đo đang trả lời câu hỏi nào.

Footprint các đối tượng có thể đi tới cũng không tự có nghĩa toàn bộ số byte đó sẽ được giải phóng khi bỏ riêng một tập, vì các khóa hoặc đối tượng khác còn có thể được nơi khác tham chiếu tới.

### 9.4. Bộ nhớ còn sống và lượng cấp phát là hai thước đo khác nhau

Một phép đo sau khi xây dựng có thể cho biết những đối tượng còn sống trong cấu trúc được quan sát. Nó chưa mô tả toàn bộ lượng cấp phát tạm thời trong quá trình tăng dung lượng hoặc tạo khóa truy vấn.

Nếu quan tâm áp lực thu gom rác trong tải thêm/xóa liên tục, cần đánh giá lượng cấp phát và vòng đời đối tượng tương ứng. Nếu quan tâm sức chứa ổn định của một bảng tra cứu ít thay đổi, footprint trạng thái đã xây dựng có thể gần câu hỏi hơn.

Không lấy một phép trừ bộ nhớ trống trước–sau một lần chạy nhỏ rồi coi đó là kích thước chính xác của từng mục. Các công việc khác của JVM và trạng thái thu gom rác làm cách diễn giải đó thiếu cơ sở.

## 10. Các tình huống lựa chọn cụ thể

### 10.1. Chủ yếu kiểm tra mã đã thấy, không cần thứ tự

Nếu chương trình giữ một tập mã và gọi `contains` rất nhiều, ít khi duyệt toàn bộ, không có yêu cầu trình bày theo thứ tự, `HashSet` thường là điểm bắt đầu phù hợp.

Nó không cần chi phí duy trì thứ tự chèn mà bài toán không sử dụng. Vẫn cần kiểm tra quy mô, cấu hình dung lượng và chất lượng khóa.

### 10.2. Loại trùng rồi xuất theo thứ tự gặp đầu tiên

Nếu đầu vào có thứ tự và kết quả cần giữ lần xuất hiện đầu tiên, `LinkedHashSet` cung cấp đúng hành vi trong một cấu trúc.

Chọn `HashSet` rồi cố suy ra thứ tự chèn từ output không đáp ứng hợp đồng. Việc tiết kiệm một phần bộ nhớ không bù được kết quả sai yêu cầu.

### 10.3. Tập được duyệt nhiều và có bảng thưa

`LinkedHashSet` có mô hình duyệt theo số phần tử, nên đáng được đánh giá trong tình huống này. Nhưng cần so cả bộ nhớ của liên kết lẫn bảng và xem có thể cấu hình lại `HashSet` cho hợp lý hơn không.

Không thể chỉ từ mô hình O(n) mà bảo đảm tốc độ cụ thể trên mọi tập dữ liệu. Cách bố trí bộ nhớ và công việc làm với từng phần tử vẫn ảnh hưởng kết quả thực tế.

### 10.4. Có rất nhiều phần tử và bộ nhớ là giới hạn chính

Khi không cần thứ tự, phần liên kết bổ sung có thể là chi phí đáng tránh. Hãy đo cấu trúc với loại khóa thật và cùng điều kiện dung lượng.

Nếu các khóa chiếm phần lớn heap, tối ưu biểu diễn khóa hoặc vòng đời dữ liệu có thể có ảnh hưởng lớn hơn đổi giữa hai loại tập. Điều này phải dựa trên phân tích ứng dụng, không phải một giả định chung cho mọi hệ thống.

## 11. Các điều kiện chung không được bỏ qua

Cả hai cấu trúc đều không tự đồng bộ để nhiều luồng cùng sửa đổi. So thời gian trong một bài toán nhiều luồng cần đưa cơ chế đồng bộ hoặc cấu trúc phù hợp vào thiết kế; không so một cấu trúc được bảo vệ với một cấu trúc bị dùng sai rồi gọi đó là chênh lệch tự nhiên giữa hai lớp.

Cả hai đều cần quy tắc phần tử ổn định. Đổi lớp tập không giải quyết việc sửa trường tham gia `equals`/`hashCode` khi phần tử đang được lưu.

Cả hai đều có thể chịu tác động của phân bố băm kém. Liên kết thứ tự không tự làm các truy vấn băm hết va chạm.

Các điểm này thuộc tính đúng và điều kiện phân tích. Một phép đo nhanh của chương trình sai không phải cơ sở lựa chọn cấu trúc.

## 12. Những kết luận sai thường gặp

| Kết luận | Vì sao chưa đúng | Cách sửa |
| --- | --- | --- |
| Cùng O(1) nên nhanh như nhau | Độ phức tạp không xác định mọi hằng số và chi phí JVM | Đo đúng kiểu thao tác khi cần con số |
| LinkedHashSet chứa linked list nên contains là O(n) | Liên kết phục vụ thứ tự; tìm thành viên vẫn dùng băm | Tách đường tìm với đường duyệt |
| HashSet luôn duyệt nhanh hơn vì ít liên kết hơn | Duyệt còn phụ thuộc capacity | Xét n và C, đặc biệt khi bảng thưa |
| LinkedHashSet luôn nhanh hơn vì duyệt O(n) | Ứng dụng có thể chủ yếu thêm/xóa hoặc tra cứu | So đúng tải công việc |
| LinkedHashSet luôn thêm đúng một số byte cố định trên mọi JVM | Bố trí đối tượng, tham chiếu và loại mục khác nhau | Ghi môi trường và đo footprint |
| Chỉ đo chính đối tượng Set là đủ | Bảng và các mục nằm ở đồ thị phía sau | Xem phạm vi đo bộ nhớ |
| Hai tập cùng size thì bộ nhớ nền chắc như nhau | Capacity và loại mục có thể khác | Giữ cấu hình và quan sát cấu trúc |
| Cộng footprint hai tập dùng chung khóa là tổng heap thực tế | Có thể đếm lặp đối tượng dùng chung | Xác định gốc và quy tắc đếm |
| Một vòng add cùng khóa đo chi phí thêm mới | Hầu hết lượt là thêm trùng | Chuẩn bị trạng thái đúng câu hỏi |
| Đổi sang LinkedHashSet sửa được hashCode kém | Cả hai vẫn dùng băm | Sửa quy tắc khóa và phân bố băm |

## 13. Tự luyện và đối chiếu

### Bài 1: đọc đúng hai công thức duyệt

Có hai tập cùng `n = 2_000`. Một bảng có capacity cùng quy mô với số phần tử, bảng khác có capacity lớn hơn rất nhiều.

1. Vì sao chỉ biết `n` chưa đủ để mô tả công việc duyệt `HashSet`?
2. Theo mô hình tài liệu, capacity ảnh hưởng đường duyệt `LinkedHashSet` như thế nào?
3. Có thể từ đó kết luận chắc chắn một phép duyệt mất bao nhiêu nano giây không?

Đối chiếu: `HashSet` có mô hình O(n + C); `LinkedHashSet` duyệt theo chuỗi phần tử với mô hình O(n); các công thức chưa cung cấp số đo thời gian cụ thể.

### Bài 2: kiểm tra một phép tính bộ nhớ

Một người nói: “Có 100.000 mục, giả sử mỗi tham chiếu 4 byte, hai tham chiếu bổ sung tương ứng 800.000 byte, vậy tổng chênh lệch heap chắc chắn đúng 800.000 byte”.

Phần tính trường theo giả định là đúng. Phần kết luận tổng heap chắc chắn là không đủ cơ sở vì còn căn chỉnh, cấu trúc quản lý, loại mục, cấu hình JVM và phạm vi tính dữ liệu phần tử.

### Bài 3: phát hiện so sánh không tương đương

Một phép đo tạo `HashSet` với gợi ý dung lượng rất lớn, còn `LinkedHashSet` dùng cấu hình mặc định; sau đó nạp cùng 1.000 giá trị và đo duyệt.

Kết quả có thể hữu ích để quan sát hai cấu hình cụ thể. Nhưng nó chưa tách được ảnh hưởng của “loại tập” khỏi ảnh hưởng của “cấu hình bảng”. Muốn so có kiểm soát, cần thêm các cặp cấu hình tương đương và mô tả rõ mục tiêu.

### Bài 4: chọn theo yêu cầu

- Tập mã chỉ cần kiểm tra thành viên, không cần thứ tự: bắt đầu cân nhắc `HashSet`.
- Kết quả loại trùng phải theo lần xuất hiện đầu tiên: `LinkedHashSet` đáp ứng ý nghĩa thứ tự.
- Tập được duyệt nhiều, có dấu hiệu bảng quá thưa: kiểm tra capacity/cấu hình và đánh giá cả hai theo tải duyệt.
- Cần quyết định dựa trên giới hạn heap: đo cùng dữ liệu, cùng cấu hình và ghi rõ cách tính đối tượng dùng chung.

Mỗi lựa chọn cần được giải thích bằng yêu cầu và bằng chứng, không bằng một khẩu hiệu “cấu trúc này luôn tốt hơn”.

## 14. Tài liệu tra cứu

- [HashSet Java 17 — điều kiện hiệu năng và chi phí duyệt](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HashSet.html)
- [LinkedHashSet Java 17 — liên kết thứ tự, thao tác và duyệt](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/LinkedHashSet.html)
- [HashMap Java 17 — dung lượng và hệ số tải](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HashMap.html)
- [OpenJDK 17 LinkedHashMap — chi tiết mục liên kết dùng để giải thích chi phí](https://github.com/openjdk/jdk17u/blob/master/src/java.base/share/classes/java/util/LinkedHashMap.java)
- [OpenJDK JMH — thiết kế và chạy benchmark trên JVM](https://github.com/openjdk/jmh)
- [OpenJDK JOL — bố trí và footprint đối tượng](https://github.com/openjdk/jol)
