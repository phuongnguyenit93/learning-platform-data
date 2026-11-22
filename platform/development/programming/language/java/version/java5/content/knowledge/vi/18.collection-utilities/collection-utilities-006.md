# Collections.addAll với tham số varargs

## 1. Mục đích: thêm nhiều đối số vào một collection đã có

`Collections.addAll` là phương thức static giúp thêm nhiều phần tử vào một collection đích:

```java
List<String> names = new ArrayList<>();
Collections.addAll(names, "An", "Binh", "Chi");
```

Sau lời gọi, names chứa ba phần tử theo thứ tự thêm của ArrayList.

Điểm quan trọng:

- Collection đích đã tồn tại.
- Phương thức thay đổi collection đích nếu đích cho phép thêm.
- Các đối số cuối được nhận qua varargs.
- Kết quả trả về là boolean cho biết collection có thay đổi hay không, không phải một collection mới.

Đây là API vẫn có giá trị trong Java hiện đại. Các ví dụ trong bài chạy trên Java 17+.

## 2. Hiểu chữ ký để chọn đúng kiểu dữ liệu

Chữ ký rút gọn:

```java
static <T> boolean addAll(Collection<? super T> collection, T... elements)
```

Ý nghĩa:

- T là kiểu phần tử của lời gọi.
- Collection đích nhận được các giá trị T hoặc kiểu phù hợp.
- `? super T` cho phép đích có kiểu phần tử là kiểu cha của T.
- `T...` là tham số varargs; trong thân phương thức nó có dạng mảng T[].

Ví dụ:

```java
Collection<Number> numbers = new ArrayList<>();
Collections.addAll(numbers, Integer.valueOf(1), Double.valueOf(2.5));
```

Collection<Number> có thể nhận các giá trị Integer và Double. Trong khi đó, không thể thêm một String vào List<Integer> bằng cách dùng Collections.addAll để vượt qua kiểm tra kiểu.

Collection<?> nhìn chung không cung cấp quyền thêm một giá trị tùy ý khác null qua API generic, vì kiểu phần tử thật chưa biết. Khi thiết kế phương thức nhận đích để thêm, hãy chọn ràng buộc kiểu thể hiện đúng khả năng ghi.

## 3. Varargs nhận các phần tử rời hoặc một mảng tham chiếu có sẵn

Hai cách dùng:

```java
Collections.addAll(names, "An", "Binh");

String[] more = {"Chi", "Dung"};
Collections.addAll(names, more);
```

Ở lời gọi thứ hai, từng phần tử trong more được thêm vào names. Đây không phải thêm nguyên String[] như một phần tử của List<String>.

Cơ chế varargs có thể nhận trực tiếp mảng tương thích. Nó không tự sao chép sâu các đối tượng phần tử. Collection giữ các tham chiếu được thêm theo hợp đồng của nó.

Nếu thay một ô trong mảng nguồn sau khi thêm:

```java
more[0] = "Changed";
```

ô tương ứng trong ArrayList không tự đổi thành chuỗi mới, vì các vị trí của list không được liên kết như một view vào mảng nguồn. Nhưng nếu phần tử là một đối tượng có thể thay đổi và cả list lẫn mảng cùng giữ tham chiếu tới nó, sửa trạng thái đối tượng đó vẫn có thể được quan sát từ cả hai nơi.

## 4. Chương trình đầy đủ

Lưu thành `CollectionsAddAllDemo.java`:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;

public class CollectionsAddAllDemo {
    public static void main(String[] args) {
        List<String> names = new ArrayList<>();
        boolean firstChange =
                Collections.addAll(names, "An", "Binh");

        String[] more = {"Chi", "Dung"};
        boolean secondChange = Collections.addAll(names, more);
        more[0] = "Changed";

        System.out.println("first change=" + firstChange);
        System.out.println("second change=" + secondChange);
        System.out.println("names=" + names);
        System.out.println("source=" + Arrays.toString(more));

        Set<String> tags = new LinkedHashSet<>();
        System.out.println("set first="
                + Collections.addAll(tags, "java", "queue", "java"));
        System.out.println("set repeated="
                + Collections.addAll(tags, "java"));
        System.out.println("tags=" + tags);
        System.out.println("empty input="
                + Collections.addAll(tags));

        int[] raw = {1, 2, 3};
        List<int[]> arrays = new ArrayList<>();
        Collections.addAll(arrays, raw);

        System.out.println("primitive array count=" + arrays.size());
        System.out.println("primitive array same="
                + (arrays.get(0) == raw));
        System.out.println("primitive array content="
                + Arrays.toString(arrays.get(0)));

        List<Integer> values = new ArrayList<>();
        Collections.addAll(values, 1, 2, 3);
        System.out.println("boxed values=" + values);
    }
}
```

Biên dịch và chạy:

```shell
javac -encoding UTF-8 CollectionsAddAllDemo.java
java CollectionsAddAllDemo
```

Kết quả:

```text
first change=true
second change=true
names=[An, Binh, Chi, Dung]
source=[Changed, Dung]
set first=true
set repeated=false
tags=[java, queue]
empty input=false
primitive array count=1
primitive array same=true
primitive array content=[1, 2, 3]
boxed values=[1, 2, 3]
```

LinkedHashSet được chọn để thứ tự in tags ổn định theo thứ tự gặp đầu tiên. Không dùng HashSet rồi khẳng định một thứ tự stdout không được hợp đồng bảo đảm.

Mảng nguồn more và list không có quan hệ view theo từng vị trí. Ngược lại, raw được thêm như một đối tượng mảng vào List<int[]>, nên `arrays.get(0) == raw` là true.

## 5. Giá trị boolean phụ thuộc việc đích có thay đổi không

Với một ArrayList cho phép thêm, thêm một hay nhiều phần tử thường làm kích thước tăng và kết quả là true.

Với Set:

```java
Set<String> tags = new LinkedHashSet<>();
Collections.addAll(tags, "java"); // true
Collections.addAll(tags, "java"); // false
```

Lời gọi thứ hai không thêm một phần tử trùng, nên đích không thay đổi.

Nếu một batch có cả giá trị đã tồn tại và giá trị mới, kết quả là true nếu collection thay đổi trong quá trình thêm.

Lời gọi không có đối số phần tử:

```java
Collections.addAll(tags);
```

không thêm gì và trả false. Điều này khác với truyền một phần tử null hoặc truyền mảng varargs null.

Boolean không cho biết có bao nhiêu phần tử được thêm. Nếu cần số lượng, phải dùng một chính sách đo/đếm phù hợp; chỉ lấy chênh lệch size cũng cần xem xét truy cập đồng thời và hợp đồng collection.

## 6. Mảng nguyên thủy không tự trở thành dãy phần tử bao

Lời gọi sau không hợp lệ:

```java
List<Integer> values = new ArrayList<>();

// Không biên dịch:
// Collections.addAll(values, new int[] {1, 2, 3});
```

Java có thể đóng hộp từng đối số int rời:

```java
Collections.addAll(values, 1, 2, 3);
```

nhưng không tự đổi một int[] thành Integer[] bằng cách đóng hộp toàn bộ các phần tử.

Một int[] có thể là **một đối tượng phần tử** nếu collection đích nhận int[] hoặc Object, như chương trình đầy đủ đã minh họa. Nó không tự được trải thành ba Integer.

Nếu đã có int[] và muốn thêm các số vào List<Integer>, dùng vòng lặp rõ ràng:

```java
int[] raw = {1, 2, 3};
List<Integer> values = new ArrayList<>();
for (int value : raw) {
    values.add(value);
}
```

Ở đây việc đóng hộp xảy ra cho từng value được thêm.

## 7. Phân biệt với Collection.addAll và Arrays.asList

| Cách viết | Đầu vào phần tử | Tác động chính |
| --- | --- | --- |
| `Collections.addAll(dest, a, b)` | Các đối số rời hoặc mảng tham chiếu phù hợp | Thêm vào dest đã có |
| `dest.addAll(source)` | Một Collection nguồn | Thêm các phần tử từ collection nguồn vào dest |
| `Arrays.asList(array)` | Mảng tham chiếu/varargs | Tạo list kích thước cố định được hỗ trợ bởi mảng |
| `new ArrayList<>(source)` | Một Collection nguồn | Tạo một list mới chứa các phần tử từ nguồn |

Nếu nguồn đã là Collection, `dest.addAll(source)` thường thể hiện ý định trực tiếp và có thể có tối ưu riêng theo cài đặt. Không cần biến source thành mảng chỉ để gọi static Collections.addAll.

Arrays.asList không có cùng mục tiêu với Collections.addAll. List do Arrays.asList trả về có kích thước cố định:

```java
List<String> fixed = Arrays.asList("A", "B");

// Không hỗ trợ tăng kích thước:
// Collections.addAll(fixed, "C");
```

Lời gọi bị chú thích sẽ ném UnsupportedOperationException khi cố thêm phần tử. Muốn một list có thể tăng kích thước:

```java
List<String> editable =
        new ArrayList<>(Arrays.asList("A", "B"));
Collections.addAll(editable, "C");
```

Nếu dùng List.of để tạo list không sửa được, việc thêm cũng không được hỗ trợ. Collections.addAll không biến một collection không sửa được thành collection sửa được.

## 8. Null: phân biệt collection đích, mảng đầu vào và phần tử

### Collection đích null

Collections.addAll yêu cầu một collection đích hợp lệ. Không dùng null thay cho collection rồi kỳ vọng phương thức tạo đích mới.

### Mảng varargs null

```java
// String[] missing = null;
// Collections.addAll(names, missing);
```

Đây là truyền mảng đầu vào null, không phải mảng rỗng; lời gọi sẽ ném NullPointerException.

### Một phần tử null

```java
Collections.addAll(names, (String) null);
```

Lời gọi này có một phần tử null. Có được thêm hay không phụ thuộc collection:

- ArrayList cho phép phần tử null.
- PriorityQueue, ArrayDeque và nhiều cấu trúc khác không chấp nhận null.

Không viết trần `Collections.addAll(names, null)` rồi giả định ý nghĩa là một phần tử null. Với names có kiểu List<String>, null có thể được hiểu theo cách truyền mảng varargs null; dùng ép kiểu phần tử hoặc mảng rõ ràng để biểu đạt ý định.

Các giới hạn khác của đích như kiểu được phép, sức chứa hoặc điều kiện nghiệp vụ vẫn có hiệu lực. Static utility không bỏ qua các kiểm tra đó.

## 9. Không có cam kết thêm cả batch một cách nguyên tử

Collections.addAll không phải một giao dịch “thêm tất cả hoặc không thay đổi gì”. Nếu một lần thêm giữa chừng thất bại, các phần tử trước đó có thể đã được thêm.

Ví dụ, đích không cho phép null và các đối số là một giá trị hợp lệ rồi null: không được mặc định rằng lỗi ở null tự hoàn tác phần tử đầu.

Nếu cần kiểm tra trước toàn bộ dữ liệu, hãy định nghĩa bước xác thực trước khi ghi. Nếu cần tính nguyên tử với nhiều luồng hoặc với các tài nguyên khác, phải có giao thức đồng bộ/giao dịch phù hợp; việc kiểm tra trước đơn thuần chưa tự giải quyết thay đổi đồng thời.

Một collection an toàn luồng cũng không tự bảo đảm cả batch static addAll là một thao tác nguyên tử không xen kẽ. Phải xem đúng hợp đồng bulk operation và cơ chế của lớp đang sử dụng.

## 10. Chi phí và cách dùng phù hợp

Có thể hình dung phương thức lần lượt yêu cầu collection đích thêm từng phần tử. Chi phí tổng phụ thuộc thao tác add của đích:

- ArrayList có thêm cuối O(1) khấu hao, nên thêm m phần tử có chi phí phân bổ tương ứng.
- PriorityQueue cần duy trì heap cho từng lần thêm.
- Set có kiểm tra phần tử đã tồn tại theo cấu trúc và quan hệ bằng nhau của nó.

Không có một cận O(m) cho mọi collection và mọi kiểu phần tử chỉ vì cú pháp lời gọi ngắn.

Nếu truyền các đối số rời, cơ chế varargs chuẩn bị mảng đối số; nếu truyền một mảng tham chiếu tương thích có sẵn, không cần mảng bao ngoài chỉ vì varargs. Đóng hộp cũng có thể liên quan khi các đối số nguyên thủy được đưa vào collection kiểu bao.

Không chọn cách viết chỉ dựa vào một phỏng đoán rằng Collections.addAll luôn nhanh hơn mọi dest.addAll. Hãy ưu tiên dạng phù hợp dữ liệu nguồn; khi chi phí có ý nghĩa, đo trong bối cảnh và cài đặt thật.

## 11. Thực hành

1. Thêm hai tên giống nhau vào ArrayList rồi vào LinkedHashSet. Giải thích khác biệt về kích thước và boolean.
2. Đổi more[0] sau khi thêm vào list; sau đó thay String bằng một đối tượng có thể sửa và phân biệt thay ô mảng với sửa trạng thái đối tượng được chia sẻ.
3. Thử thêm int[] vào List<Integer> và đọc lỗi biên dịch; sau đó sửa bằng vòng lặp.
4. So sánh mảng varargs null, một phần tử null và không có phần tử nào.
5. Nếu đích là collection không cho phép null, hãy dự đoán khả năng thay đổi một phần trước khi quan sát lỗi của batch.

## Tài liệu đối chiếu

- [Collections.addAll — Chữ ký generic, varargs và kết quả thay đổi](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Collections.html#addAll(java.util.Collection,T...)).
- [Collection.addAll — Thêm từ một collection nguồn](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Collection.html#addAll(java.util.Collection)).
- [Arrays.asList — List kích thước cố định được hỗ trợ bởi mảng](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Arrays.html#asList(T...)).
