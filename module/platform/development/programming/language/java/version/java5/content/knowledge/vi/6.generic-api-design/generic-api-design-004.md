# Ràng buộc `Comparable` và `Comparator` trong thuật toán generic

## 1. Thuật toán cần một quan hệ thứ tự, không chỉ một kiểu phần tử

Một hàm generic tìm phần tử lớn nhất không thể chỉ khai báo `<T>` rồi dùng toán tử `>` trên hai giá trị `T`. Java không biết `T` có hỗ trợ phép so sánh đó hay không, và các đối tượng có thể có nhiều cách sắp thứ tự.

Có hai cách cung cấp quy tắc:

- **Thứ tự tự nhiên:** kiểu phần tử thực hiện `Comparable`, với phương thức `compareTo`.
- **Quy tắc bên ngoài:** nơi gọi truyền một `Comparator`, với phương thức `compare`.

Ràng buộc generic cần diễn đạt rằng những giá trị thuật toán lấy ra thực sự có thể so sánh với nhau theo quy tắc đã chọn. Nó còn cần đủ linh hoạt để nhận lớp con và các bộ so sánh của kiểu cha.

Ví dụ các chữ ký sẽ dùng trong bài:

```text
<T extends Comparable<? super T>> T maxNatural(Collection<? extends T> values)
<T> T maxBy(Collection<? extends T> values, Comparator<? super T> order)
```

Đây là dạng chữ ký rút gọn; chương trình đầy đủ ở phía dưới có cả phần triển khai. Bài dùng Java 17 trở lên và thư viện chuẩn.

## 2. `Comparable<T>`: đối tượng biết cách so sánh với kiểu nào?

`Comparable<X>` có phương thức:

```java
int compareTo(X other);
```

Một giá trị trả về:

- Âm: đối tượng nhận lời gọi đứng trước `other` theo thứ tự.
- Bằng `0`: hai đối tượng tương đương theo quan hệ so sánh.
- Dương: đối tượng nhận lời gọi đứng sau `other`.

Không được giả định kết quả chỉ là `-1`, `0` hoặc `1`. Thuật toán nên kiểm tra dấu, chẳng hạn `candidate.compareTo(best) > 0`.

`Comparable<X>` nói “đối tượng này so sánh được với `X`”, không nhất thiết nói `X` phải trùng chính xác lớp của đối tượng hiện tại. Đây là điểm quan trọng khi có kế thừa.

Ví dụ `Employee implements Comparable<Employee>` có thể xác định thứ tự tự nhiên theo mã nhân viên. Một lớp `Manager extends Employee` kế thừa khả năng so sánh với `Employee`; vì `Manager` cũng là `Employee`, so sánh hai quản lý theo quy tắc đó là có nghĩa.

Hợp đồng chính thức nằm trong [Comparable](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Comparable.html). Chọn thứ tự tự nhiên là quyết định mô hình dữ liệu: nó nên là một thứ tự mặc định có ý nghĩa, không phải một tiêu chí bất kỳ chỉ để làm thuật toán biên dịch.

## 3. Vì sao `<T extends Comparable<T>>` có thể quá chặt?

Xét phiên bản chữ ký đơn giản:

```text
<T extends Comparable<T>> T maxStrict(List<T> values)
```

Nó yêu cầu `T` thực hiện `Comparable<T>` đúng với `T` của danh sách.

Nếu có:

```text
Employee thực hiện Comparable<Employee>
Manager kế thừa Employee
```

`Manager` kế thừa `Comparable<Employee>`, không phải `Comparable<Manager>`. Với một biến `List<Manager>`, chữ ký `maxStrict(List<T>)` buộc `T` là `Manager` bởi tính bất biến của `List`; ràng buộc `Comparable<Manager>` không được thỏa mãn.

Những đoạn trên chỉ mô tả cấu trúc kiểu; lớp và thuật toán chạy đầy đủ nằm ở cuối bài. Không cần sửa `Manager` để thực hiện thêm một phiên bản `Comparable<Manager>`. Một lớp không thể tùy tiện kế thừa cùng interface generic với hai đối số kiểu khác nhau.

Vấn đề ở đây là API đang yêu cầu mạnh hơn điều thuật toán thực sự cần. Để so sánh hai `Manager`, khả năng so sánh với `Employee` đã đủ.

## 4. Đọc ràng buộc `T extends Comparable<? super T>`

Ràng buộc:

```java
<T extends Comparable<? super T>>
```

có thể đọc thành: **`T` phải so sánh được với `T` hoặc một kiểu cha của `T`.**

Với `T = Manager`, `Comparable<Employee>` phù hợp vì `Employee` là kiểu cha của `Manager`. Thuật toán có thể đưa một giá trị `Manager` vào vị trí nhận `Employee`.

Không nên đọc dấu `extends` bên ngoài thành “`T` chỉ kế thừa một lớp”. Trong khai báo tham số kiểu, từ khóa này cũng dùng để nêu interface mà kiểu phải thỏa mãn.

Wildcard `? super T` bên trong phản ánh vai trò **nhận giá trị** của đối số `compareTo`: phương thức cần nhận được một `T`, nên khả năng nhận kiểu cha cũng dùng được.

Còn tham số nguồn:

```java
Collection<? extends T> values
```

cho phép thuật toán đọc phần tử nguồn như `T`, không bắt buộc nguồn luôn có đối số kiểu chính xác là `T` trong mọi ngữ cảnh. Kiểu trả về `T` giữ quan hệ giữa phần tử đầu vào và kết quả.

Mô hình ràng buộc `Comparable<? super T>` được sử dụng trong [Collections.max theo thứ tự tự nhiên](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Collections.html#max(java.util.Collection)). Khi viết mã ứng dụng, ưu tiên thuật toán thư viện nếu hợp đồng của nó phù hợp; triển khai trong bài nhằm làm rõ cách thiết kế ràng buộc.

## 5. `Comparator<? super T>`: quy tắc so sánh là một đầu vào riêng

Một thuật toán nhận `Comparator` không cần ép kiểu dữ liệu phải thực hiện `Comparable`:

```text
<T> T maxBy(Collection<? extends T> values, Comparator<? super T> order)
```

Thuật toán gọi:

```java
order.compare(candidate, best)
```

với cả hai giá trị thuộc `T`. Bộ so sánh nhận được một kiểu cha của `T` cũng nhận được các giá trị này.

Vì thế, một `Comparator<Employee>` có thể dùng để so sánh các `Manager`. Nếu buộc tham số là `Comparator<T>` trong một chữ ký có `List<T>`, API có thể từ chối sự kết hợp an toàn này do tính bất biến của generic.

`Comparator<? extends T>` không đúng vai trò đó: nó có thể là bộ so sánh chỉ nhận một kiểu con hẹp hơn `T`, nên không bảo đảm nhận được mọi giá trị `T` do thuật toán truyền vào.

Chọn `Comparator` khi:

- Lớp dữ liệu không có hoặc không nên có một thứ tự tự nhiên.
- Cần nhiều cách sắp thứ tự, như mã nhân viên, tên hoặc một điểm đánh giá.
- Không muốn sửa lớp dữ liệu chỉ để phục vụ một thuật toán cụ thể.

Cùng một danh sách có thể có những phần tử lớn nhất khác nhau theo từng `Comparator`. “Lớn nhất” luôn có nghĩa theo quan hệ thứ tự được chọn, không phải một thuộc tính tuyệt đối của đối tượng.

## 6. Ghép tiêu chí bằng API chuẩn

Ví dụ bộ so sánh vé theo độ ưu tiên rồi theo mã:

```java
Comparator<Ticket> byPriorityThenCode =
        Comparator.comparingInt(Ticket::priority)
                  .thenComparing(Ticket::code);
```

Ở đây `Ticket` có các phương thức truy xuất `priority()` và `code()`. Chương trình đầy đủ bên dưới khai báo nó bằng `record`.

- `comparingInt` tạo bộ so sánh theo một khóa `int`, tránh phải tự viết phép trừ.
- `thenComparing` chỉ xét tiêu chí sau khi tiêu chí trước cho kết quả `0`.
- `reversed()` đảo thứ tự của bộ so sánh đang được gọi.

Không nên viết:

```java
// return left.priority() - right.priority(); // Có thể tràn int.
```

Dùng `Integer.compare(...)` hoặc các hàm `Comparator.comparingInt(...)` để tránh lỗi dấu do tràn số.

Cũng không đảo thứ tự bằng cách tùy ý lấy số đối của kết quả so sánh: giá trị trả về có thể là `Integer.MIN_VALUE`, khiến phép đổi dấu vẫn bị tràn. Dùng `reversed()` hoặc đảo đối số theo thiết kế phù hợp.

Tài liệu [Comparator](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Comparator.html) mô tả các phép ghép tiêu chí và hợp đồng của quan hệ thứ tự.

## 7. Ràng buộc generic không chứng minh comparator đúng

Một bộ so sánh có kiểu `Comparator<T>` vẫn có thể sai về mặt hành vi. Hệ thống kiểu không chứng minh được:

- Hai hướng so sánh có dấu đối nhau một cách nhất quán.
- Quan hệ có tính bắc cầu.
- Nếu hai giá trị so sánh bằng `0`, quan hệ của chúng với giá trị thứ ba nhất quán.
- Quy tắc không tự thay đổi trong quá trình thuật toán chạy.

Ví dụ một comparator đọc thời gian hiện tại hoặc trạng thái liên tục bị sửa có thể làm kết quả không đáng tin, dù mã biên dịch được.

`compare(a, b) == 0` cũng không tự đồng nghĩa `a.equals(b)`. Sự nhất quán với `equals` là điểm cần thiết kế và tài liệu hóa. Nếu dùng comparator cho `TreeSet` hoặc khóa `TreeMap`, các phần tử/khóa so sánh bằng `0` được coi là tương đương theo cấu trúc có thứ tự đó.

Trong ví dụ vé, hai vé mã `B` và `C` cùng độ ưu tiên `8` so sánh bằng `0` nếu chỉ dùng độ ưu tiên, dù chúng không bằng nhau theo `equals` của record. Đó là một quan hệ hữu ích cho xếp hạng, nhưng cần hiểu hệ quả nếu tái sử dụng nó để xác định tính duy nhất trong tập hợp.

## 8. Hợp đồng thuật toán minh họa

Hai hàm trong chương trình phía dưới có hợp đồng rõ ràng:

- Nguồn không được `null` và phải có ít nhất một phần tử.
- Không chấp nhận phần tử `null`.
- `maxBy` yêu cầu comparator khác `null`; nó không dùng `null` làm ký hiệu chọn thứ tự tự nhiên.
- Không sửa collection nguồn.
- Trả chính tham chiếu phần tử được chọn, không tạo bản sao phần tử.
- Khi so sánh bằng `0`, giữ phần tử gặp trước theo thứ tự duyệt.

Thuật toán lấy phần tử đầu làm ứng viên tốt nhất, rồi duyệt phần còn lại. Chỉ thay `best` khi `compare(candidate, best) > 0`.

Với `n` phần tử hợp lệ, số lần so sánh là `n - 1`, bộ nhớ phụ là hằng số. Ví dụ dùng `Iterator` để không giả định collection truy cập theo chỉ số có chi phí hằng số.

Phải phân biệt hợp đồng này với từng overload thư viện chuẩn. Chẳng hạn một API khác có thể cho `null` comparator một ý nghĩa riêng, hoặc cho phép phần tử `null` nếu comparator hỗ trợ. Không suy ra mọi hàm cùng tên `max` có hợp đồng giống hệt nhau.

Nếu thiết kế API cho phép `null`, có thể dùng các bộ so sánh như `Comparator.nullsFirst` hoặc `nullsLast`, nhưng cần điều chỉnh cả quy tắc kiểm tra đầu vào và ý nghĩa kết quả. Chỉ truyền một comparator hỗ trợ `null` vào hàm minh họa không làm hàm ngừng từ chối phần tử `null`.

## 9. Chương trình hoàn chỉnh

Lưu vào `GenericOrderingDemo.java`, dùng Java 17 trở lên:

```java
import java.util.Collection;
import java.util.Comparator;
import java.util.Iterator;
import java.util.List;
import java.util.NoSuchElementException;
import java.util.Objects;

public class GenericOrderingDemo {
    static class Employee implements Comparable<Employee> {
        private final int id;
        private final String name;

        Employee(int id, String name) {
            this.id = id;
            this.name = Objects.requireNonNull(name);
        }

        int id() { return id; }
        String name() { return name; }

        @Override
        public int compareTo(Employee other) {
            return Integer.compare(id, other.id);
        }

        @Override
        public boolean equals(Object other) {
            return other instanceof Employee employee && id == employee.id;
        }

        @Override
        public int hashCode() {
            return Integer.hashCode(id);
        }

        @Override
        public String toString() {
            return name + "#" + id;
        }
    }

    static final class Manager extends Employee {
        Manager(int id, String name) { super(id, name); }
    }

    record Ticket(String code, int priority) {}

    static <T extends Comparable<? super T>> T maxNatural(Collection<? extends T> values) {
        return maxBy(values, Comparator.naturalOrder());
    }

    static <T> T maxBy(Collection<? extends T> values, Comparator<? super T> order) {
        Objects.requireNonNull(values, "values");
        Objects.requireNonNull(order, "order");
        Iterator<? extends T> cursor = values.iterator();
        if (!cursor.hasNext()) {
            throw new NoSuchElementException("Collection must be nonempty");
        }
        T best = Objects.requireNonNull(cursor.next(), "element");
        while (cursor.hasNext()) {
            T candidate = Objects.requireNonNull(cursor.next(), "element");
            if (order.compare(candidate, best) > 0) {
                best = candidate;
            }
        }
        return best;
    }

    public static void main(String[] args) {
        List<Manager> managers = List.of(
                new Manager(1, "Zoe"),
                new Manager(2, "An"),
                new Manager(3, "Minh"));

        Manager natural = maxNatural(managers);
        Comparator<Employee> byName = Comparator.comparing(Employee::name)
                .thenComparingInt(Employee::id);
        Manager named = maxBy(managers, byName);
        System.out.println("natural = " + natural);
        System.out.println("by name = " + named);

        List<Ticket> tickets = List.of(
                new Ticket("B", 8), new Ticket("C", 8), new Ticket("A", 1));
        Comparator<Ticket> byPriority = Comparator.comparingInt(Ticket::priority);
        Ticket priorityOnly = maxBy(tickets, byPriority);
        Ticket priorityThenCode = maxBy(tickets, byPriority.thenComparing(Ticket::code));
        System.out.println("priority only = " + priorityOnly.code());
        System.out.println("priority then code = " + priorityThenCode.code());

        System.out.println("largest integer = " + maxNatural(List.of(2, 9, 4)));
        try {
            GenericOrderingDemo.<Integer>maxNatural(List.of());
        } catch (NoSuchElementException ex) {
            System.out.println("empty rejected");
        }
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -Xlint:unchecked -encoding UTF-8 GenericOrderingDemo.java
java GenericOrderingDemo
```

Kết quả chuẩn:

```text
natural = Minh#3
by name = Zoe#1
priority only = B
priority then code = C
largest integer = 9
empty rejected
```

Giải thích:

- Thứ tự tự nhiên của `Employee` theo `id`, nên quản lý có mã `3` được chọn. `Manager` dùng được nhờ ràng buộc `Comparable<? super T>`.
- `Comparator<Employee>` theo tên nhận được cả các giá trị `Manager`. Theo thứ tự chuỗi của ví dụ, `Zoe` đứng sau `Minh` và `An`.
- `Ticket` không thực hiện `Comparable`; vẫn dùng được `maxBy` vì quy tắc được truyền riêng.
- Chỉ xét độ ưu tiên, `B` và `C` hòa nhau. Thuật toán giữ `B` vì gặp trước.
- Thêm tiêu chí mã làm `C` đứng sau `B`, nên kết quả đổi thành `C`.
- Nguồn rỗng bị từ chối bằng `NoSuchElementException` theo hợp đồng.

Trong mô hình minh họa, danh tính của nhân viên là `id` xuyên suốt các lớp con; `compareTo`, `equals` và `hashCode` phản ánh lựa chọn đó. Comparator theo tên phục vụ một cách xếp thứ tự khác. Trước khi dùng một comparator như vậy để xác định khóa/tính duy nhất trong cấu trúc có thứ tự, phải kiểm tra quan hệ với quy tắc `equals` của mô hình.

## 10. Những chữ ký sai hoặc quá chặt thường gặp

### Không có ràng buộc nhưng gọi `compareTo`

```java
static <T> int compareUnknown(T left, T right) {
    return left.compareTo(right); // Lỗi biên dịch: T chưa được bảo đảm có compareTo.
}
```

Đừng dùng hàm này làm cách triển khai. Cần thêm một ràng buộc `Comparable` phù hợp hoặc nhận `Comparator`.

### Buộc đồng thời `Comparable` khi đã có comparator

Một hàm chỉ gọi comparator không cần thêm `T extends Comparable<...>`. Ràng buộc thừa sẽ loại bỏ những kiểu như `Ticket`, dù thuật toán có đủ quy tắc để hoạt động.

### Buộc `Comparator<T>` khi comparator kiểu cha đã đủ

Với nguồn `List<Manager>` và comparator `Comparator<Employee>`, `Comparator<? super T>` biểu đạt đúng nhu cầu nhận hai giá trị `T`. Không cần tạo một comparator mới chỉ để trùng tên đối số kiểu.

### Dùng kiểu quá rộng rồi ép kiểu trong thân hàm

Nhận `Collection<?>`, lấy `Object`, rồi ép sang `Comparable<Object>` làm mất bằng chứng so sánh an toàn giữa các phần tử. Hãy biểu đạt điều kiện ở chữ ký generic để lỗi được phát hiện tại nơi gọi.

### Giả định generic bảo đảm mọi phần tử khác `null`

Ràng buộc `T extends Comparable<? super T>` không cấm một biến tham chiếu có giá trị `null`. Quy tắc về `null` cần được kiểm tra hoặc được comparator xử lý theo hợp đồng riêng.

## 11. Tự kiểm tra

**Câu 1.** Vì sao `Manager` kế thừa khả năng so sánh với `Employee` vẫn có thể dùng với ràng buộc `Comparable<? super Manager>`?

Vì `Employee` là kiểu cha của `Manager`, và một phương thức nhận `Employee` cũng nhận được một `Manager`. Không cần có một interface `Comparable<Manager>` riêng.

**Câu 2.** Vì sao hàm nhận `Comparator` thường không cần giới hạn `T extends Comparable<T>`?

Vì quy tắc so sánh đến từ đối tượng comparator, không đến từ khả năng tự so sánh của phần tử. Ràng buộc đó sẽ loại bỏ những kiểu hợp lệ không có thứ tự tự nhiên.

**Câu 3.** Để chọn phần tử lớn nhất, có nên kiểm tra `compare(candidate, best) == 1` không?

Không. Chỉ dấu dương mới có ý nghĩa chung; một comparator hợp lệ có thể trả một số dương khác `1`.

**Câu 4.** Hai phần tử hòa nhau thì hàm minh họa chọn phần tử nào?

Phần tử gặp trước theo thứ tự duyệt, vì chỉ thay ứng viên khi kết quả so sánh lớn hơn `0`.

**Câu 5.** Đổi `byPriority` thành `byPriority.reversed()` rồi vẫn tìm `max` có giữ nghĩa “độ ưu tiên cao nhất” không?

Không. Quan hệ thứ tự đã đảo, nên phần tử lớn nhất theo comparator đảo tương ứng với phần tử nhỏ hơn theo comparator ban đầu. Hãy chọn cả thuật toán và chiều comparator theo đúng yêu cầu nghiệp vụ.
