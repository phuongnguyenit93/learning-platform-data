# Sao chép nông và đối tượng phần tử vẫn được chia sẻ

## 1. Hai lớp cần phân biệt khi sao chép mảng

Giả sử một mảng chứa các tác vụ. Mỗi tác vụ có tên và mức ưu tiên có thể thay đổi. Ta sao chép mảng để thử sắp xếp hoặc chỉnh sửa mà không muốn ảnh hưởng bản gốc.

Mảng mới giải quyết được một phần nhu cầu: việc thay phần tử hoặc đổi thứ tự các ô trong bản sao không tự thay các ô tương ứng của mảng gốc. Nhưng nếu các ô chứa tham chiếu tới đối tượng, hai mảng vẫn có thể cùng truy cập một tác vụ.

Có hai lớp khác nhau:

1. **Đối tượng mảng:** vùng chứa các ô phần tử.
2. **Đối tượng được phần tử tham chiếu:** tác vụ, học viên, đơn hàng hoặc đối tượng khác.

Sao chép nông (shallow copy) tạo bản sao ở lớp vùng chứa và giữ nguyên các giá trị phần tử. Với phần tử kiểu tham chiếu, giá trị đó là tham chiếu, nên đối tượng ở lớp thứ hai vẫn được dùng chung.

```text
trước sao chép:

source ──→ mảng A
            [0] ──→ tác vụ X
            [1] ──→ tác vụ Y

sau sao chép nông:

source ──→ mảng A
            [0] ──┐
                  ├──→ tác vụ X
copy   ──→ mảng B  │
            [0] ──┘

mảng A và B khác nhau; tác vụ X vẫn chỉ có một đối tượng
```

Đây là hành vi hiện hành của Java, không phải hạn chế riêng của Java 6. Các ví dụ trong bài dùng Java 17 trở lên và chỉ dựa trên những cơ chế còn được áp dụng hiện nay.

## 2. Gán tham chiếu chưa phải sao chép mảng

Đoạn này chỉ tạo một tên tham chiếu khác tới cùng mảng:

```java
// Đoạn minh họa; source là mảng đã có.
Task[] alias = source;
```

Không có mảng mới và không có đối tượng `Task` mới. Nếu viết `alias[0] = anotherTask`, ô số 0 của chính mảng mà `source` trỏ tới sẽ thay đổi.

Ngược lại:

```java
import java.util.Arrays;

// Đoạn minh họa; Task là lớp của ứng dụng.
Task[] copy = Arrays.copyOf(source, source.length);
```

Ở đây có mảng mới, nhưng các phần tử trong phần được sao chép vẫn giữ tham chiếu như nguồn.

Ta có thể kiểm tra hai điều độc lập:

```java
// Đoạn minh họa khi source có ít nhất một phần tử.
System.out.println(source == copy);       // false
System.out.println(source[0] == copy[0]); // true ngay sau sao chép
```

Toán tử `==` trên tham chiếu kiểm tra hai phía có trỏ tới cùng đối tượng không. Một phương thức `equals` được lớp tự định nghĩa có thể so sánh nội dung, nên không thay thế được phép kiểm tra danh tính trong câu hỏi “có cùng đối tượng hay không”.

Theo [JLS về biến mảng](https://docs.oracle.com/javase/specs/jls/se25/html/jls-10.html#jls-10.2), biến mảng giữ tham chiếu tới đối tượng mảng. Phân biệt biến tham chiếu, mảng và đối tượng phần tử giúp tránh nhầm ngay từ thao tác gán.

## 3. Các cách sao chép phổ biến có cùng giới hạn độ sâu

| Cách thực hiện | Vùng chứa kết quả | Đối tượng phần tử được tự sao chép không? |
| --- | --- | --- |
| `source.clone()` | Mảng mới cùng độ dài | Không |
| `Arrays.copyOf(source, length)` | Mảng mới theo độ dài yêu cầu | Không |
| `Arrays.copyOfRange(source, from, to)` | Mảng mới chứa đoạn yêu cầu | Không |
| `System.arraycopy(source, ..., target, ..., count)` | Ghi vào mảng đích đã tồn tại | Không |

Với `System.arraycopy`, việc mảng đích có độc lập với nguồn hay không còn phụ thuộc bạn truyền đối tượng nào làm `target`. Bản thân phương thức không cấp phát mảng đích. Nếu đích là một mảng mới, nó vẫn chỉ nhận các tham chiếu phần tử được chuyển từ nguồn. Xem [System.arraycopy](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/System.html#arraycopy(java.lang.Object,int,java.lang.Object,int,int)).

Hợp đồng `clone()` của mảng được quy định trong [JLS về thành viên của mảng](https://docs.oracle.com/javase/specs/jls/se25/html/jls-10.html#jls-10.7). `Arrays.copyOf` và `copyOfRange` là các cách tạo mảng mới, không phải công cụ tự đi theo mọi tham chiếu để nhân bản đối tượng. Tham khảo [Arrays.copyOf](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Arrays.html#copyOf(T%5B%5D,int)).

Không cần so sánh tốc độ các API để trả lời câu hỏi về độ sâu. Đổi từ một API trong bảng sang API khác không tự biến bản sao nông thành bản sao sâu.

## 4. Chương trình đầy đủ: thay ô mảng và sửa đối tượng

Lưu tệp **ShallowTaskCopyDemo.java**:

```java
import java.util.Arrays;

public class ShallowTaskCopyDemo {
    static class Task {
        final String name;
        int priority;

        Task(String name, int priority) {
            this.name = name;
            this.priority = priority;
        }
    }

    public static void main(String[] args) {
        Task[] source = {
                new Task("A", 1),
                new Task("B", 2)
        };

        Task[] alias = source;
        Task[] copy = Arrays.copyOf(source, source.length);
        Task[] cloned = source.clone();
        Task[] range = Arrays.copyOfRange(source, 0, 1);
        Task[] target = new Task[source.length];
        System.arraycopy(source, 0, target, 0, source.length);

        System.out.println("alias shares array: " + (alias == source));
        System.out.println("copy is new array: " + (copy != source));
        System.out.println("clone shares first task: "
                + (cloned[0] == source[0]));
        System.out.println("range shares first task: "
                + (range[0] == source[0]));
        System.out.println("arraycopy shares first task: "
                + (target[0] == source[0]));

        copy[0].priority = 7;
        System.out.println("source priority after object edit: "
                + source[0].priority);

        copy[0] = new Task("C", 9);
        System.out.println("source name after slot replacement: "
                + source[0].name);
        System.out.println("copy name after slot replacement: "
                + copy[0].name);

        copy[1] = null;
        System.out.println("source second task after copy slot cleared: "
                + source[1].name);

        alias[1] = null;
        System.out.println("source second slot after alias edit: "
                + (source[1] == null));

        source[0].priority = 8;
        System.out.println("clone still sees source object edit: "
                + cloned[0].priority);
        System.out.println("replaced copy task priority: "
                + copy[0].priority);
    }
}
```

Biên dịch và chạy với JDK 17 trở lên:

```shell
javac ShallowTaskCopyDemo.java
java ShallowTaskCopyDemo
```

Stdout:

```text
alias shares array: true
copy is new array: true
clone shares first task: true
range shares first task: true
arraycopy shares first task: true
source priority after object edit: 7
source name after slot replacement: A
copy name after slot replacement: C
source second task after copy slot cleared: B
source second slot after alias edit: true
clone still sees source object edit: 8
replaced copy task priority: 9
```

### Đọc kết quả theo từng mức

`copy[0].priority = 7` đi qua tham chiếu ở ô số 0 rồi sửa đối tượng tác vụ A. Mảng nguồn cũng nhìn thấy số 7 vì nó trỏ tới cùng tác vụ.

`copy[0] = new Task("C", 9)` chỉ đổi ô số 0 của mảng `copy`. Mảng `source` vẫn trỏ tới A; từ thời điểm đó ô số 0 của hai mảng không còn trỏ tới cùng tác vụ.

`copy[1] = null` không làm `source[1]` thành `null`, vì hai ô thuộc hai mảng khác nhau. Nhưng `alias[1] = null` có ảnh hưởng trực tiếp vì `alias` và `source` là hai tham chiếu tới cùng mảng.

Cuối cùng, thay đổi tác vụ A qua `source` vẫn được `cloned` nhìn thấy. Riêng tác vụ C của `copy` không bị ảnh hưởng bởi lần thay đổi này.

## 5. Mảng kiểu nguyên thủy và phần tử bất biến

### 5.1. Với int[], phần tử là giá trị số

```java
import java.util.Arrays;

// Đoạn minh họa.
int[] measurements = {12, 15};
int[] edited = measurements.clone();

edited[0] = 99;
System.out.println(Arrays.toString(measurements)); // [12, 15]
System.out.println(Arrays.toString(edited));       // [99, 15]
```

Mỗi ô chứa một giá trị `int`, không phải tham chiếu tới một đối tượng số có thể bị sửa. Sau khi có mảng mới, gán vào ô của bản sao không ảnh hưởng ô của nguồn.

Không suy điều này sang `Integer[]` bằng cách coi `Integer` là `int`. `Integer[]` vẫn chứa tham chiếu; chỉ là đối tượng `Integer` bất biến nên không có thao tác đổi giá trị bên trong nó.

### 5.2. Với đối tượng bất biến, dùng chung có thể là lựa chọn đúng

`String` là ví dụ dễ gặp. Mảng `String[]` sao chép nông vẫn chia sẻ các đối tượng chuỗi, nhưng không thể sửa nội dung bên trong một `String` đã tồn tại.

```java
// Đoạn minh họa.
String[] labels = {"draft", "ready"};
String[] renamed = labels.clone();

renamed[0] = renamed[0].toUpperCase();

System.out.println(labels[0]);  // draft
System.out.println(renamed[0]); // DRAFT
```

Lời gọi `toUpperCase()` trong tình huống này trả chuỗi kết quả; phép gán đổi tham chiếu tại `renamed[0]`. Nó không sửa chuỗi `"draft"` mà mảng nguồn đang tham chiếu.

Dùng chung đối tượng bất biến thường tiết kiệm cấp phát và vẫn đáp ứng nhu cầu tách biệt dữ liệu. Chỉ nên sao chép sâu khi yêu cầu của ứng dụng thực sự cần độc lập ở các phần trạng thái có thể thay đổi.

## 6. Mảng nhiều chiều: hàng bên trong vẫn là đối tượng

Một `int[][]` là mảng chứa các tham chiếu tới `int[]`. Dù phần tử tận cùng là số nguyên, việc sao chép mảng ngoài vẫn chia sẻ các hàng:

```java
// Đoạn minh họa.
int[][] table = {{3, 6}, {9, 12}};
int[][] outerCopy = table.clone();

System.out.println(table == outerCopy);       // false
System.out.println(table[0] == outerCopy[0]); // true

outerCopy[0][1] = 100;
System.out.println(table[0][1]);             // 100

outerCopy[0] = new int[] {7, 8};
System.out.println(table[0][1]);             // 100
System.out.println(outerCopy[0][1]);         // 8
```

Hai biểu thức gán đi theo hai đường khác nhau:

- `outerCopy[0][1] = 100` sửa hàng đang dùng chung.
- `outerCopy[0] = ...` thay tham chiếu hàng trong mảng ngoài của bản sao.

Nếu cần độc lập mọi giá trị của một `int[][]`, có thể tạo mảng ngoài rồi sao chép từng hàng khác `null`. Cách này dùng được với hàng dài ngắn khác nhau, không giả định mảng luôn là hình chữ nhật.

```java
// Phương thức thành viên minh họa; không phải chương trình độc lập.
static int[][] copyIntRows(int[][] source) {
    int[][] result = new int[source.length][];
    for (int i = 0; i < source.length; i++) {
        result[i] = source[i] == null ? null : source[i].clone();
    }
    return result;
}
```

Với `Task[][]`, sao chép mảng ngoài và từng hàng chỉ tách các mảng; các đối tượng `Task` vẫn dùng chung. Độ sâu phải được xác định theo cấu trúc thật, không theo số lần gọi `clone`.

## 7. Khi cần đối tượng phần tử độc lập

Một bản sao phục vụ chỉnh sửa độc lập thường cần tạo đối tượng phần tử mới và sao chép những trường có thể thay đổi mà ứng dụng muốn tách biệt.

Không có một quy tắc tự động đúng cho mọi kiểu đối tượng:

- Trường nguyên thủy có thể lấy giá trị.
- Trường bất biến như `String` có thể chia sẻ.
- Danh sách có thể thay đổi cần vùng chứa danh sách mới nếu không muốn chia sẻ việc thêm/xóa.
- Nếu phần tử trong danh sách cũng có thể thay đổi, tạo danh sách mới vẫn chưa đủ.
- Tài nguyên như kết nối cơ sở dữ liệu, luồng I/O hoặc bộ thực thi không nên bị “nhân bản” theo một quy tắc sao chép dữ liệu chung chung.

Hàm tạo sao chép hoặc phương thức sao chép do ứng dụng định nghĩa giúp thể hiện chính sách đó rõ ràng.

## 8. Chương trình đầy đủ: sao chép tài liệu để chỉnh sửa

Trong ví dụ này, mỗi `Document` có tiêu đề `String` và danh sách nhãn `List<String>`. Tiêu đề và từng nhãn là chuỗi bất biến; danh sách nhãn và đối tượng tài liệu có thể thay đổi. Do đó cần tách đối tượng tài liệu và vùng chứa danh sách, còn các chuỗi có thể dùng chung.

Lưu tệp **DocumentCopyDemo.java**:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

public class DocumentCopyDemo {
    static class Document {
        String title;
        final List<String> tags;

        Document(String title, List<String> tags) {
            this.title = title;
            this.tags = new ArrayList<>(tags);
        }

        Document(Document source) {
            this(source.title, source.tags);
        }
    }

    static Document[] copyForEditing(Document[] source) {
        Objects.requireNonNull(source, "source");
        Document[] result = new Document[source.length];
        for (int i = 0; i < source.length; i++) {
            result[i] = source[i] == null
                    ? null
                    : new Document(source[i]);
        }
        return result;
    }

    public static void main(String[] args) {
        Document[] source = {
                new Document("Guide", List.of("java")),
                null
        };
        Document[] edited = copyForEditing(source);

        System.out.println("new array: " + (source != edited));
        System.out.println("new document: " + (source[0] != edited[0]));
        System.out.println("new tag list: "
                + (source[0].tags != edited[0].tags));
        System.out.println("same immutable tag: "
                + (source[0].tags.get(0) == edited[0].tags.get(0)));
        System.out.println("null preserved: " + (edited[1] == null));

        edited[0].title = "Revised";
        edited[0].tags.add("reviewed");

        System.out.println("source title: " + source[0].title);
        System.out.println("edited title: " + edited[0].title);
        System.out.println("source tags: " + source[0].tags);
        System.out.println("edited tags: " + edited[0].tags);
    }
}
```

Biên dịch và chạy:

```shell
javac DocumentCopyDemo.java
java DocumentCopyDemo
```

Stdout:

```text
new array: true
new document: true
new tag list: true
same immutable tag: true
null preserved: true
source title: Guide
edited title: Revised
source tags: [java]
edited tags: [java, reviewed]
```

`new ArrayList<>(source.tags)` tạo danh sách mới nhưng sao chép tham chiếu các phần tử của danh sách. Điều đó đáp ứng ví dụ này vì các phần tử là `String` bất biến. Nếu đổi thành `List<MutableTag>`, phải xem lại chính sách sao chép từng nhãn.

Trường `tags` là `final` chỉ ngăn gán lại trường sang danh sách khác; nó không ngăn thêm/xóa phần tử của danh sách. Ví dụ cố ý cho thấy `final` không thay thế tính bất biến.

### Phần tử lặp lại và chu trình cần chính sách riêng

Nếu nguồn chứa cùng một tài liệu ở hai vị trí, `copyForEditing` tạo hai tài liệu mới riêng biệt. Nó không bảo toàn quan hệ “hai vị trí cùng trỏ một tài liệu”. Đây là lựa chọn phù hợp khi muốn chỉnh sửa từng vị trí độc lập, nhưng có thể sai với mô hình cần giữ danh tính dùng chung.

Nếu đồ thị đối tượng có chu trình hoặc nhiều đường tham chiếu tới cùng đối tượng, sao chép đệ quy đơn giản có thể lặp vô hạn hoặc nhân đôi sai danh tính. Khi thật sự cần sao chép dạng đồ thị, phải lưu ánh xạ theo danh tính từ đối tượng nguồn sang đối tượng đã sao chép và xác định phần nào cần giữ quan hệ. Đó là bài toán rộng hơn việc sao chép mảng.

## 9. Bản sao phòng vệ phải bảo vệ đúng mức

Bản sao phòng vệ (defensive copy) giúp đối tượng không để mã bên ngoài tùy ý thay cấu trúc nội bộ.

Ví dụ lớp giữ các nhãn `String[]` có thể sao chép ở cả lúc nhận vào và trả ra:

```java
// Một lớp hoàn chỉnh về khai báo, không có main để chạy độc lập.
final class LabelSet {
    private final String[] labels;

    LabelSet(String[] labels) {
        this.labels = labels.clone();
    }

    String[] labels() {
        return labels.clone();
    }
}
```

Sao chép đầu vào ngăn bên gọi sửa các ô của mảng ban đầu rồi làm đổi cấu trúc bên trong. Sao chép đầu ra ngăn bên gọi nhận được chính mảng nội bộ. Việc dùng chung các `String` không mở đường sửa nội dung của chúng.

Nếu thay `String[]` bằng `Task[]`, hai lần sao chép nông trên chỉ bảo vệ các ô mảng. Bên gọi vẫn có thể sửa `priority` của một `Task` dùng chung. Muốn ngăn điều đó, cần phần tử bất biến, biểu diễn chỉ đọc phù hợp hoặc bản sao độc lập theo chính sách của lớp.

Không mặc định “getter trả mảng mới” đồng nghĩa đã bảo vệ mọi trạng thái bên trong.

## 10. Chọn độ sâu theo quyền sở hữu dữ liệu

| Nhu cầu | Mức sao chép thường đủ |
| --- | --- |
| Thử đổi thứ tự các tham chiếu, không sửa đối tượng | Sao chép mảng ngoài |
| Tách các giá trị trong `int[]` | Sao chép mảng |
| Tách mọi giá trị của `int[][]` | Sao chép mảng ngoài và từng hàng |
| Giữ tập các chuỗi nhưng cho phép mỗi bên đổi các ô riêng | Sao chép mảng `String[]` |
| Chỉnh sửa độc lập phần tử có trạng thái thay đổi | Tạo phần tử mới và sao chép phần trạng thái cần tách |
| Giữ cấu trúc danh tính của đồ thị đối tượng | Giao thức sao chép đồ thị có ánh xạ danh tính |

Sao chép nông không phải lỗi tự thân. Nó phù hợp khi chủ ý chia sẻ đối tượng, khi phần tử bất biến hoặc khi chỉ cần tách cấu trúc vùng chứa. Vấn đề phát sinh khi yêu cầu cần độc lập trạng thái nhưng mã chỉ tách mảng ngoài.

Ngoài độ sâu, còn phải xét thời điểm sao chép. Nếu các luồng khác đang thay đổi nguồn hoặc đối tượng phần tử, việc sao chép mảng không tự tạo ảnh chụp nhất quán của toàn bộ dữ liệu. Khi cần tính nhất quán giữa nhiều trường, ứng dụng phải có giao thức đồng bộ hoặc sử dụng các giá trị bất biến được công bố đúng cách.

Việc tạo mảng mới cũng không tự làm các phần tử dùng chung trở nên an toàn giữa nhiều luồng. Quyền sửa và cách phối hợp vẫn thuộc đối tượng phần tử và ứng dụng.

## 11. Các lỗi dễ nhầm

- **Thấy mảng khác nhau rồi kết luận dữ liệu hoàn toàn độc lập:** cần kiểm tra tiếp các tham chiếu và trạng thái có thể thay đổi.
- **Thử nghiệm bằng thay ô mảng rồi cho rằng sửa đối tượng cũng an toàn:** phải thử cả hai kiểu thao tác.
- **Dùng phần tử String để chứng minh mọi đối tượng đều độc lập:** chuỗi bất biến che đi tác động của việc dùng chung tham chiếu.
- **Sao chép từng hàng rồi gọi đó là sao chép sâu cho mọi mảng hai chiều:** đúng mức cần thiết với hàng chứa nguyên thủy, chưa đủ nếu hàng chứa đối tượng có thể thay đổi.
- **Cho rằng final làm đối tượng được tham chiếu bất biến:** final khóa phép gán lại biến hoặc trường, không khóa toàn bộ đối tượng phía sau.
- **Dùng một hàm sao chép chung mà không định nghĩa trường nào được chia sẻ:** dễ sao chép thiếu dữ liệu cần tách hoặc sao chép cả tài nguyên không nên nhân bản.

## 12. Thực hành để kiểm tra mô hình tư duy

1. Trong chương trình tác vụ, thay `copy[0].priority = 7` bằng việc gán một `Task` mới vào `copy[0]`. Dự đoán giá trị ở nguồn trước khi chạy.
2. Đổi một mảng `String[]` thành mảng `StringBuilder[]`. Sao chép mảng rồi gọi `append` trên phần tử. Giải thích vì sao kết quả khác việc gán một chuỗi mới.
3. Tạo `int[][]` có một hàng `null` và hai hàng dài khác nhau. Kiểm tra hàm `copyIntRows` giữ hình dạng và tách trạng thái của từng hàng có dữ liệu.
4. Cho hai vị trí của mảng nguồn cùng trỏ tới một `Document`. Xác định bạn muốn bản sao giữ chung danh tính hay tách thành hai tài liệu; chỉ sau đó mới chọn cách sao chép.
5. Với lớp giữ `Task[]`, liệt kê những thay đổi từ bên ngoài mà việc `clone` mảng đầu vào/đầu ra chặn được, và những thay đổi vẫn còn đi xuyên qua đối tượng phần tử.

Khi đánh giá một bản sao, hãy vẽ đường tham chiếu sau thao tác và xác định chính xác đối tượng nào mới, đối tượng nào vẫn dùng chung và ai được quyền sửa chúng.
