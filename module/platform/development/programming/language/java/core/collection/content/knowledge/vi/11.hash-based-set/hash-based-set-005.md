# LinkedHashSet và thứ tự chèn

## 1. Khi cần loại trùng nhưng vẫn giữ thứ tự gặp đầu tiên

Giả sử dữ liệu đầu vào là:

```text
sql, java, sql, http, java
```

Yêu cầu là giữ mỗi giá trị một lần và trình bày theo lần xuất hiện đầu tiên:

```text
sql, java, http
```

Ở đây có hai yêu cầu cùng tồn tại:

- Không giữ nhiều phần tử bằng nhau: ý nghĩa của `Set`.
- Có thứ tự duyệt xác định theo lịch sử chèn: đặc tính của `LinkedHashSet`.

`LinkedHashSet<E>` là một tập dùng băm và duy trì thêm liên kết giữa các phần tử để duyệt theo thứ tự chèn. Nó phù hợp khi cần loại trùng mà không muốn mất trình tự đầu vào đã có ý nghĩa.

Điều quan trọng là hiểu đúng “thứ tự chèn”:

> Các phần tử đang có trong tập được duyệt theo thứ tự chúng được thêm mới. Thử thêm lại một phần tử đã có không làm phần tử đó chuyển xuống cuối.

Nó không có nghĩa phần tử được tự sắp xếp theo bảng chữ cái hoặc theo số. Nó cũng không có nghĩa phần tử vừa được tìm bằng `contains` sẽ trở thành phần tử cuối.

Các ví dụ trong bài dùng API tương thích Java 17. Ta tập trung vào `add`, `contains`, `remove`, cách duyệt và sao chép để thấy rõ quy tắc thứ tự. [Đặc tả LinkedHashSet Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/LinkedHashSet.html)

## 2. Hai cấu trúc phối hợp: băm để tìm, liên kết để duyệt

Có thể hiểu `LinkedHashSet` qua hai trách nhiệm:

| Cơ chế | Trách nhiệm |
| --- | --- |
| Cấu trúc băm | Kiểm tra phần tử đã có chưa, tìm và xóa theo giá trị |
| Chuỗi liên kết giữa các mục | Ghi lại thứ tự duyệt của các phần tử đang được lưu |

Ví dụ sau ba lần thêm mới `"sql"`, `"java"`, `"http"`, có thể hình dung phần thứ tự như sau:

```text
đầu → sql ↔ java ↔ http ← cuối
```

Đây là sơ đồ khái niệm về liên kết hai chiều phục vụ thứ tự, không phải một danh sách mà người gọi có thể truy cập theo chỉ số.

Khi gọi `contains("java")`, tập dùng cơ chế băm để tìm theo quy tắc bằng nhau. Nó không cần coi `"java"` là “phần tử số 1” trong một danh sách.

Khi duyệt bằng `for-each`, bộ duyệt đi qua thứ tự đã được duy trì:

```java
// Đoạn minh họa: topics là một LinkedHashSet<String>.
for (String topic : topics) {
    System.out.println(topic);
}
```

Với trạng thái trong sơ đồ, thứ tự các dòng là `sql`, `java`, `http`.

Thay đổi dung lượng cấu trúc băm không biến quy tắc duyệt thành sắp xếp theo mã băm. Trật tự liên kết phục vụ duyệt là một phần riêng của thiết kế. Người dùng không cần biết chỉ số ngăn băm nội bộ để suy luận thứ tự.

## 3. Quy tắc thứ tự sau từng thao tác

### 3.1. Thêm một giá trị chưa có: đặt ở cuối

Bắt đầu từ tập rỗng:

```text
add("sql")  → [sql]
add("java") → [sql, java]
add("http") → [sql, java, http]
```

Các lời gọi đều trả về `true`, vì mỗi lần có một phần tử mới được thêm vào tập.

Thứ tự này là thứ tự chèn, không phải thứ tự chữ cái. Nếu chèn `"http"` trước `"sql"`, trình tự duyệt cũng phản ánh lựa chọn đó.

### 3.2. Thêm một giá trị đã có: giữ vị trí cũ

Nếu tập hiện là `[sql, java, http]`:

```java
// Đoạn minh họa.
boolean changed = topics.add(new String("sql"));
```

Kết quả là `false`; tập vẫn là:

```text
[sql, java, http]
```

Chuỗi được tạo bằng `new String("sql")` khác tham chiếu với một chuỗi khác nhưng bằng nhau theo giá trị. Tập không thêm bản sao và không chuyển `"sql"` về cuối.

Từ “chèn” không được hiểu là đếm mọi lần gọi `add`. Chỉ khi phần tử chưa có và thực sự được thêm mới thì nó nhận vị trí mới trong thứ tự.

Hợp đồng của `LinkedHashSet` nêu rõ việc thêm lại một phần tử đang tồn tại không thay đổi thứ tự chèn. [LinkedHashSet: quy tắc thêm lại phần tử](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/LinkedHashSet.html)

### 3.3. contains không thay đổi thứ tự

Một phép kiểm tra thuộc tập:

```java
boolean exists = topics.contains("java");
```

không đưa `"java"` lên đầu hoặc xuống cuối. Nếu trạng thái trước là `[sql, java, http]`, trạng thái sau vẫn như vậy.

Vì thế, `LinkedHashSet` thông thường không phải cấu trúc “phần tử vừa truy cập sẽ thành mới nhất”. Nếu bài toán cần thứ tự theo lần truy cập hoặc một cơ chế bộ nhớ đệm riêng, phải chọn thiết kế đáp ứng yêu cầu đó; không suy ra từ chữ `Linked`.

### 3.4. Xóa phần tử: bỏ vị trí của nó, giữ thứ tự tương đối của phần còn lại

Từ `[sql, java, http]`, gọi `remove("java")` thành công:

```text
trước: [sql, java, http]
sau:   [sql, http]
```

`"sql"` vẫn trước `"http"`. Tập không sắp xếp lại các phần tử còn lại.

Xóa một giá trị không có trong tập trả về `false` và không thay đổi thứ tự. `remove` nhận giá trị cần xóa; `LinkedHashSet` trên Java 17 không cung cấp phép xóa theo chỉ số như một `List`.

### 3.5. Xóa rồi thêm lại: đây là một lần thêm mới

Nếu `"java"` đã được xóa khỏi tập `[sql, http]`, sau đó gọi `add("java")`:

```text
[sql, http, java]
```

Phần tử không còn tồn tại ngay trước lần thêm, nên nó được thêm mới ở cuối.

Cần phân biệt hai chuỗi thao tác:

| Thao tác khi tập đang là [sql, java, http] | Kết quả cuối |
| --- | --- |
| Chỉ gọi `add("java")` | `[sql, java, http]` |
| Gọi `remove("java")`, rồi `add("java")` | `[sql, http, java]` |

Nếu dùng chuỗi xóa–thêm để thay đổi vị trí, hãy hiểu rằng đó là sửa nội dung tập qua hai thao tác. Nó không tự có tính nguyên tử, và không phù hợp để thực hiện tùy tiện khi một bộ duyệt khác đang hoạt động.

### 3.6. addAll: phần tử cũ giữ chỗ, phần tử mới nối theo thứ tự gặp

Giả sử tập đang là:

```text
[sql, http, java]
```

Thêm một danh sách theo thứ tự:

```java
topics.addAll(List.of("http", "git", "sql", "docker"));
```

Kết quả:

```text
[sql, http, java, git, docker]
```

`"http"` và `"sql"` đã có nên giữ nguyên chỗ. `"git"` và `"docker"` được thêm ở cuối theo thứ tự chúng được gặp trong danh sách.

Nếu nguồn của `addAll` không có cam kết thứ tự duyệt, không thể suy ra một trình tự mới được bảo đảm chỉ từ các giá trị mà nguồn chứa. `LinkedHashSet` giữ thứ tự nó tiếp nhận; nó không tạo ra lịch sử chèn đã bị mất ở phía nguồn.

### 3.7. null cũng chịu cùng quy tắc không trùng và thứ tự

`LinkedHashSet` cho phép `null`, nhưng tối đa một phần tử `null`.

Nếu tập là `[a, null, b]`:

- `add(null)` trả về `false`, thứ tự không đổi.
- Xóa `null` rồi thêm lại tạo thứ tự `[a, b, null]`.

Để tạo nguồn có `null` trong ví dụ, dùng `Arrays.asList(...)`. `List.of(...)` không cho phần tử `null`, nên không phù hợp cho đầu vào đó.

## 4. Chương trình đầy đủ: quan sát thứ tự sau mỗi thao tác

Lưu toàn bộ mã vào **LinkedHashSetOrderDemo.java**:

```java
import java.util.Arrays;
import java.util.Iterator;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;

public class LinkedHashSetOrderDemo {
    public static void main(String[] args) {
        Set<String> topics = new LinkedHashSet<>();
        topics.add("sql");
        topics.add("java");
        topics.add("http");
        System.out.println("initial: " + topics);

        System.out.println("contains java: " + topics.contains("java"));
        System.out.println("after contains: " + topics);
        System.out.println("add equal sql: " + topics.add(new String("sql")));
        System.out.println("after duplicate: " + topics);

        System.out.println("remove java: " + topics.remove("java"));
        System.out.println("after removal: " + topics);
        System.out.println("add java again: " + topics.add("java"));
        System.out.println("after re-add: " + topics);

        System.out.println("addAll changed: "
                + topics.addAll(List.of("http", "git", "sql", "docker")));
        System.out.println("after addAll: " + topics);

        Iterator<String> iterator = topics.iterator();
        while (iterator.hasNext()) {
            if (iterator.next().equals("git")) {
                iterator.remove();
            }
        }
        System.out.println("after iterator removal: " + topics);

        Set<String> nullable =
                new LinkedHashSet<>(Arrays.asList("a", null, "b"));
        System.out.println("nullable: " + nullable);
        System.out.println("add null again: " + nullable.add(null));
        System.out.println("after duplicate null: " + nullable);
        nullable.remove(null);
        nullable.add(null);
        System.out.println("after null re-add: " + nullable);
    }
}
```

Biên dịch theo mức Java 17 và chạy:

```shell
javac --release 17 -encoding UTF-8 LinkedHashSetOrderDemo.java
java LinkedHashSetOrderDemo
```

Stdout:

```text
initial: [sql, java, http]
contains java: true
after contains: [sql, java, http]
add equal sql: false
after duplicate: [sql, java, http]
remove java: true
after removal: [sql, http]
add java again: true
after re-add: [sql, http, java]
addAll changed: true
after addAll: [sql, http, java, git, docker]
after iterator removal: [sql, http, java, docker]
nullable: [a, null, b]
add null again: false
after duplicate null: [a, null, b]
after null re-add: [a, b, null]
```

Các điểm cần tự giải thích từ kết quả:

1. Ban đầu `sql` đứng trước `java` dù đó không phải thứ tự chữ cái.
2. `contains("java")` chỉ trả lời câu hỏi thuộc tập; nó không đổi trật tự.
3. Thử thêm một chuỗi bằng `"sql"` không tạo phần tử mới và không đẩy `sql` về cuối.
4. Sau khi xóa `java`, việc thêm lại nó đưa nó sau `http`.
5. `addAll` giữ vị trí của phần tử cũ, chỉ nối thêm `git` và `docker`.
6. Xóa `git` bằng `Iterator.remove` không thay đổi thứ tự tương đối của các phần tử còn lại.
7. `null` được xử lý như một giá trị được triển khai này chấp nhận, vẫn chỉ xuất hiện một lần.

Ví dụ dùng `Set<String>` ở kiểu khai báo và `LinkedHashSet` ở đối tượng thực tế. Kiểu biến là `Set` không làm mất hành vi của đối tượng thực tế. Tuy nhiên, nếu một API chỉ hứa trả về một `Set` bất kỳ mà không hứa thứ tự, bên gọi không nên tự giả định mọi triển khai thay thế sau này đều giữ thứ tự chèn.

## 5. Loại trùng ổn định từ một nguồn có thứ tự

Một cách dùng thường gặp:

```java
// Đoạn minh họa.
List<String> input = List.of("sql", "java", "sql", "http", "java");
Set<String> distinct = new LinkedHashSet<>(input);
```

Thứ tự của `distinct` là:

```text
[sql, java, http]
```

Ý nghĩa là:

- Lần đầu gặp `sql`: thêm vào.
- Lần đầu gặp `java`: thêm vào sau `sql`.
- Gặp lại `sql`: không đổi.
- Lần đầu gặp `http`: thêm ở cuối.
- Gặp lại `java`: không đổi.

Đây là loại trùng nhưng giữ thứ tự lần xuất hiện đầu tiên. Danh sách `input` không bị thay đổi cấu trúc bởi việc tạo tập mới.

Nếu cần một danh sách kết quả sau khi loại trùng:

```java
List<String> result = new ArrayList<>(distinct);
```

Danh sách được xây dựng theo thứ tự duyệt của tập tại thời điểm sao chép. Từ đó, danh sách có thể phục vụ một API yêu cầu dãy hoặc cần truy cập theo chỉ số.

Không tạo `HashSet` trước rồi mới chuyển sang `LinkedHashSet` nếu yêu cầu là giữ thứ tự gốc của danh sách. Bước đầu đã không cam kết giữ thứ tự đó:

```java
// Không dùng chuỗi chuyển đổi này để bảo đảm thứ tự gốc của input.
Set<String> intermediate = new HashSet<>(input);
Set<String> tooLate = new LinkedHashSet<>(intermediate);
```

`tooLate` sẽ giữ thứ tự mà nó nhận từ `intermediate`, không khôi phục thứ tự lần xuất hiện đầu tiên trong danh sách ban đầu.

Tương tự, sao chép một `HashSet` thành `LinkedHashSet` giúp giữ trình tự duyệt đã quan sát ở lần sao chép đó cho bản sao. Nó không biến thứ tự không được cam kết của nguồn thành lịch sử chèn có thể suy ra cho mọi lần chạy.

## 6. Phần tử nào được giữ khi gặp một giá trị bằng nhau?

Loại trùng dựa trên `equals` và `hashCode`, không dựa trên cách phần tử in ra hoặc việc hai tham chiếu có giống nhau không.

Khi `add(candidate)` trả về `false` vì đã có phần tử bằng nó, tập giữ nguyên. Không hiểu thao tác đó là “cập nhật đối tượng đang lưu bằng đối tượng mới”.

Ví dụ, giả sử một lớp thẻ định nghĩa bằng nhau chỉ theo mã. Hai đối tượng có cùng mã nhưng khác nhãn hiển thị được xem là bằng nhau theo quy tắc của lớp. Thêm đối tượng thứ hai vào tập đã có đối tượng thứ nhất không phải lệnh cập nhật nhãn.

Có ba yêu cầu khác nhau cần phân biệt:

| Yêu cầu | Điều cần thiết kế |
| --- | --- |
| Giữ đại diện được gặp đầu tiên | Cách loại trùng bằng LinkedHashSet từ nguồn có thứ tự phù hợp |
| Giữ dữ liệu mới nhất theo một mã | Cần quy tắc cập nhật/ghi đè theo khóa, thường hợp với Map |
| Giữ vị trí đầu tiên nhưng cập nhật một số dữ liệu | Cần thiết kế riêng cả nhận diện, dữ liệu cập nhật và thứ tự |

Không sửa các trường tham gia `equals` hoặc `hashCode` khi đối tượng đang ở trong tập. `LinkedHashSet` vẫn dựa vào băm; có chuỗi liên kết phục vụ thứ tự không làm khóa thay đổi trở nên an toàn.

Nếu lớp phần tử dùng bằng nhau theo tham chiếu, hai đối tượng có nội dung giống nhau vẫn có thể cùng được lưu. Muốn loại trùng theo giá trị, phải thiết kế quy tắc giá trị trước. Không có một chế độ “tự hiểu các trường giống nhau” chỉ nhờ chọn `LinkedHashSet`. [Set: hợp đồng phần tử và dữ liệu có thể sửa đổi](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Set.html)

## 7. Thứ tự chèn không trở thành tiêu chí equals của Set

Xét hai tập:

```text
first:  [sql, java, http]
second: [http, java, sql]
```

Chúng có cùng các phần tử, nên có thể bằng nhau theo `Set.equals` dù trình tự duyệt khác nhau.

`LinkedHashSet` giữ thứ tự để duyệt; nó vẫn tuân thủ ý nghĩa bằng nhau của tập hợp. Mã băm của tập cũng không đưa thứ tự duyệt vào tiêu chí phân biệt: hai tập bằng nhau phải có cùng mã băm. [Set.equals và hashCode](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Set.html)

Nếu bài toán cần so sánh hai thứ tự hiển thị, có thể so sánh các danh sách được tạo từ thứ tự duyệt của chúng:

```java
// Đoạn minh họa: first và second là hai LinkedHashSet.
boolean sameMembers = first.equals(second);
boolean sameSequence =
        new ArrayList<>(first).equals(new ArrayList<>(second));
```

Hai câu hỏi khác nhau:

- `sameMembers`: hai tập có cùng thành viên không?
- `sameSequence`: hai trình tự duyệt hiện tại có giống nhau không?

Không dùng `Set.equals` để kiểm tra thứ tự, rồi kết luận phương thức bị lỗi khi nó trả về `true` cho hai trình tự khác nhau.

## 8. Giữ thứ tự qua sao chép, khung nhìn và Stream

### 8.1. Bản sao cấu trúc bằng LinkedHashSet

```java
Set<String> copy = new LinkedHashSet<>(source);
```

Bản sao tiếp nhận các phần tử theo thứ tự duyệt của `source` tại lúc tạo. Sau đó, thêm hoặc xóa trong `source` không tự thêm hoặc xóa thành viên trong `copy`.

Đây là bản sao cấu trúc tập, không phải bản sao sâu của từng phần tử. Hai tập vẫn có thể chứa tham chiếu đến cùng đối tượng phần tử.

Nếu nguồn có thứ tự được cam kết, chẳng hạn một `List` hoặc `LinkedHashSet`, có thể suy luận thứ tự sao chép từ cam kết đó. Nếu nguồn không có cam kết, bản sao chỉ lưu thứ tự đã tiếp nhận, không tự tạo ra bảo đảm về thứ tự nguồn.

### 8.2. Chỉ đọc không có nghĩa là bản sao

```java
Set<String> view = Collections.unmodifiableSet(source);
```

Đây là một **khung nhìn không cho sửa đổi** qua tham chiếu `view`. Nó vẫn đọc dữ liệu từ `source`. Khi nơi khác sửa tập gốc, thay đổi có thể được quan sát qua khung nhìn.

Nếu `source` là một `LinkedHashSet`, xóa rồi thêm lại một phần tử trong `source` có thể làm thứ tự quan sát qua `view` thay đổi, dù bản thân `view` không cho gọi sửa đổi.

Khi yêu cầu là một bản chụp riêng, giữ thứ tự hiện tại và không cho bên nhận sửa cấu trúc, có thể sao chép rồi mới bọc:

```java
Set<String> snapshot =
        Collections.unmodifiableSet(new LinkedHashSet<>(source));
```

Cách này tách cấu trúc tập của bản chụp khỏi tập nguồn. Các đối tượng phần tử vẫn cần được xét riêng nếu chúng có thể sửa đổi. [Collections.unmodifiableSet](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#unmodifiableSet(java.util.Set))

### 8.3. Set.copyOf không phải cách hứa giữ thứ tự chèn

`Set.copyOf(source)` tạo một tập không sửa đổi được theo hợp đồng của nó, nhưng các tập do những phương thức factory tương ứng tạo ra không cam kết thứ tự duyệt theo thứ tự chèn của nguồn.

Vì vậy, không thay biểu thức sao chép có yêu cầu thứ tự bằng `Set.copyOf` rồi mặc định output phải giữ nguyên trình tự. Tính không sửa đổi được và thứ tự duyệt là hai thuộc tính khác nhau. [Set: các tập không sửa đổi được và thứ tự duyệt](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Set.html)

### 8.4. Dùng collector chỉ rõ LinkedHashSet khi cần kết quả đó

Với một danh sách có thứ tự:

```java
Set<String> distinct = input.stream()
        .collect(Collectors.toCollection(LinkedHashSet::new));
```

`toCollection` tích lũy theo thứ tự gặp của nguồn và dùng factory được chỉ định để tạo tập kết quả. Kết hợp với `LinkedHashSet`, cách viết này phù hợp với yêu cầu loại trùng giữ thứ tự gặp đầu tiên.

Không dùng `Collectors.toSet()` rồi giả định kết quả luôn là `LinkedHashSet` hoặc luôn giữ thứ tự. Collector đó không cam kết kiểu tập cụ thể và là collector không yêu cầu giữ thứ tự.

Nguồn cũng phải có thứ tự gặp có ý nghĩa nếu muốn hứa một thứ tự kết quả tương ứng. Chọn kiểu tập ở cuối không khôi phục một thứ tự đã bị bỏ đi trước đó. [Collectors.toCollection và toSet](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Collectors.html)

## 9. Chương trình đầy đủ: loại trùng, so sánh và tạo bản chụp

Lưu mã vào **LinkedHashSetCopyDemo.java**:

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;
import java.util.stream.Collectors;

public class LinkedHashSetCopyDemo {
    public static void main(String[] args) {
        List<String> input = List.of("sql", "java", "sql", "http", "java");
        Set<String> distinct = new LinkedHashSet<>(input);
        Set<String> viaStream = input.stream()
                .collect(Collectors.toCollection(LinkedHashSet::new));

        System.out.println("input: " + input);
        System.out.println("distinct: " + distinct);
        System.out.println("distinct as list: " + new ArrayList<>(distinct));
        System.out.println("via stream: " + viaStream);

        Set<String> otherOrder =
                new LinkedHashSet<>(List.of("http", "java", "sql"));
        System.out.println("other order: " + otherOrder);
        System.out.println("set equality: " + distinct.equals(otherOrder));
        System.out.println("hash equality: "
                + (distinct.hashCode() == otherOrder.hashCode()));
        System.out.println("iteration lists equal: "
                + new ArrayList<>(distinct).equals(new ArrayList<>(otherOrder)));

        Set<String> source =
                new LinkedHashSet<>(List.of("first", "second"));
        Set<String> view = Collections.unmodifiableSet(source);
        Set<String> snapshot =
                Collections.unmodifiableSet(new LinkedHashSet<>(source));

        source.remove("first");
        source.add("first");
        System.out.println("source after reorder: " + source);
        System.out.println("read-only view: " + view);
        System.out.println("copied snapshot: " + snapshot);
        try {
            view.add("third");
        } catch (UnsupportedOperationException ex) {
            System.out.println("view mutation: UnsupportedOperationException");
        }
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 LinkedHashSetCopyDemo.java
java LinkedHashSetCopyDemo
```

Stdout:

```text
input: [sql, java, sql, http, java]
distinct: [sql, java, http]
distinct as list: [sql, java, http]
via stream: [sql, java, http]
other order: [http, java, sql]
set equality: true
hash equality: true
iteration lists equal: false
source after reorder: [second, first]
read-only view: [second, first]
copied snapshot: [first, second]
view mutation: UnsupportedOperationException
```

Cách đọc kết quả:

1. Đầu vào vẫn giữ các phần tử lặp; việc tạo tập mới không sửa danh sách gốc.
2. Tập và danh sách được sao chép từ tập giữ thứ tự lần xuất hiện đầu tiên: `sql`, `java`, `http`.
3. Collector chỉ rõ `LinkedHashSet` tạo cùng trình tự cho danh sách đầu vào có thứ tự.
4. Hai tập có cùng thành viên nhưng thứ tự khác nhau vẫn bằng nhau và cùng mã băm.
5. Hai danh sách tạo từ hai thứ tự duyệt không bằng nhau, vì danh sách xét vị trí.
6. Sau khi tập gốc xóa rồi thêm lại `first`, khung nhìn chỉ đọc phản ánh thứ tự mới.
7. Bản chụp đã sao chép trước đó vẫn giữ thứ tự `first`, `second`.
8. Thử sửa qua `view` bị từ chối bằng `UnsupportedOperationException`.

Hai chương trình trong bài đã được biên dịch bằng `--release 17` và chạy để đối chiếu đúng stdout. Tùy chọn này kiểm tra mức ngôn ngữ/API và tạo bytecode tương thích Java 17; nó không khẳng định JVM thực thi chính là JDK 17.

## 10. Hiệu năng và chi phí của việc duy trì thứ tự

`LinkedHashSet` vẫn dùng băm cho các thao tác `add`, `contains`, `remove`. Thời gian hằng số kỳ vọng phụ thuộc vào giả định mã băm phân bố phần tử phù hợp và chi phí nhận diện phần tử được kiểm soát.

Nó duy trì thêm liên kết phục vụ thứ tự, nên có chi phí bộ nhớ và cập nhật liên kết. Không có căn cứ để nói nó luôn nhanh hơn `HashSet` chỉ vì thứ tự dễ đoán.

Một điểm khác biệt hữu ích là duyệt toàn bộ:

| Cấu trúc | Thứ tự duyệt | Công việc duyệt được tài liệu mô tả |
| --- | --- | --- |
| `HashSet` | Không cam kết | Tỷ lệ với size cộng capacity của bảng nền |
| `LinkedHashSet` | Theo thứ tự chèn | Tỷ lệ với số phần tử, không phụ thuộc capacity theo mô tả của lớp |

Điều này không làm capacity hoặc load factor trở nên vô nghĩa với `LinkedHashSet`. Chúng vẫn ảnh hưởng cấu trúc băm và tài nguyên dùng để lưu. Chỉ riêng việc đi qua chuỗi phần tử có mô hình chi phí khác. [LinkedHashSet](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/LinkedHashSet.html), [HashSet](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HashSet.html)

Không dùng số lần in output hoặc thứ tự in làm thước đo tốc độ tìm kiếm. Muốn đánh giá hiệu năng thực tế cần xét số phần tử, số lượt thêm/xóa/tra cứu/duyệt và kiểu khóa.

## 11. Chọn cấu trúc theo ý nghĩa thứ tự

| Yêu cầu chính | Cấu trúc hoặc hướng phù hợp |
| --- | --- |
| Loại trùng, không có yêu cầu thứ tự duyệt | Có thể dùng `HashSet` |
| Loại trùng, giữ thứ tự gặp đầu tiên từ nguồn có thứ tự | `LinkedHashSet` |
| Duyệt theo thứ tự sắp xếp của giá trị | Cân nhắc `TreeSet` với quy tắc so sánh phù hợp |
| Giữ cả phần tử lặp và vị trí | `List` |
| Lưu dữ liệu mới nhất theo mã, kèm yêu cầu thứ tự | Thiết kế bằng `Map` và quy tắc cập nhật/thứ tự rõ ràng |

`TreeSet` dùng thứ tự tự nhiên hoặc bộ so sánh, không dùng thứ tự chèn để quyết định trình tự duyệt. Đồng thời, quy tắc so sánh cần được thiết kế phù hợp với ý nghĩa bằng nhau của phần tử. [TreeSet](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/TreeSet.html)

Một vài tình huống phù hợp với `LinkedHashSet`:

- Tập thẻ được chọn cần loại trùng nhưng hiển thị theo trình tự chọn.
- Các tùy chọn cấu hình được hợp nhất theo thứ tự đọc, giữ vị trí lần đầu gặp.
- Danh sách mã nhập từ tệp cần loại trùng mà không tự sắp xếp lại.
- Kết quả của một bước xử lý cần giữ thứ tự đã tiếp nhận để dễ đối chiếu với nguồn.

Nếu thứ tự gốc không có ý nghĩa hoặc đã không xác định từ đầu, việc dùng `LinkedHashSet` không tự tạo ra một thứ tự nghiệp vụ đúng. Ví dụ, nó không thể biết thứ tự ưu tiên, thời điểm tạo hay thứ tự bảng chữ cái nếu các thông tin đó không được thể hiện trong nguồn hoặc quy tắc xử lý.

## 12. Duyệt và sửa đổi đúng cách

`LinkedHashSet` không tự đồng bộ cho nhiều luồng cùng sửa. Thứ tự chèn dễ dự đoán không đồng nghĩa các thao tác đồng thời đã có một thứ tự nghiệp vụ được bảo đảm.

Trong một luồng, khi cần xóa phần tử ngay trong lúc duyệt, dùng cơ chế phù hợp như `Iterator.remove`, như chương trình đầu đã làm.

Không dùng cách sau để xóa qua đường khác với bộ duyệt đang hoạt động:

```java
// Đoạn minh họa cách cần tránh, không phải mẫu xóa đúng.
for (String topic : topics) {
    if (topic.equals("git")) {
        topics.remove(topic);
    }
}
```

Bộ duyệt có thể phát hiện sửa đổi cấu trúc không hợp lệ và ném `ConcurrentModificationException`. Cơ chế fail-fast chỉ có tính nỗ lực tốt nhất; không thấy ngoại lệ trong một lần chạy không chứng minh cách duyệt là đúng.

Xóa rồi thêm một phần tử để đổi vị trí cũng là sửa cấu trúc. Không thực hiện thao tác đó tùy tiện trong một vòng duyệt hiện tại rồi mong bộ duyệt tự điều chỉnh cho đúng yêu cầu. [LinkedHashSet: đồng bộ và fail-fast](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/LinkedHashSet.html)

## 13. Các lỗi thường gặp

| Cách hiểu hoặc cách viết | Vấn đề | Cách suy nghĩ đúng |
| --- | --- | --- |
| Gọi add phần tử đang có để đẩy nó về cuối | Thêm trùng không thay đổi thứ tự | Phân biệt thêm lại khi đang có với xóa rồi thêm mới |
| Gọi contains rồi mong phần tử trở thành mới nhất | Truy vấn không đổi thứ tự chèn | Đây không phải thứ tự theo lần truy cập |
| Nghĩ LinkedHashSet tự sắp xếp | Nó giữ lịch sử thêm mới | Muốn thứ tự giá trị cần quy tắc sắp xếp riêng |
| Tạo HashSet trước rồi mới chuyển sang LinkedHashSet | Thứ tự gốc có thể đã mất cam kết | Tạo LinkedHashSet trực tiếp từ nguồn có thứ tự |
| Dùng equals để so thứ tự hiển thị | equals của Set bỏ qua thứ tự | So một biểu diễn dãy khi cần thứ tự |
| Dùng Set.copyOf để hứa giữ thứ tự chèn | Factory đó không có bảo đảm thứ tự tương ứng | Chọn cách sao chép đáp ứng cả quyền sửa và thứ tự |
| Cho rằng unmodifiableSet là bản sao | Nó là khung nhìn đọc qua tập gốc | Sao chép trước khi bọc nếu cần bản chụp |
| Dùng Collectors.toSet và giả định LinkedHashSet | Collector không hứa loại tập đó | Chỉ rõ toCollection khi cần |
| Thêm đối tượng bằng giá trị để cập nhật dữ liệu đang lưu | add trùng giữ tập nguyên trạng | Thiết kế cập nhật theo khóa phù hợp |
| Sửa trường định danh khi phần tử đang trong tập | Vẫn có rủi ro của khóa dùng băm | Giữ equals/hashCode ổn định |
| Dựa vào không có ngoại lệ khi vừa duyệt vừa sửa trực tiếp | Fail-fast không phải bằng chứng tính đúng | Dùng cơ chế xóa khi duyệt được hỗ trợ |

Khi kết quả sai thứ tự mong muốn, hãy kiểm tra từ đầu nguồn: nguồn có cam kết thứ tự không, đã đi qua một bước làm mất cam kết đó chưa, phần tử có thực sự mới hay chỉ bằng phần tử cũ, và yêu cầu cuối cùng là so thành viên hay so trình tự.

## 14. Tự luyện và đối chiếu

### Bài 1: theo dõi thứ tự

Khởi tạo:

```java
Set<String> values =
        new LinkedHashSet<>(List.of("p", "q", "p", "r"));
```

Thực hiện lần lượt:

```java
values.add("q");
values.contains("p");
values.remove("p");
values.add("p");
values.addAll(List.of("r", "s", "q"));
```

Đối chiếu:

| Bước | Kết quả thao tác | Thứ tự sau bước |
| --- | --- | --- |
| Khởi tạo | Không phải biểu thức boolean cần xét | `[p, q, r]` |
| `add("q")` | `false` | `[p, q, r]` |
| `contains("p")` | `true` | `[p, q, r]` |
| `remove("p")` | `true` | `[q, r]` |
| `add("p")` | `true` | `[q, r, p]` |
| `addAll(...)` | `true` | `[q, r, p, s]` |

Giải thích vì sao hai lời gọi `add` cho `q` và `p` có tác động thứ tự khác nhau ở thời điểm tương ứng.

### Bài 2: cùng thành viên hay cùng trình tự?

Cho:

```java
Set<Integer> a = new LinkedHashSet<>(List.of(3, 1, 2));
Set<Integer> b = new LinkedHashSet<>(List.of(1, 2, 3));
```

Dự đoán:

- `a.equals(b)`: `true`.
- `a.hashCode() == b.hashCode()`: `true`.
- `new ArrayList<>(a).equals(new ArrayList<>(b))`: `false`.

Một lời giải đúng cần phân biệt hợp đồng của tập với phép so sánh dãy. Không dùng việc “đã có thứ tự” để kết luận equals của tập phải xét thứ tự.

### Bài 3: chọn đúng kiểu sao chép

Một thành phần nhận `LinkedHashSet<String> source` và cần trả kết quả không cho bên nhận sửa cấu trúc, giữ nguyên thứ tự tại thời điểm tạo, đồng thời không phản ánh việc nơi khác thêm/xóa vào `source`.

Chọn giữa:

```java
Collections.unmodifiableSet(source);
Collections.unmodifiableSet(new LinkedHashSet<>(source));
Set.copyOf(source);
```

Cách thứ hai đáp ứng đầy đủ các yêu cầu đã nêu cho cấu trúc và thứ tự. Cách thứ nhất còn đọc qua nguồn. Cách thứ ba không cung cấp cam kết giữ thứ tự chèn như yêu cầu.

Nếu đổi phần tử từ `String` sang một lớp có thể sửa đổi, cần xét thêm tính ổn định và quyền sửa dữ liệu của từng đối tượng phần tử; một bản sao tập không tự là bản sao sâu.

### Bài 4: nguồn không có cam kết thứ tự

Một `HashSet` được truyền vào `new LinkedHashSet<>(source)`. Có thể kết luận bản sao:

1. Giữ thứ tự duyệt mà nó nhận ở lần sao chép đó.
2. Khôi phục được thứ tự người dùng đã thêm vào HashSet từ trước.
3. Luôn giống thứ tự sao chép trên mọi lần chạy ứng dụng.

Chỉ kết luận thứ nhất phù hợp. Hai kết luận sau đòi hỏi thông tin hoặc bảo đảm mà nguồn không cung cấp.

## 15. Tài liệu tra cứu

- [LinkedHashSet Java 17 — thứ tự chèn, thêm lại, hiệu năng và bộ duyệt](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/LinkedHashSet.html)
- [HashSet Java 17 — thứ tự không được cam kết và cơ chế dùng băm](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HashSet.html)
- [Set — hợp đồng bằng nhau và các tập không sửa đổi được](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Set.html)
- [Collections.unmodifiableSet — khung nhìn không cho sửa đổi](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#unmodifiableSet(java.util.Set))
- [Collectors — chỉ rõ kiểu tập kết quả bằng toCollection](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Collectors.html)
- [TreeSet — thứ tự tự nhiên hoặc Comparator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/TreeSet.html)
