# Collections.disjoint để kiểm tra hai tập dữ liệu

## 1. Câu hỏi mà disjoint trả lời

`Collections.disjoint(c1, c2)` kiểm tra hai collection có **không có phần tử chung** hay không.

Điểm cần nhớ ngay từ tên:

```text
disjoint == true  → không có phần tử chung
disjoint == false → có ít nhất một phần tử chung
```

Ví dụ:

```text
A = [java, sql]
B = [linux, sql]
A và B có "sql" chung → disjoint(A, B) là false

A = [java, sql]
C = [go, rust]
A và C không có phần tử chung → disjoint(A, C) là true
```

Nếu câu hỏi của ứng dụng là “có trùng dữ liệu không?”, dùng phủ định:

```java
boolean hasCommon = !Collections.disjoint(first, second);
```

Đặt tên biến đúng chiều ý nghĩa giúp tránh lỗi đọc một kết quả true thành “có giao nhau”.

Phương thức có chữ ký:

```java
public static boolean disjoint(Collection<?> c1, Collection<?> c2)
```

Nó nhận các collection, không chỉ `Set`. `List`, `Set` và những kiểu collection phù hợp khác đều có thể là đầu vào. Đây là API vẫn áp dụng trên Java hiện hành; các ví dụ chạy được từ Java 17.

## 2. Hợp đồng cơ bản

Với dữ liệu hợp lệ và quy tắc bằng nhau tương thích, có thể hiểu theo phép giao:

```text
disjoint(A, B) ⇔ A ∩ B là rỗng
```

| Tình huống | Kết quả |
|---|---|
| Có một phần tử chung | false |
| Có nhiều phần tử chung | false |
| Không có phần tử chung | true |
| Một collection rỗng | true |
| Cả hai collection rỗng | true |
| Truyền cùng một collection không rỗng ở cả hai tham số | false |
| Truyền cùng một collection rỗng ở cả hai tham số | true |

Số lần lặp và thứ tự không thay đổi câu trả lời về việc **có hay không** phần tử chung. Chẳng hạn, A chứa “sql” một lần hay mười lần thì chỉ cần B có một “sql” là kết quả đã false.

Phương thức không cần tạo một collection kết quả chứa phần giao. Nó cũng không yêu cầu xóa phần tử hoặc sắp xếp đầu vào. Vì chỉ đọc, các collection không cho phép sửa như `List.of(...)` vẫn có thể dùng khi dữ liệu đáp ứng hợp đồng.

[Tài liệu Collections.disjoint](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Collections.html#disjoint(java.util.Collection,java.util.Collection)) quy định cả kết quả lẫn các giới hạn quan trọng về cách so sánh và phần tử hợp lệ.

## 3. Chương trình cơ bản: đọc đúng kết quả và quy tắc bằng nhau

Lưu tệp `DisjointBasicsDemo.java`:

```java
import java.util.Collections;
import java.util.List;

public class DisjointBasicsDemo {
    public static void main(String[] args) {
        List<String> first = List.of("java", "sql", "sql");
        List<String> second = List.of("linux", "sql");
        System.out.println("disjoint=" + Collections.disjoint(first, second));
        System.out.println("has common=" + !Collections.disjoint(first, second));
        System.out.println("no overlap="
                + Collections.disjoint(first, List.of("go", "rust")));
        System.out.println("empty="
                + Collections.disjoint(first, List.of()));
        System.out.println("same nonempty="
                + Collections.disjoint(first, first));
        List<String> empty = List.of();
        System.out.println("same empty="
                + Collections.disjoint(empty, empty));
        System.out.println("unchanged first=" + first);
        System.out.println("unchanged second=" + second);

        System.out.println("int versus long="
                + Collections.disjoint(List.of(1), List.of(1L)));
        int[] left = {1, 2};
        int[] right = {1, 2};
        System.out.println("separate arrays="
                + Collections.disjoint(List.<int[]>of(left), List.<int[]>of(right)));
        System.out.println("same array="
                + Collections.disjoint(List.<int[]>of(left), List.<int[]>of(left)));
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -Xlint:all -Werror DisjointBasicsDemo.java
java DisjointBasicsDemo
```

Stdout:

```text
disjoint=false
has common=true
no overlap=true
empty=true
same nonempty=false
same empty=true
unchanged first=[java, sql, sql]
unchanged second=[linux, sql]
int versus long=true
separate arrays=true
same array=false
```

### Có chung dữ liệu không phải là hai collection bằng nhau

`first` và `second` có khác số lượng, thứ tự và nhiều nội dung. Chúng vẫn có phần tử chung “sql”, nên `disjoint` là false.

Không thay `disjoint` bằng `first.equals(second)`. `equals` của collection kiểm tra một hợp đồng khác; với list, nó xét cả nội dung theo vị trí, không chỉ sự tồn tại của một điểm chung.

### Phần tử trùng lặp không phải kết quả đếm

`first` có “sql” hai lần. Phương thức không trả về 2 hoặc một danh sách các “sql”; nó chỉ trả boolean cho câu hỏi có phần tử chung hay không.

Nếu cần đếm số lần trùng, phân biệt phần giao theo giá trị duy nhất hay số lần xuất hiện. Đó là một bài toán khác với `disjoint`.

### Integer 1 không bằng Long 1L theo equals

`List.of(1)` và `List.of(1L)` chứa các đối tượng thuộc hai kiểu bao khác nhau. Trong ví dụ, không có phần tử bằng nhau theo quy tắc bình thường, nên `disjoint` trả true.

Không suy ra phương thức thực hiện so sánh số học, chuyển đổi đơn vị hoặc mở rộng kiểu để đồng nhất các giá trị. Muốn một cách hiểu nghiệp vụ như vậy, cần chuẩn hóa dữ liệu về một mô hình thống nhất trước.

Chữ ký `Collection<?>` cho phép gọi với các kiểu phần tử khác nhau, nhưng không hứa rằng mọi cách triển khai collection đều chấp nhận phép tra cứu một đối tượng thuộc kiểu bất kỳ.

### Mảng không tự so sánh sâu

Hai `int[]` được tạo riêng có cùng các số không trở thành phần tử bằng nhau theo `equals()` của mảng. Vì vậy:

- Hai collection chứa hai mảng riêng có cùng nội dung vẫn có thể rời nhau.
- Hai collection chứa cùng tham chiếu mảng thì có phần tử chung.

`disjoint` không tự dùng `Arrays.equals` hay `Arrays.deepEquals`. Nếu ý định là so sánh nội dung mảng, cần chuyển về một kiểu giá trị có `equals`/`hashCode` phù hợp hoặc chọn một cách so sánh tường minh khác.

## 4. Cơ chế suy luận và vai trò của contains

Với hai collection dùng hợp đồng bằng nhau chuẩn, có thể hình dung phép kiểm tra như sau:

```java
// Mã minh họa ý tưởng, không phải cam kết thuật toán nội bộ của JDK.
for (Object element : first) {
    if (second.contains(element)) {
        return false;
    }
}
return true;
```

Đây là mảnh mã để đặt trong một phương thức trả `boolean`; giả định `first` và `second` đã tồn tại.

Nó diễn đạt ý tưởng “chỉ cần tìm được một phần tử chung là biết không rời nhau”. Tuy nhiên, API cho phép triển khai duyệt một trong hai collection và kiểm tra ở collection còn lại hoặc thực hiện phép tính tương đương.

Vì vậy, không dựa vào:

- Collection nào chắc chắn được duyệt.
- Collection nào chắc chắn nhận các lời gọi `contains`.
- Phần tử chung nào được phát hiện trước.
- Một thứ tự tác dụng phụ từ các phương thức so sánh tùy biến.

Hợp đồng của [Collection.contains](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Collection.html#contains(java.lang.Object)) và cách từng collection xác định phần tử bằng nhau ảnh hưởng trực tiếp tới phép kiểm tra.

Điều này cũng giải thích vì sao dùng những collection có quy tắc bằng nhau không tương thích là vấn đề về tính đúng đắn, không chỉ về tốc độ.

## 5. Null: phân biệt collection null và phần tử null

### Collection null là đầu vào không hợp lệ

Nếu một trong hai tham chiếu collection là null, phương thức ném `NullPointerException`. Null không có cùng nghĩa với collection rỗng.

Không tự biến null thành rỗng nếu hợp đồng của ứng dụng còn cần phân biệt “không có dữ liệu đầu vào” với “đã có danh sách nhưng không chứa phần tử”.

### Phần tử null phụ thuộc collection

Nếu cả hai collection cho phép null và cùng chứa null, null là một phần tử chung. Khi đó kết quả là false.

Nhưng một collection chứa null đem so với một collection không chấp nhận null trong thao tác kiểm tra có thể gây ngoại lệ. Đặc tả cho phép `NullPointerException` trong tình huống phần tử không hợp lệ này; không hứa luôn trả true hoặc false chỉ vì đang dùng một hàm kiểm tra.

Tương tự, một phần tử có kiểu không phù hợp với collection còn lại có thể gây `ClassCastException`. Để có phép kiểm tra an toàn, các phần tử cần hợp lệ đối với cả hai collection.

### Chương trình kiểm chứng null hợp lệ

Lưu tệp `DisjointNullDemo.java`:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;

public class DisjointNullDemo {
    public static void main(String[] args) {
        List<String> first =
                new ArrayList<>(Arrays.asList("A", null));
        List<String> second =
                new ArrayList<>(Arrays.asList("B", null));
        List<String> third = new ArrayList<>(List.of("B"));
        System.out.println("shared null="
                + Collections.disjoint(first, second));
        System.out.println("no common="
                + Collections.disjoint(first, third));
        try {
            Collections.disjoint(null, first);
        } catch (NullPointerException ex) {
            System.out.println("null collection: NullPointerException");
        }
    }
}
```

Chạy:

```shell
javac --release 17 -Xlint:all -Werror DisjointNullDemo.java
java DisjointNullDemo
```

Kết quả:

```text
shared null=false
no common=true
null collection: NullPointerException
```

Hai list đầu đều dùng `ArrayList`, có thể chứa và kiểm tra null. Vì cùng có null nên không rời nhau.

List thứ ba không chứa null nhưng vẫn là một `ArrayList` chấp nhận kiểm tra null. Nó chỉ có “B”, không trùng với “A” hoặc null, nên kết quả true.

Cố ý không dùng `List.of(null)` để tạo dữ liệu kiểm chứng: lời gọi tạo list đó tự nó đã từ chối null, trước khi `disjoint` có cơ hội chạy.

## 6. Khi cách hiểu “bằng nhau” không giống nhau

Một số collection dùng quy tắc khác với `equals` thông thường. Ví dụ:

- `TreeSet` xác định tương đương theo kết quả comparator hoặc thứ tự tự nhiên.
- Một tập hợp theo đồng nhất đối tượng có thể xem cùng tham chiếu là tiêu chí thay cho `equals`.

Với `TreeSet<String>` dùng `String.CASE_INSENSITIVE_ORDER`, “Admin” và “ADMIN” được xem là cùng một giá trị theo quy tắc so sánh của tập, dù `String.equals` phân biệt chúng.

[Tài liệu TreeSet](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/TreeSet.html) giải thích sự liên hệ giữa comparator và hợp đồng `Set`.

### Không trộn các quy tắc rồi dựa vào kết quả tình cờ

Nếu một bên dùng quy tắc không chuẩn như không phân biệt hoa/thường, bên còn lại dùng quy tắc phân biệt hoa/thường, kết quả `disjoint` không được xác định theo hợp đồng cho trường hợp đó.

Không sửa bằng cách:

- Đảo thứ tự tham số cho đến khi được kết quả mong muốn.
- Chọn kích thước dữ liệu để buộc một nhánh thuật toán nội bộ.
- Kết luận từ một lần chạy rằng comparator luôn thắng hoặc `equals` luôn thắng.

Nếu một bên dùng quy tắc bằng nhau không chuẩn, hai bên phải dùng cùng quy tắc ấy khi đem so bằng `disjoint`.

“Cùng quy tắc” nói về ngữ nghĩa, không chỉ tên lớp. Hai `TreeSet` với hai comparator xác định tương đương khác nhau vẫn có thể không phù hợp để đem so trực tiếp.

## 7. Chương trình: cùng quy tắc và chuẩn hóa tường minh

Lưu tệp `DisjointEqualityDemo.java`:

```java
import java.util.Collection;
import java.util.Collections;
import java.util.HashSet;
import java.util.List;
import java.util.Locale;
import java.util.Objects;
import java.util.Set;
import java.util.TreeSet;

public class DisjointEqualityDemo {
    static Set<String> canonicalKeys(Collection<String> values) {
        Objects.requireNonNull(values, "values");
        Set<String> result = new HashSet<>();
        for (String value : values) {
            result.add(Objects.requireNonNull(value, "value")
                    .strip().toLowerCase(Locale.ROOT));
        }
        return result;
    }

    public static void main(String[] args) {
        Set<String> left = new TreeSet<>(String.CASE_INSENSITIVE_ORDER);
        Set<String> right = new TreeSet<>(String.CASE_INSENSITIVE_ORDER);
        left.add("Admin");
        right.add("ADMIN");
        System.out.println("same comparison rule="
                + Collections.disjoint(left, right));

        List<String> a = List.of(" Admin ", "Read");
        List<String> b = List.of("admin", "Write");
        System.out.println("raw="
                + Collections.disjoint(a, b));
        System.out.println("normalized="
                + Collections.disjoint(canonicalKeys(a), canonicalKeys(b)));
        System.out.println("original a=" + a);
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -Xlint:all -Werror DisjointEqualityDemo.java
java DisjointEqualityDemo
```

Stdout:

```text
same comparison rule=false
raw=true
normalized=false
original a=[ Admin , Read]
```

### Cách 1: cả hai bên dùng cùng quy tắc comparator

Hai `TreeSet` trong phần đầu đều dùng `String.CASE_INSENSITIVE_ORDER`. Chúng xem “Admin” và “ADMIN” là cùng giá trị, nên `disjoint` trả false.

Không lấy ví dụ này làm lý do đem một TreeSet như vậy so trực tiếp với một HashSet dùng `String.equals`. Đó sẽ là cách trộn hai ngữ nghĩa khác nhau.

### Cách 2: chuẩn hóa về khóa nghiệp vụ trước khi so

Trong phần sau, hai list gốc không có chuỗi bằng nhau theo `String.equals`:

```text
a = [" Admin ", "Read"]
b = ["admin", "Write"]
```

Hàm `canonicalKeys` quy định một phép chuẩn hóa cụ thể cho ví dụ:

1. Không nhận collection hoặc phần tử null.
2. Bỏ khoảng trắng ở đầu/cuối bằng `strip()`.
3. Đổi về chữ thường bằng `Locale.ROOT`.
4. Thu vào `HashSet<String>` để so các khóa đã chuẩn hóa bằng cùng hợp đồng.

Sau chuẩn hóa, hai bên có khóa “admin” chung nên kết quả false. List gốc không bị thay đổi.

Đây là một hợp đồng dữ liệu mới được lựa chọn rõ ràng cho thí nghiệm, không phải tác dụng tự có của `disjoint`. Chỉ áp dụng việc bỏ khoảng trắng hoặc đổi hoa/thường khi miền dữ liệu thực sự coi các biến thể ấy là một giá trị.

Đừng tự khẳng định mọi cách chuẩn hóa chuỗi đều tương đương với mọi comparator không phân biệt hoa/thường. Điều cần giữ là hai bộ dữ liệu được đưa về cùng mô hình khóa mà ứng dụng đã định nghĩa.

## 8. Chi phí thực hiện và khi nào cần một tập tra cứu

Không có một bảo đảm chung rằng `disjoint` luôn chạy trong thời gian tuyến tính bất kể đầu vào.

Chi phí phụ thuộc:

- Số phần tử được xét trước khi đủ kết luận.
- Chi phí duyệt collection.
- Chi phí kiểm tra tồn tại.
- Chi phí `equals`, `hashCode` hoặc comparator.
- Cách triển khai cụ thể của collection và thuật toán.

Nếu mô hình thực hiện là duyệt n phần tử rồi tìm tuyến tính trong m phần tử, trường hợp xấu có thể gần `O(n × m)`. Với một tập băm được dùng để kiểm tra tồn tại, chi phí tra cứu thường thuận lợi hơn khi hàm băm phân bố phù hợp.

Có thể cân nhắc tạo chỉ mục:

```java
Set<String> index = new HashSet<>(first);
boolean noCommon = Collections.disjoint(index, second);
```

Đây là mảnh mã, giả định có các import và biến phù hợp. Phải tính cả chi phí tạo `HashSet` và bộ nhớ bổ sung. Khi kiểm tra nhiều lần với cùng một bộ dữ liệu, giữ một chỉ mục phù hợp có thể đáng cân nhắc hơn việc dựng lại mỗi lần.

Không mặc định sao chép sang HashSet là một tối ưu không đổi nghĩa. Nếu nguồn dùng quy tắc tương đương riêng như comparator không phân biệt hoa/thường, chuyển sang HashSet có thể đổi cách hiểu phần tử bằng nhau. Chuẩn hóa ngữ nghĩa trước, rồi mới tối ưu cấu trúc.

API cũng không buộc ứng dụng được quyền dựa vào việc “bên có Set luôn chắc chắn là bên nhận contains”. Dùng cấu trúc thích hợp để tạo điều kiện thực hiện tốt, nhưng đánh giá bằng dữ liệu và môi trường thực tế thay vì gắn một độ phức tạp cố định vào tên phương thức.

## 9. Dùng trong kiểm tra hai nhóm dữ liệu

Ví dụ, một hệ thống có hai công việc khai báo các mã tài nguyên mà chúng cần:

```java
Set<String> jobA = Set.of("database-main", "search-index");
Set<String> jobB = Set.of("mail-gateway");

boolean shareNoResource = Collections.disjoint(jobA, jobB);
```

Kết quả kiểm tra các mã tài nguyên cho biết hai nhóm không có mã chung. Nếu đổi `jobB` thành tập có `"database-main"`, kết quả sẽ false.

Cần giữ đúng phạm vi kết luận:

- Nó kiểm tra sự trùng mã theo hợp đồng bằng nhau.
- Nó không tự giữ chỗ tài nguyên.
- Nó không xét thời gian sử dụng hay sức chứa của tài nguyên.
- Nó không làm nguyên tử quy trình “kiểm tra rồi cập nhật”.

Nếu dữ liệu có thể đổi sau khi kiểm tra, kết quả phản ánh dữ liệu được quan sát tại phép kiểm tra, không phải một cam kết cho mọi thao tác tương lai.

Các collection không an toàn đồng thời không nên bị sửa trong lúc phương thức đang duyệt/kiểm tra. Với collection có cơ chế đồng thời, vẫn phải hiểu hợp đồng quan sát của cấu trúc đó; một phép gọi `disjoint` không tự tạo ra ảnh chụp nguyên tử của cả hai bộ dữ liệu.

## 10. Disjoint khác với lấy phần giao

Nếu chỉ cần boolean, `disjoint` diễn đạt ý định trực tiếp:

```java
boolean overlap = !Collections.disjoint(first, second);
```

Nếu cần danh sách hoặc tập các giá trị chung, cần một phép tính tạo phần giao. Ví dụ với hai tập dùng cùng quy tắc bằng nhau chuẩn:

```java
Set<String> common = new HashSet<>(first);
common.retainAll(second);
```

`retainAll` sửa collection mà nó được gọi trên, nên ví dụ tạo bản sao trước. Đừng gọi trực tiếp `first.retainAll(second)` rồi nghĩ đó là một phép kiểm tra không làm thay đổi dữ liệu.

Khi có phần tử lặp trong list, còn phải xác định muốn giao theo giá trị duy nhất hay muốn giữ số lần xuất hiện. `disjoint` không giải quyết việc lựa chọn đó vì nó chỉ trả có/không.

## 11. Tự kiểm tra

### Câu 1

A chứa [1, 2, 2], B chứa [2, 3]. `disjoint(A, B)` trả gì?

**Đáp án:** False, vì có phần tử 2 chung. Số lần lặp không đổi câu trả lời boolean.

### Câu 2

Một bên rỗng, bên còn lại hợp lệ và không null. Kết quả là gì?

**Đáp án:** True. Collection rỗng không có phần tử để giao với bên còn lại.

### Câu 3

Muốn biết có ít nhất một phần tử chung, đặt tên biến `hasCommon` thì biểu thức nên là gì?

**Đáp án:** `!Collections.disjoint(first, second)`.

### Câu 4

TreeSet không phân biệt hoa/thường đem so trực tiếp với HashSet phân biệt hoa/thường có phải một phép kiểm tra được bảo đảm không?

**Đáp án:** Không. Hai bên đang dùng quy tắc tương đương khác nhau. Chọn cùng quy tắc hoặc chuẩn hóa về cùng mô hình khóa trước.

### Câu 5

Hai collection chứa hai mảng `int[]` khác nhau nhưng có cùng số. Có tự được coi là có phần tử chung không?

**Đáp án:** Không theo ngữ nghĩa mặc định của mảng. Cần một kiểu giá trị so sánh theo nội dung nếu đó là yêu cầu.

### Câu 6

Có thể coi null đầu vào là tập rỗng để bỏ qua lỗi không?

**Đáp án:** Chỉ khi hợp đồng ứng dụng chủ động quy định như vậy và xử lý trước. `Collections.disjoint` không tự thực hiện phép đổi nghĩa đó; collection null là đầu vào không hợp lệ.

Khi kiểm tra hai bộ dữ liệu, hãy xác định **true đang có nghĩa không giao nhau → phần tử bằng nhau theo quy tắc nào → dữ liệu có hợp lệ cho cả hai bên không → chỉ cần boolean hay cần phần giao → dữ liệu có đổi trong lúc kiểm tra không**.
