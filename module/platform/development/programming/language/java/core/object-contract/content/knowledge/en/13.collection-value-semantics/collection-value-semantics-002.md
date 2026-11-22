# `Set.equals()` xét cùng các phần tử, không phụ thuộc thứ tự duyệt

## 1. Quy tắc cốt lõi của `Set.equals()`

Trong Java, `java.util.Set` biểu diễn một tập hợp **không chứa các phần tử trùng nhau theo quan hệ bằng nhau mà cấu trúc sử dụng**. Hợp đồng `Set.equals(Object)` xác định hai tập hợp bằng nhau khi:

1. Đối tượng được so sánh cũng là một `Set`.
2. Hai tập hợp có **cùng số phần tử** (`size()`).
3. **Mọi phần tử** của tập hợp này đều xuất hiện trong tập hợp kia, theo cách xác định quan hệ phần tử của các tập hợp hợp lệ.

Thứ tự thêm phần tử, thứ tự duyệt bằng `iterator()` và kiểu triển khai cụ thể **không phải tiêu chí** của hợp đồng này.

Ví dụ về mặt ý nghĩa:

```text
{ "Java", "Kotlin", "Scala" }
{ "Scala", "Java", "Kotlin" }
→ Set.equals(): true (cùng 3 phần tử, dù thứ tự liệt kê khác nhau)

{ "Java", "Kotlin", "Scala" }
{ "Java", "Kotlin" }
→ Set.equals(): false (khác số phần tử)
```

Ký hiệu trong khối trên là **minh họa tập hợp**, không phải cú pháp khởi tạo `Set` của Java.

**Phân biệt với `List`:** `List.equals()` yêu cầu cùng kích thước và các phần tử tương ứng **đúng cùng vị trí** phải bằng nhau. Vì vậy, hai danh sách có cùng phần tử nhưng hoán đổi vị trí thường không bằng nhau, trong khi hai `Set` chứa cùng phần tử sẽ bằng nhau.

## 2. `HashSet`, `LinkedHashSet` và `TreeSet` khác thứ tự duyệt nhưng vẫn có thể bằng nhau

Ba triển khai thường gặp:

| Triển khai | Đặc điểm duyệt | Khi so sánh bằng `equals()` |
| --- | --- | --- |
| `HashSet` | **Không cam kết** thứ tự duyệt | So sánh tính thành viên và kích thước, không dựa vào thứ tự duyệt |
| `LinkedHashSet` | Thường duyệt theo **thứ tự chèn** | Vẫn áp dụng hợp đồng `Set.equals()` không xét vị trí |
| `TreeSet` | Duyệt theo **thứ tự sắp xếp** (natural order hoặc `Comparator`) | Vẫn phải tuân hợp đồng `Set` khi cách sắp xếp **nhất quán với `equals`** |

Với các phần tử `String` khác `null` và cách sắp xếp tự nhiên thông thường, một `HashSet`, một `LinkedHashSet` và một `TreeSet` có thể bằng nhau nếu chứa cùng các chuỗi. Ví dụ, thứ tự duyệt thấy ở ba tập hợp có thể khác mà `equals()` vẫn trả về `true`.

Không suy ra thứ tự duyệt của `HashSet` từ kết quả chạy máy hoặc nội dung hàm băm. Java không cam kết `HashSet` duyệt theo thứ tự chèn, thứ tự từ điển hay thứ tự ổn định sau các thao tác thay đổi tập hợp.

## 3. Chương trình Java 17+ chạy được

Lưu mã sau vào tệp `SetEqualityDemo.java`:

```java
import java.util.Arrays;
import java.util.HashSet;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Objects;
import java.util.Set;
import java.util.TreeSet;

public class SetEqualityDemo {
    record Tag(String code) {}

    public static void main(String[] args) {
        Set<String> hash = new HashSet<>(
                List.of("Java", "Kotlin", "Scala"));
        Set<String> linked = new LinkedHashSet<>(
                List.of("Scala", "Java", "Kotlin"));
        Set<String> sorted = new TreeSet<>(
                List.of("Kotlin", "Scala", "Java"));

        System.out.println("hash.equals(linked): " + hash.equals(linked));
        System.out.println("linked.equals(sorted): " + linked.equals(sorted));
        System.out.println("same set hashCode: "
                + (hash.hashCode() == linked.hashCode()));
        System.out.println("List order matters: "
                + List.of("Java", "Kotlin")
                        .equals(List.of("Kotlin", "Java")));
        System.out.println("missing an element: "
                + hash.equals(Set.of("Java", "Scala")));
        System.out.println("Set vs List: "
                + hash.equals(List.of("Java", "Kotlin", "Scala")));

        Set<Integer> unique = new HashSet<>(Arrays.asList(1, 2, 2, 3));
        System.out.println("unique.size(): " + unique.size());
        System.out.println("integer set hashCode: "
                + Set.of(1, 2, 3).hashCode());

        Set<String> withNull = new HashSet<>(
                Arrays.asList(null, "Java"));
        Set<String> nullInOtherOrder = new LinkedHashSet<>(
                Arrays.asList("Java", null));
        System.out.println("sets with null: "
                + withNull.equals(nullInOtherOrder));

        Set<Tag> firstTags = Set.of(new Tag("A"), new Tag("B"));
        Set<Tag> secondTags = new LinkedHashSet<>(
                List.of(new Tag("B"), new Tag("A")));
        System.out.println("record member equality: "
                + firstTags.equals(secondTags));

        Set<String> absent = null;
        System.out.println("Objects.equals(null, null): "
                + Objects.equals(absent, null));
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac SetEqualityDemo.java
java SetEqualityDemo
```

Kết quả dự kiến, không phụ thuộc thứ tự duyệt các `Set`:

```text
hash.equals(linked): true
linked.equals(sorted): true
same set hashCode: true
List order matters: false
missing an element: false
Set vs List: false
unique.size(): 3
integer set hashCode: 6
sets with null: true
record member equality: true
Objects.equals(null, null): true
```

Giải thích:

- `hash`, `linked`, `sorted` có cùng ba giá trị chuỗi, nên bằng nhau bất kể thứ tự thêm hoặc duyệt.
- Hai `List` chứa `"Java"` và `"Kotlin"` theo thứ tự trái ngược nên **không bằng nhau**.
- `Set` không bằng `List`, ngay cả khi các giá trị xuất hiện giống hệt: điều kiện đối tượng kia phải là một `Set` không thỏa.
- `new HashSet<>(Arrays.asList(1, 2, 2, 3))` loại phần tử `2` lặp; kết quả chỉ có ba phần tử khác nhau.
- `HashSet` và `LinkedHashSet` cho phép một phần tử `null`; vị trí thêm `null` không làm thay đổi sự bằng nhau. Không suy rộng khả năng chứa `null` cho mọi triển khai `Set`.
- `Tag` là Java `record`, tự cung cấp `equals()`/`hashCode()` theo trường `code`. Hai đối tượng `new Tag("A")` khác nhau vẫn **bằng nhau theo giá trị**; hai tập hợp chứa các thẻ tương đương được coi là bằng nhau.

## 4. Hình dung thuật toán so sánh tập hợp

Về mặt quy tắc, có thể diễn giải việc so sánh hai `Set` hợp lệ bằng giả mã:

```text
if (this == other)                 return true
if (!(other instanceof Set))      return false
if (this.size() != other.size())   return false
return this chứa mọi phần tử của other
```

Đây là **giả mã mô tả hợp đồng**, không phải mã nguồn bắt buộc của mọi bản triển khai. Trong Java, kiểm tra thành viên thường dùng `contains(...)`; `HashSet` dựa vào giá trị `hashCode()` và `equals()` của phần tử, còn `TreeSet` tìm theo quan hệ thứ tự do `compareTo`/`Comparator` cung cấp.

Điều kiện **cùng kích thước** là cần thiết: chỉ kiểm tra `containsAll(...)` một chiều sẽ cho kết quả sai với tập lớn chứa toàn bộ tập nhỏ. Và việc duyệt các phần tử để ghép vào `List`, rồi so sánh hai danh sách bằng `equals`, cũng sai vì vô tình đưa thứ tự vào tiêu chí tập hợp.

## 5. `Set.hashCode()` cũng không phụ thuộc thứ tự duyệt

Hợp đồng `Set.hashCode()` được định nghĩa là **tổng `hashCode()` của mọi phần tử trong tập hợp**; phần tử `null` đóng góp `0` nếu được phép tồn tại. Phép cộng diễn ra theo kiểu `int`, có thể tràn số. Vì phép cộng không phụ thuộc thứ tự nên các tập hợp chứa cùng phần tử cho cùng mã băm, dù thứ tự duyệt khác nhau.

Ví dụ `Set.of(1, 2, 3).hashCode()` trả về `1 + 2 + 3 = 6`, vì `Integer.hashCode(int)` trả lại chính giá trị `int`.

Quy tắc bắt buộc vẫn là:

```text
s1.equals(s2) == true  =>  s1.hashCode() == s2.hashCode()
s1.hashCode() == s2.hashCode()  =/=>  s1.equals(s2) == true
```

Chiều thứ hai không đúng vì va chạm mã băm có thể xảy ra. Chẳng hạn hai tập hợp số nguyên khác nhau `{1, 4}` và `{2, 3}` đều có mã băm bằng `5`, nhưng **không bằng nhau** vì không cùng phần tử.

Không được viết phép so sánh tập hợp bằng cách **chỉ** so `hashCode()`. Hash code hỗ trợ tra cứu; nó không thay thế kiểm tra thành viên.

## 6. Sự bằng nhau của `Set` phụ thuộc sự bằng nhau của phần tử

Hai `Set` có thể chứa các đối tượng thuộc hai vùng nhớ khác nhau nhưng vẫn bằng nhau nếu các phần tử tương ứng **bằng nhau theo `equals()`** và các hàm băm nhất quán.

Ví dụ dùng `record` trong chương trình ở trên. Với lớp tự tạo thông thường, cần ghi đè `equals()` và `hashCode()` nhất quán theo đúng dữ liệu định danh phần tử. Nếu không, `Object.equals()` mặc định kiểm tra danh tính đối tượng, dẫn đến hai phần tử trông giống nhau nhưng không được nhận là bằng nhau.

Các trường hợp cần phân biệt:

- `Set.of(1).equals(Set.of(1L))` trả `false`: `Integer(1)` và `Long(1)` không bằng nhau theo `equals()`, dù có cùng trị số toán học.
- Hai tập hợp có cùng số phần tử nhưng chứa giá trị khác nhau trả `false`.
- Các triển khai có hợp đồng `Set` đúng không đòi hai bên dùng cùng loại cụ thể, ví dụ `HashSet` vẫn so sánh được với `LinkedHashSet`.
- Đưa phần tử có `equals()`/`hashCode()` **phụ thuộc thuộc tính có thể thay đổi** vào `HashSet`, rồi sửa thuộc tính ấy, có thể khiến `contains()`/`remove()` không tìm lại được phần tử. Nên ưu tiên phần tử bất biến khi dùng trong cấu trúc băm.

## 7. Ngoại lệ thiết kế cần biết: `TreeSet` và `Comparator`

`TreeSet` dùng `compareTo()` hoặc `Comparator.compare()` để xác định vị trí sắp xếp và nhận diện phần tử trùng trong cây. Để đáp ứng đầy đủ hợp đồng `Set`, **quan hệ so sánh cho kết quả `0` phải nhất quán với `equals()`** của phần tử.

Ví dụ `String.CASE_INSENSITIVE_ORDER` coi `"java"` và `"JAVA"` bằng nhau theo thứ tự (`compare(...) == 0`), trong khi `"java".equals("JAVA")` là `false`. Một `TreeSet<String>` dùng comparator này có thể chỉ giữ một trong hai chuỗi, khác với `HashSet` thông thường.

```java
TreeSet<String> insensitive = new TreeSet<>(String.CASE_INSENSITIVE_ORDER);
insensitive.add("java");
insensitive.add("JAVA");
System.out.println(insensitive.size()); // 1
```

Đoạn mã trên là **minh họa trong một phương thức Java**, cần import `java.util.TreeSet` hoặc dùng tên đầy đủ. Dùng comparator không nhất quán với `equals` có thể khiến kết quả so sánh giữa các kiểu `Set` trở nên bất ngờ, thậm chí vi phạm tính đối xứng kỳ vọng của `Set.equals`. Do đó, không nên áp dụng một cách máy móc kết luận “cùng phần tử” khi mỗi cấu trúc đang dùng **một quan hệ nhận diện phần tử khác nhau**.

Với `TreeSet` dùng thứ tự tự nhiên của `String` như ví dụ chạy đầy đủ, `compareTo()` nhất quán với `String.equals()`, nên không gặp vấn đề này.

## 8. Những nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu đúng |
| --- | --- |
| Hai tập hợp được duyệt khác thứ tự thì `equals()` phải là `false` | `Set.equals()` không xét thứ tự duyệt |
| `LinkedHashSet` giữ thứ tự chèn nên `equals()` cũng xét thứ tự chèn | Thứ tự chỉ là đặc tính duyệt; hợp đồng bằng nhau vẫn là hợp đồng `Set` |
| `HashSet` không giữ thứ tự nên kết quả `equals()` ngẫu nhiên | `equals()` có quy tắc rõ ràng, độc lập thứ tự duyệt khi phần tử và hợp đồng được cài đặt đúng |
| Hai tập hợp cùng kích thước thì bằng nhau | Cần **cùng các phần tử**, không chỉ cùng số lượng |
| Hai tập hợp có cùng `hashCode()` thì bằng nhau | Mã băm có thể va chạm; cần `equals()`/kiểm tra thành viên |
| Dùng `List.equals()` sau khi đổi `Set` thành `List` | Sai nếu thứ tự duyệt khác nhau, đặc biệt với `HashSet` |
| Bất kỳ hai `TreeSet` và `HashSet` nào chứa chuỗi “gần giống” cũng bằng nhau | Comparator trong `TreeSet` phải nhất quán với `equals()` để giữ đúng hợp đồng tập hợp |
| `Set` nào cũng chấp nhận `null` | `HashSet` cho phép, nhưng `Set.of(...)` và `TreeSet` với thứ tự tự nhiên thường từ chối `null` |

Đừng nhầm hai thao tác: **so sánh nội dung `Set`** và **so sánh thứ tự duyệt**. Nếu bài toán cần giữ vị trí, dùng `List`; nếu cần xét cùng các phần tử mà không xét vị trí, dùng `Set` và quan hệ bằng nhau đúng với miền dữ liệu.

## 9. Câu hỏi tự kiểm tra

1. `new HashSet<>(List.of("A", "B")).equals(new LinkedHashSet<>(List.of("B", "A")))` trả gì? **`true`**, vì cùng các phần tử.
2. Hai `Set` cùng kích thước 3 có chắc bằng nhau? **Không**, còn phải kiểm tra từng thành viên.
3. Hai `Set` bằng nhau có được phép có mã băm khác nhau? **Không**, phải thỏa hợp đồng `hashCode()`.
4. Hai `Set` khác nhau có được phép cùng mã băm? **Có**, đó là va chạm.
5. Một `TreeSet` bỏ qua chữ hoa/chữ thường có thể có ngữ nghĩa thành viên khác `HashSet<String>` không? **Có**, vì comparator có thể không nhất quán với `String.equals()`.

**Ghi nhớ:** Hai `Set` bằng nhau khi **cùng kích thước và cùng các phần tử theo hợp đồng `Set`**, không phụ thuộc vào thứ tự chèn hay duyệt. Hãy bảo đảm `equals()`/`hashCode()` của phần tử và `Comparator` (nếu dùng `TreeSet`) nhất quán với quan hệ bằng nhau mong muốn.